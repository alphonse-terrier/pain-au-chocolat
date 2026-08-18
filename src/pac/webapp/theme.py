"""Palette et petites fonctions de mise en forme partagées entre la carte,
le tableau de classement et les cartes KPI -- un seul endroit pour la
cohérence visuelle de l'app (cf. plan)."""

import re

# Points de contrôle de l'échelle de couleur du score pain-au-chocolat
# (rouge -> orange -> jaune -> vert clair -> vert foncé), interpolés
# linéairement entre les points plutôt que par paliers bruts.
_SCORE_COLOR_STOPS = [
    (0.0, (0xD6, 0x45, 0x45)),   # rouge
    (4.0, (0xE8, 0x97, 0x4E)),   # orange
    (6.0, (0xE8, 0xC5, 0x47)),   # jaune
    (7.5, (0x8B, 0xC3, 0x4A)),   # vert clair
    (10.0, (0x2E, 0x7D, 0x32)),  # vert foncé
]
INSUFFICIENT_DATA_COLOR = "#9AA5B1"  # gris -- lieu sans mention pain-au-chocolat

CONFIDENCE_LABELS = {
    "high": ("Fiable", "#2E7D32"),
    "medium": ("Correct", "#E8974E"),
    "low": ("Peu de données", "#D6A245"),
    "insufficient_data": ("Pas assez d'avis", "#9AA5B1"),
}

PARIS_CENTER = (48.8566, 2.3522)

_ARRONDISSEMENT_RE = re.compile(r"\b750(\d{2})\b")


def score_to_color(score: float | None) -> str:
    """Note /10 -> couleur hex sur l'échelle rouge->vert, interpolée
    linéairement entre les points de contrôle. None (pas de score calculé,
    cf. plan -- pas de valeur inventée) -> gris."""
    if score is None:
        return INSUFFICIENT_DATA_COLOR

    score = max(0.0, min(10.0, score))
    for (s0, c0), (s1, c1) in zip(_SCORE_COLOR_STOPS, _SCORE_COLOR_STOPS[1:]):
        if s0 <= score <= s1:
            t = 0.0 if s1 == s0 else (score - s0) / (s1 - s0)
            rgb = tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
            return "#{:02X}{:02X}{:02X}".format(*rgb)
    # score == 10.0 exactement tombe dans la dernière borne ci-dessus ;
    # ce repli ne devrait être atteint qu'en cas d'entrée hors bornes.
    return "#{:02X}{:02X}{:02X}".format(*_SCORE_COLOR_STOPS[-1][1])


def confidence_badge(confidence: str | None) -> tuple[str, str]:
    """confidence -> (libellé affichable, couleur). Repli neutre si une
    valeur inattendue apparaît (le schéma évolue peut-être un jour)."""
    return CONFIDENCE_LABELS.get(confidence or "insufficient_data", ("Inconnu", "#9AA5B1"))


def extract_arrondissement(formatted_address: str | None) -> int | None:
    """Extrait l'arrondissement (1-20) depuis un code postal 750XX présent
    dans l'adresse formatée. None si absent ou hors Paris intra-muros."""
    if not formatted_address:
        return None
    m = _ARRONDISSEMENT_RE.search(formatted_address)
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 20 else None


def format_stars(rating: float | None) -> str:
    """Note Google (0-5) -> chaîne d'étoiles unicode + valeur numérique.

    Accepte aussi bien None que NaN (pandas représente ainsi une valeur SQL
    NULL après un LEFT JOIN dans une colonne numérique -- `rating is None`
    seul ne suffit pas, `rating != rating` est vrai uniquement pour NaN)."""
    if rating is None or rating != rating:
        return "—"
    filled = int(round(rating))
    filled = max(0, min(5, filled))
    return "★" * filled + "☆" * (5 - filled) + f" {rating:.1f}"
