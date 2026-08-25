"use client";

import {
  parseAsArrayOf,
  parseAsBoolean,
  parseAsFloat,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
  useQueryStates,
} from "nuqs";
import type { Filters, Place } from "./types";

export const TABS = ["map", "ranking", "nearby", "about"] as const;
export type Tab = (typeof TABS)[number];

/** All URL-synced state for the whole app: filters, active tab, selected
 * place, ranking sort, nearby-search inputs. One hook, one source of
 * truth (cf. plan -- shareable/bookmarkable views, a real win over the
 * Streamlit version's in-memory session state). */
export function useAppState() {
  return useQueryStates(
    {
      tab: parseAsStringLiteral(TABS).withDefault("map"),
      q: parseAsString.withDefault(""),
      arr: parseAsArrayOf(parseAsInteger).withDefault([]),
      smin: parseAsFloat.withDefault(0),
      smax: parseAsFloat.withDefault(10),
      unscored: parseAsBoolean.withDefault(false),
      grate: parseAsFloat.withDefault(0),
      nrel: parseAsInteger.withDefault(0),
      sel: parseAsString.withDefault(""),
      sort: parseAsString.withDefault("score_10"),
      dir: parseAsStringLiteral(["asc", "desc"] as const).withDefault("desc"),
      addr: parseAsString.withDefault(""),
      rad: parseAsInteger.withDefault(800),
    },
    { clearOnDefault: true }
  );
}

/** Default value for each filter field, matching the `.withDefault(...)`
 * calls in useAppState() above -- kept as one object so the active-filter
 * count and the "Reset" action can't drift from the actual defaults. */
export const FILTER_DEFAULTS: Filters = {
  q: "",
  arr: [],
  smin: 0,
  smax: 10,
  unscored: false,
  grate: 0,
  nrel: 0,
};

/** Number of filters that differ from their default -- smin/smax count as
 * ONE "Score" facet, since a user thinks "I filtered by score", not "I
 * set two sliders". Used for the drawer's active-filter badge. */
export function countActiveFilters(f: Filters): number {
  let n = 0;
  if (f.q.trim() !== "") n++;
  if (f.arr.length > 0) n++;
  if (f.smin !== FILTER_DEFAULTS.smin || f.smax !== FILTER_DEFAULTS.smax) n++;
  if (f.unscored !== FILTER_DEFAULTS.unscored) n++;
  if (f.grate > 0) n++;
  if (f.nrel > 0) n++;
  return n;
}

/** Pure filter composition -- mirrors app.py's filter block exactly,
 * including the null-coercion semantics (a null google_rating drops out
 * the moment grate > 0, same for n_relevant). Order: name -> arr ->
 * rating -> n_relevant -> score range/unscored. */
export function applyFilters(places: Place[], f: Filters): Place[] {
  let out = places;
  if (f.q) {
    const needle = f.q.toLowerCase();
    out = out.filter((p) => (p.name ?? "").toLowerCase().includes(needle));
  }
  if (f.arr.length > 0) {
    const wanted = new Set(f.arr);
    out = out.filter((p) => p.arrondissement !== null && wanted.has(p.arrondissement));
  }
  out = out.filter((p) => (p.google_rating ?? 0) >= f.grate);
  out = out.filter((p) => (p.n_relevant ?? 0) >= f.nrel);
  out = out.filter((p) => {
    const hasScore = p.score_10 !== null;
    if (hasScore) return p.score_10! >= f.smin && p.score_10! <= f.smax;
    return f.unscored;
  });
  return out;
}
