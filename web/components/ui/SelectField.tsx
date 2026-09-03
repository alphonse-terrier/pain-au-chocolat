"use client";

import { useId } from "react";
import { Chevron } from "./icons";
import styles from "./SelectField.module.css";

export default function SelectField<T extends string>({
  label,
  hideLabel,
  value,
  onChange,
  options,
}: {
  label: string;
  hideLabel?: boolean;
  value: T;
  onChange: (v: T) => void;
  options: Array<{ value: T; label: string }>;
}) {
  const id = useId();
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={hideLabel ? "visually-hidden" : styles.label}>
        {label}
      </label>
      <div className={styles.selectWrap}>
        <select id={id} className={styles.select} value={value} onChange={(e) => onChange(e.target.value as T)}>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <Chevron size={10} direction="down" className={styles.chevron} />
      </div>
    </div>
  );
}
