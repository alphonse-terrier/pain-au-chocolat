import styles from "./KpiCard.module.css";

export default function KpiCard({
  value,
  unit,
  label,
  icon,
  accentColor,
}: {
  value: string;
  unit?: string;
  label: string;
  icon?: string;
  accentColor?: string;
}) {
  return (
    <div className={styles.card}>
      {icon && (
        <span className={styles.icon} aria-hidden="true">
          {icon}
        </span>
      )}
      <div className={styles.label}>{label}</div>
      <div className={`${styles.value} tnum`} style={accentColor ? { color: accentColor } : undefined}>
        {value}
        {unit && <span className={styles.unit}>{unit}</span>}
      </div>
    </div>
  );
}
