import { confidenceDisplayBadge, confidenceTextColor } from "@/lib/theme";
import styles from "./ConfidencePill.module.css";

/** Just the confidence word + a colored dot -- the review count used to
 * live inside this pill's text, but it's a headline fact, not pill
 * garnish, so callers render it as its own line (see PlaceSummary). Uses
 * the playful display label, not the plain one CSV export relies on. */
export default function ConfidencePill({ confidence }: { confidence: string | null }) {
  const [label, dotColor] = confidenceDisplayBadge(confidence);
  const textColor = confidenceTextColor(confidence);
  return (
    <span className={styles.pill} style={{ color: textColor }}>
      <span className={styles.dot} style={{ background: dotColor }} aria-hidden="true" />
      {label}
    </span>
  );
}
