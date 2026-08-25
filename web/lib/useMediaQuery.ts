"use client";

import { useSyncExternalStore } from "react";

/** SSR-safe media query hook via useSyncExternalStore. getServerSnapshot
 * returns false unconditionally -- this app statically prerenders, and
 * every consumer here (drawer vs static sidebar, table vs card list) is
 * fine starting in its "closed"/"desktop-false" state on first paint and
 * settling immediately on hydration with no visible flash. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false
  );
}

export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 1024px)");
}

export function usePrefersReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}
