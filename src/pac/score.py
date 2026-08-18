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
]

SYSTEM_PROMPT = """Tu analyses un avis Google Maps sur une boulangerie parisienne.
On t'indique un terme détecté ("pain au chocolat" ou "chocolatine") dans le
texte. Détermine si le passage autour de ce terme exprime un avis sur le
GOÛT/LA QUALITÉ de la pâtisserie elle-même (texture, fraîcheur, feuilletage,
quantité de chocolat, etc.) -- PAS sur son prix, le service, ou une simple
mention en passant sans jugement.

Réponds en JSON strict avec exactement ces clés :
{"relevant": true|false, "sentiment": <float entre -1.0 et 1.0>, "reason": "<courte justification>"}

- relevant=false si la mention parle de prix, de service, ou est neutre/sans
  jugement sur la qualité (même si l'avis global est très négatif ou positif).
- Si relevant=true, sentiment doit juger UNIQUEMENT la qualité de la
  pâtisserie décrite, pas la note globale de l'avis ni le prix.
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


def _pending_mentions(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    return con.execute(
        """
        SELECT m.review_id, m.place_id, m.text, m.matched_term
        FROM pac_mentions_raw m
        WHERE m.review_id NOT IN (SELECT review_id FROM pac_mentions)
        """
    ).fetchall()


def _classify_one(
    client: httpx.Client, review_id: str, place_id: str, text: str, term: str, model: str
) -> dict:
    user_prompt = f'Terme détecté : "{term}"\n\nAvis complet :\n{text}'
    try:
        result = classify_json(client, SYSTEM_PROMPT, user_prompt, model=model)
        relevant = bool(result.get("relevant"))
        sentiment = float(result.get("sentiment", 0.0))
        sentiment = max(-1.0, min(1.0, sentiment))
        reason = str(result.get("reason", ""))[:500]
        failed = False
    except (LLMError, ValueError, TypeError) as exc:
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
        relevant, sentiment, reason, failed = False, 0.0, f"classification échouée: {exc}", True
    return {
        "review_id": review_id,
        "place_id": place_id,
        "relevant": relevant,
        "sentiment": sentiment,
        "reason": reason,
        "failed": failed,
    }


def classify_mentions(con: duckdb.DuckDBPyConnection, workers: int, model: str) -> int:
    """Étage 2 : classification LLM des mentions pas encore traitées.

    Idempotent : ne reclassifie jamais un review_id déjà présent dans
    pac_mentions -- relancer après un nouveau `pac reviews` ne coûte que le
    delta de nouvelles mentions.
    """
    pending = _pending_mentions(con)
    if not pending:
        return 0

    results = []
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
                results.append(f.result())

    classified_at = datetime.now(timezone.utc)
    con.executemany(
        """
        INSERT INTO pac_mentions (review_id, place_id, relevant, sentiment, reason, model, classified_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (review_id) DO NOTHING
        """,
        [
            (r["review_id"], r["place_id"], r["relevant"], r["sentiment"], r["reason"], model, classified_at)
            for r in results
        ],
    )
    return len(results)


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
    premier modèle via un second avis indépendant sur le MÊME texte."""
    pending = _pending_anomalies(con)
    if not pending:
        return 0

    results = []
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
                results.append(f.result())

    n_updated = 0
    for r in results:
        if r["failed"]:
            # Échec technique du second modèle : on NE TOUCHE PAS à la
            # classification existante (verified reste false, elle sera
            # retentée au prochain `pac score`) -- plutôt que d'écraser une
            # classification valide par un résultat par défaut inventé.
            continue
        con.execute(
            """
            UPDATE pac_mentions
            SET relevant = ?, sentiment = ?, reason = ?, model = ?, verified = true
            WHERE review_id = ?
            """,
            [r["relevant"], r["sentiment"], r["reason"], model, r["review_id"]],
        )
        n_updated += 1
    return n_updated


# Constantes de pondération (cf. plan, section Étape 3) ---------------------
REVIEWER_WEIGHT_CAP = math.log(1 + 500)  # plafonne l'effet des power users
RECENCY_HALFLIFE_DAYS = 730  # ~2 ans : un avis perd moitié de son poids en 2 ans
SHRINKAGE_K = 2  # force du lissage vers le prior global, volontairement faible


def compute_scores(con: duckdb.DuckDBPyConnection) -> int:
    """Étage 3 : agrégation pondérée en SQL (cf. plan pour la justification
    détaillée de chaque choix, notamment l'absence de lissage vers la note
    globale du lieu -- décision explicite de l'utilisateur)."""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _weighted AS
        SELECT
            m.place_id,
            m.sentiment,
            least(ln(1 + coalesce(r.author_review_count, 0)), {REVIEWER_WEIGHT_CAP})
                * pow(0.5, (epoch(current_timestamp) - r.published_at) / 86400.0 / {RECENCY_HALFLIFE_DAYS})
                AS weight
        FROM pac_mentions m
        JOIN reviews r ON r.review_id = m.review_id
        WHERE m.relevant = true
    """
    )

    prior_row = con.execute(
        "SELECT sum(sentiment * weight) / sum(weight) FROM _weighted"
    ).fetchone()
    prior_global = prior_row[0] if prior_row and prior_row[0] is not None else 0.0

    con.execute("DELETE FROM pac_scores")
    con.execute(
        f"""
        INSERT INTO pac_scores (place_id, name, n_mentions_total, n_relevant, score_10, confidence)
        SELECT
            p.place_id,
            p.name,
            coalesce(raw.n_total, 0) AS n_mentions_total,
            coalesce(w.n_relevant, 0) AS n_relevant,
            CASE
                WHEN coalesce(w.n_relevant, 0) = 0 THEN NULL
                ELSE (
                    (w.n_relevant * w.raw_score + {SHRINKAGE_K} * {prior_global}) / (w.n_relevant + {SHRINKAGE_K})
                    + 1
                ) * 5
            END AS score_10,
            CASE
                WHEN coalesce(w.n_relevant, 0) = 0 THEN 'insufficient_data'
                WHEN w.n_relevant < 3 THEN 'low'
                WHEN w.n_relevant < 6 THEN 'medium'
                ELSE 'high'
            END AS confidence
        FROM places p
        LEFT JOIN (
            SELECT place_id, count(*) AS n_total FROM pac_mentions_raw GROUP BY place_id
        ) raw ON raw.place_id = p.place_id
        LEFT JOIN (
            SELECT place_id, count(*) AS n_relevant, sum(sentiment * weight) / sum(weight) AS raw_score
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
