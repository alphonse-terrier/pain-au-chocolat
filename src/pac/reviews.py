"""Phase 2 du plan : récolte des avis d'un lieu.

Conséquence de l'étape 0 (cf. protocol.py) : on ne pilote PAS nous-mêmes les
appels au protocole d'avis de Google. On laisse la vraie page Google Maps
faire son travail (ouvrir l'onglet "Avis", défiler la liste) et on
intercepte passivement les réponses réseau qu'elle émet elle-même. C'est
plus lent qu'un appel API direct mais c'est la seule approche qui a
fonctionné de façon reproductible lors du spike.
"""

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Browser, TimeoutError as PlaywrightTimeoutError

from pac.config import DEFAULT_USER_AGENT, RAW_REVIEWS_DIR
from pac.parse import parse_ugc_posts_payload
from pac.protocol import decode_batchexecute, is_ugc_posts_response

PLACE_URL_TEMPLATE = "https://www.google.com/maps/place/?q=place_id:{place_id}"
MAX_SCROLL_ROUNDS = 400  # garde-fou dur, indépendant de max_reviews_per_place
STALL_ROUNDS_LIMIT = 6  # arrêt si aucune nouvelle donnée après N défilements


def _accept_consent(page) -> None:
    for label in ("Tout accepter", "J'accepte", "Accept all"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0:
                btn.first.click(timeout=3000)
                page.wait_for_timeout(1200)
                return
        except Exception:
            continue


def _open_reviews_tab(page) -> bool:
    # `.count()` is a synchronous, non-waiting check -- it returns 0
    # immediately if the tab bar hasn't finished rendering yet, which is a
    # real race (confirmed live: the exact same page reliably has the
    # "Avis" tab a few hundred ms later). That race is almost certainly
    # what silently truncated ~130 crawls to a handful of reviews each in
    # one session (they "succeeded" at finding SOME reviews tab/content on
    # a later attempt, or via a fallback timing that produced less scroll
    # time, rather than cleanly failing). `.wait_for(state="visible")`
    # actively polls up to its timeout instead of sampling once.
    for label in ("avis", "reviews"):
        try:
            tab = page.get_by_role("tab", name=label, exact=False).first
            tab.wait_for(state="visible", timeout=8000)
            tab.click(timeout=5000)
            return True
        except Exception:
            continue
    return False


def crawl_place_reviews(
    browser: Browser,
    place_id: str,
    max_reviews: int = 500,
    sort: str = "newest",
) -> dict:
    """Récolte les avis d'un lieu via un contexte Playwright dédié.

    Renvoie un résumé {place_id, status, reviews_fetched, error}. Les avis
    eux-mêmes sont écrits en JSONL au fil de l'eau dans
    data/raw/reviews/<place_id>.jsonl (dédup par review_id).

    sort n'est actuellement PAS appliqué explicitement (l'UI Maps trie par
    défaut sur "les plus pertinents" ; changer le tri nécessiterait de
    cliquer le sélecteur "Trier" -- non implémenté dans cette première
    version, cf. TODO plus bas). Documenté pour ne pas laisser croire à un
    tri "newest" qui ne serait pas réellement appliqué.
    """
    seen_ids: set[str] = set()
    collected: list[dict] = []
    out_path = RAW_REVIEWS_DIR / f"{place_id}.jsonl"

    context = browser.new_context(
        locale="fr-FR",
        viewport={"width": 1400, "height": 1000},
        user_agent=DEFAULT_USER_AGENT,
    )
    page = context.new_page()
    stall_rounds = 0

    def on_response(response):
        nonlocal stall_rounds
        if "MapsWizUi" not in response.url or "qv9Egd" not in response.url:
            return
        try:
            text = response.text()
        except Exception:
            return
        for rpc_id, payload in decode_batchexecute(text):
            if not is_ugc_posts_response(rpc_id):
                continue
            reviews, _ = parse_ugc_posts_payload(payload)
            new = 0
            for r in reviews:
                if r.review_id in seen_ids:
                    continue
                seen_ids.add(r.review_id)
                collected.append(asdict(r))
                new += 1
            if new:
                stall_rounds = 0

    page.on("response", on_response)

    try:
        # ~3-4% des lieux échouent à l'ouverture de l'onglet Avis pour des
        # raisons transitoires (timing sous forte parallélisation, rendu
        # partiel de la page) plutôt que parce qu'ils n'ont réellement aucun
        # avis -- un simple rechargement suffit dans la grande majorité des
        # cas observés. On ne retente PAS pour les lieux qui n'ont
        # probablement aucun avis (cf. cli.py, qui n'appelle ce module que
        # pour des place_id déjà connus).
        opened = False
        for attempt in range(3):
            page.goto(
                PLACE_URL_TEMPLATE.format(place_id=place_id),
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_timeout(1500 if attempt == 0 else 2500)
            _accept_consent(page)
            opened = _open_reviews_tab(page)
            if opened:
                break
        if not opened:
            return {
                "place_id": place_id,
                "status": "no_reviews_tab",
                "reviews_fetched": 0,
                "error": "onglet avis introuvable après 3 tentatives "
                         "(probablement un lieu sans aucun avis, ou sélecteur changé)",
            }
        page.wait_for_timeout(2500)

        # mouse.wheel() dispatches at the CURRENT cursor position, which
        # after just clicking the reviews tab sits up near the tab bar --
        # not over the scrollable review list below it. Confirmed live:
        # without this, wheel events land outside the list, nothing lazy-
        # loads, and the stall-detection below gives up after only the
        # first natural batch (~5-10 reviews) regardless of how many the
        # place actually has. This coordinate is inside the left detail
        # panel for the 1400x1000 viewport created above.
        page.mouse.move(300, 500)

        for _ in range(MAX_SCROLL_ROUNDS):
            if max_reviews and len(collected) >= max_reviews:
                break
            before = len(collected)
            page.mouse.wheel(0, 2200)
            page.wait_for_timeout(900)
            if len(collected) == before:
                stall_rounds += 1
            if stall_rounds >= STALL_ROUNDS_LIMIT:
                break

        status = "ok"
    except PlaywrightTimeoutError as exc:
        status = "timeout"
        return {"place_id": place_id, "status": status, "reviews_fetched": len(collected), "error": str(exc)}
    except Exception as exc:
        return {"place_id": place_id, "status": "error", "reviews_fetched": len(collected), "error": str(exc)}
    finally:
        context.close()

    if max_reviews:
        collected = collected[:max_reviews]

    scraped_at = datetime.now(timezone.utc).isoformat()
    with out_path.open("a", encoding="utf-8") as f:
        for r in collected:
            f.write(json.dumps(
                {"place_id": place_id, **r, "scraped_at": scraped_at}, ensure_ascii=False
            ) + "\n")

    return {"place_id": place_id, "status": status, "reviews_fetched": len(collected), "error": None}
