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
    load_mentions_for_place,
    load_place_aspects,
    load_kpis,
    load_places_with_scores,
)
from pac.webapp.geocode import GeocodeError, geocode_address, haversine_m
from pac.webapp.map_view import build_map, build_marker_specs, spread_duplicate_coordinates
from pac.webapp.theme import (
    MAPS_LINK_LABEL,
    aspect_bar_html,
    confidence_badge,
    confidence_pill_html,
    format_percent,
    mention_card_html,
)

st.set_page_config(
    page_title="The best pain au chocolat in Paris",
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

    /* Rétréci juste la valeur des cartes KPI sur petit écran -- PAS de
       flex-direction:column forcé sur les st.columns ici : ça casse le
       rendu de la carte Leaflet (essayé, la carte redevient vide sur
       mobile -- Leaflet calcule la taille de son conteneur une seule fois
       au premier rendu, et un changement de largeur imposé par CSS APRÈS
       coup le laisse avec un viewport figé sur l'ancienne taille, cf. plan
       performance). */
    @media (max-width: 768px) {
        .kpi-value { font-size: 22px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _kpi_card(value: str, label: str) -> str:
    return f'<div class="kpi-card"><div class="kpi-value">{value}</div><div class="kpi-label">{label}</div></div>'


def _render_place_summary(row: pd.Series, *, show_score: bool) -> None:
    """Métriques + badge de confiance + lien Google Maps pour un lieu --
    partagé entre le panneau de détail de la carte (show_score=True, 3
    métriques) et les résultats de l'onglet "Near an address"
    (show_score=False, 2 métriques : le score est déjà dans l'en-tête de
    chaque expander, pas la peine de le répéter)."""
    google_rating_str = (
        f"{row['google_rating']:.1f}/5" if pd.notna(row.get("google_rating")) else "—"
    )
    if show_score:
        b1, b2, b3 = st.columns(3)
        score_str = f"{row['score_10']:.1f}/10" if pd.notna(row.get("score_10")) else "—"
        b1.metric("Score", score_str)
        b2.metric("Positive reviews", format_percent(row.get("positive_ratio")))
        b3.metric("Google rating", google_rating_str)
    else:
        b1, b2 = st.columns(2)
        b1.metric("Positive reviews", format_percent(row.get("positive_ratio")))
        b2.metric("Google rating", google_rating_str)
    st.markdown(
        confidence_pill_html(row.get("confidence"), row.get("n_relevant")), unsafe_allow_html=True
    )
    aspects = load_place_aspects(row["place_id"])
    if not aspects.empty:
        st.markdown(
            "".join(
                aspect_bar_html(r.aspect, r.score_10, r.n_mentions) for r in aspects.itertuples()
            ),
            unsafe_allow_html=True,
        )
    if row.get("google_maps_uri"):
        st.markdown(f"[{MAPS_LINK_LABEL}]({row['google_maps_uri']})")


@st.cache_data(ttl=60, show_spinner=False)
def _build_marker_specs_cached(jittered: pd.DataFrame) -> list[dict]:
    """La partie coûteuse par marqueur (couleur, tooltip, HTML du popup --
    pour ~1700 lieux) ne doit pas être recalculée à chaque rerun, notamment
    sur un simple clic de marqueur qui ne change que le panneau de droite.
    On met en cache ces specs (dicts/str, cache_data classique) plutôt que
    l'objet folium.Map lui-même : le cacher directement (essayé en
    cache_resource) a cassé la carte en prod -- un folium.Map est mutable,
    et le réutiliser tel quel à travers plusieurs reruns/sessions ne
    correspond pas à la façon dont folium/streamlit-folium sont conçus pour
    être rendus (cf. plan performance). build_map() reste appelé sans cache
    à chaque rerun, mais reconstruire l'objet folium à partir de ces specs
    déjà calculées est bon marché."""
    return build_marker_specs(jittered)


@st.cache_data(ttl=86400, show_spinner=False)
def _geocode_address_cached(address: str) -> dict:
    """Une adresse ne bouge pas -- pas de raison de retaper la même requête
    à l'API Adresse à chaque recherche identique. TTL long (24h) plutôt que
    CACHE_TTL_SECONDS (60s, pensé pour les données du pipeline qui changent
    en tâche de fond) puisque rien ici ne devient jamais périmé."""
    return geocode_address(address)


st.title("🥐 The best pain au chocolat in Paris")
st.caption(
    "Where to find the best pain au chocolat in Paris — scored from the Google "
    "reviews that actually talk about it, not from the bakery's overall rating."
)

try:
    kpis = load_kpis()
    places = load_places_with_scores()
except DatabaseUnavailable as exc:
    st.warning(f"⏳ {exc}")
    st.stop()

if places.empty:
    st.info("No bakeries loaded yet. Run `pac discover`, then `pac reviews` and `pac load`.")
    st.stop()

if "selected_place_id" not in st.session_state:
    st.session_state.selected_place_id = None
if "_last_map_click" not in st.session_state:
    st.session_state._last_map_click = None


def _select_place(place_id: str | None) -> None:
    st.session_state.selected_place_id = place_id


# --- Barre latérale : filtres ------------------------------------------------
with st.sidebar:
    st.header("Filters")

    search = st.text_input("🔍 Search by name", "")

    arrondissements = sorted(a for a in places["arrondissement"].dropna().unique())
    selected_arr = st.multiselect(
        "Arrondissement", arrondissements, default=[], help="Paris administrative district (1-20)"
    )

    score_range = st.slider("Score", 0.0, 10.0, (0.0, 10.0), step=0.5)
    include_unscored = st.checkbox("Include places without a score yet", value=True)

    min_google_rating = st.slider("Minimum Google rating", 0.0, 5.0, 0.0, step=0.5)
    min_n_relevant = st.slider(
        "Minimum pain-au-chocolat reviews", 0, 100, 0,
        help="Places with fewer than this many retained pain-au-chocolat/viennoiserie "
             "reviews are hidden -- a quick way to focus on well-established scores.",
    )

    # --- Application des filtres --------------------------------------------
    filtered = places.copy()
    if search:
        filtered = filtered[filtered["name"].str.contains(search, case=False, na=False)]
    if selected_arr:
        filtered = filtered[filtered["arrondissement"].isin(selected_arr)]
    filtered = filtered[filtered["google_rating"].fillna(0) >= min_google_rating]
    filtered = filtered[filtered["n_relevant"].fillna(0) >= min_n_relevant]

    has_score = filtered["score_10"].notna()
    in_range = filtered["score_10"].between(score_range[0], score_range[1])
    filtered = filtered[(has_score & in_range) | (~has_score & include_unscored)]

    st.divider()
    st.caption(f"Last review collected: {kpis['last_review_at']}")

st.caption(f"Showing {len(filtered)} of {len(places)} bakeries.")

# --- Onglets ------------------------------------------------------------------
tab_map, tab_ranking, tab_nearby, tab_about = st.tabs(
    ["🗺️ Map", "🏆 Ranking", "📍 Near an address", "ℹ️ Methodology"]
)

with tab_map:
    st.caption("👉 Click a marker to see all its reviews in the panel on the right.")

    jittered = spread_duplicate_coordinates(filtered)

    map_col, panel_col = st.columns([2, 1])

    with map_col:
        marker_specs = _build_marker_specs_cached(jittered)
        fmap = build_map(marker_specs)
        map_state = st_folium(
            fmap,
            use_container_width=True,
            height=620,
            returned_objects=["last_object_clicked"],
        )

    clicked = (map_state or {}).get("last_object_clicked")
    if clicked and clicked.get("lat") is not None and clicked != st.session_state._last_map_click:
        st.session_state._last_map_click = clicked
        dist2 = (jittered["map_lat"] - clicked["lat"]) ** 2 + (jittered["map_lon"] - clicked["lng"]) ** 2
        nearest = dist2.idxmin()
        if dist2.loc[nearest] < (0.0005) ** 2:  # ~50 m -- ignore un clic sur du vide
            _select_place(jittered.loc[nearest, "place_id"])
            st.rerun()

    with panel_col:
        pid = st.session_state.selected_place_id
        if not pid or pid not in places["place_id"].values:
            st.info("Click a marker on the map to see all its reviews here.")
        else:
            prow = places.loc[places["place_id"] == pid].iloc[0]
            st.markdown(f"#### {prow['name']}")
            st.caption(prow["formatted_address"])

            _render_place_summary(prow, show_score=True)

            mentions = load_mentions_for_place(pid)
            st.write("")
            if mentions.empty:
                st.caption("No review mentions pain au chocolat for this place yet.")
            else:
                f1, f2 = st.columns(2)
                tone = f1.radio(
                    "Tone", ["All", "Positive", "Negative"], horizontal=True, key="mention_tone_filter"
                )
                sort_by = f2.selectbox(
                    "Sort by", ["Relevance", "Most recent"], key="mention_sort_by"
                )

                if tone == "Positive":
                    mentions = mentions[mentions["sentiment"] >= 0]
                elif tone == "Negative":
                    mentions = mentions[mentions["sentiment"] < 0]

                if sort_by == "Most recent":
                    mentions = mentions.sort_values("published_at", ascending=False, na_position="last")
                else:
                    mentions = mentions.sort_values("sentiment", ascending=False)

                st.caption(f"{len(mentions)} reviews")
                if mentions.empty:
                    st.caption("No review matches this filter.")
                else:
                    with st.container(height=420, border=True):
                        for _, m in mentions.iterrows():
                            st.markdown(
                                mention_card_html(
                                    m["sentiment"],
                                    m["text"],
                                    m["author_name"],
                                    rating=m.get("rating"),
                                    relative_time=m.get("relative_time_text"),
                                    max_chars=None,
                                ),
                                unsafe_allow_html=True,
                            )

with tab_ranking:
    ranking = filtered.dropna(subset=["score_10"]).sort_values("score_10", ascending=False).copy()
    ranking["positive_ratio"] = ranking["positive_ratio"] * 100
    ranking["confidence"] = ranking["confidence"].map(lambda c: confidence_badge(c)[0])
    st.dataframe(
        ranking[
            [
                "name",
                "formatted_address",
                "arrondissement",
                "google_rating",
                "user_rating_count",
                "score_10",
                "positive_ratio",
                "confidence",
                "n_relevant",
            ]
        ],
        column_config={
            "name": "Bakery",
            "formatted_address": "Address",
            "arrondissement": st.column_config.NumberColumn("Arr.", format="%d"),
            "google_rating": st.column_config.NumberColumn("Google rating", format="%.1f ★"),
            "user_rating_count": st.column_config.NumberColumn("Google reviews (total)", format="%d"),
            "score_10": st.column_config.ProgressColumn("PAC score", min_value=0, max_value=10, format="%.1f/10"),
            "positive_ratio": st.column_config.NumberColumn("Positive reviews", format="%.0f%%"),
            "confidence": "Confidence",
            "n_relevant": "Relevant reviews",
        },
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "⬇️ Export as CSV",
        ranking.to_csv(index=False).encode("utf-8"),
        file_name="paris_pain_au_chocolat_ranking.csv",
        mime="text/csv",
    )

with tab_nearby:
    st.caption(
        "Geocoding via the French government address API (adresse.data.gouv.fr) — "
        "any address or place name in France."
    )
    with st.form("nearby_form"):
        c1, c2 = st.columns([3, 1])
        address = c1.text_input("Address", placeholder="e.g. 10 rue de Rivoli, Paris")
        radius_m = c2.slider("Radius (m)", 200, 2000, 800, step=100)
        submitted = st.form_submit_button("🔍 Search")

    if submitted and address.strip():
        try:
            geo = _geocode_address_cached(address.strip())
        except GeocodeError as exc:
            st.error(f"⚠️ {exc}")
        else:
            st.success(f"📍 {geo['formatted_address']}")
            candidates = filtered.dropna(subset=["score_10"]).copy()
            candidates["distance_m"] = haversine_m(
                geo["lat"], geo["lon"], candidates["lat"], candidates["lon"]
            )
            nearby = candidates[candidates["distance_m"] <= radius_m].sort_values(
                ["score_10", "distance_m"], ascending=[False, True]
            )
            if nearby.empty:
                st.info(
                    f"No scored bakery within {radius_m} m (the sidebar filters apply "
                    "here too — try widening them, or increasing the radius)."
                )
            else:
                st.caption(f"{len(nearby)} bakeries found, ranked by score.")
                for _, prow in nearby.head(10).iterrows():
                    header = (
                        f"🥐 {prow['score_10']:.1f}/10 — {prow['name']} "
                        f"({prow['distance_m']:.0f} m)"
                    )
                    with st.expander(header):
                        st.caption(prow["formatted_address"])
                        _render_place_summary(prow, show_score=False)
                        mentions = load_mentions_for_place(prow["place_id"])
                        with st.container(height=260, border=True):
                            if mentions.empty:
                                st.caption("No review mentions pain au chocolat for this place yet.")
                            for _, m in mentions.iterrows():
                                st.markdown(
                                    mention_card_html(
                                        m["sentiment"],
                                        m["text"],
                                        m["author_name"],
                                        rating=m.get("rating"),
                                        relative_time=m.get("relative_time_text"),
                                        max_chars=None,
                                    ),
                                    unsafe_allow_html=True,
                                )

with tab_about:
    st.markdown("### Coverage")
    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(_kpi_card(f"{kpis['n_places']:,}", "Bakeries loaded"), unsafe_allow_html=True)
    avg_score_str = f"{kpis['avg_score']:.1f}/10" if pd.notna(kpis["avg_score"]) else "—"
    col2.markdown(_kpi_card(avg_score_str, "Weighted average score"), unsafe_allow_html=True)
    col3.markdown(_kpi_card(f"{kpis['coverage_pct']:.0f}%", "Places with a score"), unsafe_allow_html=True)
    col4.markdown(_kpi_card(f"{kpis['n_reviews']:,}", "Reviews analysed"), unsafe_allow_html=True)
    st.write("")

    st.markdown(
        """
        ### How the score is calculated

        1. **Detection** — Google reviews that explicitly mention
           *"pain au chocolat"*, *"chocolatine"* (and variants) are
           picked up by keyword.
        2. **Classification** — a language model reads each mention and
           judges whether it really talks about the **taste/quality** of the
           pastry, or only about its **price** (in which case it is excluded:
           a 1★ review complaining about the price of a chocolatine that is
           otherwise described as excellent should not drag the score down).
           It also nets out a plain yes/no *"was this appreciated?"* call,
           used alongside the continuous sentiment score.
        3. **Weighting** — each retained mention is weighted by several
           factors combined: the contributor's credibility (number of
           reviews posted, capped), its freshness (a review loses half its
           weight every year, so one from 2 years ago counts for a quarter
           of one posted today), whether it names the pastry specifically
           or only the generic *"viennoiserie"* (down-weighted), whether it
           describes a one-off incident or a lasting pattern (a single bad
           batch counts for less than "since the new owner, it's not the
           same"), the model's own confidence in its reading of the
           passage, and whether it names a precise quality criterion (a
           vague "not great" counts for a little less than a specific "not
           enough chocolate").
        4. **Aggregation** — a place's score out of 10 blends the weighted
           average sentiment with the share of appreciated mentions,
           slightly smoothed toward the Paris average when a place has only
           one or two mentions — **never** toward the place's overall
           Google rating: a beloved bakery can perfectly well have a bad
           pain au chocolat, and vice versa. That blended score is then
           nudged by the place's overall Google rating, but only a
           little — it counts for 20% of the final number, a minority
           vote rather than a second opinion.

        A place with no pain au chocolat mention in its reviews has **no**
        score by default — it shows up grey on the map rather than being
        assigned a made-up value.

        The model also tags each mention with the specific criteria it
        raises (freshness, baking, chocolate quantity, lamination, price
        relative to quality). When at least 3 mentions cover the same
        criterion for a place, it gets its own mini score, shown as a
        small breakdown next to the main one.
        """
    )
