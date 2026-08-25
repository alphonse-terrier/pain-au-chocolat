"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
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
    if (!el) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    dragState.current = { startY: e.clientY, startTime: performance.now(), startHeightPx: el.getBoundingClientRect().height };
    el.dataset.dragging = "true";
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragState.current || !sheetRef.current) return;
    const dy = e.clientY - dragState.current.startY;
    sheetRef.current.style.setProperty("--drag-y", `${Math.max(0, dy)}px`);
  };

  const onPointerUp = (e: React.PointerEvent) => {
    const el = sheetRef.current;
    const drag = dragState.current;
    if (!el || !drag) return;
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    const dy = e.clientY - drag.startY;
    const elapsed = Math.max(1, performance.now() - drag.startTime);
    const velocity = dy / elapsed; // px/ms, positive = downward

    delete el.dataset.dragging;
    el.style.setProperty("--drag-y", "0px");

    const currentIndex = SNAP_ORDER.indexOf(snap);
    if (velocity > 0.6 || (dy > drag.startHeightPx * 0.4 && velocity >= 0)) {
      // Fast/large downward flick -- drop one snap, or close from peek.
      if (currentIndex === 0) onClose();
      else setSnap(SNAP_ORDER[currentIndex - 1]);
    } else if (velocity < -0.6) {
      if (currentIndex < SNAP_ORDER.length - 1) setSnap(SNAP_ORDER[currentIndex + 1]);
    } else {
      // Snap to whichever point is nearest the released height.
      const releasedHeight = drag.startHeightPx - dy;
      const nearest = SNAP_ORDER.reduce((best, point) => {
        const target = resolveSnapPx(point);
        const bestPx = resolveSnapPx(best);
        return Math.abs(target - releasedHeight) < Math.abs(bestPx - releasedHeight) ? point : best;
      }, snap);
      if (releasedHeight < resolveSnapPx("peek") * 0.6) onClose();
      else setSnap(nearest);
    }
    dragState.current = null;
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
            ×
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
