import type { ReactNode } from "react";
import Logo from "./ui/Logo";
import ShopWindow from "./ui/ShopWindow";
import styles from "./Header.module.css";

export default function Header({ actions }: { actions?: ReactNode }) {
  return (
    <header className={styles.header}>
      <div className={styles.titleRow}>
        <h1 className={`${styles.title} display`}>
          {/* The full illustrated scene is the header's real brand moment
              on tablet/desktop; on mobile the 100dvh shell can't spare
              that much height, so it falls back to the plain mark
              (still bigger than the old 22px). Toggled by CSS, not JS, to
              match the caption's existing responsive pattern below. */}
          <ShopWindow width={72} className={styles.logoDesktop} />
          <Logo size={30} className={styles.logoMobile} />
          The best pain au chocolat in Paris
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
