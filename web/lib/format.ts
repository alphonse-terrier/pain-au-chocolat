export { formatPercent } from "./theme";

export function formatInt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-GB");
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return score.toFixed(1);
}

export function formatScoreOutOf10(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return `${score.toFixed(1)}/10`;
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

/** Rough walking time at ~80 m/min, rounded to the nearest minute
 * (minimum 1) -- just enough precision for a "should I walk there?" cue. */
export function formatWalkTime(meters: number): string {
  const minutes = Math.max(1, Math.round(meters / 80));
  return `≈ ${minutes} min walk`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
}
