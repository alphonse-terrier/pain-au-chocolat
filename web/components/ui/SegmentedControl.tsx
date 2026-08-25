"use client";

import { useId } from "react";
import styles from "./SegmentedControl.module.css";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  count?: number;
  disabled?: boolean;
}

/** A native radiogroup (visually-hidden radios inside labels) rather than
 * a row of aria-pressed buttons -- the options here are mutually
 * exclusive, so radios buy native arrow-key roving focus and
 * :focus-visible for free with zero JS. */
export default function SegmentedControl<T extends string>({
  legend,
  options,
  value,
  onChange,
}: {
  legend: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (v: T) => void;
}) {
  const name = useId();
  return (
    <fieldset className={styles.fieldset}>
      <legend className="visually-hidden">{legend}</legend>
      <div className={styles.group} role="radiogroup" aria-label={legend}>
        {options.map((opt) => (
          <label
            key={opt.value}
            className={`${styles.segment} ${value === opt.value ? styles.active : ""} ${opt.disabled ? styles.disabled : ""}`}
          >
            <input
              type="radio"
              name={name}
              value={opt.value}
              checked={value === opt.value}
              disabled={opt.disabled}
              onChange={() => onChange(opt.value)}
              className="visually-hidden"
            />
            {opt.label}
            {opt.count !== undefined && <span className={styles.count}>{opt.count}</span>}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
