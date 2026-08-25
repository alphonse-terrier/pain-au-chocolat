"use client";

import { useEffect, useState } from "react";
import type { Place, Review } from "@/lib/types";
import { fetchPlaceReviews } from "@/lib/reviews";
import PlaceSummary from "./PlaceSummary";
import ReviewList from "./ReviewList";
import DetailEmptyState from "./DetailEmptyState";
import styles from "./PlaceDetailPanel.module.css";

type Status = "idle" | "loading" | "ready";

export default function PlaceDetailPanel({
  place,
  topPlaces = [],
  onSelectPlace,
}: {
  place: Place | null;
  /** Highest-scored places in the current filtered view, shown when
   * nothing is selected. */
  topPlaces?: Place[];
  onSelectPlace?: (placeId: string) => void;
}) {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [status, setStatus] = useState<Status>("idle");

  useEffect(() => {
    if (!place) {
      setReviews([]);
      setStatus("idle");
      return;
    }
    let cancelled = false;
    // Reset synchronously on every selection change (keyed on place_id,
    // not the object reference) -- otherwise the previous bakery's
    // reviews stay on screen under the new bakery's name while the new
    // shard is still in flight.
    setReviews([]);
    setStatus("loading");
    fetchPlaceReviews(place.place_id).then((data) => {
      if (!cancelled) {
        setReviews(data.reviews);
        setStatus("ready");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [place?.place_id]); // eslint-disable-line react-hooks/exhaustive-deps -- keyed on id, not the object

  if (!place) {
    return (
      <aside className={styles.panel} aria-label="Bakery details">
        <DetailEmptyState topPlaces={topPlaces.slice(0, 5)} onSelect={(id) => onSelectPlace?.(id)} />
      </aside>
    );
  }

  return (
    <aside className={styles.panel} aria-label="Bakery details">
      <h2 className={styles.name}>{place.name}</h2>
      <p className={styles.address}>{place.address}</p>
      <PlaceSummary place={place} showScore />
      <ReviewList reviews={reviews} showControls loading={status === "loading"} />
    </aside>
  );
}
