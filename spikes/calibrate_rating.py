"""Calibre la position du champ "note" (rating) dans les entrées UGC brutes,
en croisant le DOM réel (aria-label="X étoiles" affiché par Google) avec le
JSON intercepté pour les MÊMES avis -- pour ne plus deviner à l'aveugle.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from playwright.sync_api import sync_playwright

from pac.protocol import decode_batchexecute
from pac.reviews import _accept_consent, _open_reviews_tab

import sys as _sys
_place_id = _sys.argv[1] if len(_sys.argv) > 1 else "ChIJp1Zmqglu5kcRVOw4CYHBUYg"
PLACE_URL = f"https://www.google.com/maps/place/?q=place_id:{_place_id}"
FIXTURES_DIR = Path("tests/fixtures")


def main():
    captured_payloads = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        from pac.config import DEFAULT_USER_AGENT
        context = browser.new_context(
            locale="fr-FR", viewport={"width": 1400, "height": 1000}, user_agent=DEFAULT_USER_AGENT
        )
        page = context.new_page()

        def on_response(response):
            if "MapsWizUi" in response.url and "qv9Egd" in response.url:
                try:
                    text = response.text()
                    for rpc_id, payload in decode_batchexecute(text):
                        if rpc_id == "/MapsUgcPostService.ListUgcPosts":
                            captured_payloads.append(payload)
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(PLACE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)
        _accept_consent(page)
        opened = _open_reviews_tab(page)
        print("onglet ouvert:", opened)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(FIXTURES_DIR / "calibrate_debug.png"))

        # Vérité terrain : lit le DOM des avis affichés (auteur -> étoiles).
        dom_ratings = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('span[aria-label*="toile"]').forEach(el => {
                    const label = el.getAttribute('aria-label');
                    const container = el.closest('div[aria-label]');
                    out.push({label, container_aria: container ? container.getAttribute('aria-label') : null});
                });
                return out;
            }"""
        )
        (FIXTURES_DIR / "dom_ratings.json").write_text(json.dumps(dom_ratings, indent=1, ensure_ascii=False))
        print(f"{len(dom_ratings)} étoiles trouvées dans le DOM")
        for d in dom_ratings[:10]:
            print(" ", d)

        browser.close()

    (FIXTURES_DIR / "raw_payload_for_rating.json").write_text(
        json.dumps(captured_payloads, ensure_ascii=False)
    )
    print(f"{len(captured_payloads)} payload(s) UGC capturés -> tests/fixtures/raw_payload_for_rating.json")


if __name__ == "__main__":
    main()
