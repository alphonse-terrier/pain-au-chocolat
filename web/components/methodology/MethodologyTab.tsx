import type { PlacesMeta } from "@/lib/types";
import { scoreToColor } from "@/lib/theme";
import { formatDate, formatInt } from "@/lib/format";
import ScoreLegend from "../ui/ScoreLegend";
import KpiCard from "./KpiCard";
import styles from "./MethodologyTab.module.css";

const STEPS = [
  {
    title: "Detection",
    body: 'Reviews mentioning "pain au chocolat" or "chocolatine" (typos included) are found by keyword.',
  },
  {
    title: "Classification",
    body: "A language model checks whether the mention is really about taste, not just price, and gives a quick yes/no on whether the reviewer liked it.",
  },
  {
    title: "Weighting",
    body: "Each mention is weighted by the reviewer's credibility, how recent it is, how precise its criticism is, and whether it describes a one-off slip or a lasting pattern.",
  },
  {
    title: "Aggregation",
    body: "The score blends weighted sentiment with the share of positive mentions, smoothed toward the Paris average for places with very few reviews (never toward their own Google rating). The bakery's overall Google rating is then folded in at just 20%, a light nudge rather than a second vote.",
  },
];

export default function MethodologyTab({ meta }: { meta: PlacesMeta }) {
  const avgScore = meta.avg_score !== null ? meta.avg_score.toFixed(1) : "—";

  return (
    <div className={styles.page}>
      <h2 className={`${styles.pageHeading} display`}>How the score works</h2>
      <p className={styles.introText}>
        Scored from the Google reviews that actually talk about the pastry, not from the bakery&apos;s overall
        rating.
      </p>

      <div className={styles.layout}>
        <ol className={styles.steps}>
          {STEPS.map((step, i) => (
            <li key={step.title} className={styles.step}>
              {/* A numbered "baton chip" -- a chocolate baton standing on
                  end -- rather than a generic magnifier/scales/trophy
                  emoji per step. */}
              <span className={styles.stepNumber} aria-hidden="true">
                {i + 1}
              </span>
              <div>
                <h3 className={styles.stepTitle}>{step.title}</h3>
                <p className={styles.stepBody}>{step.body}</p>
              </div>
            </li>
          ))}
        </ol>

        <aside className={styles.sidebar}>
          <div className={styles.kpis}>
            <KpiCard value={formatInt(meta.n_places)} label="Bakeries" />
            <KpiCard value={avgScore} unit="/10" label="Avg. score" accentColor={scoreToColor(meta.avg_score)} />
            <KpiCard value={`${meta.coverage_pct.toFixed(0)}`} unit="%" label="Scored" />
            <KpiCard value={formatInt(meta.n_reviews)} label="Reviews" />
          </div>
          <p className={styles.lastReview}>Last review collected: {formatDate(meta.last_review_at)}</p>

          <div className={styles.legendCard}>
            <p className={styles.legendCaption}>What the map colors mean</p>
            <ScoreLegend />
            <p className={styles.caveat}>
              No mention of pain au chocolat means <strong>no score</strong>, shown grey rather than guessed.
            </p>
          </div>
        </aside>
      </div>

      <p className={styles.aside}>
        Each mention is also tagged with what it praises or criticizes (freshness, baking, chocolate amount,
        lamination, value for money). Once a place has 3+ mentions on the same criterion, that shows up as its own
        mini score under &quot;Strengths &amp; weaknesses&quot; and in the leaderboard.
      </p>
    </div>
  );
}
