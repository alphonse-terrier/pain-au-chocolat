/** Direct port of src/pac/webapp/geocode.py -- the BAN (Base Adresse
 * Nationale) API is CORS-open and key-less, so it's called straight from
 * the browser, same as the Python side. */

const SEARCH_URL = "https://api-adresse.data.gouv.fr/search/";
const REVERSE_URL = "https://api-adresse.data.gouv.fr/reverse/";
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // mirrors @st.cache_data(ttl=86400)

export class GeocodeError extends Error {}

export interface GeocodeResult {
  lat: number;
  lon: number;
  formatted_address: string;
}

interface CacheEntry {
  value: GeocodeResult;
  cachedAt: number;
}

function cacheKey(address: string): string {
  return `pac:geocode:${address.trim().toLowerCase()}`;
}

function readCache(address: string): GeocodeResult | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(cacheKey(address));
    if (!raw) return null;
    const entry = JSON.parse(raw) as CacheEntry;
    if (Date.now() - entry.cachedAt > CACHE_TTL_MS) return null;
    return entry.value;
  } catch {
    return null;
  }
}

function writeCache(address: string, value: GeocodeResult): void {
  if (typeof window === "undefined") return;
  try {
    const entry: CacheEntry = { value, cachedAt: Date.now() };
    window.localStorage.setItem(cacheKey(address), JSON.stringify(entry));
  } catch {
    // localStorage full/unavailable -- not worth failing the search over
  }
}

export async function geocodeAddress(address: string): Promise<GeocodeResult> {
  const cached = readCache(address);
  if (cached) return cached;

  let resp: Response;
  try {
    resp = await fetch(`${SEARCH_URL}?q=${encodeURIComponent(address)}&limit=1`);
  } catch (exc) {
    throw new GeocodeError(`Address API call failed: ${String(exc)}`);
  }
  if (!resp.ok) {
    throw new GeocodeError(`Address API call failed: HTTP ${resp.status}`);
  }

  const data = (await resp.json()) as {
    features: Array<{ geometry: { coordinates: [number, number] }; properties: { label?: string } }>;
  };
  const best = data.features?.[0];
  if (!best) {
    throw new GeocodeError(`No result for "${address}".`);
  }

  const [lon, lat] = best.geometry.coordinates;
  const result: GeocodeResult = { lat, lon, formatted_address: best.properties.label ?? address };
  writeCache(address, result);
  return result;
}

/** Coordinates -> a human label, for the "use my location" flow -- the
 * device gives us lat/lon, not an address, and "48.856900, 2.352200" in
 * the geo chip would be a worse UX than "10 Rue de Rivoli, Paris" for
 * basically no reason. Best-effort: caller falls back to a generic label
 * if this throws (e.g. offline, or the coordinates are outside France --
 * this API only covers France, same limitation as forward geocoding). */
export async function reverseGeocode(lat: number, lon: number): Promise<string> {
  let resp: Response;
  try {
    resp = await fetch(`${REVERSE_URL}?lon=${lon}&lat=${lat}`);
  } catch (exc) {
    throw new GeocodeError(`Reverse geocoding failed: ${String(exc)}`);
  }
  if (!resp.ok) {
    throw new GeocodeError(`Reverse geocoding failed: HTTP ${resp.status}`);
  }
  const data = (await resp.json()) as { features: Array<{ properties: { label?: string } }> };
  const label = data.features?.[0]?.properties.label;
  if (!label) {
    throw new GeocodeError("No address found for this location.");
  }
  return label;
}
