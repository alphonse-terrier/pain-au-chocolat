"""Géocodage léger d'une adresse libre saisie par l'utilisateur (feature
"boulangerie la plus proche de chez moi"), via l'API Adresse du gouvernement
(BAN -- Base Adresse Nationale) : ouverte, gratuite, sans clé, pas de
dépendance à un fournisseur privé pour une simple conversion adresse ->
coordonnées."""

import httpx
import numpy as np

SEARCH_URL = "https://api-adresse.data.gouv.fr/search/"


class GeocodeError(RuntimeError):
    """L'adresse n'a pas pu être résolue (introuvable, ou erreur API)."""


def geocode_address(address: str) -> dict:
    """address -> {"lat": float, "lon": float, "formatted_address": str}.
    Lève GeocodeError si rien n'est trouvé ou si l'appel échoue."""
    try:
        resp = httpx.get(SEARCH_URL, params={"q": address, "limit": 1}, timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise GeocodeError(f"Address API call failed: {exc}") from exc

    features = resp.json().get("features", [])
    if not features:
        raise GeocodeError(f'No result for "{address}".')

    best = features[0]
    lon, lat = best["geometry"]["coordinates"]
    return {
        "lat": lat,
        "lon": lon,
        "formatted_address": best["properties"].get("label", address),
    }


def haversine_m(lat1, lon1, lat2, lon2):
    """Distance en mètres entre (lat1, lon1) et (lat2, lon2) -- accepte des
    scalaires ou des pandas.Series (numpy gère les deux de la même façon)."""
    r = 6_371_000
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))
