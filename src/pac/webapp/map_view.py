"""Construction de la carte Folium : un marqueur par lieu, coloré selon le
score pain-au-chocolat, avec un popup HTML qui EST le panneau de détail
(cf. plan -- pas de synchronisation clic/état séparée)."""

import html

import folium
import pandas as pd
from folium.plugins import MarkerCluster

from pac.webapp.theme import PARIS_CENTER, confidence_badge, format_stars, score_to_color


def _safe(value, default=""):
    """None ET NaN pandas (une valeur SQL NULL après LEFT JOIN, dans une
    colonne numérique ou objet) doivent toutes les deux retomber sur
    `default` -- `value or default` ne suffit pas : NaN est "truthy" en
    Python, contrairement à None (bug réel rencontré et corrigé ici)."""
    return default if value is None or (isinstance(value, float) and value != value) else value


def _popup_html(row: pd.Series, excerpts: pd.DataFrame) -> str:
    name = html.escape(str(_safe(row["name"], "Boulangerie")))
    address = html.escape(str(_safe(row["formatted_address"])))
    maps_url = _safe(row.get("google_maps_uri"))
    conf_label, conf_color = confidence_badge(row.get("confidence"))

    if pd.notna(row.get("score_10")):
        score_html = (
            f'<span style="font-size:22px;font-weight:700;'
            f'color:{score_to_color(row["score_10"])}">{row["score_10"]:.1f}/10</span>'
        )
    else:
        score_html = '<span style="font-size:14px;color:#9AA5B1">pas encore de score</span>'

    excerpt_html = ""
    if not excerpts.empty:
        rows_html = []
        for _, ex in excerpts.iterrows():
            tone = "#2E7D32" if ex["sentiment"] >= 0 else "#D64545"
            text = html.escape(str(_safe(ex["text"]))[:220])
            author = html.escape(str(_safe(ex["author_name"], "Anonyme")))
            rows_html.append(
                f'<div style="border-left:3px solid {tone};padding:4px 8px;margin:6px 0;'
                f'font-size:12px;color:#333;font-style:italic;">« {text}»'
                f'<div style="color:#888;font-size:11px;margin-top:2px;">'
                f"— {author}</div></div>"
            )
        excerpt_html = "".join(rows_html)
    else:
        excerpt_html = (
            '<div style="font-size:12px;color:#9AA5B1;margin-top:6px;">'
            "Aucun avis ne mentionne encore le pain au chocolat pour ce lieu.</div>"
        )

    n_relevant = int(row["n_relevant"]) if pd.notna(row.get("n_relevant")) else 0
    link = (
        f'<a href="{html.escape(maps_url)}" target="_blank" '
        f'style="font-size:12px;color:#4A6FE3;text-decoration:none;">Voir sur Google Maps →</a>'
        if maps_url
        else ""
    )

    return f"""
    <div style="font-family:-apple-system,Helvetica,Arial,sans-serif;width:260px;">
      <div style="font-size:15px;font-weight:700;color:#1a1a1a;margin-bottom:2px;">{name}</div>
      <div style="font-size:11px;color:#777;margin-bottom:8px;">{address}</div>
      <div style="display:flex;align-items:center;justify-content:space-between;
                  padding:8px;background:#F7F7F9;border-radius:8px;margin-bottom:6px;">
        <div style="font-size:13px;color:#555;">Google&nbsp;: {format_stars(row.get("google_rating"))}</div>
        <div>{score_html}</div>
      </div>
      <div style="display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;
                  background:{conf_color}20;color:{conf_color};font-weight:600;margin-bottom:4px;">
        {conf_label} · {n_relevant} avis pain-au-chocolat
      </div>
      {excerpt_html}
      <div style="margin-top:8px;">{link}</div>
    </div>
    """


def build_map(df: pd.DataFrame, excerpts_by_place: dict[str, pd.DataFrame]) -> folium.Map:
    """df : sortie filtrée de data.load_places_with_scores().
    excerpts_by_place : place_id -> DataFrame (déjà chargé par l'appelant,
    pour éviter une requête DuckDB par marqueur pendant le rendu)."""
    fmap = folium.Map(location=PARIS_CENTER, zoom_start=12, tiles="CartoDB positron")
    cluster = MarkerCluster(name="Boulangeries").add_to(fmap)

    for _, row in df.iterrows():
        score = row["score_10"] if pd.notna(row["score_10"]) else None
        color = score_to_color(score)
        excerpts = excerpts_by_place.get(row["place_id"], pd.DataFrame())

        folium.CircleMarker(
            location=(row["lat"], row["lon"]),
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
