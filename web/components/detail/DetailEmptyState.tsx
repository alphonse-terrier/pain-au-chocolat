import type { Place } from "@/lib/types";
import ShopWindow from "../ui/ShopWindow";
import ScoreLegend from "../ui/ScoreLegend";
import styles from "./DetailEmptyState.module.css";

/** Shown in the detail panel/sheet when nothing is selected -- the
 * biggest wasted space in the app used to be one grey sentence here.
 * Explains the map's color encoding (the only place it's explained) and
 * offers the top-scored places in the current filtered view as a quick
 * way in. The mark now does the pointing that the 👉 used to, so the
 * emoji is gone -- this is the app's single largest brand moment. */
export default function DetailEmptyState({
  topPlaces,
  onSelect,
}: {
  topPlaces: Place[];
  onSelect: (placeId: string) => void;
}) {
  return (
    <div className={styles.wrap}>
      <div className={styles.hero}>
        <ShopWindow width={220} className={styles.heroLogo} />
        <p className={styles.instruction}>Poke a marker on the map to meet its reviews.</p>
      </div>
      <ScoreLegend />
      {topPlaces.length > 0 && (
        <div className={styles.topList}>
          <h3 className={styles.topHeading}>Top 20 matching your filters</h3>
          <ol className={styles.list}>
            {topPlaces.map((p, i) => (
              <li key={p.place_id}>
                <button type="button" className={styles.topItem} onClick={() => onSelect(p.place_id)}>
                  <span className={styles.rank}>{i + 1}</span>
                  <span className={styles.name}>{p.name}</span>
                  <span className={`${styles.score} tnum`}>{p.score_10?.toFixed(1)}</span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
