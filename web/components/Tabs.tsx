import type { Tab } from "@/lib/filters";
import styles from "./Tabs.module.css";

const LABELS: Record<Tab, { full: string; short: string }> = {
  map: { full: "Map", short: "Map" },
  ranking: { full: "Leaderboard", short: "Ranking" },
  nearby: { full: "Near me", short: "Nearby" },
  about: { full: "The Fine Print", short: "About" },
};

const ORDER: Tab[] = ["map", "ranking", "nearby", "about"];

export default function Tabs({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  function onKeyDown(e: React.KeyboardEvent, index: number) {
    let next = index;
    if (e.key === "ArrowRight") next = (index + 1) % ORDER.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + ORDER.length) % ORDER.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = ORDER.length - 1;
    else return;
    e.preventDefault();
    onChange(ORDER[next]);
    (document.getElementById(`tab-${ORDER[next]}`) as HTMLElement | null)?.focus();
  }

  return (
    <nav aria-label="Views" className={styles.nav}>
      <div className={styles.list} role="tablist">
        {ORDER.map((tab, i) => (
          <button
            key={tab}
            id={`tab-${tab}`}
            type="button"
            role="tab"
            aria-selected={active === tab}
            aria-controls={`panel-${tab}`}
            tabIndex={active === tab ? 0 : -1}
            className={`${styles.tab} ${active === tab ? styles.tabActive : ""}`}
            onClick={() => onChange(tab)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            <span className={styles.labelFull}>{LABELS[tab].full}</span>
            <span className={styles.labelShort}>{LABELS[tab].short}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}
