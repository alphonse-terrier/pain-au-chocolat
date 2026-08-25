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
{"relevant": true|false, "appreciated": true|false|null, "sentiment": <float entre -1.0 et 1.0>, "signal_type": "isolated_incident"|"ongoing_pattern"|null, "aspects": [{"aspect": "freshness"|"baking"|"chocolate_quantity"|"lamination"|"price_value"|"other", "weight": <float entre 0.0 et 1.0>}, ...], "confidence": <float entre 0.0 et 1.0>, "reason": "<courte justification>"}

- relevant=false si la mention parle de prix, de service, ou est neutre/sans
  jugement sur la qualité (même si l'avis global est très négatif ou positif).
  Dans ce cas, appreciated et signal_type doivent être null, et aspects [].
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
  - aspects : les CRITÈRES précis évoqués, un ou plusieurs (liste vide si
    aucun ne se dégage clairement) -- fraîcheur/cuisson du jour (freshness),
    cuisson/feuilletage râté ou four (baking), quantité de chocolat
    (chocolate_quantity), qualité du feuilletage/texture (lamination),
    rapport qualité/prix perçu MALGRÉ un jugement sur le goût (price_value
    -- différent de relevant=false qui exclut les plaintes de prix SANS
    jugement sur le goût), ou "other". Un avis peut cumuler plusieurs
    critères (ex. "pas assez de chocolat ET feuilletage détrempé" ->
    chocolate_quantity ET lamination) -- ne force pas un seul aspect si le
    texte en évoque clairement plusieurs. weight (0..1) : à quel point CE
    critère précis pèse dans le jugement global de la mention (le critère
    principal doit avoir le poids le plus haut si plusieurs sont cités).
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
        # .get(..., 0.0) ne protège que si la clé est absente -- le modèle
        # renvoie souvent littéralement "sentiment": null quand relevant=false
        # (le prompt ne précise pas quoi mettre dans ce cas), et .get()
        # retourne alors None malgré le défaut, faisant planter float(None).
        # Ce bug réel a fait échouer 81% des appels lors d'un reclassify
        # complet (19849/24501), chaque échec étant silencieusement
        # enregistré comme relevant=false par le fallback ci-dessous --
        # jamais un vrai jugement du modèle.
        sentiment_raw = result.get("sentiment")
        sentiment = float(sentiment_raw) if sentiment_raw is not None else 0.0
        sentiment = max(-1.0, min(1.0, sentiment))
        # appreciated : jugement net (apprécié/pas apprécié), distinct de
        # l'intensité continue `sentiment` -- plus robuste pour le ratio
        # d'avis positifs qu'un simple seuil sentiment >= 0 (cf. plan). Pas
        # de valeur inventée si le modèle omet le champ ou répond hors
        # sujet : None reste None (positive_ratio retombe sur le seuil de
        # sentiment pour ces cas, cf. compute_scores).
        appreciated_raw = result.get("appreciated")
        appreciated = bool(appreciated_raw) if relevant and appreciated_raw is not None else None

        # signal_type : valeur d'un enum fermé -- une valeur hors liste
        # (hallucination, faute de frappe du modèle) retombe sur None
        # plutôt que d'être stockée telle quelle (cf. plan : pas de valeur
        # inventée, mais pas non plus de valeur invalide qui casserait un
        # filtre/groupby en aval).
        signal_type = result.get("signal_type") if relevant else None
        signal_type = signal_type if signal_type in VALID_SIGNAL_TYPES else None

        # aspects : liste de {aspect, weight} -- une mention peut cumuler
        # plusieurs critères (cf. plan). Chaque entrée invalide (aspect hors
        # enum, weight non numérique) est silencieusement écartée plutôt que
        # de faire échouer toute la mention pour un seul champ mal formé ;
        # les doublons d'aspect (le modèle répète la même valeur) gardent le
        # poids le plus élevé rencontré.
        aspects: dict[str, float] = {}
        if relevant:
            for item in result.get("aspects") or []:
                if not isinstance(item, dict):
                    continue
                a = item.get("aspect")
                if a not in VALID_ASPECTS:
                    continue
                try:
                    w = max(0.0, min(1.0, float(item.get("weight", 0.0))))
                except (ValueError, TypeError):
                    continue
                aspects[a] = max(w, aspects.get(a, 0.0))

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
        relevant, appreciated, sentiment, signal_type, aspects, llm_confidence, reason, failed = (
            False, None, 0.0, None, {}, None, f"classification échouée: {exc}", True,
        )
    return {
        "review_id": review_id,
        "place_id": place_id,
        "relevant": relevant,
        "appreciated": appreciated,
        "sentiment": sentiment,
        "signal_type": signal_type,
        "aspects": aspects,
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
                _write_mention_result(con, f.result(), model, verified=False)
                n_done += 1

    return n_done


def _write_mention_result(con: duckdb.DuckDBPyConnection, r: dict, model: str, verified: bool) -> None:
    """Enregistre le résultat d'une classification (pac_mentions) et ses
    aspects (pac_mention_aspects) -- factorisé entre classify_mentions et
    verify_anomalies, les deux appelant _classify_one et devant écrire les
    deux tables de la même façon."""
    con.execute(
        """
        INSERT INTO pac_mentions
            (review_id, place_id, relevant, appreciated, sentiment, signal_type,
             llm_confidence, reason, model, classified_at, verified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (review_id) DO UPDATE SET
            relevant = excluded.relevant,
            appreciated = excluded.appreciated,
            sentiment = excluded.sentiment,
            signal_type = excluded.signal_type,
            llm_confidence = excluded.llm_confidence,
            reason = excluded.reason,
            model = excluded.model,
            classified_at = excluded.classified_at,
            verified = excluded.verified
        """,
        [
            r["review_id"], r["place_id"], r["relevant"], r["appreciated"],
            r["sentiment"], r["signal_type"], r["llm_confidence"],
            r["reason"], model, datetime.now(timezone.utc), verified,
        ],
    )
    # DELETE puis INSERT plutôt qu'un upsert par aspect : le NOMBRE d'aspects
    # peut changer d'une classification à l'autre (reclassify), il faut donc
    # pouvoir aussi bien ajouter que retirer des lignes, pas juste les mettre
    # à jour une à une.
    con.execute("DELETE FROM pac_mention_aspects WHERE review_id = ?", [r["review_id"]])
    if r["aspects"]:
        con.executemany(
            "INSERT INTO pac_mention_aspects (review_id, aspect, weight) VALUES (?, ?, ?)",
            [(r["review_id"], aspect, weight) for aspect, weight in r["aspects"].items()],
        )


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
                _write_mention_result(con, r, model, verified=True)
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

# Une mention qui identifie un critère qualité précis (fraîcheur, cuisson,
# quantité de chocolat, etc. -- pac_mention_aspects) est jugée plus fiable/
# spécifique qu'une mention vague ("pas terrible" sans plus de détail) --
# léger bonus de poids, volontairement modeste (contrairement à
# signal_type, ce n'est pas un signal fort sur la fiabilité du jugement,
# juste un indice de précision). Neutre (1.0) si la mention n'a aucun
# aspect détecté -- c'est le cas de TOUTE mention non pertinente (aspects
# gated sur relevant dans _classify_one) et de toute mention classifiée
# avant l'introduction de ce champ.
ASPECT_SPECIFICITY_BONUS = 1.15

# En dessous de ce nombre de mentions, un score par aspect serait décidé
# par un ou deux avis -- pas un échantillon assez large pour un chiffre
# affiché en tête de fiche (cf. plan).
MIN_ASPECT_MENTIONS = 3

# Décision révisée de l'utilisateur (la version précédente excluait
# délibérément la note Google globale, cf. l'ancien commentaire ci-dessus
# sur le lissage) : la note Google du lieu compte maintenant un peu dans
# le score final -- un léger mélange DIRECT sur le score déjà agrégé, pas
# une modification du prior de lissage (SHRINKAGE_K continue de lisser
# vers la moyenne parisienne des mentions, jamais vers la note du lieu :
# ce mécanisme-là reste inchangé et protège toujours les lieux à peu de
# mentions contre un score fantaisiste). Le mélange ne s'applique que si
# le lieu a une note Google ET un score pain-au-chocolat calculable ; pas
# de valeur inventée pour un lieu sans mention. 20% : un vrai effet
# perceptible sur un classement serré, mais un pain au chocolat vraiment
# raté dans une boulangerie adorée (4.8★) doit rester nettement en
# dessous d'un bon pain au chocolat dans une boulangerie moyenne (3.5★).
GOOGLE_RATING_BLEND_WEIGHT = 0.2


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
                    * CASE WHEN coalesce(asp.max_aspect_weight, 0) > 0 THEN {ASPECT_SPECIFICITY_BONUS} ELSE 1.0 END
                    AS weight
            FROM pac_mentions m
            JOIN reviews r ON r.review_id = m.review_id
            JOIN pac_mentions_raw mr ON mr.review_id = m.review_id
            LEFT JOIN (
                SELECT review_id, max(weight) AS max_aspect_weight
                FROM pac_mention_aspects
                GROUP BY review_id
            ) asp ON asp.review_id = m.review_id
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
            place_id,
            name,
            n_mentions_total,
            n_relevant,
            -- Mélange léger avec la note Google globale du lieu, appliqué
            -- DIRECTEMENT sur le score déjà agrégé (pas une modification du
            -- prior de lissage ci-dessus, qui continue à lisser vers la
            -- moyenne parisienne des mentions, jamais vers la note du lieu
            -- -- cf. commentaire sur GOOGLE_RATING_BLEND_WEIGHT). Jamais de
            -- mélange si le lieu n'a pas de note Google ou pas de score
            -- pain-au-chocolat calculable : pas de valeur inventée.
            CASE
                WHEN pac_score_10 IS NULL THEN NULL
                WHEN google_rating IS NULL THEN pac_score_10
                ELSE {1 - GOOGLE_RATING_BLEND_WEIGHT} * pac_score_10 + {GOOGLE_RATING_BLEND_WEIGHT} * (google_rating * 2)
            END AS score_10,
            confidence,
            positive_ratio
        FROM (
            SELECT
                p.place_id,
                p.name,
                p.rating AS google_rating,
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
                END AS pac_score_10,
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
                    -- cf. commentaire sur pac_score_10 ci-dessus) donnerait 0/0
                    -- = NaN plutôt que NULL en SQL flottant -- on force
                    -- explicitement NULL, jamais un NaN qui traverserait
                    -- silencieusement les filtres IS NOT NULL en aval.
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
        )
        """
    )
    n_scored = con.execute("SELECT count(*) FROM pac_scores WHERE score_10 IS NOT NULL").fetchone()[0]
    _compute_aspect_scores(con, generic_terms_sql)
    return n_scored


def _compute_aspect_scores(con: duckdb.DuckDBPyConnection, generic_terms_sql: str) -> None:
    """Étage 3bis : un score /10 par (lieu, critère qualité), en plus du
    score global -- jamais à sa place. Réutilise le même poids par mention
    que _weighted ci-dessus (crédibilité x fraîcheur x terme générique x
    signal_type x llm_confidence x bonus de spécificité), multiplié par le
    poids de CET aspect dans la mention (une mention peut compter beaucoup
    pour "chocolate_quantity" et peu pour "lamination" si elle cite les
    deux avec des poids différents). Volontairement plus simple que le
    score global : pas de lissage vers un prior (MIN_ASPECT_MENTIONS protège
    déjà des petits échantillons), pas de blend avec positive_ratio -- une
    moyenne pondérée du sentiment, mappée sur 0..10 (cf. plan)."""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _weighted_aspects AS
        SELECT
            m.place_id,
            pma.aspect,
            greatest({SENTIMENT_WINSOR_FLOOR}, m.sentiment) AS sentiment,
            (
                least(ln(1 + coalesce(r.author_review_count, 0)), {REVIEWER_WEIGHT_CAP})
                    * pow(0.5, (epoch(current_timestamp) - r.published_at) / 86400.0 / {RECENCY_HALFLIFE_DAYS})
                    * CASE WHEN mr.matched_term IN ({generic_terms_sql}) THEN {GENERIC_TERM_WEIGHT} ELSE 1.0 END
                    * CASE m.signal_type
                          WHEN 'isolated_incident' THEN {ISOLATED_INCIDENT_WEIGHT}
                          WHEN 'ongoing_pattern' THEN {ONGOING_PATTERN_WEIGHT}
                          ELSE 1.0
                      END
                    * coalesce(m.llm_confidence, 1.0)
                    * {ASPECT_SPECIFICITY_BONUS}
                    * pma.weight
            ) AS weight
        FROM pac_mentions m
        JOIN reviews r ON r.review_id = m.review_id
        JOIN pac_mentions_raw mr ON mr.review_id = m.review_id
        JOIN pac_mention_aspects pma ON pma.review_id = m.review_id
        WHERE m.relevant = true
        """
    )
    con.execute("DELETE FROM pac_place_aspects")
    con.execute(
        f"""
        INSERT INTO pac_place_aspects (place_id, aspect, score_10, n_mentions)
        SELECT
            place_id,
            aspect,
            greatest(0.0, least(10.0, (sum(sentiment * weight) / nullif(sum(weight), 0) + 1) * 5)) AS score_10,
            count(*) AS n_mentions
        FROM _weighted_aspects
        GROUP BY place_id, aspect
        HAVING count(*) >= {MIN_ASPECT_MENTIONS}
        """
    )


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
