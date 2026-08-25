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
      <p className={styles.caption}>
        A very important, extremely serious ranking of who&apos;s actually good at pastry, not just good at getting
        five stars.
      </p>
    </header>
  );
}
