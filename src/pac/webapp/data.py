"""Accès en lecture seule à data/pac.duckdb pour l'app Streamlit.

La base continue d'être écrite par le crawl/scoring en tâche de fond
pendant que l'app tourne (cf. plan) -- toute connexion se fait en
read_only=True, et chaque fonction publique est décorée @st.cache_data
avec un TTL court pour limiter la fréquence de réouverture tout en laissant
l'app se rafraîchir seule au fil du crawl."""

from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from pac.config import DUCKDB_PATH
from pac.webapp.theme import extract_arrondissement

CACHE_TTL_SECONDS = 60


class DatabaseUnavailable(RuntimeError):
    """La base n'existe pas encore, ou est momentanément inaccessible
    (verrouillée par une écriture concurrente du crawl)."""


def _connect() -> duckdb.DuckDBPyConnection:
    if not Path(DUCKDB_PATH).exists():
        raise DatabaseUnavailable(
            f"{DUCKDB_PATH} n'existe pas encore -- lance `pac load` au moins une fois."
        )
    try:
        return duckdb.connect(str(DUCKDB_PATH), read_only=True)
    except duckdb.Error as exc:
        raise DatabaseUnavailable(
            "Base momentanément indisponible (probablement en cours d'écriture par le "
            "crawl en tâche de fond) -- réessaie dans quelques secondes."
        ) from exc


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_places_with_scores() -> pd.DataFrame:
    """Un lieu par ligne, avec son score pain-au-chocolat s'il existe et
    son arrondissement dérivé de l'adresse."""
    con = _connect()
    try:
        df = con.execute(
            """
            SELECT
                p.place_id, p.name, p.formatted_address, p.lat, p.lon,
                p.rating AS google_rating, p.user_rating_count, p.google_maps_uri,
                s.score_10, s.confidence, s.n_relevant, s.n_mentions_total
            FROM places p
            LEFT JOIN pac_scores s ON s.place_id = p.place_id
            WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL
            """
        ).fetchdf()
    finally:
        con.close()
    df["confidence"] = df["confidence"].fillna("insufficient_data")
    df["arrondissement"] = df["formatted_address"].apply(extract_arrondissement)
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_kpis() -> dict:
    con = _connect()
    try:
        row = con.execute(
            """
            SELECT
                (SELECT count(*) FROM places) AS n_places,
                (SELECT count(*) FROM reviews) AS n_reviews,
                (SELECT count(*) FROM pac_scores WHERE score_10 IS NOT NULL) AS n_scored,
                (SELECT avg(score_10) FROM pac_scores WHERE score_10 IS NOT NULL) AS avg_score,
                (SELECT max(scraped_at) FROM reviews) AS last_review_at
            """
        ).fetchone()
    finally:
        con.close()
    n_places, n_reviews, n_scored, avg_score, last_review_at = row
    return {
        "n_places": n_places or 0,
        "n_reviews": n_reviews or 0,
        "n_scored": n_scored or 0,
        "coverage_pct": (n_scored / n_places * 100) if n_places else 0.0,
        "avg_score": avg_score,
        "last_review_at": last_review_at,
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_review_excerpts_by_place() -> dict[str, pd.DataFrame]:
    """L'extrait le plus positif ET le plus négatif par lieu, pour TOUS les
    lieux en une seule requête (fenêtrée par place_id) -- pas une requête
    par marqueur au moment du rendu de la carte, qui serait beaucoup trop
    lent dès quelques centaines de lieux."""
    con = _connect()
    try:
        df = con.execute(
            """
            WITH ranked AS (
                SELECT
                    m.place_id, m.sentiment, m.reason, r.text, r.author_name, r.rating,
                    row_number() OVER (PARTITION BY m.place_id ORDER BY m.sentiment DESC) AS rank_pos,
                    row_number() OVER (PARTITION BY m.place_id ORDER BY m.sentiment ASC) AS rank_neg
                FROM pac_mentions m
                JOIN reviews r ON r.review_id = m.review_id
                WHERE m.relevant = true
            )
            SELECT place_id, sentiment, reason, text, author_name, rating
            FROM ranked WHERE rank_pos = 1
            UNION ALL
            SELECT place_id, sentiment, reason, text, author_name, rating
            FROM ranked WHERE rank_neg = 1 AND rank_pos != 1
            """
        ).fetchdf()
    finally:
        con.close()
    return {pid: g.drop(columns="place_id") for pid, g in df.groupby("place_id")}
