import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "The best pain au chocolat in Paris — a very important, extremely serious ranking";

/** Social preview card for links (Slack, iMessage, X/Twitter, WhatsApp...).
 * Generated at request/build time via Satori rather than a static asset,
 * so it always matches the live title/tagline in layout.tsx and the
 * site's own palette (globals.css amber tokens) instead of drifting out
 * of sync with a hand-exported PNG. */
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
          background: "linear-gradient(135deg, #fdf6ec 0%, #f8e8cf 100%)",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", fontSize: 150, marginBottom: 12 }}>🥐</div>
        <div
          style={{
            display: "flex",
            fontSize: 68,
            fontWeight: 800,
            color: "#1c1a16",
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
            color: "#6b675c",
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
