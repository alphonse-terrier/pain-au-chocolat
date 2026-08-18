"""Spike bloquant (étape 0 du plan) : valider que l'on peut passer d'un lieu
Google Maps à ses avis via l'endpoint interne /maps/rpc/listugcposts.

Deux inconnues à lever avant de construire quoi que ce soit d'autre :
1. Peut-on extraire un feature_id (0x...:0x...) exploitable pour un lieu donné ?
2. listugcposts répond-il avec un pb minimal, et la pagination (next_page_token)
   fonctionne-t-elle sur au moins 2 pages ?

Usage:
    uv run python spikes/feature_id.py "Du Pain et des Idées Paris"
    uv run python spikes/feature_id.py --url "https://www.google.com/maps/place/..."

Résultat attendu : dump JSON de 2 pages dans tests/fixtures/, avec >=10 avis
chacune et une progression de next_page_token.
"""

import json
import re
import sys
from pathlib import Path

import httpx

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

FEATURE_ID_RE = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)")
FEATURE_ID_RE_FALLBACK = re.compile(r"(0x[0-9a-f]{16}:0x[0-9a-f]{16})")


def resolve_feature_id(client: httpx.Client, query_or_url: str) -> tuple[str, str]:
    """Retourne (feature_id, url_finale) pour une requête texte ou une URL maps.

    Google encode le feature_id dans l'URL canonique de la fiche lieu, sous la
    forme `!1s0x...:0x...`. On laisse httpx suivre les redirections (recherche
    texte -> fiche lieu) puis on grep l'URL finale et, en repli, le corps HTML.
    """
    if query_or_url.startswith("http"):
        url = query_or_url
    else:
        url = f"https://www.google.com/maps/search/{httpx.QueryParams({'q': query_or_url})['q']}"

    resp = client.get(url, headers=HEADERS, follow_redirects=True, timeout=15)
    resp.raise_for_status()
    final_url = str(resp.url)

    m = FEATURE_ID_RE.search(final_url) or FEATURE_ID_RE_FALLBACK.search(final_url)
    if not m:
        m = FEATURE_ID_RE.search(resp.text) or FEATURE_ID_RE_FALLBACK.search(resp.text)
    if not m:
        raise RuntimeError(
            f"feature_id introuvable ni dans l'URL finale ({final_url}) ni dans le HTML. "
            "L'hypothèse de l'étape 0 échoue pour cette requête -- voir plan de repli Playwright."
        )
    return m.group(1), final_url


def build_pb(feature_id: str, page_token: str = "", sort: int = 1, page_size: int = 10) -> str:
    """Construit le paramètre pb pour listugcposts.

    Structure reverse-engineered (cf. plan, section pb.py) : c'est une chaîne
    protobuf-like séparée par '!'. Champs utiles connus :
      !1s<feature_id>   -- identifiant du lieu
      !2s<page_token>   -- jeton de pagination (vide en page 1)
      !3s<sort>          -- 1 = plus pertinents, 2 = plus récents
      !4i<page_size>     -- nombre d'avis par page
      !8m<n>!8b1         -- inclut le texte complet des avis
    Ce gabarit est délibérément minimal : le but du spike est de vérifier qu'il
    suffit à obtenir une réponse paginable, pas de couvrir tous les champs.
    """
    return (
        f"!1m6!1s{feature_id}!6m4!4m1!1e1!4m1!1e3"
        f"!2m1!1s{page_token}"
        f"!5m2!1s{sort}"
        f"!7m4!8m3!1s{page_size}!2s0!3s1!8b1"
    )


def fetch_reviews_page(client: httpx.Client, feature_id: str, page_token: str = "") -> dict:
    params = {
        "authuser": "0",
        "hl": "fr",
        "pb": build_pb(feature_id, page_token=page_token),
    }
    resp = client.get(
        "https://www.google.com/maps/rpc/listugcposts",
        params=params,
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    text = resp.text
    if text.startswith(")]}'"):
        text = text[4:]
    return json.loads(text)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    arg = sys.argv[1]
    query = arg if arg != "--url" else sys.argv[2]

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # Depuis une IP UE, Google intercale un mur de consentement RGPD avant tout
    # accès à maps/search. Le cookie CONSENT pré-posé l'évite -- c'est ce que
    # font tous les scrapers cités dans le plan (YasogaN, gaspa93, omkarcloud).
    cookies = {"CONSENT": "YES+cb.20240101-00-p0.fr+FX+000"}

    with httpx.Client(cookies=cookies) as client:
        print(f"[1/3] Résolution du feature_id pour: {query!r}")
        try:
            feature_id, final_url = resolve_feature_id(client, query)
        except Exception as exc:
            print(f"ÉCHEC étape 0.1 (résolution feature_id): {exc}")
            return 2
        print(f"  feature_id = {feature_id}")
        print(f"  url finale  = {final_url}")

        pages = []
        token = ""
        for i in range(2):
            print(f"[2/3] Requête listugcposts page {i + 1} (token={token!r})")
            try:
                data = fetch_reviews_page(client, feature_id, page_token=token)
            except Exception as exc:
                print(f"ÉCHEC étape 0.2 (page {i + 1}): {exc}")
                return 3
            pages.append(data)

            out_path = FIXTURES_DIR / f"listugcposts_page{i + 1}.json"
            out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"  -> dump écrit dans {out_path}")

            # La forme exacte de `data` est l'inconnue de l'étape 0 : on l'imprime
            # brute pour inspection manuelle plutôt que de deviner sa structure.
            print(f"  type de la réponse racine: {type(data).__name__}, "
                  f"longueur: {len(data) if hasattr(data, '__len__') else 'n/a'}")

            token = None  # à déterminer après inspection manuelle du 1er dump
            if token is None:
                print("  -> inspection manuelle requise pour localiser next_page_token, arrêt après 1 page.")
                break

    print("[3/3] Spike terminé. Inspecter les fixtures dans tests/fixtures/ "
          "pour localiser: liste des avis, next_page_token, champs par avis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
