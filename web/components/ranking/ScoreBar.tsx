import { scoreToColor } from "@/lib/theme";
import styles from "./ScoreBar.module.css";

export default function ScoreBar({
  score,
  size = "sm",
  showLabel = true,
}: {
  score: number | null;
  size?: "sm" | "lg";
  showLabel?: boolean;
}) {
  if (score === null) return <span className={`${styles.label} ${styles[size]}`}>—</span>;
  return (
    <div className={`${styles.wrap} ${styles[size]}`}>
      <div className={styles.track}>
        <div
          className={styles.fill}
          style={{ width: `${(score / 10) * 100}%`, background: scoreToColor(score) }}
        />
      </div>
      {showLabel && <span className={`${styles.label} ${styles[size]} tnum`}>{score.toFixed(1)}/10</span>}
    </div>
  );
}
