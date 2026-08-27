import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** iOS home-screen icon -- iOS applies its own rounded-corner mask on top
 * of whatever we give it, so (unlike the tab favicon) this needs an opaque
 * background rather than transparency, or the mask reveals a checkerboard/
 * black square depending on device. Uses the site's own cream tint
 * (globals.css --amber-50) so it matches the app's palette. */
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#fdf6ec",
          fontSize: 120,
        }}
      >
        🥐
      </div>
    ),
    { ...size }
  );
}
