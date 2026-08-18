"""Spike étape 0 (suite) : peut-on piloter nous-mêmes la pagination des avis
en émettant un fetch() depuis le contexte JS de la page (donc dans la session
vivante, cookies inclus), plutôt qu'en cliquant/scrollant l'UI ?

Hypothèse : le rejeu après coup (curl, cookie-jar réutilisé) échoue parce que
le serveur suit l'état de session en direct -- mais un fetch() émis DANS la
page, juste après la vraie requête initiale interceptée, devrait rester dans
cette même session vivante et donc réussir pour les pages suivantes.

Usage:
    uv run python spikes/sniff_reviews2.py
"""

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
PLACE_URL = "https://www.google.com/maps/place/?q=place_id:ChIJp1Zmqglu5kcRVOw4CYHBUYg"


def main() -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
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

        def on_request(request):
            if "MapsWizUi" in request.url and "qv9Egd" in request.url and not first_call:
                first_call["url"] = request.url
                first_call["post_data"] = request.post_data
                print(f"[capturé] premier appel qv9Egd réel: {request.url[:100]}")

        page.on("request", on_request)

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

        if not first_call:
            print("ÉCHEC: aucun appel qv9Egd réel capturé, impossible de continuer.")
            browser.close()
            return 1

        # Étape décisive : depuis CE MÊME contexte page (session vivante), on
        # rejoue nous-mêmes qv9Egd pour une page 2, en réutilisant le vrai
        # f.req initial mais avec un reqid frais -- test volontairement naïf
        # (sans même connaître le curseur de pagination) juste pour vérifier
        # si un fetch() in-page est accepté là où un rejeu hors-bande a échoué.
        fresh_url = re.sub(r"_reqid=\d+", "_reqid=555000111", first_call["url"])
        result = page.evaluate(
            """async ([url, body]) => {
                const resp = await fetch(url, {
                    method: "POST",
                    headers: {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                    body: body,
                    credentials: "include",
                });
                const text = await resp.text();
                return {status: resp.status, text: text};
            }""",
            [fresh_url, first_call["post_data"]],
        )

        (FIXTURES_DIR / "inpage_fetch_result.txt").write_text(
            f"status={result['status']}\n\n{result['text']}"
        )
        found = "Pierre-Albert" in result["text"] or "viennoiseries assez classiques" in result["text"]
        print(f"[fetch in-page] status={result['status']} taille={len(result['text'])} avis_trouvé={found}")

        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
