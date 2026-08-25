"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { MAP_STYLE, PARIS_CENTER, PARIS_ZOOM } from "./mapStyle";

/** Thin wrapper around raw maplibre-gl: create once, tear down on unmount,
 * expose the live map instance. Deliberately not react-map-gl -- the
 * interactions this app needs (getClusterExpansionZoom, setData on filter
 * change, popups) all require the raw instance anyway, and this repo
 * already learned the hard way (FastMarkerCluster silently breaking
 * streamlit-folium's click detection) that an extra rendering layer
 * between the code and the map library hides exactly the behavior that
 * matters (cf. plan). */
export function useMaplibreMap(containerRef: React.RefObject<HTMLDivElement | null>) {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: PARIS_CENTER,
      zoom: PARIS_ZOOM,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => setLoaded(true));
    mapRef.current = map;

    // The map's container now sizes itself from a flexed/grid parent
    // (height: 100%) rather than a hardcoded pixel height, so its box can
    // change for reasons beyond a tab switch: the filter drawer opening,
    // the bottom sheet appearing, a window resize, mobile browser chrome
    // collapsing on scroll, device rotation. A ResizeObserver catches all
    // of these in one place. Skip when the box is zero (the container is
    // display:none on an inactive tab) so a hidden container never writes
    // a garbage viewport into the map.
    let rafId: number | null = null;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentBoxSize?.[0];
      if (!box || box.inlineSize === 0 || box.blockSize === 0) return;
      if (rafId !== null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        rafId = null;
        mapRef.current?.resize();
      });
    });
    observer.observe(containerRef.current);

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      observer.disconnect();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- container ref is stable, map created exactly once
  }, []);

  return { mapRef, loaded };
}
