"use client";

import { useEffect, useState } from "react";
import type { Place, Review } from "@/lib/types";
import { fetchPlaceReviews } from "@/lib/reviews";
import { formatDistance, formatWalkTime } from "@/lib/format";
import PlaceSummary from "../detail/PlaceSummary";
import ReviewList from "../detail/ReviewList";
import ScoreBar from "../ranking/ScoreBar";
import Button from "../ui/Button";
import styles from "./NearbyResultCard.module.css";

export default function NearbyResultCard({
  place,
  distanceM,
  rank,
}: {
  place: Place;
  distanceM: number;
  rank: number;
}) {
  const [open, setOpen] = useState(false);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    fetchPlaceReviews(place.place_id).then((data) => {
      if (!cancelled) {
        setReviews(data.reviews);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [open, place.place_id]);

  const reviewsId = `nearby-reviews-${place.place_id}`;

  return (
    <div className={styles.card}>
      <div className={styles.headerRow}>
        <span className={styles.rank}>{rank}</span>
        <div className={styles.headerMain}>
          <p className={styles.name}>{place.name}</p>
          <p className={styles.address}>{place.address}</p>
        </div>
        <div className={styles.distance}>
          <span className={`${styles.distanceValue} tnum`}>{formatDistance(distanceM)}</span>
          <span className={styles.walkTime}>{formatWalkTime(distanceM)}</span>
        </div>
      </div>
      <ScoreBar score={place.score_10} size="lg" />
      <PlaceSummary place={place} showScore={false} />
      <Button
        variant="ghost"
        size="sm"
        aria-expanded={open}
        aria-controls={reviewsId}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Enough, thanks" : `Read the ${place.n_relevant} reviews`}
      </Button>
      <div id={reviewsId} className={styles.reveal} data-open={open || undefined}>
        <div className={styles.revealInner}>
          {open && <ReviewList reviews={reviews} showControls={false} compact loading={loading} />}
        </div>
      </div>
    </div>
  );
}
