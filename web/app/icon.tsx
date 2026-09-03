import { ImageResponse } from "next/og";
import Logo from "@/components/ui/Logo";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

/** Browser-tab favicon -- the site's own pain-au-chocolat mark, not the
 * default Next.js/Vercel triangle nobody ever replaced (and not the 🥐
 * croissant emoji it briefly became -- wrong pastry). Opaque crust-gold
 * plate rather than a transparent background: a dark mono mark on nothing
 * disappears against dark tab chrome. */
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
          background: "#f3d79a",
          borderRadius: 7,
        }}
      >
        <Logo size={22} tone="mono" color="#2e1608" />
      </div>
    ),
    { ...size }
  );
}
