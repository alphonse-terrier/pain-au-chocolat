"use client";

import { useEffect, useRef } from "react";
import type { Point } from "geojson";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useMaplibreMap } from "./useMaplibreMap";
import { placesToFeatureCollection } from "./toGeoJSON";
import { SOURCE_ID, CLUSTERS_LAYER, CLUSTER_COUNT_LAYER, UNCLUSTERED_POINT_LAYER, selectedPointLayer } from "./layers";
import { CLUSTER_MAX_ZOOM, CLUSTER_RADIUS, SELECTED_PLACE_ZOOM } from "./mapStyle";
import type { Place } from "@/lib/types";
import styles from "./MapView.module.css";

interface Props {
  places: Place[];
  selectedId: string | null;
  onSelect: (placeId: string) => void;
  active: boolean;
  /** Reserves camera space at the bottom for the mobile bottom sheet, so
   * a tapped marker isn't hidden underneath it. */
  cameraPaddingBottom?: number;
  reducedMotion?: boolean;
}

export default function MapView({ places, selectedId, onSelect, active, cameraPaddingBottom = 0, reducedMotion = false }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { mapRef, loaded } = useMaplibreMap(containerRef);
  // Latest places/onSelect for handlers registered once in the setup
  // effect below -- avoids re-registering listeners (and losing hover
  // state) on every filter change.
  const placesRef = useRef(places);
  placesRef.current = places;
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  // Tracks the last selection the map itself emitted (via a marker
  // click), so the fly-to effect below only recenters on selections that
  // came from elsewhere (e.g. the Ranking tab) -- not on every marker tap.
  const lastEmittedRef = useRef<string | null>(null);
  const reducedMotionRef = useRef(reducedMotion);
  reducedMotionRef.current = reducedMotion;

  // Add source + layers once, right after the base style finishes loading.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || map.getSource(SOURCE_ID)) return;

    map.addSource(SOURCE_ID, {
      type: "geojson",
      data: placesToFeatureCollection(placesRef.current),
      cluster: true,
      clusterRadius: CLUSTER_RADIUS,
      clusterMaxZoom: CLUSTER_MAX_ZOOM,
      clusterProperties: {
        score_sum: ["+", ["coalesce", ["get", "score"], 0]],
        score_n: ["+", ["case", ["==", ["get", "score"], null], 0, 1]],
      },
    });
    map.addLayer(CLUSTERS_LAYER);
    map.addLayer(CLUSTER_COUNT_LAYER);
    map.addLayer(UNCLUSTERED_POINT_LAYER);
    map.addLayer(selectedPointLayer(null));

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });

    // MapLibre's own layer-scoped `map.on("click", layerId, ...)` hit-tests
    // at the exact event pixel, which is fine with a mouse but a real
    // problem with a fingertip on a 7px-radius dot -- reproducibly hard to
    // tap on a phone. Querying a padded box around the tap point instead
    // (and picking the closest match when several features fall in it)
    // gives touch a generous target without changing how the dots look.
    const TAP_HIT_PADDING = 14;
    const hitBox = (point: maplibregl.Point): [[number, number], [number, number]] => [
      [point.x - TAP_HIT_PADDING, point.y - TAP_HIT_PADDING],
      [point.x + TAP_HIT_PADDING, point.y + TAP_HIT_PADDING],
    ];
    const queryNearest = (point: maplibregl.Point, layer: string) => {
      const features = map.queryRenderedFeatures(hitBox(point), { layers: [layer] });
      if (features.length <= 1) return features[0];
      let best = features[0];
      let bestDistSq = Infinity;
      for (const f of features) {
        const projected = map.project((f.geometry as Point).coordinates as [number, number]);
        const distSq = (projected.x - point.x) ** 2 + (projected.y - point.y) ** 2;
        if (distSq < bestDistSq) {
          bestDistSq = distSq;
          best = f;
        }
      }
      return best;
    };

    const onMapClick = (e: maplibregl.MapMouseEvent) => {
      const point = queryNearest(e.point, "unclustered-point");
      const placeId = point?.properties?.place_id as string | undefined;
      if (placeId) {
        lastEmittedRef.current = placeId;
        onSelectRef.current(placeId);
        return;
      }

      const cluster = queryNearest(e.point, "clusters");
      if (!cluster) return;
      const clusterId = cluster.properties?.cluster_id as number;
      const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
      const center = (cluster.geometry as Point).coordinates as [number, number];
      source
        .getClusterExpansionZoom(clusterId)
        .then((zoom) => {
          if (!Number.isFinite(center[0]) || !Number.isFinite(center[1]) || !Number.isFinite(zoom)) return;
          // jumpTo, not easeTo: reproducibly confirmed (real-browser
          // repro) that this MapLibre version's multi-frame ease
          // animation can read a stale/null projection matrix mid-flight
          // and throw "Invalid LngLat object: (NaN, NaN)". jumpTo
          // computes the camera once, synchronously, avoiding that
          // per-frame code path entirely.
          try {
            map.jumpTo({ center, zoom });
          } catch {
            // Never let a camera-move edge case crash the app.
          }
        })
        .catch(() => {});
    };

    const onEnter = () => {
      map.getCanvas().style.cursor = "pointer";
    };
    const onLeave = () => {
      map.getCanvas().style.cursor = "";
      popup.remove();
    };
    const onHover = (e: maplibregl.MapMouseEvent) => {
      const feature = map.queryRenderedFeatures(e.point, { layers: ["unclustered-point"] })[0];
      if (!feature) {
        popup.remove();
        return;
      }
      const name = (feature.properties?.name as string) ?? "Bakery";
      const score = feature.properties?.score as number | null | undefined;
      const label = score !== null && score !== undefined ? `${name} · ${score.toFixed(1)}/10` : name;
      popup
        .setLngLat((feature.geometry as Point).coordinates as [number, number])
        .setText(label)
        .addTo(map);
    };

    map.on("click", onMapClick);
    map.on("mouseenter", "clusters", onEnter);
    map.on("mouseenter", "unclustered-point", onEnter);
    map.on("mouseleave", "clusters", onLeave);
    map.on("mouseleave", "unclustered-point", onLeave);
    map.on("mousemove", "unclustered-point", onHover);

    // React Strict Mode double-invokes effects in dev (mount -> cleanup ->
    // mount); without this cleanup, a second `[loaded]` run would register
    // every one of these listeners a second time, firing onPointClick etc.
    // twice per real click.
    return () => {
      map.off("click", onMapClick);
      map.off("mouseenter", "clusters", onEnter);
      map.off("mouseenter", "unclustered-point", onEnter);
      map.off("mouseleave", "clusters", onLeave);
      map.off("mouseleave", "unclustered-point", onLeave);
      map.off("mousemove", "unclustered-point", onHover);
      popup.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs exactly once, when `loaded` first flips true
  }, [loaded]);

  // Push new data into the source on every filter change (sub-millisecond
  // for ~1700 features -- this is the interaction Streamlit couldn't do
  // without a full rerun + ~0.5s of server-side re-render, cf. plan).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    source?.setData(placesToFeatureCollection(places));
  }, [places, loaded, mapRef]);

  // Move the highlight ring to the selected place, and fly to it when the
  // selection came from outside the map (e.g. the Ranking tab) -- a
  // marker click already centers naturally, so don't re-fly on those.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !map.getLayer("selected-point")) return;
    map.setFilter("selected-point", ["==", ["get", "place_id"], selectedId ?? "__none__"]);

    if (selectedId && selectedId !== lastEmittedRef.current) {
      const place = placesRef.current.find((p) => p.place_id === selectedId);
      if (place && Number.isFinite(place.map_lon) && Number.isFinite(place.map_lat)) {
        // A selection made elsewhere (e.g. the Ranking tab) also switches
        // to this tab in the same update, so the map container may have
        // just gone from display:none to visible -- resize synchronously
        // first so the move isn't computed against a stale viewport.
        // jumpTo (not easeTo/flyTo): this MapLibre version's multi-frame
        // ease animation has a reproducible bug where a mid-animation
        // frame can read a stale/uninitialized projection matrix and
        // throw "Invalid LngLat object: (NaN, NaN)" -- confirmed via a
        // real-browser repro. jumpTo computes the camera once,
        // synchronously, sidestepping that code path entirely.
        try {
          map.resize();
          map.jumpTo({
            center: [place.map_lon, place.map_lat],
            // Always zoom in at least to neighbourhood scale: a selection
            // made from a list (not a map click) is often coming from a
            // zoomed-out or clustered view, where the target place isn't
            // visible as its own marker yet. Never zoom back OUT though --
            // if the user is already closer, leave their zoom alone.
            zoom: Math.max(map.getZoom(), SELECTED_PLACE_ZOOM),
            padding: { bottom: cameraPaddingBottom, top: 0, left: 0, right: 0 },
          });
        } catch {
          // Never let a camera-move edge case (e.g. a mid-resize race)
          // crash the app -- worst case the map just doesn't recenter.
        }
      }
    }
    lastEmittedRef.current = selectedId;
  }, [selectedId, loaded, mapRef, cameraPaddingBottom]);

  // A container resized while hidden (display:none on the inactive tab)
  // leaves MapLibre with a stale viewport -- the exact class of bug that
  // already broke the Streamlit map on mobile once (cf. plan). The
  // ResizeObserver in useMaplibreMap handles most cases; this effect
  // covers the specific tab-activation transition as belt and braces.
  useEffect(() => {
    if (active && mapRef.current) {
      const id = requestAnimationFrame(() => mapRef.current?.resize());
      return () => cancelAnimationFrame(id);
    }
  }, [active, mapRef]);

  return <div ref={containerRef} className={styles.map} />;
}
