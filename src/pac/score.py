"""Score qualité "pain au chocolat" par boulangerie (cf. plan).

Pipeline en 3 étages, chacun idempotent par review_id :
  extract_mentions -> classify_mentions (LLM) -> compute_scores (SQL)

Le point le plus important de ce module (découvert en explorant les
données réelles) : beaucoup de mentions "pain au chocolat"/"chocolatine"
sont des plaintes sur le PRIX, pas sur le goût (ex: avis 1 étoile
"3,90€ la chocolatine, même chez les mac..."). La note globale de l'avis
est donc un MAUVAIS proxy pour la qualité du pain au chocolat -- d'où la
classification LLM qui isole explicitement le sentiment propre à la
mention, avec un flag `relevant` qui exclut les mentions hors-sujet
(prix, service, etc.) plutôt que de les compter comme négatives.
"""

import concurrent.futures
import json
import math
from datetime import datetime, timezone

import duckdb
import httpx
from rich.progress import track

from pac.llm import LLMError, classify_json

MENTION_TERMS = [
    "pain au chocolat",
    "pains au chocolat",
    "pain chocolat",  # variante sans "au", observée dans les données réelles
    "pains chocolat",
    "chocolatine",
    "chocolatines",
    "viennoiserie",  # terme générique (croissant, chocolatine, etc. inclus) --
    "viennoiseries",  # élargit volontairement le score au-delà du seul pain au chocolat
]

SYSTEM_PROMPT = """Tu analyses un avis Google Maps sur une boulangerie parisienne.
On t'indique un terme détecté (une pâtisserie précise comme "pain au
chocolat"/"chocolatine", ou le terme générique "viennoiserie") dans le texte.
Détermine si le passage autour de ce terme exprime un avis sur le
GOÛT/LA QUALITÉ de la ou des pâtisserie(s) elle(s)-même(s) (texture, fraîcheur,
feuilletage, quantité de chocolat, etc.) -- PAS sur son prix, le service, ou une
simple mention en passant sans jugement.

Réponds en JSON strict avec exactement ces clés :
{"relevant": true|false, "appreciated": true|false|null, "sentiment": <float entre -1.0 et 1.0>, "signal_type": "isolated_incident"|"ongoing_pattern"|null, "aspect": "freshness"|"baking"|"chocolate_quantity"|"lamination"|"price_value"|"other"|null, "confidence": <float entre 0.0 et 1.0>, "reason": "<courte justification>"}

- relevant=false si la mention parle de prix, de service, ou est neutre/sans
  jugement sur la qualité (même si l'avis global est très négatif ou positif).
  Dans ce cas, appreciated, signal_type et aspect doivent être null.
- Si relevant=true :
  - appreciated est un jugement NET, binaire : est-ce que la personne a
    globalement apprécié le goût/la qualité de la pâtisserie décrite (true),
    ou pas (false) ? Pas de zone grise : tranche même si l'avis est mesuré.
  - sentiment note l'INTENSITÉ de ce jugement sur une échelle continue de
    -1.0 (détestable) à 1.0 (excellent), cohérente avec appreciated (positif
    si appreciated=true, négatif si appreciated=false) -- juge UNIQUEMENT la
    qualité de la pâtisserie décrite, pas la note globale de l'avis ni le prix.
  - signal_type distingue un ALÉA PONCTUEL ("isolated_incident" : ce jour-là,
    cette fournée, cette fois-ci -- ex. "j'ai eu un pain au chocolat brûlé
    aujourd'hui") d'un CHANGEMENT DURABLE ("ongoing_pattern" : depuis, ne
    sont plus, changement de propriétaire/recette, "ce n'est plus ce que
    c'était", tendance décrite sur plusieurs visites). Mets "ongoing_pattern"
    si rien n'indique explicitement un incident isolé -- c'est la valeur par
    défaut d'une mention qui décrit un état plutôt qu'un événement précis.
  - aspect : le CRITÈRE précis évoqué -- fraîcheur/cuisson du jour
    (freshness), cuisson/feuilletage râté ou four (baking), quantité de
    chocolat (chocolate_quantity), qualité du feuilletage/texture
    (lamination), rapport qualité/prix perçu MALGRÉ un jugement sur le goût
    (price_value -- différent de relevant=false qui exclut les plaintes de
    prix SANS jugement sur le goût), ou "other" si aucun de ces critères ne
    correspond clairement.
  - confidence : à quel point TU es sûr de ce jugement (pas la confiance du
    client) -- 1.0 si le passage est explicite et sans ambiguïté, plus bas
    si le texte est elliptique, sarcastique, ou traduit approximativement.
"""


def extract_mentions(con: duckdb.DuckDBPyConnection) -> int:
    """Étage 1 : repère les avis mentionnant pain au chocolat/chocolatine.

    Termes volontairement précis (pas "chocolat" seul, qui noierait le
    signal -- cf. plan) : ~810 avis contiennent "chocolat" contre ~290 qui
    mentionnent spécifiquement la pâtisserie sur l'échantillon de test.
    """
    conditions = " OR ".join(f"text ILIKE '%{t}%'" for t in MENTION_TERMS)
    matched_term_case = "\n            ".join(
        f"WHEN text ILIKE '%{t}%' THEN '{t}'" for t in MENTION_TERMS
    )
    con.execute(
        f"""
        INSERT INTO pac_mentions_raw (review_id, place_id, text, matched_term)
        SELECT
            r.review_id,
            r.place_id,
            r.text,
            CASE
            {matched_term_case}
            END AS matched_term
        FROM reviews r
        WHERE r.text IS NOT NULL AND ({conditions})
          AND r.review_id NOT IN (SELECT review_id FROM pac_mentions_raw)
        """
    )
    return con.execute("SELECT count(*) FROM pac_mentions_raw").fetchone()[0]


def _pending_mentions(con: duckdb.DuckDBPyConnection, reclassify: bool = False) -> list[tuple]:
    if reclassify:
        # Reclassifie TOUT (utilisé pour faire rétroagir un nouveau champ de
        # sortie LLM -- ex. signal_type/aspect/llm_confidence -- sur les
        # mentions déjà classifiées avant son introduction, cf. plan).
        return con.execute(
            "SELECT review_id, place_id, text, matched_term FROM pac_mentions_raw"
        ).fetchall()
    return con.execute(
        """
        SELECT m.review_id, m.place_id, m.text, m.matched_term
        FROM pac_mentions_raw m
        WHERE m.review_id NOT IN (SELECT review_id FROM pac_mentions)
        """
    ).fetchall()


VALID_SIGNAL_TYPES = {"isolated_incident", "ongoing_pattern"}
VALID_ASPECTS = {"freshness", "baking", "chocolate_quantity", "lamination", "price_value", "other"}


def _classify_one(
    client: httpx.Client, review_id: str, place_id: str, text: str, term: str, model: str
) -> dict:
    user_prompt = f'Terme détecté : "{term}"\n\nAvis complet :\n{text}'
    try:
        result = classify_json(client, SYSTEM_PROMPT, user_prompt, model=model)
        relevant = bool(result.get("relevant"))
        sentiment = float(result.get("sentiment", 0.0))
        sentiment = max(-1.0, min(1.0, sentiment))
        # appreciated : jugement net (apprécié/pas apprécié), distinct de
        # l'intensité continue `sentiment` -- plus robuste pour le ratio
        # d'avis positifs qu'un simple seuil sentiment >= 0 (cf. plan). Pas
        # de valeur inventée si le modèle omet le champ ou répond hors
        # sujet : None reste None (positive_ratio retombe sur le seuil de
        # sentiment pour ces cas, cf. compute_scores).
        appreciated_raw = result.get("appreciated")
        appreciated = bool(appreciated_raw) if relevant and appreciated_raw is not None else None

        # signal_type/aspect : valeurs d'un enum fermé -- une valeur hors
        # liste (hallucination, faute de frappe du modèle) retombe sur None
        # plutôt que d'être stockée telle quelle (cf. plan : pas de valeur
        # inventée, mais pas non plus de valeur invalide qui casserait un
        # filtre/groupby en aval).
        signal_type = result.get("signal_type") if relevant else None
        signal_type = signal_type if signal_type in VALID_SIGNAL_TYPES else None
        aspect = result.get("aspect") if relevant else None
        aspect = aspect if aspect in VALID_ASPECTS else None

        # confidence : certitude du MODÈLE dans son propre jugement (pas la
        # confiance globale du score, déjà calculée ailleurs) -- None si
        # absent/invalide plutôt qu'une valeur médiane inventée.
        confidence_raw = result.get("confidence")
        llm_confidence = None
        if relevant and confidence_raw is not None:
            try:
                llm_confidence = max(0.0, min(1.0, float(confidence_raw)))
            except (ValueError, TypeError):
                llm_confidence = None

        reason = str(result.get("reason", ""))[:500]
        failed = False
    except (LLMError, ValueError, TypeError, httpx.HTTPError) as exc:
        # httpx.HTTPError couvre aussi les erreurs réseau brutes (connexion
        # coupée par une mise en veille/un verrouillage, DNS, etc.), pas
        # seulement les erreurs déjà transformées en LLMError -- sans ça,
        # une exception réseau remonte non rattrapée jusqu'au `f.result()`
        # de l'appelant, qui casse le `with ThreadPoolExecutor(...)` en plein
        # milieu : sa sortie via exception attend quand même que TOUS les
        # futures déjà soumis se terminent (shutdown(wait=True)) avant de
        # laisser remonter l'erreur -- des heures de blocage silencieux, la
        # barre de progression arrêtée, pour ce qui ressemble à un freeze.
        # On n'invente pas un sentiment par défaut : une mention qu'on n'a
        # pas pu classifier est marquée non pertinente plutôt que de
        # polluer l'agrégation avec une valeur neutre inventée. `failed`
        # permet à l'appelant de distinguer "pas pertinent" (vrai résultat)
        # de "échec technique" -- verify_anomalies s'en sert pour ne
        # JAMAIS écraser une classification existante par un échec
        # transitoire du second modèle (bug réel rencontré : Claude via
        # Bedrock renvoyait un JSON enrobé de ```json que l'ancien code ne
        # savait pas décoder, et le fallback écrasait 16 classifications
        # valides -- cf. plan et llm._strip_markdown_fence pour le correctif
        # racine).
        relevant, appreciated, sentiment, signal_type, aspect, llm_confidence, reason, failed = (
            False, None, 0.0, None, None, None, f"classification échouée: {exc}", True,
        )
    return {
        "review_id": review_id,
        "place_id": place_id,
        "relevant": relevant,
        "appreciated": appreciated,
        "sentiment": sentiment,
        "signal_type": signal_type,
        "aspect": aspect,
        "llm_confidence": llm_confidence,
        "reason": reason,
        "failed": failed,
    }


def classify_mentions(
    con: duckdb.DuckDBPyConnection, workers: int, model: str, reclassify: bool = False
) -> int:
    """Étage 2 : classification LLM des mentions pas encore traitées.

    Idempotent par défaut : ne reclassifie jamais un review_id déjà présent
    dans pac_mentions -- relancer après un nouveau `pac reviews` ne coûte
    que le delta de nouvelles mentions. Chaque résultat est inséré dès
    qu'il arrive (pas à la toute fin) : un Ctrl+C ou un crash en cours de
    route ne perd donc que les requêtes encore en vol, jamais le travail
    déjà payé et reçu.

    reclassify=True force la reclassification de TOUTES les mentions,
    écrasant leur résultat existant (`pac reclassify` en CLI) -- utile pour
    faire rétroagir un nouveau champ de sortie sur les mentions classifiées
    avant son introduction. Remet aussi `verified` à false : les mentions
    qui avaient été repassées par verify_anomalies seront à nouveau
    sélectionnées si le désaccord persiste après la reclassification,
    plutôt que de rester marquées "vérifiées" sur un résultat qui vient
    d'être remplacé."""
    pending = _pending_mentions(con, reclassify=reclassify)
    if not pending:
        return 0

    n_done = 0
    with httpx.Client() as client:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_classify_one, client, review_id, place_id, text, term, model)
                for review_id, place_id, text, term in pending
            ]
            for f in track(
                concurrent.futures.as_completed(futures),
                total=len(futures),
                description="classification LLM",
            ):
                r = f.result()
                con.execute(
                    """
                    INSERT INTO pac_mentions
                        (review_id, place_id, relevant, appreciated, sentiment, signal_type,
                         aspect, llm_confidence, reason, model, classified_at, verified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, false)
                    ON CONFLICT (review_id) DO UPDATE SET
                        relevant = excluded.relevant,
                        appreciated = excluded.appreciated,
                        sentiment = excluded.sentiment,
                        signal_type = excluded.signal_type,
                        aspect = excluded.aspect,
                        llm_confidence = excluded.llm_confidence,
                        reason = excluded.reason,
                        model = excluded.model,
                        classified_at = excluded.classified_at,
                        verified = false
                    """,
                    [
                        r["review_id"], r["place_id"], r["relevant"], r["appreciated"],
                        r["sentiment"], r["signal_type"], r["aspect"], r["llm_confidence"],
                        r["reason"], model, datetime.now(timezone.utc),
                    ],
                )
                n_done += 1

    return n_done


# Seuil de désaccord note/sentiment déclenchant une double-vérification
# (cf. plan) : calibré à 1.0 sur l'échantillon réel (15 mentions/409).
# IMPORTANT : ce désaccord sert UNIQUEMENT à sélectionner quoi
# double-vérifier -- le second avis ne doit JAMAIS trancher en faveur de la
# note de l'avis (cf. plan, Context point 3 : un avis 5★ qui déplore la
# baisse de qualité du pain au chocolat est un cas légitime, pas une erreur
# à corriger vers le haut).
ANOMALY_THRESHOLD = 1.0


def _pending_anomalies(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    return con.execute(
        f"""
        SELECT m.review_id, m.place_id, mr.text, mr.matched_term
        FROM pac_mentions m
        JOIN reviews r ON r.review_id = m.review_id
        JOIN pac_mentions_raw mr ON mr.review_id = m.review_id
        WHERE m.relevant = true
          AND m.verified = false
          AND r.rating IS NOT NULL
          AND abs(m.sentiment - (r.rating - 3) / 2.0) > {ANOMALY_THRESHOLD}
        """
    ).fetchall()


def verify_anomalies(con: duckdb.DuckDBPyConnection, workers: int, model: str) -> int:
    """Double-vérification ciblée : repasse par un second modèle (plus
    capable) les mentions où le sentiment contredit fortement la note
    globale de l'avis -- pas pour trancher vers la note (cf. docstring de
    ANOMALY_THRESHOLD), mais pour attraper les vraies erreurs de lecture du
    premier modèle via un second avis indépendant sur le MÊME texte.

    Comme classify_mentions, chaque résultat est appliqué dès qu'il arrive :
    un Ctrl+C en cours de route ne perd que les vérifications encore en
    vol, pas celles déjà reçues."""
    pending = _pending_anomalies(con)
    if not pending:
        return 0

    n_updated = 0
    with httpx.Client() as client:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_classify_one, client, review_id, place_id, text, term, model)
                for review_id, place_id, text, term in pending
            ]
            for f in track(
                concurrent.futures.as_completed(futures),
                total=len(futures),
                description="vérification des anomalies",
            ):
                r = f.result()
                if r["failed"]:
                    # Échec technique du second modèle : on NE TOUCHE PAS à
                    # la classification existante (verified reste false,
                    # elle sera retentée au prochain `pac score`) -- plutôt
                    # que d'écraser une classification valide par un
                    # résultat par défaut inventé.
                    continue
                con.execute(
                    """
                    UPDATE pac_mentions
                    SET relevant = ?, appreciated = ?, sentiment = ?, signal_type = ?,
                        aspect = ?, llm_confidence = ?, reason = ?, model = ?, verified = true
                    WHERE review_id = ?
                    """,
                    [
                        r["relevant"], r["appreciated"], r["sentiment"], r["signal_type"],
                        r["aspect"], r["llm_confidence"], r["reason"], model, r["review_id"],
                    ],
                )
                n_updated += 1
    return n_updated


# Constantes de pondération (cf. plan, section Étape 3) ---------------------
REVIEWER_WEIGHT_CAP = math.log(1 + 500)  # plafonne l'effet des power users
RECENCY_HALFLIFE_DAYS = 365  # un avis perd moitié de son poids par an
SHRINKAGE_K = 2  # force du lissage vers le prior global, volontairement faible

# Poids du "consensus" (part pondérée des mentions positives, sentiment >= 0)
# dans le score final, face à l'intensité moyenne du sentiment. Sans ça, un
# lieu avec 90% de mentions modérément positives et une seule mention très
# négative peut finir avec la même moyenne pondérée qu'un lieu où l'avis est
# vraiment partagé -- le consensus positif est un signal différent de
# l'intensité moyenne, qui mérite son propre poids plutôt que d'être
# noyé dans une simple moyenne. Remonté de 0.3 à 0.5 (cf. plan) : un lieu
# comme "Blé Sucré" (82% de mentions positives, médiane de sentiment 0.9,
# mais une petite traîne d'avis très négatifs qui tirait la MOYENNE à 0.67)
# doit être jugé sur son consensus large, pas noyé par quelques outliers.
POSITIVE_RATIO_WEIGHT = 0.5

# "viennoiserie"/"viennoiseries" est un terme générique (peut désigner un
# croissant, une brioche, etc. -- pas spécifiquement le pain au chocolat) :
# une mention qui l'utilise a moins de poids qu'une mention qui nomme
# explicitement "pain au chocolat"/"chocolatine", plutôt que de compter à
# l'identique dans le score.
GENERIC_TERM_WEIGHT = 0.4
GENERIC_TERMS = ("viennoiserie", "viennoiseries")

# Aucune mention ne peut représenter plus de MAX_MENTION_SHARE du poids total
# d'un lieu -- sans ça, une seule mention très fortement pondérée (auteur
# actif + avis récent + terme spécifique) peut dominer entièrement la
# moyenne d'un lieu qui a par ailleurs plusieurs autres mentions plus
# modestes. Sans effet quand un lieu n'a qu'1 seule mention pertinente (le
# poids s'annule dans une moyenne à un seul terme) -- dans ce cas c'est le
# lissage (SHRINKAGE_K) qui protège, pas ce plafond.
MAX_MENTION_SHARE = 0.5

# Seuils de confiance sur le POIDS effectif cumulé (somme des `weight`), pas
# sur le nombre brut de mentions -- 3 mentions récentes de contributeurs
# actifs et 3 mentions anciennes de comptes neufs ne méritent pas le même
# badge de confiance, alors qu'elles avaient le même n_relevant=3 avant ce
# changement.
CONFIDENCE_LOW_WEIGHT = 3.0
CONFIDENCE_MEDIUM_WEIGHT = 6.0

# Winsorizing du PLANCHER négatif uniquement (asymétrique, volontairement) :
# un -1.0 isolé ne doit pas peser plus qu'un -0.8 dans la moyenne,
# indépendamment de son poids (auteur/fraîcheur/spécificité du terme, déjà
# plafonnés séparément par ailleurs). PAS de plafond côté positif : sur un
# cas réel ("Blé Sucré", médiane 0.9 mais moyenne 0.67 à cause d'une petite
# traîne de mentions très négatives), 62% des mentions dépassaient déjà 0.8
# -- une borne symétrique les aurait toutes écrasées et FAIT BAISSER le
# score, l'inverse de l'effet recherché (bug réel rencontré en testant).
# Ne change jamais le signe d'une mention -- n'affecte donc pas
# positive_ratio (seuil à 0).
SENTIMENT_WINSOR_FLOOR = -0.8

# signal_type (cf. plan, cas réel "Blé Sucré" : plusieurs avis décrivaient
# explicitement un changement de propriétaire et un déclin durable, mêlés à
# des incidents ponctuels comme "j'ai eu un pain brûlé aujourd'hui" -- les
# deux comptaient pareil dans le score alors qu'ils portent une information
# très différente). Un incident isolé est amorti (poids réduit) : il en dit
# peu sur l'état ACTUEL du lieu. Une tendance durable est renforcée (poids
# accru) : c'est justement le signal le plus informatif sur ce qu'un client
# doit attendre aujourd'hui. NULL (mention non pertinente, ou classifiée
# avant l'introduction de ce champ) -> poids neutre (1.0), ni renforcé ni
# amorti.
ISOLATED_INCIDENT_WEIGHT = 0.6
ONGOING_PATTERN_WEIGHT = 1.3


def compute_scores(con: duckdb.DuckDBPyConnection) -> int:
    """Étage 3 : agrégation pondérée en SQL (cf. plan pour la justification
    détaillée de chaque choix, notamment l'absence de lissage vers la note
    globale du lieu -- décision explicite de l'utilisateur)."""
    generic_terms_sql = ", ".join(f"'{t}'" for t in GENERIC_TERMS)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _weighted AS
        SELECT
            place_id, sentiment, appreciated,
            least(weight, {MAX_MENTION_SHARE} * sum(weight) OVER (PARTITION BY place_id)) AS weight
        FROM (
            SELECT
                m.place_id,
                greatest({SENTIMENT_WINSOR_FLOOR}, m.sentiment) AS sentiment,
                m.appreciated,
                least(ln(1 + coalesce(r.author_review_count, 0)), {REVIEWER_WEIGHT_CAP})
                    * pow(0.5, (epoch(current_timestamp) - r.published_at) / 86400.0 / {RECENCY_HALFLIFE_DAYS})
                    * CASE WHEN mr.matched_term IN ({generic_terms_sql}) THEN {GENERIC_TERM_WEIGHT} ELSE 1.0 END
                    * CASE m.signal_type
                          WHEN 'isolated_incident' THEN {ISOLATED_INCIDENT_WEIGHT}
                          WHEN 'ongoing_pattern' THEN {ONGOING_PATTERN_WEIGHT}
                          ELSE 1.0
                      END
                    * coalesce(m.llm_confidence, 1.0)
                    AS weight
            FROM pac_mentions m
            JOIN reviews r ON r.review_id = m.review_id
            JOIN pac_mentions_raw mr ON mr.review_id = m.review_id
            WHERE m.relevant = true
        )
    """
    )

    prior_row = con.execute(
        "SELECT sum(sentiment * weight) / nullif(sum(weight), 0) FROM _weighted"
    ).fetchone()
    prior_global = prior_row[0] if prior_row and prior_row[0] is not None else 0.0

    con.execute("DELETE FROM pac_scores")
    con.execute(
        f"""
        INSERT INTO pac_scores (place_id, name, n_mentions_total, n_relevant, score_10, confidence, positive_ratio)
        SELECT
            p.place_id,
            p.name,
            coalesce(raw.n_total, 0) AS n_mentions_total,
            coalesce(w.n_relevant, 0) AS n_relevant,
            CASE
                -- sum_weight = 0 (ex: seule(s) mention(s) d'un lieu postée(s)
                -- par un compte à 0 avis publiés -> poids crédibilité nul) ->
                -- raw_score/positive_ratio seraient 0/0 = NaN, pas NULL, en
                -- SQL flottant -- un NaN traverse `WHERE score_10 IS NOT
                -- NULL` (NaN != NULL) et pollue tout avg() en aval (bug réel
                -- rencontré : KPI "score moyen" affichait NaN/10). On traite
                -- explicitement ce cas comme un lieu sans score exploitable,
                -- pas différent de n_relevant=0.
                WHEN coalesce(w.n_relevant, 0) = 0 OR coalesce(w.sum_weight, 0) = 0 THEN NULL
                ELSE (
                    (
                        w.n_relevant * (
                            {1 - POSITIVE_RATIO_WEIGHT} * w.raw_score
                            + {POSITIVE_RATIO_WEIGHT} * (2 * w.positive_ratio - 1)
                        )
                        + {SHRINKAGE_K} * {prior_global}
                    ) / (w.n_relevant + {SHRINKAGE_K})
                    + 1
                ) * 5
            END AS score_10,
            CASE
                WHEN coalesce(w.sum_weight, 0) = 0 THEN 'insufficient_data'
                WHEN w.sum_weight < {CONFIDENCE_LOW_WEIGHT} THEN 'low'
                WHEN w.sum_weight < {CONFIDENCE_MEDIUM_WEIGHT} THEN 'medium'
                ELSE 'high'
            END AS confidence,
            w.positive_ratio
        FROM places p
        LEFT JOIN (
            SELECT place_id, count(*) AS n_total FROM pac_mentions_raw GROUP BY place_id
        ) raw ON raw.place_id = p.place_id
        LEFT JOIN (
            SELECT
                place_id,
                count(*) AS n_relevant,
                sum(weight) AS sum_weight,
                -- nullif(sum(weight), 0) : un poids total nul (mention(s)
                -- postée(s) uniquement par des comptes à 0 avis publiés,
                -- cf. commentaire sur score_10 ci-dessus) donnerait 0/0 = NaN
                -- plutôt que NULL en SQL flottant -- on force explicitement
                -- NULL, jamais un NaN qui traverserait silencieusement les
                -- filtres IS NOT NULL en aval.
                sum(sentiment * weight) / nullif(sum(weight), 0) AS raw_score,
                -- `appreciated` (jugement net du LLM) prime sur le seuil
                -- sentiment >= 0 quand il est disponible -- plus robuste
                -- qu'un simple seuil sur une note continue (cf. plan).
                sum(
                    CASE
                        WHEN appreciated IS NOT NULL THEN CASE WHEN appreciated THEN weight ELSE 0 END
                        WHEN sentiment >= 0 THEN weight
                        ELSE 0
                    END
                ) / nullif(sum(weight), 0) AS positive_ratio
            FROM _weighted GROUP BY place_id
        ) w ON w.place_id = p.place_id
        """
    )
    return con.execute("SELECT count(*) FROM pac_scores WHERE score_10 IS NOT NULL").fetchone()[0]


def leaderboard(con: duckdb.DuckDBPyConnection, top_n: int = 15) -> tuple[list, list]:
    """Renvoie (top, bottom) -- le bottom se limite à confidence='high' pour
    ne pas afficher en dernière place un lieu jugé sur une seule mention
    malchanceuse (cf. plan)."""
    top = con.execute(
        f"""
        SELECT name, score_10, n_relevant, confidence FROM pac_scores
        WHERE score_10 IS NOT NULL ORDER BY score_10 DESC LIMIT {top_n}
        """
    ).fetchall()
    bottom = con.execute(
        f"""
        SELECT name, score_10, n_relevant, confidence FROM pac_scores
        WHERE score_10 IS NOT NULL AND confidence = 'high' ORDER BY score_10 ASC LIMIT {top_n}
        """
    ).fetchall()
    return top, bottom
