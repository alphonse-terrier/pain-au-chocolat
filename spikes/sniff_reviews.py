"""Spike étape 0 (repli) : capturer la VRAIE requête réseau émise par un
navigateur réel quand on ouvre l'onglet Avis d'une fiche Google Maps.

Les tentatives de reconstruction manuelle du protocole (listugcposts avec pb
"pb" gabarit public, GetLocalBoqProxy avec reqpld JSON reconstruit) ont toutes
deux échoué (403 / 200 avec payload vide) -- signe que Google exige un
contexte de session que l'on ne peut pas deviner. On capture donc la requête
telle qu'émise par un vrai navigateur, avec tous ses en-têtes et paramètres
exacts, pour la rejouer ensuite avec httpx sans deviner quoi que ce soit.

Usage:
    uv run python spikes/sniff_reviews.py
"""

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
PLACE_URL = (
    "https://www.google.com/maps/place/?q=place_id:ChIJp1Zmqglu5kcRVOw4CYHBUYg"
)

CANDIDATE_MARKERS = ("listugcposts", "GetLocalBoqProxy", "review", "MapsWizUi", "batchexecute")


def main() -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    captured = []

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

        all_requests = []

        def on_request(request):
            url = request.url
            all_requests.append(url)
            if any(m in url for m in CANDIDATE_MARKERS):
                captured.append(
                    {
                        "url": url,
                        "method": request.method,
                        "headers": dict(request.headers),
                        "post_data": request.post_data,
                    }
                )
                print(f"[capture] {request.method} {url[:160]}")

        def on_response(response):
            url = response.url
            if "/maps/preview/place" in url or "MapsWizUi" in url:
                try:
                    body = response.text()
                except Exception as exc:
                    body = f"<erreur lecture body: {exc}>"
                tag = "wiz" if "MapsWizUi" in url else "place"
                fname = f"resp_{tag}_{abs(hash(url)) % 1000000}.txt"
                (FIXTURES_DIR / fname).write_text(f"URL: {url}\n\n{body}")
                print(f"[response] {tag} ({len(body)} bytes) -> {fname}")

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"Navigation vers {PLACE_URL}")
        page.goto(PLACE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(FIXTURES_DIR / "debug_1_initial.png"), full_page=False)

        # Accepter le consentement si un mur apparaît (bouton "Tout accepter").
        for label in ["Tout accepter", "J'accepte", "Accept all"]:
            try:
                btn = page.get_by_role("button", name=label)
                if btn.count() > 0:
                    btn.first.click(timeout=3000)
                    print(f"Consentement accepté via bouton {label!r}")
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        page.screenshot(path=str(FIXTURES_DIR / "debug_2_after_consent.png"), full_page=False)

        # Cliquer sur l'onglet/le lien "avis" pour déclencher le chargement.
        clicked = False
        for label in ["avis", "reviews"]:
            try:
                el = page.get_by_role("tab", name=label, exact=False)
                if el.count() > 0:
                    el.first.click(timeout=5000)
                    clicked = True
                    print(f"Onglet '{label}' cliqué")
                    break
            except Exception:
                pass
        if not clicked:
            print("Onglet avis non trouvé via role=tab, tentative via texte brut")
            try:
                page.get_by_text("avis", exact=False).first.click(timeout=5000)
                clicked = True
            except Exception as exc:
                print(f"  échec: {exc}")

        page.wait_for_timeout(4000)
        page.screenshot(path=str(FIXTURES_DIR / "debug_3_after_avis_click.png"), full_page=False)

        # Scroller le VRAI conteneur scrollable du panneau d'avis (pas la page/carte).
        # Ce panneau est un <div> interne avec son propre overflow ; un mouse.wheel au
        # niveau page défile la carte, pas la liste d'avis.
        marker_before = len([u for u in all_requests if "/maps/preview/place" in u])
        try:
            scrollable = page.locator(
                "div[role='main'] div[jsaction*='pane'], div.m6QErb.DxyBCb, div.m6QErb"
            ).last
            for i in range(6):
                scrollable.hover(timeout=3000)
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(1500)
            print(f"Scroll effectué. Nouvelles requêtes preview/place depuis: "
                  f"{len([u for u in all_requests if '/maps/preview/place' in u]) - marker_before}")
        except Exception as exc:
            print(f"scroll échoué: {exc}")

        page.screenshot(path=str(FIXTURES_DIR / "debug_4_after_scroll.png"), full_page=False)
        page.wait_for_timeout(3000)

        # Test décisif : rejouer un appel qv9Egd (ListUgcPosts) avec le VRAI
        # cookie jar accumulé par ce contexte navigateur, pour confirmer que
        # c'est bien l'absence de cookies de session (pas le token lui-même)
        # qui faisait échouer les rejeux via curl nu.
        wiz_calls = [r for r in captured if "MapsWizUi" in r["url"] and "qv9Egd" in r["url"]]
        if wiz_calls:
            sample = wiz_calls[0]
            fresh_url = re.sub(r"_reqid=\d+", "_reqid=88899900", sample["url"])
            resp = context.request.post(
                fresh_url,
                data=sample["post_data"],
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "Referer": "https://www.google.com/",
                    "X-Same-Domain": "1",
                },
            )
            body = resp.text()
            (FIXTURES_DIR / "replay_with_context_cookies.txt").write_text(body)
            found = "viennoiseries assez classiques" in body or "Pierre-Albert" in body
            print(f"[replay avec cookies du contexte] status={resp.status} "
                  f"taille={len(body)} avis_trouvé={found}")

        browser.close()

    out = FIXTURES_DIR / "captured_requests.json"
    out.write_text(json.dumps(captured, indent=2, ensure_ascii=False))
    (FIXTURES_DIR / "all_urls.txt").write_text("\n".join(all_requests))
    print(f"\n{len(captured)} requête(s) capturée(s) -> {out}")
    print(f"{len(all_requests)} requêtes totales -> {FIXTURES_DIR / 'all_urls.txt'}")
    if not captured:
        print("ÉCHEC: aucune requête pertinente capturée. "
              "Le sélecteur de l'onglet avis a probablement changé.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
