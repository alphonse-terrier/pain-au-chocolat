import Skeleton from "./ui/Skeleton";
import styles from "./AppSkeleton.module.css";

/** Shown in the content region while places.json loads. Header/Tabs are
 * already rendered around this (buildMeta is server-rendered), so only
 * the data-dependent region needs a placeholder. Fixed-height blocks
 * mirror the real layout so there's no layout shift on swap-in. */
export default function AppSkeleton() {
  return (
    <div className={styles.wrap}>
      <div className={styles.sidebar}>
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} height="34px" radius="var(--r-md)" />
        ))}
      </div>
      <div className={styles.main}>
        <Skeleton height="100%" radius="var(--r-lg)" />
      </div>
    </div>
  );
}
