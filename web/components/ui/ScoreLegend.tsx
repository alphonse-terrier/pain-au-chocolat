import { scoreGradientCss, INSUFFICIENT_DATA_COLOR } from "@/lib/theme";
import styles from "./ScoreLegend.module.css";

/** The only place the map's marker-color encoding is explained in text --
 * doubles as the fix for "color alone conveys meaning" on the map. */
export default function ScoreLegend() {
  return (
    <div className={styles.wrap}>
      <div className={styles.bar} style={{ background: `linear-gradient(to right, ${scoreGradientCss()})` }} />
      <div className={styles.labels}>
        <span>0</span>
        <span>5</span>
        <span>10</span>
      </div>
      <div className={styles.noScore}>
        <span className={styles.swatch} style={{ background: INSUFFICIENT_DATA_COLOR }} aria-hidden="true" />
        No score yet
      </div>
    </div>
  );
}
