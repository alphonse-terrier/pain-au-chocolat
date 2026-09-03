import styles from "./KpiCard.module.css";

export default function KpiCard({
  value,
  unit,
  label,
  accentColor,
}: {
  value: string;
  unit?: string;
  label: string;
  accentColor?: string;
}) {
  return (
    <div className={styles.card}>
      <div className={styles.label}>{label}</div>
      <div className={`${styles.value} tnum`} style={accentColor ? { color: accentColor } : undefined}>
        {value}
        {unit && <span className={styles.unit}>{unit}</span>}
      </div>
    </div>
  );
}
