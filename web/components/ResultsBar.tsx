import type { ReactNode } from "react";
import { formatInt } from "@/lib/format";
import styles from "./ResultsBar.module.css";

export default function ResultsBar({
  shown,
  total,
  activeFilterCount,
  onReset,
  onOpenFilters,
  actions,
}: {
  shown: number;
  total: number;
  activeFilterCount: number;
  onReset: () => void;
  /** Present only below the lg breakpoint -- opens the filter drawer. */
  onOpenFilters?: () => void;
  actions?: ReactNode;
}) {
  const filtered = shown !== total;
  return (
    <div className={styles.bar}>
      <div className={styles.left}>
        {onOpenFilters && (
          <button type="button" className={styles.filtersBtn} onClick={onOpenFilters} aria-controls="filters" aria-label={`Filters${activeFilterCount ? `, ${activeFilterCount} active` : ""}`}>
            Filters
            {activeFilterCount > 0 && <span className={styles.badge}>{activeFilterCount}</span>}
          </button>
        )}
        <p className={styles.count} role="status" aria-live="polite" aria-atomic="true">
          {shown === 0 ? (
            <>No bakeries match</>
          ) : filtered ? (
            <>
              <strong className="tnum">{formatInt(shown)}</strong> of {formatInt(total)} bakeries
            </>
          ) : (
            <>
              <strong className="tnum">{formatInt(total)}</strong> bakeries
            </>
          )}
          {activeFilterCount > 0 && (
            <>
              {" "}
              · {activeFilterCount} filter{activeFilterCount > 1 ? "s" : ""} active{" "}
              <button type="button" className={styles.resetLink} onClick={onReset}>
                Reset
              </button>
            </>
          )}
        </p>
      </div>
      {actions && <div className={styles.right}>{actions}</div>}
    </div>
  );
}
