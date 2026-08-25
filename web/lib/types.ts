/** Shapes of the static JSON produced by `pac export-web-json`
 * (src/pac/export_web_json.py) -- keep these in sync with that file. */

export interface Place {
  place_id: string;
  name: string | null;
  address: string | null;
  lat: number;
  lon: number;
  map_lat: number;
  map_lon: number;
  google_rating: number | null;
  user_rating_count: number | null;
  maps_uri: string | null;
  score_10: number | null;
  confidence: string;
  n_relevant: number;
  positive_ratio: number | null;
  arrondissement: number | null;
  // Score /10 secondaire par critère qualité, en plus de score_10 --
  // jamais à sa place. NULL si le critère n'est couvert par aucune (ou
  // trop peu de) mention pour ce lieu.
  asp_freshness: number | null;
  asp_baking: number | null;
  asp_chocolate_quantity: number | null;
  asp_lamination: number | null;
  asp_price_value: number | null;
  asp_other: number | null;
}

export interface PlacesMeta {
  n_places: number;
  n_places_rendered: number;
  n_reviews: number;
  n_scored: number;
  coverage_pct: number;
  avg_score: number | null;
  last_review_at: string | null;
}

export interface PlacesFile {
  version: number;
  generated_at: string;
  meta: PlacesMeta;
  columns: string[];
  rows: Array<Array<string | number | null>>;
}

export interface Review {
  t: string | null; // text
  a: string | null; // author
  r: number | null; // rating 1-5
  w: string | null; // relative_time_text
  p: number | null; // published_at, unix seconds
  s: number; // sentiment -1..1
  asp: string[]; // quality criteria identified in this review, e.g. ["freshness"]
}

export interface PlaceReviews {
  place_id: string;
  n: number;
  reviews: Review[];
}

export interface Filters {
  q: string;
  arr: number[];
  smin: number;
  smax: number;
  unscored: boolean;
  grate: number;
  nrel: number;
}
