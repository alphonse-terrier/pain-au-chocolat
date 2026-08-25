import styles from "./Skeleton.module.css";

export default function Skeleton({
  width = "100%",
  height = "1em",
  radius = "var(--r-sm)",
}: {
  width?: string | number;
  height?: string | number;
  radius?: string;
}) {
  return (
    <span
      className={styles.skeleton}
      style={{ width, height, borderRadius: radius }}
      aria-hidden="true"
    />
  );
}
