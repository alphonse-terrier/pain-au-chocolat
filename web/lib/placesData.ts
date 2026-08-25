import type { Place, PlacesFile, PlacesMeta } from "./types";

/** Decodes the columns/rows-of-arrays shape from places.json into a plain
 * Place[] (and a lookup Map keyed by place_id). Column order must match
 * export_web_json.py's `columns` list -- we index by name once here rather
 * than hardcoding positions everywhere else. */
export function decodePlaces(file: PlacesFile): { places: Place[]; byId: Map<string, Place>; meta: PlacesMeta } {
  const idx = (name: string) => {
    const i = file.columns.indexOf(name);
    if (i === -1) throw new Error(`places.json is missing column "${name}"`);
    return i;
  };
  const col = {
    place_id: idx("place_id"),
    name: idx("name"),
    address: idx("address"),
    lat: idx("lat"),
    lon: idx("lon"),
    map_lat: idx("map_lat"),
    map_lon: idx("map_lon"),
    google_rating: idx("google_rating"),
    user_rating_count: idx("user_rating_count"),
    maps_uri: idx("maps_uri"),
    score_10: idx("score_10"),
    confidence: idx("confidence"),
    n_relevant: idx("n_relevant"),
    positive_ratio: idx("positive_ratio"),
    arrondissement: idx("arrondissement"),
  };

  const places: Place[] = file.rows.map((row) => ({
    place_id: row[col.place_id] as string,
    name: row[col.name] as string | null,
    address: row[col.address] as string | null,
    lat: row[col.lat] as number,
    lon: row[col.lon] as number,
    map_lat: row[col.map_lat] as number,
    map_lon: row[col.map_lon] as number,
    google_rating: row[col.google_rating] as number | null,
    user_rating_count: row[col.user_rating_count] as number | null,
    maps_uri: row[col.maps_uri] as string | null,
    score_10: row[col.score_10] as number | null,
    confidence: row[col.confidence] as string,
    n_relevant: row[col.n_relevant] as number,
    positive_ratio: row[col.positive_ratio] as number | null,
    arrondissement: row[col.arrondissement] as number | null,
  }));

  const byId = new Map(places.map((p) => [p.place_id, p]));
  return { places, byId, meta: file.meta };
}

let cached: Promise<{ places: Place[]; byId: Map<string, Place>; meta: PlacesMeta }> | null = null;

/** Fetches and decodes /data/places.json exactly once per page load
 * (module-level cache -- every consumer awaits the same in-flight
 * promise instead of re-fetching).
 *
 * Important: `cached` is cleared on rejection. Without this, one failed
 * fetch (offline, server error, a bad places.json) would permanently
 * poison the module -- every subsequent call, including a user-triggered
 * Retry, would resolve the same rejected promise forever. */
export function loadPlaces(): Promise<{ places: Place[]; byId: Map<string, Place>; meta: PlacesMeta }> {
  if (!cached) {
    cached = fetch("/data/places.json", { signal: AbortSignal.timeout(15_000) })
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to load places.json: ${r.status}`);
        return r.json() as Promise<PlacesFile>;
      })
      .then(decodePlaces)
      .catch((err) => {
        cached = null;
        throw err;
      });
  }
  return cached;
}
