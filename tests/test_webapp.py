"""Tests des fonctions pures de l'app Streamlit (cf. plan, section
Vérification, point 2) -- pas de test d'UI, juste la logique de couleur et
d'extraction d'arrondissement qui alimentent la carte et le tableau."""

from pac.webapp.theme import (
    confidence_badge,
    confidence_pill_html,
    extract_arrondissement,
    format_percent,
    format_stars,
    score_to_color,
)


def test_score_to_color_bounds():
    assert score_to_color(None) == "#9AA5B1"  # gris, pas de score
    assert score_to_color(0) == "#D64545"      # rouge pur
    assert score_to_color(10) == "#2E7D32"     # vert foncé pur
    assert score_to_color(7.5) == "#8BC34A"    # point de contrôle exact


def test_score_to_color_is_monotonic_from_red_to_green():
    # La composante rouge doit globalement décroître et la verte croître
    # en allant de 0 à 10 -- pas de vérification exacte pixel par pixel,
    # juste que l'échelle va bien dans le sens attendu.
    def to_rgb(hexcolor):
        h = hexcolor.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))

    low = to_rgb(score_to_color(1))
    mid = to_rgb(score_to_color(5))
    high = to_rgb(score_to_color(9.5))
    assert low[0] > high[0]  # moins rouge en montant
    assert low[1] < high[1]  # plus vert en montant


def test_score_to_color_clamps_out_of_range():
    assert score_to_color(-5) == score_to_color(0)
    assert score_to_color(15) == score_to_color(10)


def test_extract_arrondissement_valid():
    assert extract_arrondissement("34 Rue Yves Toudic, 75010 Paris, France") == 10
    assert extract_arrondissement("1 Place Vendôme, 75001 Paris") == 1
    assert extract_arrondissement("Quelque chose, 75020 Paris") == 20


def test_extract_arrondissement_missing_or_invalid():
    assert extract_arrondissement(None) is None
    assert extract_arrondissement("") is None
    assert extract_arrondissement("Adresse sans code postal") is None
    assert extract_arrondissement("75099 hors plage") is None  # > 20, invalide


def test_confidence_badge_known_and_unknown():
    label, color = confidence_badge("high")
    assert label == "Reliable"
    label, color = confidence_badge(None)
    assert label == "Not enough reviews"
    label, color = confidence_badge("valeur-inattendue")
    assert label == "Unknown"


def test_format_stars():
    assert format_stars(None) == "—"
    assert format_stars(4.3) == "★★★★☆ 4.3"
    assert format_stars(5.0) == "★★★★★ 5.0"
    assert format_stars(0.4) == "☆☆☆☆☆ 0.4"


def test_format_percent():
    assert format_percent(None) == "—"
    assert format_percent(float("nan")) == "—"
    assert format_percent(0.834) == "83%"
    assert format_percent(0) == "0%"


def test_confidence_pill_html_handles_missing_count():
    # NaN/None n_relevant (valeur SQL NULL après LEFT JOIN) ne doit jamais
    # faire planter le rendu -- retombe sur 0, comme n_relevant ailleurs.
    html = confidence_pill_html(None, float("nan"))
    assert "0 pain au chocolat reviews" in html
    assert "Not enough reviews" in html
