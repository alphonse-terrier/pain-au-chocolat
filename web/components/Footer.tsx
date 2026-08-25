import styles from "./Footer.module.css";

const ITEMS = [
  "🙈 Yes, we scraped Google for this. We know, we know",
  "🎭 Reviewer names are pseudonymised, not the real Google ones",
  "💸 100% free, no ads, no upsell",
  "🇫🇷 Made with love (and a lot of pain au chocolat) in France",
];

/** Thin disclaimer strip, always visible -- covers the four things people
 * actually ask about: a wink acknowledging the scraping (not a warning
 * TO scrapers -- this project's own data source, said with a shrug);
 * reviewer names are pseudonymised, not the real Google ones; it's free;
 * it's a labour of love, not a startup. Each item is its own list entry
 * (not one long string) so it wraps cleanly on narrow screens instead of
 * splitting mid-sentence. */
export default function Footer() {
  return (
    <footer className={styles.footer}>
      <ul className={styles.list}>
        {ITEMS.map((item) => (
          <li key={item} className={styles.item}>
            {item}
          </li>
        ))}
      </ul>
    </footer>
  );
}
