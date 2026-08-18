"""Point d'entrée Streamlit : `uv run streamlit run app.py` (cf. plan
"App Streamlit — carte des boulangeries de Paris").

Ce fichier reste un orchestrateur : configuration de page, filtres, mise en
page. Toute la logique de requête vit dans src/pac/webapp/data.py, le rendu
de la carte dans src/pac/webapp/map_view.py, et la palette/mise en forme
dans src/pac/webapp/theme.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from pac.webapp.data import (
    DatabaseUnavailable,
    load_kpis,
    load_places_with_scores,
    load_review_excerpts_by_place,
)
from pac.webapp.map_view import build_map
from pac.webapp.theme import score_to_color

st.set_page_config(
    page_title="Pain au Chocolat de Paris",
    page_icon="🥐",
    layout="wide",
)

st.markdown(
    """
    <style>
    .kpi-card {
        background: #F7F7F9; border-radius: 12px; padding: 16px 20px;
        text-align: center; border: 1px solid #ECECEF;
    }
    .kpi-value { font-size: 28px; font-weight: 700; color: #1a1a1a; }
    .kpi-label { font-size: 12px; color: #777; text-transform: uppercase;
                 letter-spacing: 0.04em; margin-top: 2px; }
    .legend-dot { display:inline-block; width:10px; height:10px; border-radius:50%;
                  margin-right:6px; vertical-align:middle; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _kpi_card(value: str, label: str) -> str:
    return f'<div class="kpi-card"><div class="kpi-value">{value}</div><div class="kpi-label">{label}</div></div>'


st.title("🥐 Pain au Chocolat de Paris")
st.caption(
    "Où trouver le meilleur pain au chocolat de Paris — score calculé à partir des avis "
    "Google qui en parlent spécifiquement, pas de la note globale de la boulangerie."
)

try:
    kpis = load_kpis()
    places = load_places_with_scores()
except DatabaseUnavailable as exc:
    st.warning(f"⏳ {exc}")
    st.stop()

if places.empty:
    st.info("Aucune boulangerie chargée encore. Lance `pac discover` puis `pac reviews` et `pac load`.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.markdown(_kpi_card(f"{kpis['n_places']:,}".replace(",", " "), "Boulangeries chargées"), unsafe_allow_html=True)
avg_score_str = f"{kpis['avg_score']:.1f}/10" if kpis["avg_score"] else "—"
col2.markdown(_kpi_card(avg_score_str, "Score moyen pondéré"), unsafe_allow_html=True)
col3.markdown(_kpi_card(f"{kpis['coverage_pct']:.0f}%", "Lieux avec un score"), unsafe_allow_html=True)
col4.markdown(_kpi_card(f"{kpis['n_reviews']:,}".replace(",", " "), "Avis analysés"), unsafe_allow_html=True)

st.write("")

# --- Barre latérale : filtres ------------------------------------------------
with st.sidebar:
    st.header("Filtres")

    search = st.text_input("🔍 Rechercher par nom", "")

    arrondissements = sorted(a for a in places["arrondissement"].dropna().unique())
    selected_arr = st.multiselect("Arrondissement", arrondissements, default=[])

    score_range = st.slider("Score pain-au-chocolat", 0.0, 10.0, (0.0, 10.0), step=0.5)
    include_unscored = st.checkbox("Inclure les lieux sans score encore", value=True)

    min_google_rating = st.slider("Note Google minimale", 0.0, 5.0, 0.0, step=0.5)

    st.divider()
    st.subheader("Aller à")
    goto_options = [""] + sorted(places["name"].dropna().unique().tolist())
    goto = st.selectbox("Centrer la carte sur…", goto_options, index=0)

    st.divider()
    if st.button("🔄 Actualiser les données"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Dernier avis récolté : {kpis['last_review_at']}")

# --- Application des filtres -------------------------------------------------
filtered = places.copy()
if search:
    filtered = filtered[filtered["name"].str.contains(search, case=False, na=False)]
if selected_arr:
    filtered = filtered[filtered["arrondissement"].isin(selected_arr)]
filtered = filtered[filtered["google_rating"].fillna(0) >= min_google_rating]

has_score = filtered["score_10"].notna()
in_range = filtered["score_10"].between(score_range[0], score_range[1])
filtered = filtered[(has_score & in_range) | (~has_score & include_unscored)]

st.caption(f"{len(filtered)} boulangerie(s) affichée(s) sur {len(places)}.")

# --- Onglets ------------------------------------------------------------------
tab_map, tab_ranking, tab_about = st.tabs(["🗺️ Carte", "🏆 Classement", "ℹ️ Méthodologie"])

with tab_map:
    legend_cols = st.columns(6)
    for col, (label, color) in zip(
        legend_cols,
        [
            ("< 4", score_to_color(2)),
            ("4 – 6", score_to_color(5)),
            ("6 – 7,5", score_to_color(6.5)),
            ("7,5 – 9", score_to_color(8)),
            ("9 – 10", score_to_color(9.5)),
            ("Pas encore de score", score_to_color(None)),
        ],
    ):
        col.markdown(f'<span class="legend-dot" style="background:{color}"></span>{label}', unsafe_allow_html=True)

    excerpts_by_place = load_review_excerpts_by_place()

    map_kwargs = {}
    if goto:
        row = places.loc[places["name"] == goto].iloc[0]
        map_kwargs = {"center": (row["lat"], row["lon"]), "zoom": 16}

    fmap = build_map(filtered, excerpts_by_place)
    st_folium(fmap, use_container_width=True, height=620, returned_objects=[], **map_kwargs)

with tab_ranking:
    ranking = filtered.dropna(subset=["score_10"]).sort_values("score_10", ascending=False)
    st.dataframe(
        ranking[["name", "formatted_address", "arrondissement", "google_rating", "score_10", "confidence", "n_relevant"]],
        column_config={
            "name": "Boulangerie",
            "formatted_address": "Adresse",
            "arrondissement": st.column_config.NumberColumn("Arr.", format="%d"),
            "google_rating": st.column_config.NumberColumn("Note Google", format="%.1f ★"),
            "score_10": st.column_config.ProgressColumn("Score PAC", min_value=0, max_value=10, format="%.1f"),
            "confidence": "Confiance",
            "n_relevant": "Avis pertinents",
        },
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "⬇️ Exporter en CSV",
        ranking.to_csv(index=False).encode("utf-8"),
        file_name="classement_pain_au_chocolat.csv",
        mime="text/csv",
    )

with tab_about:
    st.markdown(
        """
        ### Comment le score est calculé

        1. **Détection** — les avis Google mentionnant explicitement
           *"pain au chocolat"*, *"chocolatine"* (et variantes) sont
           repérés par mot-clé.
        2. **Classification** — un modèle de langage lit chaque mention et
           juge si elle parle vraiment du **goût/qualité** de la pâtisserie,
           ou seulement de son **prix** (dans ce cas elle est exclue : un
           avis 1★ qui se plaint du prix d'une chocolatine par ailleurs
           décrite comme excellente ne doit pas faire baisser le score).
        3. **Pondération** — chaque mention retenue est pondérée par la
           crédibilité du contributeur (nombre d'avis postés, plafonné) et
           sa fraîcheur (les avis récents comptent plus).
        4. **Agrégation** — le score /10 d'un lieu est la moyenne pondérée
           de ses mentions, légèrement lissée vers la moyenne parisienne
           quand un lieu n'a qu'une ou deux mentions — **jamais** vers la
           note Google globale du lieu : une boulangerie adorée peut très
           bien avoir un mauvais pain au chocolat, et inversement.

        Un lieu sans mention pain-au-chocolat dans ses avis n'a **pas** de
        score par défaut — il apparaît en gris sur la carte plutôt que de
        se voir attribuer une valeur inventée.
        """
    )
