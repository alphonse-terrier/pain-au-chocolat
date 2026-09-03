"use client";

import { useMemo } from "react";
import type { Place } from "@/lib/types";
import { RANKING_COLUMNS, sortPlaces } from "@/lib/ranking";
import { formatPercent, formatStars, scoreToColor } from "@/lib/theme";
import { formatInt } from "@/lib/format";
import ScoreBar from "./ScoreBar";
import ConfidencePill from "../detail/ConfidencePill";
import { Chevron } from "../ui/icons";
import styles from "./RankingTable.module.css";

export default function RankingTable({
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
  const isTopRank = sort === "score_10" && dir === "desc";

  function renderCell(col: (typeof RANKING_COLUMNS)[number], p: Place) {
    if (col.isAspect) {
      const v = col.get(p) as number | null;
      if (v === null) return <span className="tnum">—</span>;
      return (
        <span className="tnum" style={{ color: scoreToColor(v), fontWeight: 600 }}>
          {v.toFixed(1)}
        </span>
      );
    }
    switch (col.key) {
      case "name":
        return (
          <button type="button" className={styles.nameBtn} onClick={() => onSelect(p.place_id)}>
            {p.name}
          </button>
        );
      case "google_rating":
        return formatStars(p.google_rating);
      case "score_10":
        return <ScoreBar score={p.score_10} />;
      case "positive_ratio":
        return formatPercent(p.positive_ratio);
      case "confidence":
        return <ConfidencePill confidence={p.confidence} />;
      case "user_rating_count":
      case "n_relevant":
      case "arrondissement":
        return <span className="tnum">{col.get(p) ?? "—"}</span>;
      default:
        return col.get(p) ?? "—";
    }
  }

  return (
    <div className={styles.wrap}>
      <table>
        <caption className="visually-hidden">Paris bakeries ranked by pain au chocolat score</caption>
        <thead>
          <tr>
            <th scope="col" className={styles.rankHeader}>
              #
            </th>
            {RANKING_COLUMNS.map((c) => (
              <th
                key={c.key}
                scope="col"
                data-priority={c.priority}
                className={c.key === sort ? styles.active : undefined}
                aria-sort={c.key === sort ? (dir === "asc" ? "ascending" : "descending") : "none"}
              >
                <button type="button" className={styles.sortBtn} onClick={() => onSort(c.key)}>
                  {c.label}
                  {c.key === sort ? (
                    <Chevron size={10} direction={dir === "asc" ? "up" : "down"} className={styles.chevron} />
                  ) : (
                    <span className={styles.chevronPair}>
                      <Chevron size={10} direction="up" />
                      <Chevron size={10} direction="down" />
                    </span>
                  )}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p, i) => (
            <tr key={p.place_id}>
              <td className={`${styles.rankCell} tnum`}>
                {isTopRank && i < 3 ? <span className={styles.topBadge}>{i + 1}</span> : i + 1}
              </td>
              {RANKING_COLUMNS.map((c) => (
                <td key={c.key} data-priority={c.priority} data-key={c.key}>
                  {renderCell(c, p)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className={styles.count}>{formatInt(sorted.length)} rows</p>
    </div>
  );
}
