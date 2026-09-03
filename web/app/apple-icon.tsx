import { ImageResponse } from "next/og";
import Logo from "@/components/ui/Logo";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** iOS home-screen icon -- iOS applies its own rounded-corner mask on top
 * of whatever we give it, so (unlike the tab favicon) this needs an opaque
 * background rather than transparency. Cream field (globals.css
 * --crust-25) so it matches the app's parchment palette. */
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
          background: "#f3e4cd",
        }}
      >
        <Logo size={116} tone="duo" detail crust="#a97a1c" choc="#2e1608" crumb="#fef7e8" />
      </div>
    ),
    { ...size }
  );
}
