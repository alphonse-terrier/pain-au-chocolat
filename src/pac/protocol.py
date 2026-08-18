"""Le seul module qui parle le protocole non documenté de Google Maps.

Toute la fragilité "positional-JSON-de-Google" du projet est confinée ici et
dans parse.py (cf. plan, section "Principe directeur"). Quand Google changera
son format, c'est ici qu'il faudra regarder en premier.

Découvertes de l'étape 0 (spikes/feature_id.py, sniff_reviews*.py) :

1. Un `place_id` de l'API Places (ex. "ChIJ...") n'est PAS l'identifiant
   qu'attend le reste du protocole. Il faut le convertir en `feature_id`
   hexadécimal ("0x...:0x...") en récupérant la fiche lieu correspondante.
   Ce feature_id est visible dans le HTML même sans exécuter de JS.

2. Les endpoints publiquement documentés pour lister les avis
   (/maps/rpc/listugcposts, /httpservice/.../GetLocalBoqProxy) sont
   OBSOLÈTES : ils répondent 403 ou 200-avec-payload-vide. Le vrai protocole
   actuel est un appel "batchexecute" (framework interne "Wiz" de Google) :

       POST /maps/_/MapsWizUi/data/batchexecute?rpcids=qv9Egd&...
       body: f.req=<JSON encodé> qui invoque /MapsUgcPostService.ListUgcPosts

3. Ce point est important et coûteux à avoir découvert : cet appel ne peut
   PAS être reconstruit et rejoué à la main, même depuis une session vivante
   avec le bon curseur de pagination (testé et échoué plusieurs fois : le
   serveur répond un "no-op" `[null,null,null,null,null,true]`). Il faut
   laisser la vraie page Google émettre elle-même ces requêtes (en pilotant
   son UI - clic + défilement) et les intercepter passivement. C'est le rôle
   de reviews.py ; ce module-ci ne fait QUE la résolution feature_id et le
   décodage bas niveau des réponses interceptées.
"""

import json
import re

import httpx

from pac.config import CONSENT_COOKIE, DEFAULT_USER_AGENT

FEATURE_ID_RE = re.compile(r"(0x[0-9a-f]{5,16}:0x[0-9a-f]{5,16})")

HTTP_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def resolve_feature_id(client: httpx.Client, place_id: str, name_hint: str = "") -> str:
    """Convertit un place_id de l'API Places en feature_id "0x..:0x..".

    Le feature_id de l'ENTITÉ UGC (celle qui porte les avis) apparaît dans le
    HTML de la page de résultat de recherche construite avec `query_place_id`.
    On ne suit pas de redirection vers /maps/place/ : sur une requête
    ambiguë Google ne redirige pas, mais le feature_id est déjà présent dans
    le bundle de données embarqué dans le HTML initial (validé à l'étape 0).
    """
    url = "https://www.google.com/maps/search/"
    params = {"api": "1", "query": name_hint or place_id, "query_place_id": place_id}
    resp = client.get(
        url, params=params, headers=HTTP_HEADERS, follow_redirects=True, timeout=15
    )
    resp.raise_for_status()

    m = FEATURE_ID_RE.search(str(resp.url)) or FEATURE_ID_RE.search(resp.text)
    if not m:
        raise RuntimeError(
            f"feature_id introuvable pour place_id={place_id!r}. "
            "Le format de la page de recherche a probablement changé "
            "(cf. protocol.py, docstring)."
        )
    return m.group(1)


def new_http_client() -> httpx.Client:
    """Client httpx configuré avec le cookie de consentement RGPD."""
    return httpx.Client(cookies=CONSENT_COOKIE, headers=HTTP_HEADERS)


def decode_batchexecute(raw_body: str) -> list:
    """Décode une réponse batchexecute (chunks préfixés par leur longueur) en
    la liste des résultats RPC "wrb.fr" qu'elle contient.

    Format observé (spikes/sniff_reviews3.py) :
        )]}'
        <longueur_chunk_1>
        [["wrb.fr", "/UnRpc", "<JSON échappé>", ...]]
        <longueur_chunk_2>
        ...
    """
    body = raw_body[4:] if raw_body.startswith(")]}'") else raw_body
    lines = body.strip().split("\n")
    chunks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        try:
            int(line)
        except ValueError:
            i += 1
            continue
        i += 1
        if i < len(lines):
            chunks.append(lines[i])
        i += 1

    results = []
    for chunk in chunks:
        try:
            d = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(d, list) and d and isinstance(d[0], list) and d[0][0] == "wrb.fr":
            rpc_id, payload = d[0][1], d[0][2]
            if payload is None:
                continue
            try:
                results.append((rpc_id, json.loads(payload)))
            except json.JSONDecodeError:
                continue
    return results


def is_ugc_posts_response(rpc_id: str) -> bool:
    return rpc_id == "/MapsUgcPostService.ListUgcPosts"
