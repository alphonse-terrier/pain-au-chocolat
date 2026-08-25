import type { CircleLayerSpecification, SymbolLayerSpecification } from "maplibre-gl";
import { scoreColorExpression, INSUFFICIENT_DATA_COLOR } from "@/lib/theme";

export const SOURCE_ID = "places";

export const CLUSTERS_LAYER = {
  id: "clusters",
  type: "circle",
  source: SOURCE_ID,
  filter: ["has", "point_count"],
  paint: {
    // mean score of the cluster's members -- a real improvement over
    // Folium's flat cluster color (cf. plan). Derived from the same
    // SCORE_COLOR_STOPS as the unclustered points, not a second literal.
    "circle-color": scoreColorExpression(["/", ["get", "score_sum"], ["max", ["get", "score_n"], 1]]),
    "circle-radius": ["step", ["get", "point_count"], 16, 10, 22, 50, 28],
    "circle-stroke-color": "#ffffff",
    "circle-stroke-width": 1.5,
    "circle-opacity": 0.9,
  },
} as unknown as CircleLayerSpecification;

export const CLUSTER_COUNT_LAYER: SymbolLayerSpecification = {
  id: "cluster-count",
  type: "symbol",
  source: SOURCE_ID,
  filter: ["has", "point_count"],
  layout: {
    "text-field": ["get", "point_count_abbreviated"],
    "text-size": 12,
    "text-font": ["Noto Sans Regular"],
  },
  paint: {
    "text-color": "#ffffff",
  },
};

export const UNCLUSTERED_POINT_LAYER = {
  id: "unclustered-point",
  type: "circle",
  source: SOURCE_ID,
  filter: ["!", ["has", "point_count"]],
  paint: {
    "circle-radius": 7,
    "circle-stroke-color": "#ffffff",
    "circle-stroke-width": 1.5,
    "circle-opacity": 0.9,
    "circle-color": [
      "case",
      ["==", ["get", "score"], null],
      INSUFFICIENT_DATA_COLOR,
      scoreColorExpression(["get", "score"]),
    ],
  },
} as unknown as CircleLayerSpecification;

/** Highlight ring around the currently-selected place. Filtered by
 * place_id rather than feature-state: feature ids aren't stable across
 * re-clustering on a clustered GeoJSON source (cf. plan). Set to a
 * deliberately-unmatchable filter when nothing is selected. */
export function selectedPointLayer(selectedId: string | null): CircleLayerSpecification {
  return {
    id: "selected-point",
    type: "circle",
    source: SOURCE_ID,
    filter: ["==", ["get", "place_id"], selectedId ?? "__none__"],
    paint: {
      "circle-radius": 11,
      "circle-stroke-color": "#1A1A1A",
      "circle-stroke-width": 2,
      "circle-opacity": 0.9,
      "circle-color": [
        "case",
        ["==", ["get", "score"], null],
        INSUFFICIENT_DATA_COLOR,
        scoreColorExpression(["get", "score"]),
      ],
    },
  } as unknown as CircleLayerSpecification;
}
