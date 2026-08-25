"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import type { Place, PlacesMeta } from "@/lib/types";
import { loadPlaces } from "@/lib/placesData";
import { applyFilters, countActiveFilters, FILTER_DEFAULTS, useAppState, type Tab } from "@/lib/filters";
import { useIsDesktop, useMediaQuery, usePrefersReducedMotion } from "@/lib/useMediaQuery";
import Header from "./Header";
import Tabs from "./Tabs";
import ResultsBar from "./ResultsBar";
import FilterSidebar from "./FilterSidebar";
import AppSkeleton from "./AppSkeleton";
import ErrorState from "./ErrorState";
import PlaceDetailPanel from "./detail/PlaceDetailPanel";
import BottomSheet from "./ui/BottomSheet";
import RankingTable from "./ranking/RankingTable";
import RankingCards from "./ranking/RankingCards";
import ExportCsvButton from "./ranking/ExportCsvButton";
import NearbyTab from "./nearby/NearbyTab";
import MethodologyTab from "./methodology/MethodologyTab";
import styles from "./AppShell.module.css";

// MapLibre touches `window` at module scope -- must not be evaluated
// during SSR/build.
const MapView = dynamic(() => import("./map/MapView"), { ssr: false });

type LoadStatus = "loading" | "ready" | "error";

export default function AppShell({ buildMeta }: { buildMeta: PlacesMeta }) {
  const [state, setState] = useAppState();
  const [data, setData] = useState<{ places: Place[]; byId: Map<string, Place> } | null>(null);
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sheetHeight, setSheetHeight] = useState(0);

  const isDesktop = useIsDesktop();
  const isNarrowRanking = useMediaQuery("(max-width: 767px)");
  const reducedMotion = usePrefersReducedMotion();

  const fetchPlaces = useCallback(() => {
    setStatus("loading");
    loadPlaces()
      .then(({ places, byId }) => {
        setData({ places, byId });
        setStatus("ready");
      })
      .catch((err) => {
        setErrorMessage(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
  }, []);

  useEffect(() => {
    fetchPlaces();
  }, [fetchPlaces]);

  // Escape closes the mobile filter drawer.
  useEffect(() => {
    if (!filtersOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFiltersOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [filtersOpen]);

  const filters = useMemo(
    () => ({
      q: state.q,
      arr: state.arr,
      smin: state.smin,
      smax: state.smax,
      unscored: state.unscored,
      grate: state.grate,
      nrel: state.nrel,
    }),
    [state.q, state.arr, state.smin, state.smax, state.unscored, state.grate, state.nrel]
  );

  const filtered = useMemo(() => (data ? applyFilters(data.places, filters) : []), [data, filters]);
  const selectedPlace = state.sel && data ? (data.byId.get(state.sel) ?? null) : null;
  const activeFilterCount = countActiveFilters(filters);

  const topPlaces = useMemo(
    () =>
      [...filtered]
        .filter((p) => p.score_10 !== null)
        .sort((a, b) => b.score_10! - a.score_10!)
        .slice(0, 20),
    [filtered]
  );

  const tab = state.tab as Tab;
  const scored = filtered.filter((p) => p.score_10 !== null);
  const mobileSheetOpen = !isDesktop && tab === "map" && Boolean(state.sel);

  function handleSort(col: string) {
    setState({ sort: col, dir: state.sort === col && state.dir === "desc" ? "asc" : "desc" });
  }

  function handleSelect(id: string) {
    setState({ sel: id });
  }

  if (status === "error") {
    return (
      <div className={styles.shell}>
        <Header />
        <Tabs active={tab} onChange={(t) => setState({ tab: t })} />
        {tab === "about" ? (
          <div className={styles.content}>
            <MethodologyTab meta={buildMeta} />
          </div>
        ) : (
          <ErrorState message={errorMessage} onRetry={fetchPlaces} />
        )}
      </div>
    );
  }

  return (
    <div className={styles.shell}>
      <Header />
      <Tabs active={tab} onChange={(t) => setState({ tab: t })} />

      {status === "loading" || !data ? (
        <div className={styles.content}>
          <AppSkeleton />
        </div>
      ) : (
        <>
          <ResultsBar
            shown={filtered.length}
            total={data.places.length}
            activeFilterCount={activeFilterCount}
            onReset={() => setState(FILTER_DEFAULTS)}
            onOpenFilters={!isDesktop ? () => setFiltersOpen(true) : undefined}
            actions={tab === "ranking" ? <ExportCsvButton places={scored} /> : undefined}
          />

          <div className={styles.body} inert={filtersOpen && !isDesktop ? true : undefined}>
            <aside
              id="filters"
              className={styles.sidebar}
              data-open={isDesktop || filtersOpen || undefined}
              aria-label="Filters"
            >
              <FilterSidebar
                filters={filters}
                onChange={(patch) => setState(patch)}
                lastReviewAt={buildMeta.last_review_at}
                onClose={!isDesktop ? () => setFiltersOpen(false) : undefined}
              />
            </aside>

            <main id="main" className={styles.content}>
              {/* Map + detail panel stay mounted always (display:none when
                  inactive) -- recreating the WebGL map on every tab switch
                  would be far more expensive than hiding it (cf. plan). */}
              <div
                id="panel-map"
                role="tabpanel"
                aria-labelledby="tab-map"
                className={styles.mapRow}
                style={{ display: tab === "map" ? "grid" : "none" }}
              >
                <div className={styles.mapCol}>
                  <MapView
                    places={filtered}
                    selectedId={state.sel || null}
                    onSelect={handleSelect}
                    active={tab === "map"}
                    cameraPaddingBottom={mobileSheetOpen ? sheetHeight : 0}
                    reducedMotion={reducedMotion}
                  />
                </div>
                {isDesktop && (
                  <div className={styles.panelCol}>
                    <PlaceDetailPanel place={selectedPlace} topPlaces={topPlaces} onSelectPlace={handleSelect} />
                  </div>
                )}
              </div>

              {tab === "ranking" && (
                <div id="panel-ranking" role="tabpanel" aria-labelledby="tab-ranking" className={styles.pane}>
                  {isNarrowRanking ? (
                    <RankingCards
                      places={scored}
                      sort={state.sort}
                      dir={state.dir}
                      onSort={handleSort}
                      onSelect={(id) => setState({ sel: id, tab: "map" })}
                    />
                  ) : (
                    <RankingTable
                      places={scored}
                      sort={state.sort}
                      dir={state.dir}
                      onSort={handleSort}
                      onSelect={(id) => setState({ sel: id, tab: "map" })}
                    />
                  )}
                </div>
              )}

              {tab === "nearby" && (
                <div id="panel-nearby" role="tabpanel" aria-labelledby="tab-nearby" className={styles.pane}>
                  <NearbyTab
                    places={filtered}
                    addr={state.addr}
                    rad={state.rad}
                    onAddrChange={(addr) => setState({ addr })}
                    onRadChange={(rad) => setState({ rad })}
                  />
                </div>
              )}

              {tab === "about" && (
                <div id="panel-about" role="tabpanel" aria-labelledby="tab-about" className={styles.pane}>
                  <MethodologyTab meta={buildMeta} />
                </div>
              )}
            </main>
          </div>

          {!isDesktop && filtersOpen && (
            <div className={styles.scrim} onClick={() => setFiltersOpen(false)} aria-hidden="true" />
          )}

          {!isDesktop && (
            <BottomSheet
              open={mobileSheetOpen}
              onClose={() => setState({ sel: "" })}
              reducedMotion={reducedMotion}
              onSnapChange={setSheetHeight}
              header={selectedPlace ? <p className={styles.sheetName}>{selectedPlace.name}</p> : null}
            >
              <PlaceDetailPanel
                place={selectedPlace}
                topPlaces={topPlaces}
                onSelectPlace={handleSelect}
                showName={false}
              />
            </BottomSheet>
          )}
        </>
      )}
    </div>
  );
}
