/** Direct port of src/pac/webapp/geocode.py -- the BAN (Base Adresse
 * Nationale) API is CORS-open and key-less, so it's called straight from
 * the browser, same as the Python side. */

const SEARCH_URL = "https://api-adresse.data.gouv.fr/search/";
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
