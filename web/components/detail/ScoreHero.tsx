import { scoreToColor } from "@/lib/theme";
import ScoreBar from "../ranking/ScoreBar";
import styles from "./ScoreHero.module.css";

/** The score is the whole reason this app exists -- give it real visual
 * weight instead of treating it as one of three equal metric boxes. */
export default function ScoreHero({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <div className={styles.wrap}>
        <div className={`${styles.numeral} display`} style={{ color: "var(--text-tertiary)" }}>
          —
        </div>
        <p className={styles.noScore}>Nobody has mentioned pain au chocolat here. Suspicious, honestly.</p>
      </div>
    );
  }
  return (
    <div className={styles.wrap}>
      <div className={styles.numeralRow}>
        <span className={`${styles.numeral} display tnum`} style={{ color: scoreToColor(score) }}>
          {score.toFixed(1)}
        </span>
        <span className={styles.outOf}>/10</span>
      </div>
      <ScoreBar score={score} size="lg" showLabel={false} />
    </div>
  );
}
