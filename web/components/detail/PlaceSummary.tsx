import type { Place } from "@/lib/types";
import { formatPercent } from "@/lib/theme";
import ScoreHero from "./ScoreHero";
import ConfidencePill from "./ConfidencePill";
import styles from "./PlaceSummary.module.css";

/** Score hero + secondary metrics + confidence + Google Maps link --
 * shared between the map detail panel/bottom sheet (showScore=true) and
 * the Nearby tab's result cards (showScore=false -- the score is already
 * in the card's header there), matching _render_place_summary in app.py. */
export default function PlaceSummary({ place, showScore }: { place: Place; showScore: boolean }) {
  const googleRating = place.google_rating !== null ? `${place.google_rating.toFixed(1)}/5` : "—";
  return (
    <div>
      {showScore && <ScoreHero score={place.score_10} />}
      <div className={styles.metrics}>
        <div className={styles.metric}>
          <div className={styles.metricLabel}>Positive reviews</div>
          <div className={`${styles.metricValue} tnum`}>{formatPercent(place.positive_ratio)}</div>
        </div>
        <div className={styles.metric}>
          <div className={styles.metricLabel}>Google rating</div>
          <div className={`${styles.metricValue} tnum`}>{googleRating}</div>
        </div>
      </div>
      <div className={styles.confidenceRow}>
        <ConfidencePill confidence={place.confidence} />
        <span className={styles.reviewCount}>{place.n_relevant} pain au chocolat reviews</span>
      </div>
      {place.maps_uri && (
        <a className={styles.mapsBtn} href={place.maps_uri} target="_blank" rel="noreferrer">
          View on Google Maps →
        </a>
      )}
    </div>
  );
}
