import { Inter } from "next/font/google";

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
