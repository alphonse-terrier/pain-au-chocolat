"""Génère data/pac_app.duckdb, une base allégée dédiée à l'app Streamlit --
séparée de la base complète du pipeline (pac.config.DUCKDB_PATH, écrite par
discover/reviews/score).

Motivation (cf. discussion) : ~90% des avis bruts scrapés ne sont jamais lus
par l'app -- seul le texte des avis liés à une mention pain-au-chocolat/
viennoiserie retenue (pac_mentions.relevant=true) est affiché. Garder la
base complète (avec le texte intégral des ~236k avis) dans ce qui est
éventuellement déployé/versionné avec l'app gonfle inutilement sa taille.

Cet export préserve le SCHÉMA (mêmes noms/types de colonnes attendus par
src/pac/webapp/data.py) pour ne nécessiter aucun changement côté requêtes --
seules les colonnes jamais lues par l'app sont supprimées, et le texte des
avis non pertinents est mis à NULL plutôt que les lignes supprimées (les
agrégats "nombre total d'avis"/"dernier avis récolté" de load_kpis restent
calculés sur le VRAI volume scrapé, pas seulement les avis affichés)."""

import duckdb

from pac.config import APP_DUCKDB_PATH, DUCKDB_PATH


def export_app_db() -> dict:
    """(Re)génère APP_DUCKDB_PATH à partir de DUCKDB_PATH. Écrase le fichier
    existant s'il y en a un -- purement dérivé de la base pipeline, jamais
    la source de vérité."""
    if APP_DUCKDB_PATH.exists():
        APP_DUCKDB_PATH.unlink()

    con = duckdb.connect(str(APP_DUCKDB_PATH))
    try:
        con.execute(f"ATTACH '{DUCKDB_PATH}' AS src (READ_ONLY)")

        con.execute(
            """
            CREATE TABLE places AS
            SELECT place_id, name, formatted_address, lat, lon, rating,
                   user_rating_count, google_maps_uri
            FROM src.places
            """
        )

        con.execute(
            """
            CREATE TABLE reviews AS
            SELECT
                r.review_id, r.place_id, r.author_name,
                CASE WHEN m.review_id IS NOT NULL THEN r.text ELSE NULL END AS text,
                r.rating, r.relative_time_text, r.published_at, r.scraped_at
            FROM src.reviews r
            LEFT JOIN src.pac_mentions m ON m.review_id = r.review_id AND m.relevant = true
            """
        )

        con.execute(
            """
            CREATE TABLE pac_mentions AS
            SELECT review_id, place_id, relevant, appreciated, sentiment, reason
            FROM src.pac_mentions
            WHERE relevant = true
            """
        )

        con.execute("CREATE TABLE pac_scores AS SELECT * FROM src.pac_scores")
        con.execute("CREATE TABLE pac_place_aspects AS SELECT * FROM src.pac_place_aspects")

        con.execute("DETACH src")

        counts = {
            t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("places", "reviews", "pac_mentions", "pac_scores", "pac_place_aspects")
        }
    finally:
        con.close()

    return counts


if __name__ == "__main__":
    print(export_app_db())
