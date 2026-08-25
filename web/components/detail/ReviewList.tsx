"use client";

import { useMemo, useState } from "react";
import type { Review } from "@/lib/types";
import ReviewCard from "./ReviewCard";
import Skeleton from "../ui/Skeleton";
import SegmentedControl from "../ui/SegmentedControl";
import SelectField from "../ui/SelectField";
import EmptyState from "../ui/EmptyState";
import styles from "./ReviewList.module.css";

type Tone = "all" | "positive" | "negative";
type Sort = "relevance" | "recent";

/** Full scrollable review list -- tone/sort controls on the map detail
 * panel (showControls=true), none on the Nearby tab's cards (matches
 * app.py: the nearby tab always shows the SQL default order, no filter
 * widgets). Tone/sort are plain component state, not URL state (cf. plan
 * -- only filters/tab/selection are worth bookmarking). */
export default function ReviewList({
  reviews,
  showControls,
  compact,
  loading = false,
}: {
  reviews: Review[];
  showControls: boolean;
  compact?: boolean;
  loading?: boolean;
}) {
  const [tone, setTone] = useState<Tone>("all");
  const [sort, setSort] = useState<Sort>("relevance");

  const counts = useMemo(
    () => ({
      all: reviews.length,
      positive: reviews.filter((r) => r.s >= 0).length,
      negative: reviews.filter((r) => r.s < 0).length,
    }),
    [reviews]
  );

  const shown = useMemo(() => {
    let out = reviews;
    if (tone === "positive") out = out.filter((r) => r.s >= 0);
    if (tone === "negative") out = out.filter((r) => r.s < 0);
    if (sort === "recent") {
      out = [...out].sort((a, b) => (b.p ?? -Infinity) - (a.p ?? -Infinity));
    } else {
      out = [...out].sort((a, b) => b.s - a.s);
    }
    return out;
  }, [reviews, tone, sort]);

  if (loading) {
    return (
      <div className={`${styles.scroll} ${compact ? styles.scrollSmall : ""}`}>
        {[0, 1, 2].map((i) => (
          <div key={i} className={styles.skeletonCard}>
            <Skeleton width="40%" height="14px" />
            <Skeleton width="100%" height="14px" />
            <Skeleton width="80%" height="14px" />
          </div>
        ))}
      </div>
    );
  }

  if (reviews.length === 0) {
    return (
      <EmptyState
        title="Radio silence on the pastry front"
        body="Nobody's reviews mention pain au chocolat here, so this place stays a mystery (and unscored)."
      />
    );
  }

  return (
    <div className={styles.wrap}>
      {showControls && (
        <div className={styles.controls}>
          <SegmentedControl
            legend="Tone"
            value={tone}
            onChange={setTone}
            options={[
              { value: "all", label: "All", count: counts.all },
              { value: "positive", label: "Positive", count: counts.positive, disabled: counts.positive === 0 },
              { value: "negative", label: "Negative", count: counts.negative, disabled: counts.negative === 0 },
            ]}
          />
          <SelectField
            label="Sort"
            value={sort}
            onChange={setSort}
            options={[
              { value: "relevance", label: "Relevance" },
              { value: "recent", label: "Most recent" },
            ]}
          />
        </div>
      )}
      <div className={`${styles.scroll} ${compact ? styles.scrollSmall : ""}`}>
        {shown.length === 0 ? (
          <EmptyState
            title="Crickets"
            body="Nothing in that mood right now."
            action={
              <button type="button" className={styles.resetTone} onClick={() => setTone("all")}>
                Show everything
              </button>
            }
          />
        ) : (
          shown.map((r, i) => <ReviewCard key={`${r.a ?? ""}-${r.p ?? i}-${r.t?.slice(0, 20) ?? i}`} review={r} />)
        )}
      </div>
    </div>
  );
}
