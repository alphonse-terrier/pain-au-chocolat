import { ImageResponse } from "next/og";
import Logo from "@/components/ui/Logo";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "The best pain au chocolat in Paris — a very important, extremely serious ranking";

/** Social preview card for links (Slack, iMessage, X/Twitter, WhatsApp...).
 * Generated at request/build time via Satori rather than a static asset,
 * so it always matches the live title/tagline in layout.tsx and the
 * site's own palette (globals.css crust/cacao tokens) instead of drifting
 * out of sync with a hand-exported PNG. Text stays on a plain sans face --
 * Satori renders from font bytes, not the app's next/font CSS variables,
 * and committing a Fraunces binary just for this card isn't worth being
 * the repo's first binary asset. */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(135deg, #f3e4cd 0%, #f3d79a 100%)",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", marginBottom: 20 }}>
          <Logo size={220} tone="duo" detail crust="#a97a1c" choc="#2e1608" crumb="#fef7e8" />
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 68,
            fontWeight: 800,
            color: "#241a11",
            textAlign: "center",
            letterSpacing: "-0.02em",
            padding: "0 60px",
          }}
        >
          The best pain au chocolat in Paris
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 30,
            color: "#6e5d45",
            marginTop: 28,
            textAlign: "center",
            padding: "0 130px",
          }}
        >
          A very important, extremely serious ranking of who&apos;s actually good at pastry
        </div>
      </div>
    ),
    { ...size }
  );
}
