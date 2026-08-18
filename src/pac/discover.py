"""Phase 1 du plan : découverte des boulangeries de Paris via Places API
(New). Nécessite GOOGLE_MAPS_API_KEY dans .env -- non testée en direct dans
cette session (pas de clé disponible) : à vérifier par toi avant le run
complet (cf. plan, section Vérification, étape 3)."""

import json
import re
import time
from datetime import datetime, timezone

import httpx

from pac.config import ARRONDISSEMENT_BBOX, RAW_PLACES_DIR, settings
from pac.grid import Cell, can_subdivide, initial_cells, is_saturated, subdivide

SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.addressComponents,places.location,places.rating,"
    "places.userRatingCount,places.primaryType,places.types,places.googleMapsUri"
)
PARIS_POSTAL_RE = re.compile(r"\b75\d{3}\b")


def _search_cell(client: httpx.Client, cell: Cell) -> list[dict]:
    body = {
        "includedTypes": ["bakery"],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": cell.lat, "longitude": cell.lon},
                "radius": cell.radius_m,
            }
        },
    }
    headers = {
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
        "Content-Type": "application/json",
    }
    resp = client.post(SEARCH_URL, json=body, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("places", [])


def _postal_code(place: dict) -> str | None:
    for comp in place.get("addressComponents", []):
        if comp.get("types") and "postal_code" in comp["types"]:
            return comp.get("longText") or comp.get("shortText")
    return None


def _is_paris_intra_muros(place: dict, expected_postal_prefix: str | None = None) -> bool:
    """Filtre Paris intra-muros, ou un arrondissement précis si
    expected_postal_prefix est fourni (ex. "75012").

    Nécessaire même quand on pave la bbox d'un seul arrondissement : le
    rayon de recherche d'une cellule proche de la frontière peut déborder de
    quelques centaines de mètres dans l'arrondissement voisin (observé en
    pratique : des résultats 75020 sont revenus pour un pavage limité au
    12e). Le filtre applicatif sur le code postal élimine ce débordement.
    """
    postal = _postal_code(place)
    if not postal or not PARIS_POSTAL_RE.match(postal):
        return False
    if expected_postal_prefix and postal != expected_postal_prefix:
        return False
    return True


def discover_bakeries(
    limit: int | None = None,
    dry_run: bool = False,
    cell_size_m: float = 500.0,
    arrondissement: int | None = None,
    strict_bakery: bool = True,
) -> list[dict]:
    """Pave Paris (ou un seul arrondissement) et récolte les boulangeries via
    Nearby Search, avec subdivision quadtree des cellules saturées
    (>=20 résultats).

    arrondissement restreint le pavage à la bbox réelle de cet
    arrondissement (cf. config.ARRONDISSEMENT_BBOX, calculée depuis les
    géométries officielles d'opendata.paris.fr) -- pratique pour un run de
    validation rapide avant de lancer Paris entier.

    strict_bakery (défaut True) ne garde que les lieux dont le primaryType
    Google est exactement "bakery". Sans ce filtre, Nearby Search renvoie
    aussi des lieux où "bakery" n'est qu'un type secondaire parmi d'autres
    (supermarchés avec rayon boulangerie, restaurants, etc.) -- observé en
    pratique : ~30% de bruit de ce type sur un premier run réel.
    """
    bbox = None
    expected_postal = None
    if arrondissement is not None:
        if arrondissement not in ARRONDISSEMENT_BBOX:
            raise ValueError(f"arrondissement invalide : {arrondissement} (attendu 1-20)")
        bbox = ARRONDISSEMENT_BBOX[arrondissement]
        expected_postal = f"750{arrondissement:02d}"
    cells = initial_cells(cell_size_m=cell_size_m, bbox=bbox)

    if dry_run:
        print(f"[dry-run] {len(cells)} cellules initiales (taille {cell_size_m} m), "
              f"~{len(cells)} à ~{len(cells) * 4} appels selon subdivisions.")
        return []

    if not settings.google_maps_api_key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY manquant (.env). Impossible d'appeler Places API."
        )

    seen: dict[str, dict] = {}
    incomplete_cells = 0
    api_calls = 0

    with httpx.Client() as client:
        queue = list(cells)
        while queue:
            cell = queue.pop()
            api_calls += 1
            try:
                results = _search_cell(client, cell)
            except httpx.HTTPStatusError as exc:
                print(f"  [erreur] cellule ({cell.lat:.4f},{cell.lon:.4f}): {exc}")
                continue

            for place in results:
                pid = place.get("id")
                if not pid or pid in seen:
                    continue
                if not _is_paris_intra_muros(place, expected_postal):
                    continue
                if strict_bakery and place.get("primaryType") != "bakery":
                    continue
                seen[pid] = place

            if is_saturated(len(results)):
                if can_subdivide(cell):
                    queue.extend(subdivide(cell))
                else:
                    incomplete_cells += 1
                    print(f"  [couverture incomplète] cellule saturée à profondeur max "
                          f"({cell.lat:.4f},{cell.lon:.4f})")

            time.sleep(0.05)  # politesse minimale envers l'API

            if limit and len(seen) >= limit:
                break

    if incomplete_cells:
        print(f"AVERTISSEMENT : {incomplete_cells} cellule(s) restent saturées à la "
              f"profondeur maximale -- couverture probablement incomplète dans ces zones.")

    places = list(seen.values())[: limit or None]
    discovered_at = datetime.now(timezone.utc).isoformat()

    out_path = RAW_PLACES_DIR / "places.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for p in places:
            f.write(json.dumps({**p, "discovered_at": discovered_at}, ensure_ascii=False) + "\n")
    print(f"{api_calls} appels Nearby Search effectués -- {len(places)} lieux écrits dans {out_path}")
    return places
