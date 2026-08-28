export class GeolocationError extends Error {}

/** Promise wrapper around the callback-based Geolocation API, with
 * friendlier messages than the raw GeolocationPositionError codes. */
export function getCurrentPosition(): Promise<{ lat: number; lon: number }> {
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    return Promise.reject(new GeolocationError("Geolocation isn't supported by this browser."));
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      (err) => {
        switch (err.code) {
          case err.PERMISSION_DENIED:
            reject(new GeolocationError("Location access was denied -- allow it in your browser settings and try again."));
            break;
          case err.POSITION_UNAVAILABLE:
            reject(new GeolocationError("Your location couldn't be determined right now."));
            break;
          case err.TIMEOUT:
            reject(new GeolocationError("Finding your location took too long -- try again."));
            break;
          default:
            reject(new GeolocationError("Something went wrong finding your location."));
        }
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 }
    );
  });
}
