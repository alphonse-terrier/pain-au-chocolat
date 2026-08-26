"""Fusionne les fiches Google Places en double : plusieurs `place_id`
distincts pour le même commerce physique, typiquement une ancienne fiche
(nom du gérant précédent, raison sociale) qui traîne à côté de la fiche
actuelle après un changement de propriétaire/enseigne -- un cas très
fréquent pour les boulangeries parisiennes.

Détection : même `formatted_address` exact. Exclut volontairement les
adresses réduites à "NNNNN Paris, France" (pas de numéro/rue) -- ce n'est
pas une adresse précise partagée par plusieurs commerces, c'est une fiche à
qui il manque une adresse complète ; les regrouper produirait des fusions
absurdes entre commerces sans aucun rapport (vérifié sur les données
réelles, cf. discussion).

Fusion : tous les avis (et tout ce qui en dérive : mentions, mentions
brutes) des fiches perdantes sont réaffectés à la fiche gagnante -- celle
qui a le plus d'avis dans NOTRE base (pas le `user_rating_count` de
Google, qui est le total affiché par Google toutes langues/tout temps
confondu et peut ne pas refléter ce qu'on a réellement scrapé). Les fiches
perdantes sont ensuite supprimées. pac_scores/pac_place_aspects des fiches
perdantes sont supprimés (recalculés au prochain `pac score`, qui doit
suivre un `pac dedupe` -- ce module ne réagrège rien lui-même)."""

import duckdb

# Adresse réduite à "code postal + ville", sans numéro ni nom de rue --
# signe d'une fiche à l'adresse incomplète, pas d'un vrai doublon
# géographique. Voir docstring du module.
_GENERIC_ADDRESS_PATTERN = r"^\d{5} Paris, France$"


def find_duplicate_groups(con: duckdb.DuckDBPyConnection) -> list[list[str]]:
    """Retourne les groupes de place_id partageant la même adresse précise,
    triés par place_id au sein de chaque groupe pour un ordre déterministe."""
    rows = con.execute(
        f"""
        SELECT list(place_id ORDER BY place_id) AS ids
        FROM places
        WHERE formatted_address IS NOT NULL
          AND NOT regexp_matches(formatted_address, '{_GENERIC_ADDRESS_PATTERN}')
        GROUP BY formatted_address
        HAVING count(*) > 1
        """
    ).fetchall()
    return [row[0] for row in rows]


def _pick_survivor(con: duckdb.DuckDBPyConnection, place_ids: list[str]) -> str:
    """La fiche qui a le plus d'avis dans notre base l'emporte -- à égalité,
    le user_rating_count Google le plus élevé, puis le place_id le plus
    petit (déterministe, arbitraire au-delà de ce point)."""
    placeholders = ", ".join("?" * len(place_ids))
    rows = con.execute(
        f"""
        SELECT p.place_id,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.place_id) AS n_reviews,
               coalesce(p.user_rating_count, -1) AS user_rating_count
        FROM places p
        WHERE p.place_id IN ({placeholders})
        ORDER BY n_reviews DESC, user_rating_count DESC, p.place_id ASC
        """,
        place_ids,
    ).fetchall()
    return rows[0][0]


def merge_duplicates(con: duckdb.DuckDBPyConnection, dry_run: bool = False) -> dict:
    """(Re)fusionne toutes les fiches en double détectées par
    find_duplicate_groups. dry_run=True ne modifie rien, se contente de
    rapporter ce qui serait fait -- pratique pour vérifier avant de lancer
    pour de vrai. Retourne des compteurs, pas la liste détaillée (cf.
    discover --dry-run pour le même principe)."""
    groups = find_duplicate_groups(con)
    n_reviews_moved = 0
    n_places_removed = 0
    merges = []

    if not dry_run:
        con.execute("BEGIN TRANSACTION")
    try:
        for group in groups:
            survivor = _pick_survivor(con, group)
            losers = [p for p in group if p != survivor]
            merges.append({"survivor": survivor, "losers": losers})

            n_reviews_moved += con.execute(
                f"SELECT count(*) FROM reviews WHERE place_id IN ({', '.join('?' * len(losers))})",
                losers,
            ).fetchone()[0]
            n_places_removed += len(losers)

            if dry_run:
                continue

            for table in ("reviews", "pac_mentions_raw", "pac_mentions"):
                con.execute(
                    f"UPDATE {table} SET place_id = ? WHERE place_id IN ({', '.join('?' * len(losers))})",
                    [survivor, *losers],
                )
            for table in ("pac_scores", "pac_place_aspects", "places"):
                con.execute(
                    f"DELETE FROM {table} WHERE place_id IN ({', '.join('?' * len(losers))})",
                    losers,
                )
        if not dry_run:
            con.execute("COMMIT")
    except Exception:
        if not dry_run:
            con.execute("ROLLBACK")
        raise

    return {
        "groups_merged": len(groups),
        "places_removed": n_places_removed,
        "reviews_reassigned": n_reviews_moved,
        "merges": merges,
    }
