"use client";

import { useId } from "react";
import { scoreGradientCss } from "@/lib/theme";
import styles from "./Controls.module.css";

export function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const id = useId();
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <div className={styles.textInputWrap}>
        <svg className={styles.searchIcon} width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5" fill="none" />
          <path d="M11.5 11.5L15 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <input
          id={id}
          className={styles.textInput}
          type="search"
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
        {value && (
          <button
            type="button"
            className={styles.clearBtn}
            aria-label="Clear search"
            onClick={() => onChange("")}
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}

export function SliderField({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step,
  format,
}: {
  label: string;
  hint?: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <div className={styles.rangeRow}>
        <input
          id={id}
          className={styles.range}
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          aria-describedby={hintId}
          style={{ background: `linear-gradient(to right, var(--accent) ${pct}%, var(--surface-sunken) ${pct}%)` }}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <span className={`${styles.value} tnum`}>{format ? format(value) : value}</span>
      </div>
      {hint && (
        <span id={hintId} className={styles.hint}>
          {hint}
        </span>
      )}
    </div>
  );
}

/** Real dual-thumb range slider built from two overlapping native
 * <input type="range">, painted with the actual score-color gradient so
 * the filter doubles as the map's color legend. See plan §G for the
 * documented pitfalls this works around: vendor thumb pseudo-elements
 * can't be grouped in one CSS rule, the invisible input body must not
 * capture pointer events, and equal-valued thumbs need a z-index swap so
 * neither becomes permanently unpickable. */
export function RangeField({
  label,
  min,
  max,
  step,
  valueMin,
  valueMax,
  onChangeMin,
  onChangeMax,
  format,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  valueMin: number;
  valueMax: number;
  onChangeMin: (v: number) => void;
  onChangeMax: (v: number) => void;
  format?: (v: number) => string;
}) {
  const minId = useId();
  const maxId = useId();
  const fmt = format ?? ((v: number) => String(v));
  const pctMin = ((valueMin - min) / (max - min)) * 100;
  const pctMax = ((valueMax - min) / (max - min)) * 100;
  // When the two thumbs are close together, whichever renders on top
  // (later in the DOM = valueMax's input) grabs every pointer event near
  // it. Raise the min input above the max input once it's past the
  // midpoint of the current range, so it stays draggable.
  const minOnTop = valueMin > (min + max) / 2;

  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.label}>{label}</legend>
      <div className={styles.dualTrackRow}>
        <span className={`${styles.dualReadout} tnum`} style={{ color: "var(--accent-text)" }}>
          {fmt(valueMin)}
        </span>
        <div
          className={styles.dualTrack}
          style={{ background: `linear-gradient(to right, ${scoreGradientCss()})` }}
        >
          <div className={styles.dualTrackDim} style={{ left: 0, right: `${100 - pctMin}%` }} />
          <div className={styles.dualTrackDim} style={{ left: `${pctMax}%`, right: 0 }} />
          <input
            id={minId}
            type="range"
            className={styles.dualInput}
            style={{ zIndex: minOnTop ? 2 : 1 }}
            min={min}
            max={max}
            step={step}
            value={valueMin}
            aria-label={`Minimum ${label.toLowerCase()}`}
            aria-valuetext={`${fmt(valueMin)} out of ${fmt(max)}`}
            onChange={(e) => onChangeMin(Math.min(Number(e.target.value), valueMax))}
          />
          <input
            id={maxId}
            type="range"
            className={styles.dualInput}
            style={{ zIndex: minOnTop ? 1 : 2 }}
            min={min}
            max={max}
            step={step}
            value={valueMax}
            aria-label={`Maximum ${label.toLowerCase()}`}
            aria-valuetext={`${fmt(valueMax)} out of ${fmt(max)}`}
            onChange={(e) => onChangeMax(Math.max(Number(e.target.value), valueMin))}
          />
        </div>
        <span className={`${styles.dualReadout} tnum`} style={{ color: "var(--accent-text)" }}>
          {fmt(valueMax)}
        </span>
      </div>
    </fieldset>
  );
}

export function CheckboxField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className={styles.checkboxRow}>
      <input
        type="checkbox"
        className={styles.checkbox}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  );
}

export function ChipMultiselect({
  label,
  hint,
  options,
  selected,
  onToggle,
  onClear,
}: {
  label: string;
  hint?: string;
  options: number[];
  selected: number[];
  onToggle: (value: number) => void;
  onClear?: () => void;
}) {
  const selectedSet = new Set(selected);
  return (
    <fieldset className={styles.fieldset}>
      <div className={styles.chipHeader}>
        <legend className={styles.label}>{label}</legend>
        {onClear && selected.length > 0 && (
          <button type="button" className={styles.chipClear} onClick={onClear}>
            Clear ({selected.length})
          </button>
        )}
      </div>
      <div className={styles.chips} role="group" aria-label={label}>
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            aria-pressed={selectedSet.has(opt)}
            className={`${styles.chip} ${selectedSet.has(opt) ? styles.chipActive : ""}`}
            onClick={() => onToggle(opt)}
          >
            {selectedSet.has(opt) && (
              <svg className={styles.chipCheck} width="9" height="7" viewBox="0 0 9 7" aria-hidden="true">
                <path d="M1 3.5L3.2 6 8 1" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
            {opt}
          </button>
        ))}
      </div>
      {hint && <span className={styles.hint}>{hint}</span>}
    </fieldset>
  );
}
