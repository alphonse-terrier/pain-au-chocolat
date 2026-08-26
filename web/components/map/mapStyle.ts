/** OpenFreeMap's "positron" style -- a keyless, no-account vector
 * replacement for the CARTO Positron raster tiles this used to point at.
 * CARTO deprecated anonymous access to basemaps.cartocdn.com (every tile
 * now renders with an "API KEY REQUIRED" watermark baked in, confirmed by
 * fetching one directly -- not a bug on our end, a policy change on
 * theirs). OpenFreeMap serves the same visual style, self-funded to stay
 * free with no key/account, and its style JSON brings its own glyphs
 * (including "Noto Sans Regular", used by CLUSTER_COUNT_LAYER below) and
 * its own source attribution, which MapLibre's attribution control picks
 * up automatically -- no manual override needed. Passed as a URL rather
 * than an inline object: MapLibre fetches and owns the full style
 * (background/water/roads/labels), our own layers are added on top once
 * it's loaded. */
export const MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";

export const PARIS_CENTER: [number, number] = [2.3522, 48.8566]; // [lon, lat]
export const PARIS_ZOOM = 12;
export const CLUSTER_MAX_ZOOM = 16;
export const CLUSTER_RADIUS = 45;
// Just above CLUSTER_MAX_ZOOM, so a place selected from a list (Ranking,
// Top 20) always lands unclustered and clearly picked out, at a
// neighbourhood-scale view rather than a full street zoom-in.
export const SELECTED_PLACE_ZOOM = CLUSTER_MAX_ZOOM + 1;
