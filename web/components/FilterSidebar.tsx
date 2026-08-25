"use client";

import type { Filters } from "@/lib/types";
import { countActiveFilters, FILTER_DEFAULTS } from "@/lib/filters";
import { formatDate } from "@/lib/format";
import { ChipMultiselect, CheckboxField, RangeField, SliderField, TextField } from "./ui/Controls";
import Button from "./ui/Button";
import styles from "./FilterSidebar.module.css";

const ARRONDISSEMENTS = Array.from({ length: 20 }, (_, i) => i + 1);

export default function FilterSidebar({
  filters,
  onChange,
  lastReviewAt,
  onClose,
}: {
  filters: Filters;
  onChange: (patch: Partial<Filters>) => void;
  lastReviewAt: string | null;
  /** Present only when rendered inside the mobile drawer -- shows a close
   * button; the static desktop sidebar passes nothing. */
  onClose?: () => void;
}) {
  const activeCount = countActiveFilters(filters);

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <h2 className={styles.heading}>Filters</h2>
        <div className={styles.headerActions}>
          <Button variant="ghost" size="sm" disabled={activeCount === 0} onClick={() => onChange(FILTER_DEFAULTS)}>
            Reset
          </Button>
          {onClose && (
            <button type="button" className={styles.closeBtn} aria-label="Close filters" onClick={onClose}>
              ×
            </button>
          )}
        </div>
      </div>

      <TextField label="Search by name" value={filters.q} onChange={(q) => onChange({ q })} />

      <ChipMultiselect
        label="Arrondissement"
        hint="Paris administrative district (1-20)"
        options={ARRONDISSEMENTS}
        selected={filters.arr}
        onToggle={(v) =>
          onChange({ arr: filters.arr.includes(v) ? filters.arr.filter((x) => x !== v) : [...filters.arr, v].sort((a, b) => a - b) })
        }
        onClear={() => onChange({ arr: [] })}
      />

      <RangeField
        label="Score"
        min={0}
        max={10}
        step={0.5}
        valueMin={filters.smin}
        valueMax={filters.smax}
        onChangeMin={(smin) => onChange({ smin })}
        onChangeMax={(smax) => onChange({ smax })}
      />
      <CheckboxField
        label="Include places without a score yet"
        checked={filters.unscored}
        onChange={(unscored) => onChange({ unscored })}
      />

      <SliderField
        label="Minimum Google rating"
        min={0}
        max={5}
        step={0.5}
        value={filters.grate}
        onChange={(grate) => onChange({ grate })}
        format={(v) => v.toFixed(1)}
      />

      <SliderField
        label="Minimum pain-au-chocolat reviews"
        hint="Places with fewer than this many retained pain-au-chocolat/viennoiserie reviews are hidden."
        min={0}
        max={100}
        step={1}
        value={filters.nrel}
        onChange={(nrel) => onChange({ nrel })}
      />

      <hr className={styles.divider} />
      <p className={styles.lastReview}>Last review collected: {formatDate(lastReviewAt)}</p>
    </div>
  );
}
