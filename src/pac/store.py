"""Phase 3 du plan : chargement des JSONL bruts dans DuckDB, idempotent."""

import duckdb

from pac.config import DUCKDB_PATH, RAW_PLACES_DIR, RAW_REVIEWS_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
    place_id VARCHAR PRIMARY KEY,
    name VARCHAR,
    formatted_address VARCHAR,
    lat DOUBLE,
    lon DOUBLE,
    rating DOUBLE,
    user_rating_count INTEGER,
    primary_type VARCHAR,
    google_maps_uri VARCHAR,
    discovered_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id VARCHAR PRIMARY KEY,
    place_id VARCHAR,
    author_name VARCHAR,
    author_id VARCHAR,
    author_profile_url VARCHAR,
    author_review_count INTEGER,
    published_at DOUBLE,
    relative_time_text VARCHAR,
    text VARCHAR,
    rating INTEGER,
    scraped_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS crawl_state (
    place_id VARCHAR PRIMARY KEY,
    status VARCHAR,
    reviews_fetched INTEGER,
    error VARCHAR,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

-- Score qualité "pain au chocolat" (cf. plan) --------------------------

CREATE TABLE IF NOT EXISTS pac_mentions_raw (
    review_id VARCHAR PRIMARY KEY,
    place_id VARCHAR,
    text VARCHAR,
    matched_term VARCHAR,
    extracted_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS pac_mentions (
    review_id VARCHAR PRIMARY KEY,
    place_id VARCHAR,
    relevant BOOLEAN,
    sentiment DOUBLE,       -- -1 (mauvais) .. +1 (excellent), spécifique à la mention
    reason VARCHAR,
    model VARCHAR,
    verified BOOLEAN DEFAULT false,  -- repassé par verify_anomalies (second avis, modèle plus fort)
    classified_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS pac_scores (
    place_id VARCHAR PRIMARY KEY,
    name VARCHAR,
    n_mentions_total INTEGER,
    n_relevant INTEGER,
    score_10 DOUBLE,        -- NULL si n_relevant = 0 (cf. plan : pas de valeur par défaut)
    confidence VARCHAR,      -- 'insufficient_data' | 'low' | 'medium' | 'high'
    updated_at TIMESTAMP DEFAULT current_timestamp
);
"""


# Migrations légères pour les bases déjà créées avant l'ajout d'une colonne
# -- `CREATE TABLE IF NOT EXISTS` ne modifie pas une table existante.
MIGRATIONS = [
    "ALTER TABLE pac_mentions ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT false",
]


def get_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute(SCHEMA)
    for m in MIGRATIONS:
        con.execute(m)
    return con


def load_places(con: duckdb.DuckDBPyConnection) -> int:
    pattern = str(RAW_PLACES_DIR / "*.jsonl")
    files = list(RAW_PLACES_DIR.glob("*.jsonl"))
    if not files:
        return 0
    con.execute(
        f"""
        INSERT INTO places
        SELECT
            id AS place_id,
            displayName.text AS name,
            formattedAddress AS formatted_address,
            location.latitude AS lat,
            location.longitude AS lon,
            rating,
            userRatingCount AS user_rating_count,
            primaryType AS primary_type,
            googleMapsUri AS google_maps_uri,
            coalesce(try_cast(discovered_at AS TIMESTAMP), current_timestamp)
        FROM read_json_auto('{pattern}', union_by_name=true)
        ON CONFLICT (place_id) DO NOTHING
        """
    )
    return con.execute("SELECT count(*) FROM places").fetchone()[0]


def load_reviews(con: duckdb.DuckDBPyConnection) -> int:
    files = list(RAW_REVIEWS_DIR.glob("*.jsonl"))
    if not files:
        return 0
    pattern = str(RAW_REVIEWS_DIR / "*.jsonl")
    con.execute(
        f"""
        INSERT INTO reviews
        SELECT
            review_id, place_id, author_name, author_id, author_profile_url,
            author_review_count, published_at, relative_time_text, text, rating,
            coalesce(try_cast(scraped_at AS TIMESTAMP), current_timestamp)
        FROM read_json_auto('{pattern}', union_by_name=true)
        ON CONFLICT (review_id) DO NOTHING
        """
    )
    return con.execute("SELECT count(*) FROM reviews").fetchone()[0]
