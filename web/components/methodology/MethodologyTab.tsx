import type { PlacesMeta } from "@/lib/types";
import { scoreToColor } from "@/lib/theme";
import { formatDate, formatInt } from "@/lib/format";
import Alert from "../ui/Alert";
import KpiCard from "./KpiCard";
import styles from "./MethodologyTab.module.css";

const STEPS = [
  {
    title: "Detection",
    body: (
      <>
        Google reviews that explicitly mention <em>&quot;pain au chocolat&quot;</em>, <em>&quot;chocolatine&quot;</em>{" "}
        (and variants) are picked up by keyword.
      </>
    ),
  },
  {
    title: "Classification",
    body: (
      <>
        A language model reads each mention and judges whether it really talks about the <strong>taste/quality</strong> of
        the pastry, or only about its <strong>price</strong> (in which case it is excluded: a 1★ review complaining
        about the price of a chocolatine that is otherwise described as excellent should not drag the score down).
      </>
    ),
  },
  {
    title: "Weighting",
    body: (
      <>
        Each retained mention is weighted by the contributor&apos;s credibility (number of reviews posted, capped) and
        its freshness: a review loses half its weight every year (so a review from 2 years ago counts for a quarter of
        one posted today).
      </>
    ),
  },
  {
    title: "Aggregation",
    body: (
      <>
        A place&apos;s score out of 10 is the weighted average of its mentions, slightly smoothed toward the Paris
        average when a place has only one or two mentions. It is <strong>never</strong> smoothed toward the
        place&apos;s overall Google rating: a beloved bakery can perfectly well have a bad pain au chocolat, and vice
        versa.
      </>
    ),
  },
];

export default function MethodologyTab({ meta }: { meta: PlacesMeta }) {
  const avgScore = meta.avg_score !== null ? meta.avg_score.toFixed(1) : "—";

  return (
    <div className={styles.page}>
      <section className={styles.intro}>
        <h2 className={styles.pageHeading}>About this ranking</h2>
        <p className={styles.introText}>
          Where to find the best pain au chocolat in Paris, scored from the Google reviews that actually talk about
          it, not from the bakery&apos;s overall rating.
        </p>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionHeading}>Coverage</h3>
        <div className={styles.kpis}>
          <KpiCard value={formatInt(meta.n_places)} label="Bakeries loaded" />
          <KpiCard
            value={avgScore}
            unit="/10"
            label="Weighted average score"
            accentColor={scoreToColor(meta.avg_score)}
          />
          <KpiCard value={`${meta.coverage_pct.toFixed(0)}`} unit="%" label="Places with a score" />
          <KpiCard value={formatInt(meta.n_reviews)} label="Reviews analysed" />
        </div>
        <p className={styles.lastReview}>Last review collected: {formatDate(meta.last_review_at)}</p>
      </section>

      <hr className={styles.divider} />

      <section className={styles.section}>
        <h3 className={styles.sectionHeading}>How the score is calculated</h3>
        <ol className={styles.stepper}>
          {STEPS.map((step) => (
            <li key={step.title} className={styles.step}>
              <h4 className={styles.stepTitle}>{step.title}</h4>
              <p className={styles.stepBody}>{step.body}</p>
            </li>
          ))}
        </ol>
        <Alert tone="info">
          A place with no pain au chocolat mention in its reviews has <strong>no</strong> score by default. It shows
          up grey on the map rather than being assigned a made-up value.
        </Alert>
      </section>
    </div>
  );
}
