"use client";

import { useState } from "react";
import type { Place } from "@/lib/types";
import { GeocodeError, geocodeAddress, reverseGeocode, type GeocodeResult } from "@/lib/geocode";
import { GeolocationError, getCurrentPosition } from "@/lib/geolocation";
import { haversineM } from "@/lib/geo";
import Button from "../ui/Button";
import Alert from "../ui/Alert";
import EmptyState from "../ui/EmptyState";
import SegmentedControl from "../ui/SegmentedControl";
import Skeleton from "../ui/Skeleton";
import NearbyResultCard from "./NearbyResultCard";
import styles from "./NearbyTab.module.css";

const RADIUS_OPTIONS = [400, 800, 1200, 2000] as const;

function nearestRadius(v: number): number {
  return RADIUS_OPTIONS.reduce((best, opt) => (Math.abs(opt - v) < Math.abs(best - v) ? opt : best));
}

export default function NearbyTab({
  places,
  addr,
  rad,
  onAddrChange,
  onRadChange,
}: {
  places: Place[];
  addr: string;
  rad: number;
  onAddrChange: (v: string) => void;
  onRadChange: (v: number) => void;
}) {
  const [pending, setPending] = useState(false);
  // Separate from `pending`: address search and "use my location" are two
  // different buttons, each should only show its own spinner.
  const [locating, setLocating] = useState(false);
  const [geo, setGeo] = useState<GeocodeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!addr.trim()) return;
    setPending(true);
    setError(null);
    try {
      const result = await geocodeAddress(addr.trim());
      setGeo(result);
      setSearched(true);
    } catch (exc) {
      setGeo(null);
      setSearched(true);
      setError(exc instanceof GeocodeError ? exc.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  async function handleUseLocation() {
    setLocating(true);
    setError(null);
    try {
      const { lat, lon } = await getCurrentPosition();
      // Best-effort label -- a failed reverse lookup (offline, outside
      // France) shouldn't block using the coordinates we already have.
      const label = await reverseGeocode(lat, lon).catch(() => "Your current location");
      onAddrChange(label);
      setGeo({ lat, lon, formatted_address: label });
      setSearched(true);
    } catch (exc) {
      setGeo(null);
      setSearched(true);
      setError(exc instanceof GeolocationError ? exc.message : "Something went wrong.");
    } finally {
      setLocating(false);
    }
  }

  const effectiveRadius = nearestRadius(rad);
  const candidates = places.filter((p) => p.score_10 !== null);
  const nearby = geo
    ? candidates
        .map((p) => ({ place: p, distanceM: haversineM(geo.lat, geo.lon, p.lat, p.lon) }))
        .filter((r) => r.distanceM <= effectiveRadius)
        .sort((a, b) => (b.place.score_10! - a.place.score_10!) || (a.distanceM - b.distanceM))
        .slice(0, 10)
    : [];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <h2 className={styles.heading}>Emergency pain au chocolat locator</h2>
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.addressRow}>
            <div className={styles.addressField}>
              <svg className={styles.pinIcon} width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
                <path
                  d="M8 15s5-4.5 5-8.5A5 5 0 0 0 3 6.5C3 10.5 8 15 8 15z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.3"
                />
                <circle cx="8" cy="6.5" r="1.8" fill="currentColor" />
              </svg>
              <label htmlFor="nearby-address" className="visually-hidden">
                Address
              </label>
              <input
                id="nearby-address"
                className={styles.addressInput}
                type="text"
                value={addr}
                placeholder="e.g. 10 rue de Rivoli, Paris"
                onChange={(e) => onAddrChange(e.target.value)}
              />
            </div>
            <Button type="submit" variant="primary" loading={pending} disabled={!addr.trim()}>
              Search
            </Button>
          </div>
          <div className={styles.radiusRow}>
            <span className={styles.radiusLabel}>Within</span>
            <SegmentedControl
              legend="Search radius"
              value={String(effectiveRadius)}
              onChange={(v) => onRadChange(Number(v))}
              options={RADIUS_OPTIONS.map((r) => ({
                value: String(r),
                label: r >= 1000 ? `${(r / 1000).toFixed(1)} km` : `${r} m`,
              }))}
            />
          </div>
        </form>
        <div className={styles.orDivider}>
          <span>or</span>
        </div>
        <Button
          variant="secondary"
          className={styles.locateBtn}
          loading={locating}
          onClick={handleUseLocation}
          iconLeft={
            <span aria-hidden="true" className={styles.locateIcon}>
              📍
            </span>
          }
        >
          Use my location
        </Button>
        <p className={styles.caption}>Powered by the French government&apos;s address API. Works anywhere in France, no croissant required to use it.</p>
      </div>

      {error && <Alert tone="error">⚠️ {error}</Alert>}
      {geo && (
        <div className={styles.geoChip}>
          📍 {geo.formatted_address}
          <button type="button" className={styles.changeBtn} onClick={() => document.getElementById("nearby-address")?.focus()}>
            Change
          </button>
        </div>
      )}

      {pending && (
        <div className={styles.skeletonList}>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} height="80px" radius="var(--r-lg)" />
          ))}
        </div>
      )}

      {!pending && searched && geo && nearby.length === 0 && (
        <EmptyState
          title="A pastry desert"
          body={`Nothing scored within ${effectiveRadius} m. Time to widen the search, or move house.`}
          action={
            <Button variant="secondary" size="sm" onClick={() => onRadChange(2000)}>
              Widen to 2 km
            </Button>
          }
        />
      )}
      {!pending && nearby.length > 0 && (
        <>
          <p className={styles.caption}>{nearby.length} bakeries found, ranked by score.</p>
          {nearby.map(({ place, distanceM }, i) => (
            <NearbyResultCard key={place.place_id} place={place} distanceM={distanceM} rank={i + 1} />
          ))}
        </>
      )}
    </div>
  );
}
