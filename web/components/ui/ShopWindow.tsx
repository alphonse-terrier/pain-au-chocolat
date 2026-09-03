/** A small illustrated scene -- an arched bakery shop window, a shelf, and
 * a few pastries sitting on it under a scalloped awning -- for the app's
 * two real "brand moment" spots (the desktop header, and the empty-state
 * hero in the map detail panel). The single `Logo` mark stays the
 * lightweight favicon/small-watermark asset; this is the bigger, more
 * illustrated sibling the redesign needed once a lone geometric mark
 * wasn't reading as illustration.
 *
 * Built from the same loaf+baton construction as `Logo` (three of them,
 * varied in scale/position/rotation for a hand-arranged-on-a-shelf feel)
 * rather than inventing a new drawing vocabulary. Literal hex color
 * props, same reasoning as `Logo`: kept Satori-compatible in case a
 * future brand surface needs it there too. */

const AWNING_WIDTH = 200;
const AWNING_Y = 10;
const SCALLOP_R = 7;

/** M-then-repeated-arcs path for a row of semicircle scallops. */
function scallopPath(width: number, y: number, r: number): string {
  const n = Math.round(width / (r * 2));
  const step = width / n;
  let d = `M0 ${y}`;
  for (let i = 0; i < n; i++) {
    const x = (i + 1) * step;
    d += ` A${step / 2} ${r} 0 0 1 ${x} ${y}`;
  }
  return d;
}

function Pastry({ x, rotate = 0, scale = 1, crust, choc }: { x: number; rotate?: number; scale?: number; crust: string; choc: string }) {
  return (
    <g transform={`translate(${x} 78) rotate(${rotate}) scale(${scale})`}>
      <path
        d="M-14 8 L14 8 Q14 4 10 4 L10 -2 Q9 -8 0 -8 Q-9 -8 -10 -2 L-10 4 Q-14 4 -14 8 Z"
        fill="none"
        stroke={crust}
        strokeWidth={1.6}
        strokeLinejoin="round"
      />
      <rect x="-6" y="-3" width="3.4" height="8" rx="1.4" fill={choc} />
      <rect x="1.4" y="-3" width="3.4" height="8" rx="1.4" fill={choc} />
    </g>
  );
}

export default function ShopWindow({
  width = 200,
  crust = "#a97a1c",
  choc = "#2e1608",
  crumb = "#fef7e8",
  className,
}: {
  width?: number;
  crust?: string;
  choc?: string;
  crumb?: string;
  className?: string;
}) {
  const height = (width / AWNING_WIDTH) * 112;
  return (
    <svg width={width} height={height} viewBox="0 0 200 112" fill="none" className={className} aria-hidden="true">
      {/* Awning */}
      <path d={scallopPath(AWNING_WIDTH, AWNING_Y, SCALLOP_R)} fill="none" stroke={choc} strokeWidth={1.6} strokeLinecap="round" />
      <path d={`M0 ${AWNING_Y} L200 ${AWNING_Y}`} stroke={crust} strokeWidth={2} />

      {/* Arched window frame */}
      <path
        d="M14 100 L14 46 Q14 14 100 14 Q186 14 186 46 L186 100"
        fill={crumb}
        stroke={crust}
        strokeWidth={2}
        strokeLinejoin="round"
      />
      <path d="M14 100 L14 46 Q14 14 100 14 Q186 14 186 46 L186 100" fill="none" stroke={crust} strokeWidth={2} />

      {/* Shelf */}
      <path d="M24 82 L176 82" stroke={choc} strokeWidth={2.2} strokeLinecap="round" />

      {/* Pastries, hand-arranged: varied scale/rotation/position */}
      <Pastry x={68} rotate={-4} scale={0.92} crust={crust} choc={choc} />
      <Pastry x={100} rotate={2} scale={1.15} crust={crust} choc={choc} />
      <Pastry x={132} rotate={-2} scale={0.85} crust={crust} choc={choc} />

      {/* Sill */}
      <path d="M8 100 L192 100 L188 108 L12 108 Z" fill={crust} opacity={0.5} />
    </svg>
  );
}
