"""Palette et petites fonctions de mise en forme partagées entre la carte,
le tableau de classement et les cartes KPI -- un seul endroit pour la
cohérence visuelle de l'app (cf. plan)."""

import html
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
    "high": ("Reliable", "#2E7D32"),
    "medium": ("Fair", "#E8974E"),
    "low": ("Limited data", "#D6A245"),
    "insufficient_data": ("Not enough reviews", "#9AA5B1"),
}

MAPS_LINK_LABEL = "View on Google Maps →"

PARIS_CENTER = (48.8566, 2.3522)

_ARRONDISSEMENT_RE = re.compile(r"\b750(\d{2})\b")
# Le 16e arrondissement a un code postal alternatif "75116" (les deux sont
# utilisés dans la vraie vie/par Google), qui ne matche pas 750XX -- seul
# cas de ce genre à Paris.
_ARRONDISSEMENT_16_ALT_RE = re.compile(r"\b75116\b")


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
    return CONFIDENCE_LABELS.get(confidence or "insufficient_data", ("Unknown", "#9AA5B1"))


def extract_arrondissement(formatted_address: str | None) -> int | None:
    """Extrait l'arrondissement (1-20) depuis un code postal 750XX présent
    dans l'adresse formatée. None si absent ou hors Paris intra-muros."""
    if not formatted_address:
        return None
    if _ARRONDISSEMENT_16_ALT_RE.search(formatted_address):
        return 16
    m = _ARRONDISSEMENT_RE.search(formatted_address)
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 20 else None


def mention_card_html(
    sentiment: float,
    text: str | None,
    author: str | None,
    rating: float | None = None,
    relative_time: str | None = None,
    max_chars: int | None = 220,
) -> str:
    """Une mention pain-au-chocolat retenue (avis + jugement du modèle) ->
    petite carte HTML, colorée selon le sentiment. Partagée entre le popup
    de la carte (aperçu tronqué) et la liste défilante "tous les avis"
    (texte complet, max_chars=None)."""
    tone = "#{:02X}{:02X}{:02X}".format(*(_SCORE_COLOR_STOPS[-1][1] if sentiment >= 0 else _SCORE_COLOR_STOPS[0][1]))
    body = str(text or "")
    if max_chars is not None:
        body = body[:max_chars]
    safe_text = html.escape(body)
    safe_author = html.escape(str(author or "Anonymous"))
    meta_bits = []
    if rating is not None and rating == rating:  # exclut NaN
        meta_bits.append(format_stars(rating))
    if relative_time:
        meta_bits.append(html.escape(str(relative_time)))
    meta = " · ".join(meta_bits)
    meta_html = f'<div style="color:#888;font-size:11px;margin-top:2px;">{meta}</div>' if meta else ""
    return (
        f'<div style="border-left:3px solid {tone};padding:4px 8px;margin:6px 0;'
        f'font-size:12px;color:#333;font-style:italic;">"{safe_text}"'
        f'<div style="color:#888;font-size:11px;margin-top:2px;">— {safe_author}</div>'
        f"{meta_html}</div>"
    )


def format_percent(value: float | None) -> str:
    """Fraction 0..1 -> pourcentage entier affichable ("83%"). None ET NaN
    (valeur SQL NULL après LEFT JOIN) -> "—", même garde que format_stars
    (`value != value` n'est vrai que pour NaN)."""
    if value is None or value != value:
        return "—"
    return f"{value:.0%}"


def confidence_pill_html(confidence: str | None, n_relevant, *, extra_style: str = "") -> str:
    """Le badge de confiance coloré ("Reliable · 12 pain au chocolat
    reviews") -- partagé entre le panneau de détail de la carte, l'onglet
    "Near an address" et le popup Leaflet (qui n'a accès à aucune classe
    CSS de la page hôte, d'où `extra_style` en chaîne plutôt qu'une classe)."""
    label, color = confidence_badge(confidence)
    n = 0 if n_relevant is None or n_relevant != n_relevant else int(n_relevant)
    return (
        f'<span style="font-size:11px;padding:2px 8px;border-radius:10px;'
        f'background:{color}20;color:{color};font-weight:600;{extra_style}">'
        f"{label} · {n} pain au chocolat reviews</span>"
    )


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
