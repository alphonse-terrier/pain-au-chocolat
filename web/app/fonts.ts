import { Fraunces, Inter } from "next/font/google";

/** Self-hosted by next/font at build time (no runtime request to Google,
 * no layout shift via size-adjust fallback metrics). Inter specifically
 * because this app is dense numeric UI (scores, ratings, table cells) and
 * Inter has real tabular figures, which the system font stack does not
 * reliably provide. */
export const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

/** Display face only -- headings and the hero score numeral (the .display
 * utility class in globals.css), never body text, never tables, never KPI
 * values: Inter keeps those. Variable font with its SOFT/WONK axes active
 * (a warm, hand-lettered-shopfront feel rather than a textbook serif) --
 * self-hosted by next/font like Inter, so this is one more named import
 * from an already-used module, not a new dependency category. */
export const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  axes: ["SOFT", "WONK", "opsz"],
  variable: "--font-display",
});
