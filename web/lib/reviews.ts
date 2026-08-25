import type { PlaceReviews } from "./types";

const cache = new Map<string, Promise<PlaceReviews>>();

const EMPTY = (placeId: string): PlaceReviews => ({ place_id: placeId, n: 0, reviews: [] });

/** Fetches the per-place review shard (web/public/data/places/<id>.json),
 * caching per place_id for the life of the page -- clicking the same
 * marker twice costs one network request, not two. A 404 (place has no
 * retained mention -- export_web_json only writes a shard when n>0) is
 * treated as "no reviews", not an error. */
export function fetchPlaceReviews(placeId: string): Promise<PlaceReviews> {
  let p = cache.get(placeId);
  if (!p) {
    p = fetch(`/data/places/${encodeURIComponent(placeId)}.json`)
      .then((r) => {
        if (r.status === 404) return EMPTY(placeId);
        if (!r.ok) throw new Error(`Failed to load reviews for ${placeId}: ${r.status}`);
        return r.json() as Promise<PlaceReviews>;
      })
      .catch(() => EMPTY(placeId));
    cache.set(placeId, p);
  }
  return p;
}
