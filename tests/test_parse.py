"""Test de non-régression sur parse.py, contre une réponse réelle capturée
(tests/fixtures/listugcposts_page1_real.txt). Si Google change son format,
c'est ICI que le test doit casser -- et c'est là qu'il faudra regarder
(cf. protocol.py, parse.py)."""

import json
from pathlib import Path

from pac.parse import parse_review_entry, parse_ugc_posts_payload
from pac.protocol import decode_batchexecute

FIXTURE = Path(__file__).parent / "fixtures" / "listugcposts_page1_real.txt"
SHORT_REVIEW_FIXTURE = Path(__file__).parent / "fixtures" / "short_review_entry.json"


def _load_payload():
    raw = FIXTURE.read_text()
    body = raw.split("\n\n", 1)[1]
    results = decode_batchexecute(body)
    assert results, "aucun résultat RPC décodé depuis la fixture"
    rpc_id, payload = results[0]
    assert rpc_id == "/MapsUgcPostService.ListUgcPosts"
    return payload


def test_decode_and_parse_real_fixture():
    payload = _load_payload()
    reviews, next_cursor = parse_ugc_posts_payload(payload)

    assert next_cursor  # il y a bien une page suivante sur ce lieu très commenté
    assert len(reviews) >= 5

    named = [r for r in reviews if r.author_name]
    texted = [r for r in reviews if r.text]
    assert len(named) == len(reviews), "tous les avis de cette page ont un auteur"
    assert len(texted) >= 5, "la plupart des avis de cette page ont du texte"

    pierre_albert = next(r for r in reviews if r.author_name == "Pierre-Albert Garcias")
    assert "viennoiseries" in pierre_albert.text
    assert pierre_albert.relative_time_text == "il y a 3\xa0mois"
    assert pierre_albert.published_at is not None
    assert pierre_albert.rating == 3
    assert pierre_albert.author_review_count == 19

    rated = [r for r in reviews if r.rating is not None]
    assert len(rated) == len(reviews), "chaque avis de cette page a une note calibrée"
    assert all(1 <= r.rating <= 5 for r in rated)


def test_no_duplicate_review_ids():
    payload = _load_payload()
    reviews, _ = parse_ugc_posts_payload(payload)
    ids = [r.review_id for r in reviews]
    assert len(ids) == len(set(ids))


def test_short_review_text_is_recovered():
    """Non-régression sur le bug diagnostiqué en direct : un ancien seuil
    `len(texte) > 15` excluait à tort les avis courts ("Très bon !", 10
    caractères) -- cf. plan "Améliorer la précision du score pain au
    chocolat". La plage [0, n] de surlignage est un extrait tronqué (n peut
    être < len(texte) pour un avis long), jamais une longueur totale
    garantie -- ce fixture capture le cas court, celui de
    listugcposts_page1_real.txt couvre déjà les cas longs/tronqués."""
    entry = json.loads(SHORT_REVIEW_FIXTURE.read_text())
    parsed = parse_review_entry(entry)
    assert parsed is not None
    assert parsed.text == "Très bon !"
    assert parsed.author_name == "Raph"
