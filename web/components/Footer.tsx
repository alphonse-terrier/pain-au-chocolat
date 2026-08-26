import styles from "./Footer.module.css";

const ITEMS = [
  "🙈 Yes, we scraped Google for this. We know, we know",
  "🎭 Reviewer names are pseudonymised, not the real Google ones",
  "💸 100% free, no ads, no upsell",
  "🇫🇷 Made with love (and a lot of pain au chocolat) in France",
  "🥦 Eat five fruits and vegetables a day",
  "⚠️ Eat pain au chocolat at your own risk",
];

/** Thin disclaimer strip, always visible -- covers the things people
 * actually ask about (scraping, pseudonymised names, free, made in
 * France) plus two tongue-in-cheek "official-sounding" health notices, in
 * keeping with the site's deadpan-serious-institution voice. Each item is
 * its own list entry (not one long string) so it wraps cleanly on narrow
 * screens instead of splitting mid-sentence. */
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
