"""Tests de l'export JSON statique pour le frontend Next.js/MapLibre (cf.
plan "New Next.js + MapLibre frontend"). Construit une base au schéma de
pac_app.duckdb (celui produit par export_app_db, PAS celui du pipeline
complet -- src/pac/store.py) directement en SQL, pour ne pas dépendre du
pipeline réel."""

import json

import duckdb
import pytest

from pac.export_web_json import export_web_json

APP_SCHEMA = """
CREATE TABLE places (
    place_id VARCHAR, name VARCHAR, formatted_address VARCHAR,
    lat DOUBLE, lon DOUBLE, rating DOUBLE, user_rating_count INTEGER,
    google_maps_uri VARCHAR
);
CREATE TABLE pac_scores (
    place_id VARCHAR, name VARCHAR, n_mentions_total INTEGER, n_relevant INTEGER,
    score_10 DOUBLE, confidence VARCHAR, updated_at TIMESTAMP, positive_ratio DOUBLE
);
CREATE TABLE pac_mentions (
    review_id VARCHAR, place_id VARCHAR, relevant BOOLEAN,
    appreciated BOOLEAN, sentiment DOUBLE, reason VARCHAR
);
CREATE TABLE reviews (
    review_id VARCHAR, place_id VARCHAR, author_name VARCHAR, text VARCHAR,
    rating INTEGER, relative_time_text VARCHAR, published_at DOUBLE, scraped_at TIMESTAMP
);
CREATE TABLE pac_place_aspects (
    place_id VARCHAR, aspect VARCHAR, score_10 DOUBLE, n_mentions INTEGER
);
"""


@pytest.fixture
def app_db(tmp_path):
    """Un fichier .duckdb (pas :memory: -- export_web_json ouvre en
    read_only, qui n'a pas de sens pour une base en mémoire) au schéma
    pac_app.duckdb, avec :
    - 2 lieux à coordonnées EXACTEMENT identiques (pour le jitter)
    - 1 lieu avec un score et des mentions (dont une avec un texte à
      l'adresse 75116, pour vérifier l'arrondissement 16)
    - 1 lieu sans aucune mention (pas de fragment attendu)
    - 1 fiche "fantôme" (coord dupliquée, ni note ni avis Google -> exclue)
    """
    db_path = tmp_path / "pac_app.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(APP_SCHEMA)

    con.execute(
        """
        INSERT INTO places VALUES
        ('p1', 'Boulangerie Un', '1 Rue A, 75116 Paris, France', 48.85, 2.35, 4.5, 100, 'https://maps.google.com/?cid=1'),
        ('p2', 'Boulangerie Deux', '2 Rue B, 75011 Paris, France', 48.86, 2.36, 4.0, 50, 'https://maps.google.com/?cid=2'),
        ('p3', 'Boulangerie Trois (sans mention)', '3 Rue C, 75011 Paris, France', 48.87, 2.37, 3.5, 20, 'https://maps.google.com/?cid=3'),
        ('p_ghost', 'Fiche fantôme', '1 Rue A, 75116 Paris, France', 48.85, 2.35, NULL, NULL, 'https://maps.google.com/?cid=4')
        """
    )
    con.execute(
        """
        INSERT INTO pac_scores VALUES
        ('p1', 'Boulangerie Un', 5, 3, 8.1, 'high', now(), 0.9),
        ('p2', 'Boulangerie Deux', 2, 0, NULL, NULL, now(), NULL),
        ('p3', 'Boulangerie Trois (sans mention)', 0, 0, NULL, NULL, now(), NULL),
        ('p_ghost', 'Fiche fantôme', 0, 0, NULL, NULL, now(), NULL)
        """
    )
    con.execute(
        """
        INSERT INTO pac_mentions VALUES
        ('r1', 'p1', true, true, 0.9, 'raison 1'),
        ('r2', 'p1', true, false, -0.5, 'raison 2'),
        ('r3', 'p1', true, true, 0.3, 'raison 3')
        """
    )
    con.execute(
        """
        INSERT INTO reviews VALUES
        ('r1', 'p1', 'Alice', 'Excellent pain au chocolat.', 5, 'il y a 1 mois', 1700000000.0, now()),
        ('r2', 'p1', 'Bob', 'Décevant.', 2, 'il y a 2 mois', 1690000000.0, now()),
        ('r3', 'p1', NULL, 'Correct sans plus.', 3, 'il y a 3 mois', 1680000000.0, now())
        """
    )
    con.execute(
        """
        INSERT INTO pac_place_aspects VALUES
        ('p1', 'chocolate_quantity', 8.4, 5)
        """
    )
    con.close()
    return db_path


def test_export_counts_and_ghost_filter(app_db, tmp_path):
    out_dir = tmp_path / "out"
    counts = export_web_json(out_dir=out_dir, duckdb_path=app_db)

    # 4 lieux en base, mais la fiche fantôme (coord dupliquée avec p1, ni
    # note ni avis Google) est exclue -> 3 rendus.
    assert counts["places"] == 3
    assert counts["shards"] == 1  # seul p1 a des mentions
    assert counts["mentions"] == 3

    places = json.loads((out_dir / "places.json").read_text())
    assert places["meta"]["n_places"] == 4  # total non filtré
    assert places["meta"]["n_places_rendered"] == 3
    ids = {row[0] for row in places["rows"]}
    assert ids == {"p1", "p2", "p3"}
    assert "p_ghost" not in ids


def test_confidence_never_null_and_arrondissement(app_db, tmp_path):
    out_dir = tmp_path / "out"
    export_web_json(out_dir=out_dir, duckdb_path=app_db)
    places = json.loads((out_dir / "places.json").read_text())
    cols = places["columns"]
    conf_i, arr_i, id_i, addr_i = (cols.index(c) for c in ("confidence", "arrondissement", "place_id", "address"))

    for row in places["rows"]:
        assert row[conf_i] is not None  # jamais NULL, même sans score (-> "insufficient_data")
        if row[id_i] == "p2":
            assert row[conf_i] == "insufficient_data"
        # adresse "...75116 Paris..." -> arrondissement 16 (cas spécial)
        if "75116" in row[addr_i]:
            assert row[arr_i] == 16


def test_jitter_spreads_duplicate_coordinates(app_db, tmp_path):
    out_dir = tmp_path / "out"
    export_web_json(out_dir=out_dir, duckdb_path=app_db)
    places = json.loads((out_dir / "places.json").read_text())
    cols = places["columns"]
    lat_i, lon_i, mlat_i, mlon_i, id_i = (
        cols.index(c) for c in ("lat", "lon", "map_lat", "map_lon", "place_id")
    )
    by_id = {row[id_i]: row for row in places["rows"]}

    # p1 et la fiche fantôme partageaient une coordonnée -- la fantôme est
    # filtrée, donc p1 n'a plus de doublon parmi les lieux RENDUS : sa
    # position affichée doit rester la position réelle (pas de jitter
    # inutile appliqué à un groupe qui n'a plus qu'un membre visible).
    p1 = by_id["p1"]
    assert p1[mlat_i] == p1[lat_i]
    assert p1[mlon_i] == p1[lon_i]
    # p2 et p3 ont des coordonnées uniques -> jamais jitterées non plus.
    for pid in ("p2", "p3"):
        row = by_id[pid]
        assert row[mlat_i] == row[lat_i]
        assert row[mlon_i] == row[lon_i]


def test_shard_content_drops_reason_and_review_id_sorted_by_sentiment(app_db, tmp_path):
    out_dir = tmp_path / "out"
    export_web_json(out_dir=out_dir, duckdb_path=app_db)
    shard = json.loads((out_dir / "places" / "p1.json").read_text())

    assert shard["n"] == 3
    assert [r["s"] for r in shard["reviews"]] == sorted((r["s"] for r in shard["reviews"]), reverse=True)
    for r in shard["reviews"]:
        assert "reason" not in r
        assert "review_id" not in r
    # auteur NULL -> None côté JSON, pas une valeur inventée type "Anonymous"
    # (c'est au frontend d'afficher le repli, cf. plan -- theme.ts).
    assert any(r["a"] is None for r in shard["reviews"])

    assert not (out_dir / "places" / "p2.json").exists()  # aucune mention -> pas de fragment
    assert not (out_dir / "places" / "p3.json").exists()


def test_prunes_stale_shards(app_db, tmp_path):
    out_dir = tmp_path / "out"
    export_web_json(out_dir=out_dir, duckdb_path=app_db)
    stale = out_dir / "places" / "no-longer-exists.json"
    stale.write_text('{"place_id":"no-longer-exists"}')

    counts = export_web_json(out_dir=out_dir, duckdb_path=app_db)

    assert counts["pruned"] == 1
    assert not stale.exists()
    assert (out_dir / "places" / "p1.json").exists()


def test_aspect_score_columns_present_and_null_when_uncovered(app_db, tmp_path):
    """places.json expose un score /10 secondaire par critère qualité --
    non NULL uniquement pour (lieu, critère) présent dans
    pac_place_aspects, NULL partout ailleurs (pas de valeur inventée,
    même logique que score_10 lui-même)."""
    out_dir = tmp_path / "out"
    export_web_json(out_dir=out_dir, duckdb_path=app_db)
    places = json.loads((out_dir / "places.json").read_text())
    cols = places["columns"]
    id_i, choc_i, lam_i = (
        cols.index(c) for c in ("place_id", "asp_chocolate_quantity", "asp_lamination")
    )
    by_id = {row[id_i]: row for row in places["rows"]}

    assert by_id["p1"][choc_i] == 8.4
    assert by_id["p1"][lam_i] is None  # pas de ligne pac_place_aspects pour cet aspect
    assert by_id["p2"][choc_i] is None  # aucune ligne pac_place_aspects pour ce lieu


def test_export_is_deterministic_across_runs(app_db, tmp_path):
    """Protège l'historique git (cf. plan) : deux exports successifs de la
    même base doivent produire des fragments byte-identiques, et un
    places.json identique une fois `generated_at` exclu (seul champ
    volontairement non déterministe)."""
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    export_web_json(out_dir=out_a, duckdb_path=app_db)
    export_web_json(out_dir=out_b, duckdb_path=app_db)

    shard_a = (out_a / "places" / "p1.json").read_bytes()
    shard_b = (out_b / "places" / "p1.json").read_bytes()
    assert shard_a == shard_b

    places_a = json.loads((out_a / "places.json").read_text())
    places_b = json.loads((out_b / "places.json").read_text())
    del places_a["generated_at"]
    del places_b["generated_at"]
    assert places_a == places_b
