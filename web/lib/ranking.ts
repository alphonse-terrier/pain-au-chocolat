import type { Place } from "./types";
import { ASPECT_LABELS, confidenceBadge, formatPercent, formatStars } from "./theme";

export interface RankingColumn {
  key: string;
  label: string;
  priority: 1 | 2 | 3; // 1 = always shown, 3 = hidden first on narrow screens
  get: (p: Place) => number | string | null;
  /** Marks the 6 "Strengths & weaknesses" sub-scores -- rendered tinted by
   * scoreToColor in RankingTable, same as the main score column. */
  isAspect?: boolean;
}

const ASPECT_KEYS = [
  "asp_freshness",
  "asp_baking",
  "asp_chocolate_quantity",
  "asp_lamination",
  "asp_price_value",
] as const;

export const RANKING_COLUMNS: RankingColumn[] = [
  { key: "name", label: "Bakery", priority: 1, get: (p) => p.name },
  { key: "address", label: "Address", priority: 3, get: (p) => p.address },
  { key: "arrondissement", label: "Arr.", priority: 2, get: (p) => p.arrondissement },
  { key: "google_rating", label: "Google rating", priority: 2, get: (p) => p.google_rating },
  { key: "user_rating_count", label: "Reviews", priority: 3, get: (p) => p.user_rating_count },
  { key: "score_10", label: "Score", priority: 1, get: (p) => p.score_10 },
  { key: "positive_ratio", label: "Positive reviews", priority: 2, get: (p) => p.positive_ratio },
  { key: "confidence", label: "Confidence", priority: 2, get: (p) => p.confidence },
  { key: "n_relevant", label: "PAC mentions", priority: 2, get: (p) => p.n_relevant },
  ...ASPECT_KEYS.map(
    (key): RankingColumn => ({
      key,
      label: ASPECT_LABELS[key.slice(4)] ?? key,
      priority: 3,
      isAspect: true,
      get: (p) => p[key],
    })
  ),
];

export function sortPlaces(places: Place[], sort: string, dir: "asc" | "desc"): Place[] {
  const col = RANKING_COLUMNS.find((c) => c.key === sort) ?? RANKING_COLUMNS[5];
  const factor = dir === "asc" ? 1 : -1;
  return [...places].sort((a, b) => {
    const va = col.get(a);
    const vb = col.get(b);
    if (va === null) return 1;
    if (vb === null) return -1;
    if (typeof va === "string" || typeof vb === "string") {
      return factor * String(va).localeCompare(String(vb));
    }
    return factor * ((va as number) - (vb as number));
  });
}

export { confidenceBadge, formatPercent, formatStars };
