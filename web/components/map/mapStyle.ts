import type { StyleSpecification } from "maplibre-gl";

/** CARTO Positron raster tiles -- reproduces the current Folium
 * "CartoDB positron" look with no API key/account required (unlike vector
 * basemaps from MapTiler/Stadia). Raster is plenty for a light basemap
 * under colored circle markers; the performance win in this port comes
 * from WebGL marker/cluster rendering, not from vector tiles. */
export const MAP_STYLE: StyleSpecification = {
  version: 8,
  // Required for CLUSTER_COUNT_LAYER's text-field to render at all --
  // MapLibre silently draws nothing without a glyphs source. Free,
  // keyless, no-account demo tile font endpoint.
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    "carto-positron": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "https://d.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "© OpenStreetMap contributors © CARTO",
    },
  },
  layers: [
    {
      id: "carto-positron-layer",
      type: "raster",
      source: "carto-positron",
    },
  ],
};

export const PARIS_CENTER: [number, number] = [2.3522, 48.8566]; // [lon, lat]
export const PARIS_ZOOM = 12;
export const CLUSTER_MAX_ZOOM = 16;
export const CLUSTER_RADIUS = 45;
