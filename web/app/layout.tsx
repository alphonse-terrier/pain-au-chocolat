import type { Metadata, Viewport } from "next";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { inter } from "./fonts";
import "./globals.css";

const TITLE = "The best pain au chocolat in Paris";
const DESCRIPTION =
  "The internet's most scientific ranking of Paris bakeries, based purely on who nails the pain au chocolat, not on how nice the croissants look on Instagram.";
const SITE_URL = "https://painauchoc.com";

export const metadata: Metadata = {
  // Resolves every relative URL below (og:image, canonical, ...) into an
  // absolute one -- required for social platforms, which won't fetch a
  // relative og:image.
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  keywords: ["pain au chocolat", "chocolatine", "boulangerie Paris", "meilleure boulangerie Paris", "croissant"],
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: "/",
    siteName: TITLE,
    locale: "en_US",
    type: "website",
    // og:image itself comes from app/opengraph-image.tsx (file convention
    // -- Next generates and injects it automatically, no need to list it
    // here too).
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
  },
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
