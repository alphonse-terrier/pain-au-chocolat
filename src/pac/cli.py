"""Point d'entrée CLI : pac discover | reviews | load | stats."""

import concurrent.futures
import json

import typer
from playwright.sync_api import sync_playwright

from pac.config import RAW_PLACES_DIR, WEB_DATA_DIR, settings
from pac.discover import discover_bakeries
from pac.export_app_db import export_app_db
from pac.export_web_json import export_web_json
from pac.reviews import crawl_place_reviews
from pac.score import classify_mentions, compute_scores, extract_mentions, leaderboard, verify_anomalies
from pac.store import get_connection, load_places, load_reviews

app = typer.Typer(add_completion=False)


def _crawl_one_place(place_id: str, max_reviews: int) -> dict:
    """Fonction top-level (picklable) exécutée dans un processus worker :
    ouvre son propre navigateur Playwright, isolé des autres workers."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            return crawl_place_reviews(browser, place_id, max_reviews=max_reviews)
        finally:
            browser.close()


@app.command()
def discover(
    limit: int = typer.Option(None, help="Nombre max de lieux à garder"),
    dry_run: bool = typer.Option(False, help="Affiche juste le plan de pavage, sans appeler l'API"),
    cell_size_m: float = typer.Option(500.0, help="Taille de cellule initiale (mètres)"),
    arrondissement: int = typer.Option(
        None, help="Restreint à un seul arrondissement (1-20) au lieu de tout Paris"
    ),
    strict_bakery: bool = typer.Option(
        True, help="Ne garde que primaryType=='bakery' (sinon: bruit type supermarché/restaurant)"
    ),
):
    """Phase 1 : découvre les boulangeries de Paris (ou d'un arrondissement) via Places API."""
    discover_bakeries(
        limit=limit,
        dry_run=dry_run,
        cell_size_m=cell_size_m,
        arrondissement=arrondissement,
        strict_bakery=strict_bakery,
    )


@app.command()
def reviews(
    place_ids: str = typer.Option(None, help="Liste de place_id séparés par des virgules (sinon: tous ceux de discover)"),
    limit: int = typer.Option(None, help="Nombre max de lieux à traiter"),
    max_reviews_per_place: int = typer.Option(None, help="Défaut: settings.max_reviews_per_place (500)"),
    workers: int = typer.Option(None, help="Contextes Playwright en parallèle"),
):
    """Phase 2 : récolte les avis de chaque lieu (Playwright, scroll-driven)."""
    max_reviews = max_reviews_per_place or settings.max_reviews_per_place
    n_workers = workers or settings.workers

    if place_ids:
        ids = [p.strip() for p in place_ids.split(",") if p.strip()]
    else:
        places_file = RAW_PLACES_DIR / "places.jsonl"
        if not places_file.exists():
            typer.echo("Aucun --place-ids fourni et data/raw/places/places.jsonl absent. "
                       "Lance `pac discover` d'abord, ou passe --place-ids.")
            raise typer.Exit(1)
        ids = [json.loads(l)["id"] for l in places_file.read_text().splitlines()]

    if limit:
        ids = ids[:limit]

    typer.echo(f"{len(ids)} lieu(x) à traiter, {n_workers} worker(s), max {max_reviews} avis/lieu.")

    # ProcessPoolExecutor plutôt que des threads : l'API sync de Playwright
    # n'est PAS thread-safe (un navigateur/contexte doit être piloté depuis
    # le thread qui l'a créé). Un processus par worker = un Playwright/
    # navigateur/contexte isolé chacun, ce qui correspond à l'architecture
    # "1 contexte Playwright par lieu" validée avec l'utilisateur.
    with concurrent.futures.ProcessPoolExecutor(max_workers=n_workers) as pool:
        for result in pool.map(_crawl_one_place, ids, [max_reviews] * len(ids)):
            typer.echo(f"  {result['place_id']}: {result['status']} "
                       f"({result['reviews_fetched']} avis)"
                       + (f" -- {result['error']}" if result["error"] else ""))


@app.command()
def load():
    """Phase 3 : charge les JSONL bruts dans DuckDB (idempotent)."""
    con = get_connection()
    n_places = load_places(con)
    n_reviews = load_reviews(con)
    typer.echo(f"places={n_places} reviews={n_reviews} -> {con}")


@app.command()
def stats():
    """Statistiques rapides sur la base chargée."""
    con = get_connection()
    n_places = con.execute("SELECT count(*) FROM places").fetchone()[0]
    n_reviews = con.execute("SELECT count(*) FROM reviews").fetchone()[0]
    typer.echo(f"{n_places} lieux, {n_reviews} avis")
    rows = con.execute(
        "SELECT count(*) FILTER (WHERE text IS NOT NULL) * 1.0 / count(*) "
        "FROM reviews"
    ).fetchone()
    if rows and rows[0] is not None:
        typer.echo(f"taux d'avis avec texte extrait : {rows[0]:.1%}")


@app.command()
def score(
    dry_run: bool = typer.Option(
        False, help="N'affiche que le nombre de mentions à classifier, sans appeler l'API"
    ),
    workers: int = typer.Option(None, help="Concurrence des appels de classification LLM"),
):
    """Score qualité "pain au chocolat" : extraction des mentions, classification
    LLM (OpenRouter) du sentiment spécifique à la pâtisserie, puis agrégation
    pondérée en note /10 par lieu (cf. plan pour la justification du design)."""
    con = get_connection()

    n_mentions = extract_mentions(con)
    n_pending = con.execute(
        "SELECT count(*) FROM pac_mentions_raw WHERE review_id NOT IN (SELECT review_id FROM pac_mentions)"
    ).fetchone()[0]
    typer.echo(f"{n_mentions} mention(s) totales détectées, {n_pending} à classifier.")

    if dry_run:
        return

    n_workers = workers or settings.score_workers
    n_classified = classify_mentions(con, workers=n_workers, model=settings.openrouter_model)
    typer.echo(f"{n_classified} mention(s) classifiée(s).")

    n_verified = verify_anomalies(con, workers=n_workers, model=settings.openrouter_verify_model)
    typer.echo(f"{n_verified} anomalie(s) désaccord note/sentiment re-vérifiée(s) "
               f"(modèle {settings.openrouter_verify_model}).")

    n_scored = compute_scores(con)
    typer.echo(f"{n_scored} lieu(x) avec un score_10 calculé.")

    top, bottom = leaderboard(con)
    typer.echo("\nTop pain au chocolat :")
    for name, s, n, conf in top:
        typer.echo(f"  {s:.1f}/10  {name}  ({n} avis, confiance={conf})")
    typer.echo("\nÀ éviter (confiance haute uniquement) :")
    for name, s, n, conf in bottom:
        typer.echo(f"  {s:.1f}/10  {name}  ({n} avis, confiance={conf})")


@app.command()
def reclassify(
    dry_run: bool = typer.Option(
        False, help="N'affiche que le nombre de mentions concernées, sans appeler l'API"
    ),
    workers: int = typer.Option(None, help="Concurrence des appels de classification LLM"),
):
    """Reclassifie TOUTES les mentions déjà extraites (écrase leur résultat
    existant), pour faire rétroagir un nouveau champ de sortie LLM (ex.
    signal_type/aspect/llm_confidence) sur des mentions classifiées avant
    son introduction. Coûte autant qu'un premier `pac score` complet --
    contrairement à `pac score`, PAS idempotent par delta : c'est le point.
    Recalcule aussi les scores à la fin. Pense à relancer
    `pac export-app-db` ensuite pour que l'app affiche le résultat."""
    con = get_connection()

    n_total = con.execute("SELECT count(*) FROM pac_mentions_raw").fetchone()[0]
    typer.echo(f"{n_total} mention(s) à reclassifier (TOUTES, pas seulement les nouvelles).")

    if dry_run:
        return

    n_workers = workers or settings.score_workers
    n_classified = classify_mentions(
        con, workers=n_workers, model=settings.openrouter_model, reclassify=True
    )
    typer.echo(f"{n_classified} mention(s) reclassifiée(s).")

    n_verified = verify_anomalies(con, workers=n_workers, model=settings.openrouter_verify_model)
    typer.echo(f"{n_verified} anomalie(s) désaccord note/sentiment re-vérifiée(s) "
               f"(modèle {settings.openrouter_verify_model}).")

    n_scored = compute_scores(con)
    typer.echo(f"{n_scored} lieu(x) avec un score_10 recalculé.")


@app.command(name="export-app-db")
def export_app_db_command():
    """Régénère data/pac_app.duckdb (base allégée dédiée au Streamlit,
    séparée de la base complète du pipeline) -- à relancer après chaque
    `pac score` pour que l'app affiche les données à jour."""
    counts = export_app_db()
    typer.echo(f"pac_app.duckdb régénérée : {counts}")


@app.command(name="export-web-json")
def export_web_json_command():
    """Régénère les fichiers JSON statiques du frontend Next.js/MapLibre
    (web/public/data/) à partir de pac_app.duckdb -- à relancer après
    `pac export-app-db` pour que ce frontend affiche les données à jour."""
    counts = export_web_json()
    typer.echo(f"{WEB_DATA_DIR} régénéré : {counts}")


if __name__ == "__main__":
    app()
