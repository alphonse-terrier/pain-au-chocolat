"""Génère les fichiers JSON statiques consommés par le frontend Next.js/
MapLibre (web/), à partir de data/pac_app.duckdb -- jamais du pipeline
complet (cf. plan). Le frontend n'a ni base de données ni serveur au
runtime : tout est pré-calculé ici, une fois, et servi tel quel par le CDN
de Vercel.

Reproduit volontairement les mêmes requêtes/règles que
src/pac/webapp/data.py (filtre des fiches "fantômes", fillna confidence,
extract_arrondissement) et src/pac/webapp/map_view.py
(spread_duplicate_coordinates) -- pas de nouvelle logique, juste une
seconde sortie pour les mêmes données. Si l'une de ces règles change côté
Streamlit, elle doit changer ici aussi."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from pac.config import APP_DUCKDB_PATH, WEB_DATA_DIR
from pac.webapp.theme import extract_arrondissement

# Identique au principe de map_view._JITTER_DEGREES, mais un peu plus large
# (~8 m au lieu de ~4 m) : MapLibre n'a pas de "spiderfy" comme
# Leaflet.markercluster -- au-delà du zoom de clustering, deux points à des
# coordonnées strictement identiques resteraient superposés pixel pour pixel
# sans aucun moyen de les séparer en zoomant davantage. Un écart plus net
# donne une séparation visible dès que le clustering cesse de les regrouper
# (cf. plan, clusterMaxZoom côté frontend).
_JITTER_DEGREES = 0.00008


def _connect_readonly(duckdb_path: Path) -> duckdb.DuckDBPyConnection:
    if not duckdb_path.exists():
        raise RuntimeError(f"{duckdb_path} n'existe pas -- lance `pac export-app-db` d'abord.")
    return duckdb.connect(str(duckdb_path), read_only=True)


def _spread_duplicate_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """Port direct de map_view.spread_duplicate_coordinates (même
    algorithme, même déterminisme par position dans le groupe) -- ne pas
    laisser diverger les deux implémentations."""
    df = df.copy()
    df["map_lat"] = df["lat"]
    df["map_lon"] = df["lon"]
    for _, group in df.groupby(["lat", "lon"]):
        n = len(group)
        if n < 2:
            continue
        for offset, idx in enumerate(group.index):
            angle = 2 * math.pi * offset / n
            lat = group.loc[idx, "lat"]
            df.loc[idx, "map_lat"] = lat + _JITTER_DEGREES * math.cos(angle)
            df.loc[idx, "map_lon"] = group.loc[idx, "lon"] + _JITTER_DEGREES * math.sin(angle) / math.cos(
                math.radians(lat)
            )
    return df


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # separators compacts + tri des clés implicite (dicts construits dans un
    # ordre fixe ci-dessous) -- sortie déterministe pour que `pac
    # export-web-json` lancé deux fois de suite ne fasse pas bouger git pour
    # rien (cf. plan, test de déterminisme).
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def export_web_json(out_dir: Path = WEB_DATA_DIR, duckdb_path: Path = APP_DUCKDB_PATH) -> dict:
    con = _connect_readonly(duckdb_path)
    try:
        # --- places + scores (même requête que load_places_with_scores) ---
        places = con.execute(
            """
            WITH ranked AS (
                SELECT
                    p.*,
                    count(*) OVER (PARTITION BY p.lat, p.lon) AS n_at_coord
                FROM places p
            )
            SELECT
                p.place_id, p.name, p.formatted_address, p.lat, p.lon,
                p.rating AS google_rating, p.user_rating_count, p.google_maps_uri,
                s.score_10, s.confidence, s.n_relevant, s.n_mentions_total, s.positive_ratio
            FROM ranked p
            LEFT JOIN pac_scores s ON s.place_id = p.place_id
            WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL
              AND NOT (p.n_at_coord > 1 AND p.rating IS NULL AND p.user_rating_count IS NULL)
            ORDER BY p.place_id
            """
        ).fetchdf()
        places["confidence"] = places["confidence"].fillna("insufficient_data")
        places["arrondissement"] = places["formatted_address"].apply(extract_arrondissement)
        places = _spread_duplicate_coordinates(places)

        # --- KPIs (même requête que load_kpis, + le total non filtré) ---
        n_places, n_reviews, n_scored, avg_score, last_review_at = con.execute(
            """
            SELECT
                (SELECT count(*) FROM places) AS n_places,
                (SELECT count(*) FROM reviews) AS n_reviews,
                (SELECT count(*) FROM pac_scores WHERE score_10 IS NOT NULL) AS n_scored,
                (SELECT avg(score_10) FROM pac_scores WHERE score_10 IS NOT NULL) AS avg_score,
                (SELECT max(scraped_at) FROM reviews) AS last_review_at
            """
        ).fetchone()

        meta = {
            "n_places": n_places or 0,
            "n_places_rendered": len(places),
            "n_reviews": n_reviews or 0,
            "n_scored": n_scored or 0,
            "coverage_pct": round((n_scored / n_places * 100) if n_places else 0.0, 1),
            "avg_score": round(avg_score, 2) if avg_score is not None else None,
            "last_review_at": (
                last_review_at.replace(tzinfo=timezone.utc).isoformat() if last_review_at else None
            ),
        }

        columns = [
            "place_id", "name", "address", "lat", "lon", "map_lat", "map_lon",
            "google_rating", "user_rating_count", "maps_uri",
            "score_10", "confidence", "n_relevant", "positive_ratio", "arrondissement",
        ]
        rows = []
        for r in places.itertuples(index=False):
            rows.append([
                r.place_id,
                r.name if pd.notna(r.name) else None,
                r.formatted_address if pd.notna(r.formatted_address) else None,
                round(r.lat, 6), round(r.lon, 6), round(r.map_lat, 6), round(r.map_lon, 6),
                round(r.google_rating, 1) if pd.notna(r.google_rating) else None,
                int(r.user_rating_count) if pd.notna(r.user_rating_count) else None,
                r.google_maps_uri if pd.notna(r.google_maps_uri) else None,
                round(r.score_10, 2) if pd.notna(r.score_10) else None,
                r.confidence,
                int(r.n_relevant) if pd.notna(r.n_relevant) else 0,
                round(r.positive_ratio, 3) if pd.notna(r.positive_ratio) else None,
                int(r.arrondissement) if pd.notna(r.arrondissement) else None,
            ])

        _write_json(
            out_dir / "places.json",
            {
                "version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "meta": meta,
                "columns": columns,
                "rows": rows,
            },
        )

        # --- avis retenus, groupés par lieu (une seule requête, pas une
        # par lieu -- cf. plan, même raison que load_mentions_for_place) ---
        mentions = con.execute(
            """
            SELECT m.place_id, r.text, r.author_name, r.rating,
                   r.relative_time_text, r.published_at, m.sentiment
            FROM pac_mentions m
            JOIN reviews r ON r.review_id = m.review_id
            WHERE m.relevant = true
            ORDER BY m.place_id, m.sentiment DESC
            """
        ).fetchdf()
    finally:
        con.close()

    places_dir = out_dir / "places"
    places_dir.mkdir(parents=True, exist_ok=True)
    current_ids = set()
    n_written_reviews = 0
    for place_id, group in mentions.groupby("place_id", sort=True):
        current_ids.add(place_id)
        reviews = [
            {
                # pd.notna(...) partout : un NULL SQL dans une colonne VARCHAR
                # ressort de fetchdf() en NaN (float), pas en None, dès que la
                # requête vient d'un JOIN -- un NaN écrit tel quel par
                # json.dumps produit un `NaN` littéral, qui n'est PAS du JSON
                # valide (JSON.parse plante côté navigateur). Bug réel
                # rencontré et corrigé ici (cf. plan, author_name NULL).
                "t": row.text if pd.notna(row.text) else None,
                "a": row.author_name if pd.notna(row.author_name) else None,
                "r": int(row.rating) if pd.notna(row.rating) else None,
                "w": row.relative_time_text if pd.notna(row.relative_time_text) else None,
                "p": row.published_at if pd.notna(row.published_at) else None,
                "s": round(row.sentiment, 3),
            }
            for row in group.itertuples(index=False)
        ]
        n_written_reviews += len(reviews)
        _write_json(places_dir / f"{place_id}.json", {"place_id": place_id, "n": len(reviews), "reviews": reviews})

    # Purge les fragments orphelins (lieu qui n'a plus de mention retenue,
    # ex. après un `pac reclassify`) -- sinon un vieux fichier resterait
    # servi indéfiniment par le CDN.
    n_pruned = 0
    for f in places_dir.glob("*.json"):
        if f.stem not in current_ids:
            f.unlink()
            n_pruned += 1

    return {
        "places": len(places),
        "shards": len(current_ids),
        "mentions": n_written_reviews,
        "pruned": n_pruned,
    }


if __name__ == "__main__":
    print(export_web_json())
