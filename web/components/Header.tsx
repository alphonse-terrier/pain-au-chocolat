import type { ReactNode } from "react";
import styles from "./Header.module.css";

export default function Header({ actions }: { actions?: ReactNode }) {
  return (
    <header className={styles.header}>
      <div className={styles.titleRow}>
        <h1 className={styles.title}>
          <span aria-hidden="true">🥐</span> The best pain au chocolat in Paris
        </h1>
        {actions}
      </div>
      <p className={styles.caption}>Scored from the Google reviews that actually talk about it, not the bakery&apos;s overall rating.</p>
    </header>
  );
}
