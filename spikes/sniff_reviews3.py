"""Spike étape 0 (validation finale) : piloter nous-mêmes la pagination des
avis via fetch() in-page, en réutilisant le VRAI curseur de pagination
extrait de la réponse de la page précédente (pas le curseur déjà consommé).

Corrige l'essai précédent qui rejouait le même curseur vide (page 1) une
deuxième fois -- d'où le "no-op" (le serveur avait déjà servi cette page).
"""

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
PLACE_URL = "https://www.google.com/maps/place/?q=place_id:ChIJp1Zmqglu5kcRVOw4CYHBUYg"


def decode_batchexecute(raw_body: str) -> list:
    """Décode une réponse batchexecute (chunks longueur-préfixée) en la liste
    des objets RPC 'wrb.fr' qu'elle contient."""
    body = raw_body[4:] if raw_body.startswith(")]}'") else raw_body
    lines = body.strip().split("\n")
    chunks, i = [], 0
    while i < len(lines):
        try:
            int(lines[i].strip())
            i += 1
            chunks.append(lines[i])
            i += 1
        except ValueError:
            i += 1
    results = []
    for c in chunks:
        d = json.loads(c)
        if isinstance(d, list) and d and isinstance(d[0], list) and d[0][0] == "wrb.fr":
            results.append(json.loads(d[0][2]))
    return results


def extract_review_authors(obj: list) -> list:
    """Best-effort : parcourt obj[2] (liste des avis bruts) et remonte les
    noms d'auteurs trouvés, juste pour vérifier qu'une page contient des avis
    DIFFÉRENTS de la précédente (preuve que la pagination avance vraiment)."""
    names = []

    def walk(node):
        if isinstance(node, list):
            if len(node) == 2 and isinstance(node[0], str) and "googleusercontent" in str(node[1]):
                names.append(node[0])
            for v in node:
                walk(v)

    if len(obj) > 2 and obj[2]:
        walk(obj[2])
    return names


def main() -> int:
    first_call = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="fr-FR",
            viewport={"width": 1400, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        pending = {}

        def on_request(request):
            if "MapsWizUi" in request.url and "qv9Egd" in request.url:
                pending[request.url] = request.post_data

        def on_response(response):
            if response.url in pending and "response_text" not in first_call:
                try:
                    text = response.text()
                    objs = decode_batchexecute(text)
                    if objs and objs[0][1]:  # curseur suivant non nul -> page utile
                        first_call["url"] = response.url
                        first_call["post_data"] = pending[response.url]
                        first_call["response_text"] = text
                        print(f"[retenu] {response.url[:90]} (curseur présent)")
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        page.goto(PLACE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        try:
            page.get_by_role("button", name="Tout accepter").first.click(timeout=3000)
            page.wait_for_timeout(1500)
        except Exception:
            pass
        try:
            page.get_by_role("tab", name="avis", exact=False).first.click(timeout=5000)
        except Exception as exc:
            print(f"clic onglet avis échoué: {exc}")
        page.wait_for_timeout(3000)

        if not first_call.get("response_text"):
            print("ÉCHEC: pas de réponse capturée pour le premier appel réel.")
            browser.close()
            return 1

        page1_objs = decode_batchexecute(first_call["response_text"])
        page1_obj = page1_objs[0]
        cursor = page1_obj[1]
        authors_p1 = extract_review_authors(page1_obj)
        print(f"Page 1 (réelle) : curseur suivant = {cursor!r}, "
              f"{len(authors_p1)} auteur(s) détecté(s) = {authors_p1[:3]}")

        # Construit la page 2 : même f.req que la page 1, seule la valeur du
        # curseur change (repérée par une recherche/remplacement de motif
        # "[10,\"\"]" -> "[10,\"<curseur>\"]" dans le corps encodé).
        import urllib.parse
        params = urllib.parse.parse_qs(first_call["post_data"], keep_blank_values=True)
        print(f"  paramètres du corps: {list(params.keys())}")
        freq = json.loads(params["f.req"][0])
        args = json.loads(freq[0][0][1])
        args[1] = [10, cursor]  # [taille_page, curseur] -- seul champ qui change
        freq[0][0][1] = json.dumps(args, separators=(",", ":"))
        params["f.req"] = [json.dumps(freq, separators=(",", ":"))]
        page2_body = urllib.parse.urlencode(params, doseq=True)

        fresh_url = re.sub(r"_reqid=\d+", "_reqid=777000222", first_call["url"])
        result = page.evaluate(
            """async ([url, body]) => {
                const resp = await fetch(url, {
                    method: "POST",
                    headers: {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                    body: body,
                    credentials: "include",
                });
                return {status: resp.status, text: await resp.text()};
            }""",
            [fresh_url, page2_body],
        )
        (FIXTURES_DIR / "inpage_fetch_page2.txt").write_text(
            f"status={result['status']}\n\n{result['text']}"
        )

        if result["status"] == 200:
            try:
                page2_obj = decode_batchexecute(result["text"])[0]
                authors_p2 = extract_review_authors(page2_obj)
                new_authors = set(authors_p2) - set(authors_p1)
                print(f"Page 2 (pilotée par nous) : taille={len(result['text'])}, "
                      f"{len(authors_p2)} auteur(s) = {authors_p2[:3]}")
                print(f"Auteurs NOUVEAUX par rapport à la page 1 : {new_authors}")
                if new_authors:
                    print("\n✅ SUCCÈS : pagination pilotée depuis notre code, avis différents obtenus.")
                else:
                    print("\n⚠️ Page 2 identique à la page 1 -- curseur probablement ignoré.")
            except Exception as exc:
                print(f"Page 2 : réponse 200 mais décodage échoué ({exc}). Voir inpage_fetch_page2.txt")
        else:
            print(f"❌ Page 2 : HTTP {result['status']}")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
