"""Tests de la fusion des fiches Google Places en double (même adresse
précise) -- cf. src/pac/dedupe.py pour la justification du design."""

import duckdb
import pytest

from pac.dedupe import find_duplicate_groups, merge_duplicates
from pac.store import SCHEMA


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute(SCHEMA)
    yield c
    c.close()


def _insert_place(con, place_id, name, address, user_rating_count=None):
    con.execute(
        "INSERT INTO places (place_id, name, formatted_address, user_rating_count) VALUES (?, ?, ?, ?)",
        [place_id, name, address, user_rating_count],
    )


def _insert_review(con, review_id, place_id):
    con.execute("INSERT INTO reviews (review_id, place_id) VALUES (?, ?)", [review_id, place_id])


def _insert_mention(con, review_id, place_id, relevant=True):
    con.execute(
        "INSERT INTO pac_mentions (review_id, place_id, relevant, sentiment, model) VALUES (?, ?, ?, 0.5, 'test')",
        [review_id, place_id, relevant],
    )
    con.execute(
        "INSERT INTO pac_mentions_raw (review_id, place_id, text, matched_term) VALUES (?, ?, 'x', 'chocolatine')",
        [review_id, place_id],
    )


def test_finds_places_sharing_a_precise_address(con):
    _insert_place(con, "p1", "Ancienne Boulangerie SARL", "12 Rue de la Paix, 75002 Paris, France")
    _insert_place(con, "p2", "Boulangerie du Coin", "12 Rue de la Paix, 75002 Paris, France")
    _insert_place(con, "p3", "Autre Adresse", "5 Rue de Rivoli, 75004 Paris, France")

    groups = find_duplicate_groups(con)

    assert groups == [["p1", "p2"]]


def test_ignores_generic_postal_code_only_addresses(con):
    """"75004 Paris, France" (pas de numéro ni de rue) n'est pas une adresse
    précise partagée par plusieurs commerces -- c'est une fiche à qui il
    manque une adresse complète. Les regrouper produirait des fusions
    absurdes entre commerces sans rapport (cf. docstring du module)."""
    _insert_place(con, "p1", "Un Commerce", "75004 Paris, France")
    _insert_place(con, "p2", "Un Autre Commerce Sans Rapport", "75004 Paris, France")

    assert find_duplicate_groups(con) == []


def test_merges_into_the_place_with_the_most_reviews(con):
    _insert_place(con, "p_few", "Ancien Nom SARL", "12 Rue de la Paix, 75002 Paris, France")
    _insert_place(con, "p_many", "Boulangerie du Coin", "12 Rue de la Paix, 75002 Paris, France")
    for i in range(2):
        _insert_review(con, f"few-{i}", "p_few")
        _insert_mention(con, f"few-{i}", "p_few")
    for i in range(5):
        _insert_review(con, f"many-{i}", "p_many")
        _insert_mention(con, f"many-{i}", "p_many")

    result = merge_duplicates(con)

    assert result == {
        "groups_merged": 1,
        "places_removed": 1,
        "reviews_reassigned": 2,
        "merges": [{"survivor": "p_many", "losers": ["p_few"]}],
    }
    # Le perdant a disparu, ses avis et mentions appartiennent au survivant.
    assert con.execute("SELECT count(*) FROM places WHERE place_id = 'p_few'").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM reviews WHERE place_id = 'p_many'").fetchone()[0] == 7
    assert con.execute("SELECT count(*) FROM reviews WHERE place_id = 'p_few'").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM pac_mentions WHERE place_id = 'p_many'").fetchone()[0] == 7
    assert con.execute("SELECT count(*) FROM pac_mentions_raw WHERE place_id = 'p_many'").fetchone()[0] == 7


def test_ties_broken_by_google_user_rating_count(con):
    """À nombre d'avis égal dans NOTRE base, celle qui a le plus d'avis
    Google (user_rating_count) l'emporte -- un signal indirect de laquelle
    des deux fiches est la fiche "active" aux yeux de Google."""
    _insert_place(con, "p_low", "Ancien Nom", "1 Rue X, 75001 Paris, France", user_rating_count=10)
    _insert_place(con, "p_high", "Nom Actuel", "1 Rue X, 75001 Paris, France", user_rating_count=200)
    _insert_review(con, "r1", "p_low")
    _insert_review(con, "r2", "p_high")

    result = merge_duplicates(con)

    assert result["merges"] == [{"survivor": "p_high", "losers": ["p_low"]}]


def test_removes_stale_scores_and_aspects_for_losing_places(con):
    """pac_scores/pac_place_aspects des fiches perdantes n'ont plus de sens
    une fois leurs avis migrés ailleurs -- supprimés, pas laissés perimés
    en attendant le prochain `pac score`."""
    _insert_place(con, "p_few", "Ancien Nom", "1 Rue X, 75001 Paris, France")
    _insert_place(con, "p_many", "Nom Actuel", "1 Rue X, 75001 Paris, France")
    _insert_review(con, "r1", "p_few")
    _insert_review(con, "r2", "p_many")
    _insert_review(con, "r3", "p_many")
    con.execute(
        "INSERT INTO pac_scores (place_id, name, score_10) VALUES ('p_few', 'Ancien Nom', 5.0)"
    )
    con.execute(
        "INSERT INTO pac_place_aspects (place_id, aspect, score_10, n_mentions) VALUES ('p_few', 'freshness', 5.0, 3)"
    )

    merge_duplicates(con)

    assert con.execute("SELECT count(*) FROM pac_scores WHERE place_id = 'p_few'").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM pac_place_aspects WHERE place_id = 'p_few'").fetchone()[0] == 0


def test_dry_run_reports_without_changing_anything(con):
    _insert_place(con, "p_few", "Ancien Nom", "1 Rue X, 75001 Paris, France")
    _insert_place(con, "p_many", "Nom Actuel", "1 Rue X, 75001 Paris, France")
    _insert_review(con, "r1", "p_few")
    _insert_review(con, "r2", "p_many")
    _insert_review(con, "r3", "p_many")

    result = merge_duplicates(con, dry_run=True)

    assert result["groups_merged"] == 1
    assert result["places_removed"] == 1
    assert result["reviews_reassigned"] == 1
    assert con.execute("SELECT count(*) FROM places").fetchone()[0] == 2
    assert con.execute("SELECT place_id FROM reviews WHERE review_id = 'r1'").fetchone()[0] == "p_few"


def test_no_duplicates_is_a_no_op(con):
    _insert_place(con, "p1", "Solo", "1 Rue X, 75001 Paris, France")

    result = merge_duplicates(con)

    assert result == {"groups_merged": 0, "places_removed": 0, "reviews_reassigned": 0, "merges": []}
