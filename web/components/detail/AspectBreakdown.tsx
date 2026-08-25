import type { Place } from "@/lib/types";
import { ASPECT_LABELS } from "@/lib/theme";
import ScoreBar from "../ranking/ScoreBar";
import styles from "./AspectBreakdown.module.css";

const ASPECT_KEYS = [
  "asp_freshness",
  "asp_baking",
  "asp_chocolate_quantity",
  "asp_lamination",
  "asp_price_value",
] as const;

/** Secondary /10 score per quality criterion (freshness, baking, chocolate
 * amount, lamination, value for money) -- a detail alongside the global
 * score, never a replacement. Renders nothing if the place has no aspect
 * covered by enough mentions (score.MIN_ASPECT_MENTIONS on the Python
 * side), which is the common case for places with few reviews.
 *
 * Each row doubles as a filter: clicking it narrows the review list below
 * to just the reviews that mentioned that criterion, clicking again (or
 * clicking elsewhere) clears the filter -- onSelect is omitted where
 * there's no review list to filter (the Nearby tab's cards). */
export default function AspectBreakdown({
  place,
  selected = null,
  onSelect,
}: {
  place: Place;
  selected?: string | null;
  onSelect?: (aspect: string | null) => void;
}) {
  const rows = ASPECT_KEYS.map((key) => ({
    aspect: key.slice(4),
    score: place[key],
  })).filter((r) => r.score !== null);

  if (rows.length === 0) return null;

  return (
    <div className={styles.wrap}>
      <h3 className={styles.heading}>Strengths &amp; weaknesses</h3>
      <div className={styles.list}>
        {rows.map((r) => {
          const isSelected = selected === r.aspect;
          const label = ASPECT_LABELS[r.aspect] ?? r.aspect;
          return (
            <button
              key={r.aspect}
              type="button"
              className={`${styles.row} ${onSelect ? styles.rowClickable : ""} ${isSelected ? styles.rowSelected : ""}`}
              onClick={onSelect ? () => onSelect(isSelected ? null : r.aspect) : undefined}
              disabled={!onSelect}
              aria-pressed={onSelect ? isSelected : undefined}
              title={onSelect ? `Show only reviews mentioning ${label.toLowerCase()}` : undefined}
            >
              <span className={styles.label}>{label}</span>
              <div className={styles.barWrap}>
                <ScoreBar score={r.score} size="sm" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
