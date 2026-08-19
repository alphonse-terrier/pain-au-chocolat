"""Construction de la carte Folium : un marqueur par lieu, coloré selon le
score pain-au-chocolat, avec un popup HTML qui EST le panneau de détail
(cf. plan -- pas de synchronisation clic/état séparée)."""

import html
import math

import folium
import pandas as pd
from folium.plugins import MarkerCluster

from pac.webapp.theme import (
    INSUFFICIENT_DATA_COLOR,
    MAPS_LINK_LABEL,
    PARIS_CENTER,
    confidence_pill_html,
    format_stars,
    mention_card_html,
    score_to_color,
)

# Rayon (en degrés) du petit cercle sur lequel on écarte les lieux qui
# partagent des coordonnées GPS strictement identiques -- en pratique des
# dizaines de boulangeries au même point (immeuble/centre commercial avec
# plusieurs enseignes géocodées pareil). Sans cet écart, les CircleMarker se
# superposent pixel pour pixel à tout niveau de zoom et seul le dernier
# dessiné reçoit les clics : les autres sont invisibles/inaccessibles.
# ~0.00004° ≈ 4 m -- fond dans un même cluster une fois dézoomé, mais assez
# pour distinguer chaque marqueur une fois zoomé sur l'adresse.
_JITTER_DEGREES = 0.00004


def spread_duplicate_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute des colonnes map_lat/map_lon = lat/lon légèrement écartées pour
    les lieux qui partagent exactement les mêmes coordonnées, réparties en
    cercle autour du point réel. Écart déterministe (fonction de la position
    dans le groupe, pas aléatoire) pour que la carte soit stable entre deux
    rendus."""
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


def _safe(value, default=""):
    """None ET NaN pandas (une valeur SQL NULL après LEFT JOIN, dans une
    colonne numérique ou objet) doivent toutes les deux retomber sur
    `default` -- `value or default` ne suffit pas : NaN est "truthy" en
    Python, contrairement à None (bug réel rencontré et corrigé ici)."""
    return default if value is None or (isinstance(value, float) and value != value) else value


def _popup_html(row: pd.Series, excerpts: pd.DataFrame) -> str:
    name = html.escape(str(_safe(row["name"], "Bakery")))
    address = html.escape(str(_safe(row["formatted_address"])))
    maps_url = _safe(row.get("google_maps_uri"))

    if pd.notna(row.get("score_10")):
        score_html = (
            f'<span style="font-size:22px;font-weight:700;'
            f'color:{score_to_color(row["score_10"])}">{row["score_10"]:.1f}/10</span>'
        )
    else:
        score_html = f'<span style="font-size:14px;color:{INSUFFICIENT_DATA_COLOR}">no score yet</span>'

    n_relevant = int(row["n_relevant"]) if pd.notna(row.get("n_relevant")) else 0

    # Le popup reste un simple teaser (1 extrait) : la liste complète et
    # défilable de tous les avis vit dans le panneau Streamlit à côté de la
    # carte (cf. app.py), pas ici -- un popup Leaflet statique embarqué pour
    # chacun des ~1700 lieux ne peut pas rester léger s'il contient déjà
    # toutes les mentions (certains lieux en ont plus de 90).
    if not excerpts.empty:
        best = excerpts.iloc[0]
        excerpt_html = mention_card_html(best["sentiment"], best["text"], best["author_name"])
        if n_relevant > 1:
            excerpt_html += (
                f'<div style="font-size:11px;color:{INSUFFICIENT_DATA_COLOR};margin-top:2px;">'
                f"+ {n_relevant - 1} more reviews in the panel to the right of the map."
                f"</div>"
            )
    else:
        excerpt_html = (
            f'<div style="font-size:12px;color:{INSUFFICIENT_DATA_COLOR};margin-top:6px;">'
            "No review mentions pain au chocolat for this place yet.</div>"
        )
    link = (
        f'<a href="{html.escape(maps_url)}" target="_blank" '
        f'style="font-size:12px;color:#4A6FE3;text-decoration:none;">{MAPS_LINK_LABEL}</a>'
        if maps_url
        else ""
    )

    return f"""
    <div style="font-family:-apple-system,Helvetica,Arial,sans-serif;width:260px;">
      <div style="font-size:15px;font-weight:700;color:#1a1a1a;margin-bottom:2px;">{name}</div>
      <div style="font-size:11px;color:#777;margin-bottom:8px;">{address}</div>
      <div style="display:flex;align-items:center;justify-content:space-between;
                  padding:8px;background:#F7F7F9;border-radius:8px;margin-bottom:6px;">
        <div style="font-size:13px;color:#555;">Google: {format_stars(row.get("google_rating"))}</div>
        <div>{score_html}</div>
      </div>
      {confidence_pill_html(row.get("confidence"), n_relevant, extra_style="display:inline-block;margin-bottom:4px;")}
      {excerpt_html}
      <div style="margin-top:8px;">{link}</div>
    </div>
    """


def build_map(
    df: pd.DataFrame, excerpts_by_place: dict[str, pd.DataFrame], **map_kwargs
) -> folium.Map:
    """df : sortie filtrée de data.load_places_with_scores(), déjà passée
    par spread_duplicate_coordinates (l'appelant en a besoin de toute façon
    pour associer un clic sur la carte à un place_id -- pas de raison de
    jitterer deux fois).
    excerpts_by_place : place_id -> DataFrame (déjà chargé par l'appelant,
    pour éviter une requête DuckDB par marqueur pendant le rendu).
    map_kwargs : center=(lat, lon), zoom=... pour recentrer la carte (ex.
    sélection "Aller à" dans la barre latérale)."""
    location = map_kwargs.get("center", PARIS_CENTER)
    zoom = map_kwargs.get("zoom", 12)
    fmap = folium.Map(location=location, zoom_start=zoom, tiles="CartoDB positron")
    cluster = MarkerCluster(
        name="Bakeries",
        options={
            # Distance par défaut (1x le rayon de l'icône) souvent trop
            # serrée quand plusieurs boulangeries partagent un point
            # (immeuble/centre commercial) : les segments du "spider" se
            # touchent encore et les marqueurs restent difficiles à
            # distinguer/cliquer une fois éclatés. x3 les écarte nettement.
            "spiderfyDistanceMultiplier": 3,
        },
    ).add_to(fmap)

    for _, row in df.iterrows():
        score = row["score_10"] if pd.notna(row["score_10"]) else None
        color = score_to_color(score)
        excerpts = excerpts_by_place.get(row["place_id"], pd.DataFrame())

        folium.CircleMarker(
            location=(row["map_lat"], row["map_lon"]),
            radius=7,
            color="#ffffff",
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            tooltip=f"{row['name']} — {score:.1f}/10" if score is not None else row["name"],
            popup=folium.Popup(_popup_html(row, excerpts), max_width=300),
        ).add_to(cluster)

    return fmap
