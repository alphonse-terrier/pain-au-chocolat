/**
 * Data-encoded colors and formatting helpers ported directly from
 * src/pac/webapp/theme.py -- keep these two files in sync by hand, there's
 * no shared source of truth between the Python and TS sides (the plan
 * accepted this duplication in exchange for a fully static frontend with
 * no build-time codegen step).
 *
 * Two sources of truth, never three: this file owns color that answers
 * "what does this NUMBER mean" (score, confidence, sentiment) -- MapLibre
 * paint expressions and several inline `style` usages need real JS values.
 * app/globals.css owns color that answers "what IS this UI part" (chrome).
 */

// Score color scale: linear interpolation between stops, same as
// theme.py::score_to_color. Score is clamped to [0, 10] first.
export const SCORE_COLOR_STOPS: Array<[number, [number, number, number]]> = [
  [0.0, [0xd6, 0x45, 0x45]],
  [4.0, [0xe8, 0x97, 0x4e]],
  [6.0, [0xe8, 0xc5, 0x47]],
  [7.5, [0x8b, 0xc3, 0x4a]],
  [10.0, [0x2e, 0x7d, 0x32]],
];

export const INSUFFICIENT_DATA_COLOR = "#9AA5B1";

function toHex([r, g, b]: [number, number, number]): string {
  const h = (n: number) => n.toString(16).padStart(2, "0").toUpperCase();
  return `#${h(r)}${h(g)}${h(b)}`;
}

export function scoreToColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return INSUFFICIENT_DATA_COLOR;
  const s = Math.max(0, Math.min(10, score));
  for (let i = 0; i < SCORE_COLOR_STOPS.length - 1; i++) {
    const [s0, c0] = SCORE_COLOR_STOPS[i];
    const [s1, c1] = SCORE_COLOR_STOPS[i + 1];
    if (s >= s0 && s <= s1) {
      const t = s1 === s0 ? 0 : (s - s0) / (s1 - s0);
      const rgb: [number, number, number] = [
        Math.round(c0[0] + (c1[0] - c0[0]) * t),
        Math.round(c0[1] + (c1[1] - c0[1]) * t),
        Math.round(c0[2] + (c1[2] - c0[2]) * t),
      ];
      return toHex(rgb);
    }
  }
  return toHex(SCORE_COLOR_STOPS[SCORE_COLOR_STOPS.length - 1][1]);
}

/** A CSS `linear-gradient()` stop list over [0, 10], for painting a slider
 * track or legend bar with the same scale as the map markers. */
export function scoreGradientCss(): string {
  return SCORE_COLOR_STOPS.map(([s, rgb]) => `${toHex(rgb)} ${(s / 10) * 100}%`).join(", ");
}

/** MapLibre paint-property `interpolate` expression over the same stops --
 * derived from SCORE_COLOR_STOPS rather than a second hardcoded literal,
 * so there is exactly one place the five stops are written down. `input`
 * is the expression to interpolate on (a `["get", "score"]` for a single
 * feature, or a cluster-mean expression for the `clusters` layer). */
export function scoreColorExpression(input: unknown): unknown[] {
  const stops = SCORE_COLOR_STOPS.flatMap(([s, rgb]) => [s, toHex(rgb)]);
  return ["interpolate", ["linear"], input, ...stops];
}

/** Sentiment (mention-level, -1..1) is data, not chrome -- these are the
 * scale endpoints, kept separate from the UI's --success/--danger tokens. */
export const SENTIMENT_COLORS = {
  positive: toHex(SCORE_COLOR_STOPS[SCORE_COLOR_STOPS.length - 1][1]),
  negative: toHex(SCORE_COLOR_STOPS[0][1]),
};

export type Confidence = "high" | "medium" | "low" | "insufficient_data";

export const CONFIDENCE_LABELS: Record<Confidence, [string, string]> = {
  high: ["Reliable", "#2E7D32"],
  medium: ["Fair", "#E8974E"],
  low: ["Limited data", "#D6A245"],
  insufficient_data: ["Not enough reviews", "#9AA5B1"],
};

/** Playful variants of the labels above, for the on-screen confidence pill
 * only -- CSV export (lib/csv.ts) must keep using the plain CONFIDENCE_LABELS
 * so it stays byte-identical to the Streamlit app's export. Colors are
 * shared with CONFIDENCE_LABELS, only the wording differs. */
const CONFIDENCE_DISPLAY_TEXT: Record<Confidence, string> = {
  high: "Trust us",
  medium: "Probably fine",
  low: "Pinch of salt advised",
  insufficient_data: "Total mystery",
};

/** AA-passing (>=4.5:1 on white) text variants of the confidence colors
 * above -- the raw CONFIDENCE_LABELS colors are dot/graphical colors only
 * and must never be used as text (medium/low/insufficient_data are all
 * under 2.5:1 as text on their own tint). */
export const CONFIDENCE_TEXT_COLORS: Record<Confidence, string> = {
  high: "#2E7D32",
  medium: "#A65F14",
  low: "#8A6410",
  insufficient_data: "#5C6670",
};

export function confidenceBadge(confidence: string | null | undefined): [string, string] {
  if (confidence && confidence in CONFIDENCE_LABELS) {
    return CONFIDENCE_LABELS[confidence as Confidence];
  }
  return ["Unknown", "#9AA5B1"];
}

/** Same color, playful label -- for the on-screen pill only (see
 * CONFIDENCE_DISPLAY_TEXT above). */
export function confidenceDisplayBadge(confidence: string | null | undefined): [string, string] {
  const [, color] = confidenceBadge(confidence);
  const text = confidence && confidence in CONFIDENCE_DISPLAY_TEXT ? CONFIDENCE_DISPLAY_TEXT[confidence as Confidence] : "Unknown";
  return [text, color];
}

export function confidenceTextColor(confidence: string | null | undefined): string {
  if (confidence && confidence in CONFIDENCE_TEXT_COLORS) {
    return CONFIDENCE_TEXT_COLORS[confidence as Confidence];
  }
  return "#5C6670";
}

export const MAPS_LINK_LABEL = "View on Google Maps →";

export function formatStars(rating: number | null | undefined): string {
  if (rating === null || rating === undefined || Number.isNaN(rating)) return "—";
  const filled = Math.max(0, Math.min(5, Math.round(rating)));
  return "★".repeat(filled) + "☆".repeat(5 - filled) + ` ${rating.toFixed(1)}`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

/** Mirrors src/pac/webapp/theme.py's ASPECT_LABELS -- keep the keys/values
 * in sync by hand (same convention as the rest of this file). */
export const ASPECT_LABELS: Record<string, string> = {
  freshness: "Freshness",
  baking: "Baking",
  chocolate_quantity: "Chocolate amount",
  lamination: "Lamination",
  price_value: "Value for money",
  other: "Other",
};
