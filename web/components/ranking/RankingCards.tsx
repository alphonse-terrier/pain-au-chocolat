"use client";

import { useMemo } from "react";
import type { Place } from "@/lib/types";
import { RANKING_COLUMNS, sortPlaces } from "@/lib/ranking";
import { formatPercent, formatStars } from "@/lib/theme";
import SelectField from "../ui/SelectField";
import ScoreBar from "./ScoreBar";
import styles from "./RankingCards.module.css";

const SORTABLE = RANKING_COLUMNS.filter((c) => ["score_10", "google_rating", "positive_ratio", "n_relevant", "name"].includes(c.key));

/** Mobile equivalent of RankingTable -- a 9-column nowrap table is
 * unusable at 375px and would hide the score column, the entire point of
 * the page. Same sorted array/props as the table so they can't diverge. */
export default function RankingCards({
  places,
  sort,
  dir,
  onSort,
  onSelect,
}: {
  places: Place[];
  sort: string;
  dir: "asc" | "desc";
  onSort: (col: string) => void;
  onSelect: (placeId: string) => void;
}) {
  const sorted = useMemo(() => sortPlaces(places, sort, dir), [places, sort, dir]);

  return (
    <div>
      <div className={styles.sortRow}>
        <SelectField
          label="Sort by"
          value={sort}
          onChange={onSort}
          options={SORTABLE.map((c) => ({ value: c.key, label: c.label }))}
        />
        <button
          type="button"
          className={styles.dirBtn}
          onClick={() => onSort(sort)}
          aria-label={dir === "desc" ? "Sort ascending" : "Sort descending"}
        >
          {dir === "desc" ? "↓" : "↑"}
        </button>
      </div>
      <ul className={styles.list}>
        {sorted.map((p, i) => (
          <li key={p.place_id}>
            <button type="button" className={styles.card} onClick={() => onSelect(p.place_id)}>
              <div className={styles.topRow}>
                <span className={styles.rank}>{i + 1}</span>
                <div className={styles.nameCol}>
                  <p className={styles.name}>{p.name}</p>
                  <p className={styles.address}>{p.address}</p>
                </div>
              </div>
              <ScoreBar score={p.score_10} size="lg" />
              <div className={styles.chips}>
                {p.arrondissement && <span className={styles.chip}>{p.arrondissement}e</span>}
                <span className={styles.chip}>{formatStars(p.google_rating)}</span>
                <span className={styles.chip}>{formatPercent(p.positive_ratio)} positive</span>
                <span className={styles.chip}>{p.n_relevant} mentions</span>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
