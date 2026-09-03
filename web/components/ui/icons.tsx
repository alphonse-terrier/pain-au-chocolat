/** Small hand-drawn icon set for functional UI chrome -- consolidates what
 * used to be a handful of inconsistent inline SVGs (different viewBoxes,
 * different stroke weights) scattered across components, matching the
 * Logo mark's line weight instead. Deliberately not an icon library: six
 * icons, one shared construction, zero new dependency. */

interface IconProps {
  size?: number;
  className?: string;
}

const BASE = {
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true as const,
};

export function Chevron({ size = 14, className, direction = "down" }: IconProps & { direction?: "up" | "down" }) {
  const d = direction === "up" ? "M4 10 L8 6 L12 10" : "M4 6 L8 10 L12 6";
  return (
    <svg width={size} height={size} className={className} {...BASE}>
      <path d={d} />
    </svg>
  );
}

export function Pin({ size = 14, className }: IconProps) {
  return (
    <svg width={size} height={size} className={className} {...BASE}>
      <path d="M8 14.5s4.5-4.2 4.5-7.8A4.5 4.5 0 0 0 3.5 6.7C3.5 10.3 8 14.5 8 14.5z" />
      <circle cx="8" cy="6.6" r="1.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function Search({ size = 14, className }: IconProps) {
  return (
    <svg width={size} height={size} className={className} {...BASE}>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M13 13 L10.2 10.2" />
    </svg>
  );
}

export function Check({ size = 14, className }: IconProps) {
  return (
    <svg width={size} height={size} className={className} {...BASE}>
      <path d="M3.5 8.5 L6.5 11.5 L12.5 4.5" />
    </svg>
  );
}

export function Download({ size = 14, className }: IconProps) {
  return (
    <svg width={size} height={size} className={className} {...BASE}>
      <path d="M8 2.5 V10" />
      <path d="M4.5 7 L8 10.5 L11.5 7" />
      <path d="M3 13.5 H13" />
    </svg>
  );
}

export function Close({ size = 14, className }: IconProps) {
  return (
    <svg width={size} height={size} className={className} {...BASE}>
      <path d="M4 4 L12 12" />
      <path d="M12 4 L4 12" />
    </svg>
  );
}
