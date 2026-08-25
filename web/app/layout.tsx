import type { Metadata, Viewport } from "next";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { inter } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "The best pain au chocolat in Paris",
  description:
    "Where to find the best pain au chocolat in Paris, scored from the Google reviews that actually talk about it, not from the bakery's overall rating.",
};

// viewportFit: "cover" is required for env(safe-area-inset-*) to resolve
// to anything other than 0 -- needed by the mobile bottom sheet and the
// filter drawer (cf. plan).
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <a href="#main" className="skipLink">
          Skip to content
        </a>
        <NuqsAdapter>{children}</NuqsAdapter>
      </body>
    </html>
  );
}
