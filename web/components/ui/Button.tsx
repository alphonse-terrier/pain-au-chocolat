"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./Button.module.css";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
  iconLeft?: ReactNode;
  loading?: boolean;
  children: ReactNode;
}

/** The one button primitive in the app -- everything (CSV export, Nearby
 * search, Reset filters, disclosure toggles, retry) routes through this
 * instead of a raw unstyled <button>. */
export default function Button({
  variant = "secondary",
  size = "md",
  iconLeft,
  loading = false,
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`${styles.btn} ${styles[variant]} ${styles[size]} ${className ?? ""}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : iconLeft}
      <span>{children}</span>
    </button>
  );
}
