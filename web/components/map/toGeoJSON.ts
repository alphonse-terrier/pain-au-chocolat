import type { FeatureCollection, Point } from "geojson";
import type { Place } from "@/lib/types";

export interface PlaceFeatureProps {
  place_id: string;
  name: string;
  score: number | null;
}

/** Builds the GeoJSON source data for the `places` source (see layers.ts).
 * Uses map_lat/map_lon (jittered) for position -- true lat/lon is only
 * needed for the Nearby tab's distance math, kept on the Place object
 * itself, not duplicated into the map source. */
export function placesToFeatureCollection(places: Place[]): FeatureCollection<Point, PlaceFeatureProps> {
  return {
    type: "FeatureCollection",
    features: places.map((p) => ({
      type: "Feature",
      id: undefined, // clustered sources don't keep stable feature ids across re-clustering (cf. plan)
      geometry: { type: "Point", coordinates: [p.map_lon, p.map_lat] },
      properties: {
        place_id: p.place_id,
        name: p.name ?? "Bakery",
        score: p.score_10,
      },
    })),
  };
}
