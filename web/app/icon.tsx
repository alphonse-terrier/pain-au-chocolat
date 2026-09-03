import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

/** Browser-tab favicon -- the site's own croissant, not the default
 * Next.js/Vercel triangle nobody ever replaced. Transparent background:
 * at this size the emoji glyph reads fine against any tab chrome. */
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 26,
        }}
      >
        🥐
      </div>
    ),
    { ...size }
  );
}
