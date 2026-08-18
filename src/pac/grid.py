"""Pavage adaptatif de Paris pour contourner la limite de Nearby Search
(New) : 20 résultats max par requête, sans pagination (vérifié dans la doc
Google avant d'écrire ce module -- cf. plan)."""

from dataclasses import dataclass

from pac.config import PARIS_BBOX

EARTH_RADIUS_M = 6371000
MAX_DEPTH = 3
SATURATION_THRESHOLD = 20  # = maxResultCount ; une cellule qui le touche est jugée saturée


@dataclass
class Cell:
    lat: float
    lon: float
    radius_m: float
    depth: int = 0


def _meters_per_degree_lat() -> float:
    return (2 * 3.14159265358979 * EARTH_RADIUS_M) / 360


def _meters_per_degree_lon(lat: float) -> float:
    import math

    return _meters_per_degree_lat() * math.cos(math.radians(lat))


def initial_cells(cell_size_m: float = 500.0, bbox: dict | None = None) -> list[Cell]:
    """Grille régulière initiale de cellules de cell_size_m mètres de côté
    sur la bbox donnée (Paris par défaut). Le rayon de recherche par cellule
    est fixé à cell_size_m / sqrt(2) environ pour couvrir le carré."""
    bbox = bbox or PARIS_BBOX
    radius_m = cell_size_m * 0.7071  # demi-diagonale d'un carré de côté cell_size_m
    m_per_lat = _meters_per_degree_lat()

    cells: list[Cell] = []
    lat = bbox["lat_min"]
    while lat <= bbox["lat_max"]:
        m_per_lon = _meters_per_degree_lon(lat)
        lon = bbox["lon_min"]
        while lon <= bbox["lon_max"]:
            cells.append(Cell(lat=lat, lon=lon, radius_m=radius_m, depth=0))
            lon += cell_size_m / m_per_lon
        lat += cell_size_m / m_per_lat
    return cells


def subdivide(cell: Cell) -> list[Cell]:
    """Découpe une cellule saturée en 4 sous-cellules (quadtree), rayon
    divisé par 2. Utilisé quand une cellule renvoie >= 20 résultats : sans
    cette subdivision on perd silencieusement des lieux dans les zones
    denses (Marais, 11e...)."""
    m_per_lat = _meters_per_degree_lat()
    m_per_lon = _meters_per_degree_lon(cell.lat)
    half_radius = cell.radius_m / 2
    offset_lat = half_radius / m_per_lat
    offset_lon = half_radius / m_per_lon

    return [
        Cell(cell.lat + s_lat * offset_lat, cell.lon + s_lon * offset_lon, half_radius, cell.depth + 1)
        for s_lat in (-1, 1)
        for s_lon in (-1, 1)
    ]


def is_saturated(result_count: int) -> bool:
    return result_count >= SATURATION_THRESHOLD


def can_subdivide(cell: Cell) -> bool:
    return cell.depth < MAX_DEPTH
