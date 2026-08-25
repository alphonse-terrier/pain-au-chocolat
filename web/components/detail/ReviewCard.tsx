"use client";

import { useState } from "react";
import type { Review } from "@/lib/types";
import { formatStars, SENTIMENT_COLORS } from "@/lib/theme";
import styles from "./ReviewCard.module.css";

const CLAMP_CHARS = 320;

export default function ReviewCard({ review }: { review: Review }) {
  const [expanded, setExpanded] = useState(false);
  const positive = review.s >= 0;
  const tone = positive ? SENTIMENT_COLORS.positive : SENTIMENT_COLORS.negative;
  const meta = [review.r !== null ? formatStars(review.r) : null, review.w].filter(Boolean).join(" · ");
  const text = review.t ?? "";
  const isLong = text.length > CLAMP_CHARS;

  return (
    <div className={styles.card} style={{ borderLeftColor: tone }}>
      <div className={styles.header}>
        <span className={styles.author}>{review.a ?? "Anonymous"}</span>
        <span className={styles.sentiment} style={{ color: tone }}>
          <span className={styles.dot} style={{ background: tone }} aria-hidden="true" />
          {positive ? "Positive" : "Negative"}
        </span>
      </div>
      <p className={`${styles.body} ${expanded || !isLong ? "" : styles.clamped}`}>{text}</p>
      {isLong && (
        <button type="button" className={styles.showMore} onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
      {meta && <div className={styles.meta}>{meta}</div>}
    </div>
  );
}
