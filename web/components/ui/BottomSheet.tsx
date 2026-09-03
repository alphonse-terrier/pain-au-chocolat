"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Close } from "./icons";
import styles from "./BottomSheet.module.css";

export type SnapPoint = "peek" | "half" | "full";

const SNAP_HEIGHTS: Record<SnapPoint, string> = {
  peek: "min(38dvh, 320px)",
  half: "62dvh",
  full: "calc(100dvh - 56px)",
};
const SNAP_ORDER: SnapPoint[] = ["peek", "half", "full"];

/** Mobile bottom sheet for the place detail panel. Deliberately a fixed
 * overlay on top of the map -- the map container's box never changes size
 * because of this sheet, so map.resize() is never required for a snap
 * change. Do not turn this into a layout-participating panel; that would
 * reintroduce exactly the resize fragility the plan worked around
 * (cf. useMaplibreMap's ResizeObserver comment).
 *
 * Drag is bound to the handle region only (grabber + header), never the
 * body -- the review list below scrolls independently with no gesture
 * conflict. Height is snap-driven (a CSS custom property, transitioned);
 * the live drag offset is applied as a separate translate3d written
 * directly via style.setProperty, not React state, so a drag doesn't
 * trigger a render per pointermove. */
export default function BottomSheet({
  open,
  onClose,
  header,
  children,
  reducedMotion = false,
  onSnapChange,
}: {
  open: boolean;
  onClose: () => void;
  header: ReactNode;
  children: ReactNode;
  reducedMotion?: boolean;
  onSnapChange?: (heightPx: number) => void;
}) {
  const [snap, setSnap] = useState<SnapPoint>("peek");
  const sheetRef = useRef<HTMLDivElement>(null);
  const dragState = useRef<{ startY: number; startTime: number; startHeightPx: number } | null>(null);

  // Reset to peek on every open, so a new selection doesn't inherit the
  // last sheet's expanded height.
  useEffect(() => {
    if (open) setSnap("peek");
  }, [open]);

  const reportHeight = useCallback(() => {
    if (!onSnapChange) return;
    const el = sheetRef.current;
    if (!el) return;
    onSnapChange(open ? el.getBoundingClientRect().height : 0);
  }, [onSnapChange, open]);

  useEffect(() => {
    reportHeight();
  }, [snap, open, reportHeight]);

  const onPointerDown = (e: React.PointerEvent) => {
    const el = sheetRef.current;
    // Let the close button handle its own click -- don't hijack it into a
    // drag/tap-cycle gesture (harmless either way since closing unmounts
    // the sheet right after, but there's no reason to run that logic).
    if (!el || (e.target as HTMLElement).closest(`.${styles.closeBtn}`)) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    dragState.current = { startY: e.clientY, startTime: performance.now(), startHeightPx: el.getBoundingClientRect().height };
    el.dataset.dragging = "true";
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const el = sheetRef.current;
    const drag = dragState.current;
    if (!el || !drag) return;
    // Directly drives height (not a transform) so dragging UP visibly
    // grows the sheet in real time, same as dragging down shrinks it --
    // a transform can only slide the box, it can't reveal more of it
    // since the sheet is anchored to the bottom edge. Without this, an
    // upward drag gave no feedback at all until release, which read as
    // "the sheet doesn't respond to touch."
    const dy = e.clientY - drag.startY; // positive = finger moved down
    const maxHeightPx = resolveSnapPx("full");
    el.style.height = `${Math.min(maxHeightPx, Math.max(0, drag.startHeightPx - dy))}px`;
  };

  const onPointerUp = (e: React.PointerEvent) => {
    const el = sheetRef.current;
    const drag = dragState.current;
    if (!el || !drag) return;
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    const dy = e.clientY - drag.startY;
    const elapsed = Math.max(1, performance.now() - drag.startTime);
    const velocity = dy / elapsed; // px/ms, positive = downward
    dragState.current = null;
    delete el.dataset.dragging;

    const currentIndex = SNAP_ORDER.indexOf(snap);
    const settle = (point: SnapPoint) => {
      setSnap(point);
      // Set the target height immediately, not just via React state: if
      // the release lands back on the SAME snap point, React bails out of
      // re-rendering (no state change), which would otherwise leave the
      // drag's raw pixel height stuck instead of the snap's real value.
      el.style.height = SNAP_HEIGHTS[point];
    };

    // A tap (barely any movement) cycles to the next snap point -- a much
    // easier target than a precise drag on a small handle, and the
    // natural fallback for anyone who taps the handle expecting it to do
    // *something* rather than nothing.
    if (Math.abs(dy) < 6 && elapsed < 500) {
      settle(SNAP_ORDER[(currentIndex + 1) % SNAP_ORDER.length]);
      return;
    }

    if (velocity > 0.6) {
      // Fast downward flick -- drop one snap, or close from peek.
      if (currentIndex === 0) onClose();
      else settle(SNAP_ORDER[currentIndex - 1]);
    } else if (velocity < -0.6) {
      if (currentIndex < SNAP_ORDER.length - 1) settle(SNAP_ORDER[currentIndex + 1]);
      else settle(snap);
    } else {
      // Slow drag -- snap to whichever point is nearest the released height.
      const releasedHeight = drag.startHeightPx - dy;
      if (releasedHeight < resolveSnapPx("peek") * 0.6) {
        onClose();
        return;
      }
      const nearest = SNAP_ORDER.reduce((best, point) => {
        const target = resolveSnapPx(point);
        const bestPx = resolveSnapPx(best);
        return Math.abs(target - releasedHeight) < Math.abs(bestPx - releasedHeight) ? point : best;
      }, snap);
      settle(nearest);
    }
  };

  if (!open) return null;

  return (
    <div
      ref={sheetRef}
      className={styles.sheet}
      data-snap={snap}
      role="dialog"
      aria-label="Bakery details"
      style={{ height: SNAP_HEIGHTS[snap], transitionDuration: reducedMotion ? "0ms" : undefined }}
    >
      <div
        className={styles.handleArea}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div className={styles.grabber} aria-hidden="true" />
        <div className={styles.headerRow}>
          <div className={styles.headerContent}>{header}</div>
          <button type="button" className={styles.closeBtn} aria-label="Close" onClick={onClose}>
            <Close size={16} />
          </button>
        </div>
      </div>
      <div className={styles.body} data-scrollable={snap !== "peek" || undefined}>
        {children}
      </div>
    </div>
  );
}

function resolveSnapPx(point: SnapPoint): number {
  // Resolve a snap point's CSS value against the current viewport so drag
  // math can compare against it. dvh-based arithmetic against
  // innerHeight is accurate enough for snap selection.
  const vh = window.innerHeight;
  if (point === "peek") return Math.min(vh * 0.38, 320);
  if (point === "half") return vh * 0.62;
  return vh - 56;
}
