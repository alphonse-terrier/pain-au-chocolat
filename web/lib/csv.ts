import type { Place } from "./types";
import { confidenceBadge } from "./theme";

// Header names match app.py's `ranking.to_csv(index=False)` exactly (the
// DataFrame's raw column names, not the pretty on-screen labels) for
// parity with the Streamlit export.
const HEADERS = [
  "name",
  "formatted_address",
  "arrondissement",
  "google_rating",
  "user_rating_count",
  "score_10",
  "positive_ratio",
  "confidence",
  "n_relevant",
] as const;

function csvCell(value: string | number | null): string {
  if (value === null || value === undefined) return "";
  const s = String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Builds the ranking CSV -- positive_ratio scaled to 0-100 and confidence
 * mapped to its label, matching app.py's transformed export frame exactly. */
export function rankingToCsv(places: Place[]): string {
  const lines = [HEADERS.join(",")];
  for (const p of places) {
    const [confLabel] = confidenceBadge(p.confidence);
    lines.push(
      [
        csvCell(p.name),
        csvCell(p.address),
        csvCell(p.arrondissement),
        csvCell(p.google_rating),
        csvCell(p.user_rating_count),
        csvCell(p.score_10),
        csvCell(p.positive_ratio !== null ? Math.round(p.positive_ratio * 1000) / 10 : null),
        csvCell(confLabel),
        csvCell(p.n_relevant),
      ].join(",")
    );
  }
  return lines.join("\n") + "\n";
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
