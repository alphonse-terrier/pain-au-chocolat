"""Configuration centrale du projet, chargée depuis l'environnement/.env."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_PLACES_DIR = DATA_DIR / "raw" / "places"
RAW_REVIEWS_DIR = DATA_DIR / "raw" / "reviews"
DUCKDB_PATH = DATA_DIR / "pac.duckdb"
# Base allégée, dédiée à l'app Streamlit (cf. pac.cli.export_app_db) --
# séparée de DUCKDB_PATH (la base complète du pipeline discover/reviews/
# score) pour que l'app déployée n'embarque pas les ~90% d'avis bruts
# qu'elle ne lit jamais (cf. discussion : seuls les avis liés à une mention
# pain-au-chocolat/viennoiserie sont affichés).
APP_DUCKDB_PATH = DATA_DIR / "pac_app.duckdb"
# Données statiques consommées par le frontend Next.js/MapLibre (cf. plan
# "New Next.js + MapLibre frontend") -- régénérées par `pac export-web-json`
# à partir d'APP_DUCKDB_PATH, jamais lues par le pipeline ni par l'app
# Streamlit. Committées dans git comme APP_DUCKDB_PATH (même logique : c'est
# un export dérivé, pas une source de vérité).
WEB_DATA_DIR = ROOT_DIR / "web" / "public" / "data"

# Bbox large de Paris intra-muros (utilisée par grid.py pour le pavage).
PARIS_BBOX = {
    "lat_min": 48.8156,
    "lat_max": 48.9022,
    "lon_min": 2.2242,
    "lon_max": 2.4699,
}

# Bounding box de chaque arrondissement, calculée à partir des géométries
# réelles du jeu de données "arrondissements" d'opendata.paris.fr (min/max
# lat/lon des polygones officiels), pas une approximation à la main.
ARRONDISSEMENT_BBOX = {
    1: {"lat_min": 48.8540, "lat_max": 48.8699, "lon_min": 2.3209, "lon_max": 2.3509},
    2: {"lat_min": 48.8634, "lat_max": 48.8720, "lon_min": 2.3280, "lon_max": 2.3543},
    3: {"lat_min": 48.8557, "lat_max": 48.8693, "lon_min": 2.3502, "lon_max": 2.3685},
    4: {"lat_min": 48.8461, "lat_max": 48.8620, "lon_min": 2.3446, "lon_max": 2.3691},
    5: {"lat_min": 48.8368, "lat_max": 48.8540, "lon_min": 2.3367, "lon_max": 2.3660},
    6: {"lat_min": 48.8397, "lat_max": 48.8593, "lon_min": 2.3166, "lon_max": 2.3446},
    7: {"lat_min": 48.8459, "lat_max": 48.8638, "lon_min": 2.2898, "lon_max": 2.3333},
    8: {"lat_min": 48.8631, "lat_max": 48.8835, "lon_min": 2.2950, "lon_max": 2.3272},
    9: {"lat_min": 48.8696, "lat_max": 48.8846, "lon_min": 2.3258, "lon_max": 2.3499},
    10: {"lat_min": 48.8675, "lat_max": 48.8844, "lon_min": 2.3479, "lon_max": 2.3770},
    11: {"lat_min": 48.8481, "lat_max": 48.8721, "lon_min": 2.3638, "lon_max": 2.3993},
    12: {"lat_min": 48.8170, "lat_max": 48.8533, "lon_min": 2.3644, "lon_max": 2.4698},
    13: {"lat_min": 48.8156, "lat_max": 48.8449, "lon_min": 2.3411, "lon_max": 2.3903},
    14: {"lat_min": 48.8158, "lat_max": 48.8436, "lon_min": 2.3012, "lon_max": 2.3446},
    15: {"lat_min": 48.8252, "lat_max": 48.8582, "lon_min": 2.2630, "lon_max": 2.3247},
    16: {"lat_min": 48.8339, "lat_max": 48.8803, "lon_min": 2.2241, "lon_max": 2.3016},
    17: {"lat_min": 48.8738, "lat_max": 48.9010, "lon_min": 2.2798, "lon_max": 2.3301},
    18: {"lat_min": 48.8820, "lat_max": 48.9019, "lon_min": 2.3256, "lon_max": 2.3718},
    19: {"lat_min": 48.8721, "lat_max": 48.9022, "lon_min": 2.3647, "lon_max": 2.4108},
    20: {"lat_min": 48.8466, "lat_max": 48.8784, "lon_min": 2.3770, "lon_max": 2.4164},
}

# Cookie de consentement RGPD pré-posé : sans lui, toute requête google.com
# depuis une IP UE redirige vers consent.google.com (cf. spikes/feature_id.py).
CONSENT_COOKIE = {"CONSENT": "YES+cb.20240101-00-p0.fr+FX+000"}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_maps_api_key: str = ""
    max_reviews_per_place: int = 500  # 0 = illimité
    workers: int = 8
    sort: str = "newest"  # cf. plan : tri "newest" décidé avec l'utilisateur

    openrouter_api_key: str = ""
    openrouter_model: str = "~deepseek/deepseek-v4-flash-latest"  # ajustable sans toucher au code
    openrouter_verify_model: str = "anthropic/claude-sonnet-4.5"  # second avis, cas d'anomalie seulement
    score_workers: int = 8  # concurrence des appels de classification LLM


settings = Settings()

for d in (RAW_PLACES_DIR, RAW_REVIEWS_DIR):
    d.mkdir(parents=True, exist_ok=True)
