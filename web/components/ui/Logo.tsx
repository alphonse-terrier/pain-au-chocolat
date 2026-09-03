/** The site's mark: two chocolate batons in laminated dough, drawn flat
 * enough to read from a 16px favicon up to a 1200px OG card, and
 * deliberately NOT a croissant (no crescent) -- the app used to just reuse
 * the 🥐 emoji everywhere, which is a different pastry.
 *
 * Colors are literal hex defaults, not CSS custom properties: this
 * component is rendered in three contexts (the normal DOM, and three
 * `next/og` ImageResponse/Satori trees for the favicon/apple-icon/OG
 * image) and Satori cannot resolve CSS vars or `currentColor`
 * inheritance reliably. Callers that need to match the live palette pass
 * literal hex overrides (see app/icon.tsx etc. for the exact tokens used).
 *
 * `detail` (the fold seam + lamination arcs) auto-disables below 24px --
 * at favicon size those hairlines turn to mush, and the two-baton
 * silhouette alone is what actually reads at that scale. */
export default function Logo({
  size = 24,
  tone = "duo",
  detail,
  color = "#2e1608",
  crust = "#a97a1c",
  choc = "#2e1608",
  crumb = "#fef7e8",
  title,
  className,
}: {
  size?: number;
  tone?: "duo" | "mono";
  detail?: boolean;
  /** mono tone override */
  color?: string;
  /** duo tone overrides -- literal hex, see module docstring */
  crust?: string;
  choc?: string;
  crumb?: string;
  title?: string;
  className?: string;
}) {
  const showDetail = detail ?? size >= 24;
  const outline = tone === "mono" ? color : crust;
  const fill = tone === "mono" ? "none" : crumb;
  const batons = tone === "mono" ? color : choc;
  const bodyStroke = size < 24 ? 2.2 : 1.8;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
    >
      {title && <title>{title}</title>}
      {/* Loaf body: flat base, quarter-arc ends, shallow domed top -- the
          dome is what stops this reading as a plain rectangle/box. */}
      <path
        d="M2 18 L22 18 Q22 14.5 18.5 14.5 L18.5 8 Q17 4.6 12 4.6 Q7 4.6 5.5 8 L5.5 14.5 Q2 14.5 2 18 Z"
        fill={fill}
        stroke={outline}
        strokeWidth={bodyStroke}
        strokeLinejoin="round"
      />
      {/* Lamination arcs, painted before the batons so the batons read as
          embedded in the dough rather than stickered on top. Three
          separate conditionals rather than a wrapping <>...</> fragment --
          Satori (next/og's renderer, used for the favicon/OG images) can't
          handle React fragments in the tree. */}
      {showDetail && <path d="M4.4 8.9 Q12 8 19.6 8.9" stroke={batons} strokeWidth={1.1} opacity={0.35} fill="none" />}
      {showDetail && (
        <path d="M5.6 11.6 Q12 11 18.4 11.6" stroke={batons} strokeWidth={1.1} opacity={0.35} fill="none" />
      )}
      {/* Fold seam where the dough overlaps itself. */}
      {showDetail && <path d="M11.9 6.2 L11.9 8.4" stroke={batons} strokeWidth={1.4} strokeLinecap="round" />}
      {/* The two chocolate batons -- the only filled shapes, and the whole
          identity of the mark. */}
      <rect x="7.3" y="9" width="2.4" height="7" rx="1.2" fill={batons} />
      <rect x="14.3" y="9" width="2.4" height="7" rx="1.2" fill={batons} />
    </svg>
  );
}
