# 🥐 pain-au-chocolat

**Where's the best pain au chocolat in Paris?** This project scrapes every
bakery in Paris and its Google reviews, then uses an LLM to score the
*specific* quality of its pain au chocolat / chocolatine — not the
bakery's overall rating — and shows it all on an interactive map.

<p align="center">
  <img alt="pipeline" src="https://img.shields.io/badge/pipeline-discover%20%E2%86%92%20reviews%20%E2%86%92%20load%20%E2%86%92%20score%20%E2%86%92%20map-6b4226">
</p>

## Why bother separating the two?

Google's overall rating conflates everything — service, price, decor, that
one croissant that changed your life. A 1★ review is often just "€3.90 for
a chocolatine, are you kidding me" — not a comment on how it tastes. This
pipeline reads reviews that specifically mention pain au chocolat /
chocolatine, asks an LLM to judge *just* the taste/quality sentiment, and
throws out anything that's really about price or service.

## How it works

```
pac discover  →  pac reviews  →  pac load  →  pac score  →  streamlit run app.py
 (Places API)    (Playwright)     (DuckDB)     (OpenRouter)    (map + leaderboard)
```

Every step is independent and idempotent, writing into a single
`data/pac.duckdb` file. Re-run any step on its own without breaking the
others, and the app always reads whatever is currently in the database —
no need to wait for the full pipeline to finish before checking results.

---

## Quickstart

```bash
git clone <repo>
cd pain-au-chocolat
uv sync                              # install dependencies
uv run playwright install chromium   # headless browser for the reviews step

cp .env.example .env                 # then fill in your API keys, see below
uv run pytest tests/ -q              # sanity check: 20 tests, no network needed

uv run pac discover --arrondissement 12 --limit 50   # try it on one district first
uv run pac reviews --limit 20 --max-reviews-per-place 50
uv run pac load
uv run pac score --dry-run           # see how much this would cost before spending anything
uv run pac score
uv run streamlit run app.py          # open http://localhost:8501
```

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

### API keys

| Variable | Needed for | Get it from |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | `pac discover` | [Google Cloud Console](https://console.cloud.google.com) → enable **Places API (New)** → Credentials → Create API key. Billing must be enabled on the project (see Costs below). |
| `OPENROUTER_API_KEY` | `pac score` | [openrouter.ai/keys](https://openrouter.ai/keys) |

`pac reviews` and `pac load` need **no key at all** — no paid API, reviews
are crawled through a headless browser.

---

## The pipeline, step by step

### 1. `pac discover` — find the bakeries

Queries the Google Places API by tiling Paris into a grid (a single
request only returns up to 20 results with no pagination, so the grid
auto-subdivides dense areas to work around that).

```bash
uv run pac discover --dry-run              # always start here: shows the plan, costs nothing
uv run pac discover --arrondissement 12 --limit 50   # quick test on one district
uv run pac discover                        # the whole city
```

| Option | Effect |
|---|---|
| `--arrondissement N` (1-20) | Restrict to a single district (real bounding box, not eyeballed) |
| `--limit N` | Cap the number of places kept |
| `--dry-run` | No API calls — just prints the tiling plan |
| `--cell-size-m` | Grid cell size (default 500m) |
| `--strict-bakery` / `--no-strict-bakery` | Keep only `primaryType == "bakery"` (default **on** — otherwise ~30% noise from supermarkets/restaurants that list "bakery" as a secondary type) |

Writes to `data/raw/places/places.jsonl`.

> **💸 Cost**: current Google pricing is **$32 per 1000 Nearby Search
> requests**, with **5000 free requests/month**. Covering all of Paris
> takes roughly 700–2900 calls depending on how dense the subdivided areas
> are — comfortably inside the free tier in most cases. Always check
> `--dry-run` before a full run, and keep an eye on *Billing → Budgets &
> alerts* in Google Cloud Console.

### 2. `pac reviews` — crawl the reviews

Opens one headless browser per place and scrolls through the Google Maps
reviews panel. (The official reviews API caps out at 5 reviews per place —
nowhere near enough; see **How it works internally** below for why this
needs a browser at all.)

```bash
uv run pac reviews --limit 20 --max-reviews-per-place 50   # quick test
uv run pac reviews                                          # full run

# or target specific places directly, skipping discover
uv run pac reviews --place-ids "ChIJ...,ChIJ..." --max-reviews-per-place 100
```

| Option | Effect |
|---|---|
| `--place-ids "id1,id2,..."` | Process these specific places instead of `places.jsonl` |
| `--limit N` | Cap the number of places processed |
| `--max-reviews-per-place N` | Default 500; 0 = unlimited |
| `--workers N` | Parallel Playwright contexts (default 8) |

Writes to `data/raw/reviews/<place_id>.jsonl`. Each place reports its
status: `ok (N reviews)` or `no_reviews_tab` (auto-retried up to 3 times —
most remaining `no_reviews_tab` results are just places with genuinely no
reviews, not a bug).

> **⏱ Timing**: measured in practice, ~35-40s per 100 reviews, up to ~120s
> for a place with the full 500 (an extreme case — most places have far
> fewer). With 8 parallel workers over ~1000-1700 places, expect on the
> order of a few hours — no need to babysit it, since re-running the
> command later just picks up where it left off (idempotent per place).

> **⚠️ Known fragility**: this crawl relies on Google Maps' observed page
> behavior, not a documented stable API. If Google changes its UI,
> `_open_reviews_tab` in `src/pac/reviews.py` is the first place to look.

### 3. `pac load` — load into DuckDB

```bash
uv run pac load
uv run pac stats     # quick overview: place count, review count, % with extracted text
```

Reads every `.jsonl` file under `data/raw/` and inserts it into
`data/pac.duckdb` (`ON CONFLICT DO NOTHING` — safe to replay without
duplicating anything). This is the only command that writes to the
database; the Streamlit app and any exploratory queries are always
read-only.

### 4. `pac score` — rate the pain au chocolat

```bash
uv run pac score --dry-run   # how many mentions would be classified, no API calls
uv run pac score             # real classification + aggregation + a quick leaderboard
```

| Option | Effect |
|---|---|
| `--dry-run` | No API calls — just shows how many mentions are pending |
| `--workers N` | Concurrency for LLM calls (default 8) |

Idempotent per review: re-running after a fresh `pac reviews` + `pac load`
only classifies the new delta. See **How the score is computed** below for
the full method.

### 5. The app

```bash
uv run streamlit run app.py
```

Opens `http://localhost:8501` — a map of Paris with every bakery (colored
by score, gray if it has no pain-au-chocolat mentions yet), a detail popup
on click, a Leaderboard tab (CSV export), and a Methodology tab. It reads
`data/pac.duckdb` live, so you don't need to restart the app while the
pipeline keeps running in the background — just click "🔄 Refresh data".

---

## How it works internally

**Why Playwright instead of just the Places API for reviews?**
The official Places API (New) caps out at 5 reviews per place — not
enough. The historically-documented unofficial endpoints (`listugcposts`,
`GetLocalBoqProxy`) are dead. Google's current protocol
(`MapsUgcPostService.ListUgcPosts` via `batchexecute`) refuses to be
replayed by hand even with a valid session — the real page has to trigger
its own requests by scrolling, which we then intercept passively. All of
that fragility is isolated in `src/pac/protocol.py` (low-level decoding)
and `src/pac/parse.py` (field extraction) — that's where to look if Google
changes its format.

**How the /10 score is computed** (`src/pac/score.py`):
1. Reviews mentioning "pain au chocolat" / "chocolatine" (and spelling
   variants) are found by keyword — not "chocolat" alone, which would be
   too noisy.
2. An LLM (via OpenRouter) judges whether the mention is actually about
   the pastry's **taste/quality** or just its **price** — a real trap
   found in the data (e.g. a 1★ review complaining about the price of a
   chocolatine it otherwise describes as excellent). Price complaints are
   excluded entirely, not counted as negative.
3. Mentions are weighted by reviewer credibility (log of review count,
   capped) and by recency (exponential decay).
4. Aggregated as a weighted average, with light shrinkage toward the
   *Paris-wide* average of all mentions — never toward that bakery's own
   Google rating (a beloved bakery can still have a mediocre pain au
   chocolat).
5. A targeted verification pass re-checks, with a second and stronger
   model, any mention where the sentiment strongly disagrees with the
   review's overall rating — without ever deferring to that rating (the
   second opinion stands on its own).
6. Zero relevant mentions ⇒ `score_10 = NULL` — never a made-up default.

---

## Project structure

```
src/pac/
  config.py     # settings (.env), Paris bbox + district boundaries
  grid.py       # quadtree tiling for Nearby Search
  discover.py   # phase 1: Places API
  protocol.py   # low-level Google Maps protocol decoding (fragile, isolated)
  parse.py      # raw review field extraction (fragile, isolated)
  reviews.py    # phase 2: Playwright crawl
  store.py      # DuckDB schema + JSONL loading
  llm.py        # minimal OpenRouter client
  score.py      # mention extraction -> classification -> aggregation
  cli.py        # `pac discover|reviews|load|score|stats`
  webapp/       # theme.py, data.py, map_view.py -- app.py's logic
app.py          # Streamlit entry point
tests/          # pytest, fixtures captured from real data
spikes/         # one-off diagnostic scripts (not part of the pipeline)
data/           # generated, never committed (see .gitignore)
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `pac discover` fails with an auth error | `GOOGLE_MAPS_API_KEY` missing/invalid in `.env`, or "Places API (New)" not enabled on the Google Cloud project |
| `pac score`: `OPENROUTER_API_KEY manquant` | Double-check the exact variable name in `.env` (typos like `OPENROUTER_API_KAY` happen) |
| Lots of `no_reviews_tab` | Normal at ~10-15% (places with genuinely no reviews); if it's much higher, Google may have changed its UI — check `_open_reviews_tab` in `reviews.py` |
| Streamlit app says data "doesn't exist yet" | Run `pac load` at least once |
| `duckdb.Error` on app startup | The database is briefly locked by a `pac load`/`pac score` running in the background — retry in a few seconds |
| App doesn't reflect a new crawl | Click "🔄 Refresh data" (60s cache) |
