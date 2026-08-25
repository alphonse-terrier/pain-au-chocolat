# 🥐 pain-au-chocolat

### The most scientifically unnecessary, deeply important project in Paris.

Somewhere in this city there's a bakery whose pain au chocolat will change
your life, and somewhere else there's one selling what can only be
described as a lightly-chocolated cardboard tube for €3.90. This project
finds out which is which.

It scrapes every bakery in Paris, reads their Google reviews, and — instead
of trusting a 4.6★ overall rating that's really about the friendly owner
and the nice terrace — uses an LLM to isolate what people actually say
about **the pain au chocolat itself**. Then it plots the results on a map
so you can walk straight to the good stuff.

<p align="center">
  <img alt="pipeline" src="https://img.shields.io/badge/pipeline-discover%20%E2%86%92%20reviews%20%E2%86%92%20load%20%E2%86%92%20score%20%E2%86%92%20map-6b4226">
  <img alt="tests" src="https://img.shields.io/badge/tests-20%20passing-4c9a2a">
  <img alt="vibe" src="https://img.shields.io/badge/vibe-viennoiserie%20powered-e8a33d">
</p>

---

## The problem this solves 🕵️

Google's star rating is a soup of everything: service, price, decor, that
one time the owner's dog said hi. It tells you almost nothing about the
one thing you're actually walking in for.

Case in point, an actual 1★ review found in the wild:

> *"3,90€ la chocolatine, même chez les mac... [complains about the price
> for two more sentences] ... elle est délicieuse cela dit."*
>
> Translation: *"€3.90 for a chocolatine, that's outrageous... (it's
> delicious though)."*

That review drags down the bakery's average — for a pastry it praises. This
project reads reviews like that one, throws away the price rant, and keeps
"délicieuse." Multiply that by a few thousand reviews and you get a
leaderboard that's actually about the croissant's cousin, not the receipt.

## How it works, in one picture

```
pac discover  →  pac reviews  →  pac load  →  pac score  →  pac export-app-db  →  streamlit run app.py
 (find bakeries)  (grab reviews)  (put in DB)  (LLM judges)   (slim export)         (pretty map)
```

The pipeline (the first five steps) writes into `data/pac.duckdb`, then
`pac export-app-db` derives a much smaller `data/pac_app.duckdb` from it —
same places and scores, but only the review text the app actually shows
(skips the ~90% of raw review text that never gets displayed). **The app
only ever opens that slim file**, and `data/pac_app.duckdb` ships committed
in this repo — so browsing the map doesn't require running the pipeline at
all. Re-running the pipeline is only needed if you want to refresh the data
or hack on how it's built.

---

## 🚀 Just want to browse the map?

This is the common case — the app ships with real data already baked in,
no API key, no scraping, no waiting.

```bash
git clone <repo>
cd pain-au-chocolat
uv sync                              # grab the dependencies
uv run streamlit run app.py          # → http://localhost:8501, go find your croissant's cousin
```

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/). That's it —
`data/pac_app.duckdb` is already in the repo, so there's nothing to
generate first.

Opens a map of Paris with every bakery pinned and colored by score (gray =
no pain-au-chocolat mentions yet — not bad, just undiscovered), a detail
panel with all its reviews on click, a Ranking tab with CSV export, a "Near
an address" tab, and a Methodology tab for anyone who wants the receipts.

---

## 🔧 Want to regenerate the data yourself?

This is the advanced path: re-scraping bakeries/reviews, tweaking the
scoring, or refreshing stale data. Skip this entirely if you just want to
browse — see above.

```bash
uv run playwright install chromium   # the headless browser that reads reviews

cp .env.example .env                 # then drop your API keys in, see below 👇
uv run pytest tests/ -q              # 20 tests, no network needed, just to be sure nothing's on fire

# Take it for a spin on a single district before unleashing it on all of Paris
uv run pac discover --arrondissement 12 --limit 50
uv run pac reviews --limit 20 --max-reviews-per-place 50
uv run pac load
uv run pac score --dry-run           # peek at the bill before you pay it
uv run pac score
uv run pac export-app-db             # regenerate the slim export the app reads
uv run streamlit run app.py          # refresh the browser (data cache expires after 60s)
```

### 🔑 API keys

| Variable | Unlocks | Get it here |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | `pac discover` | [Google Cloud Console](https://console.cloud.google.com) → enable **Places API (New)** → Credentials → Create API key. You'll need billing enabled (see the cost callout below — it's cheaper than it sounds). |
| `OPENROUTER_API_KEY` | `pac score` | [openrouter.ai/keys](https://openrouter.ai/keys) |

Good news: `pac reviews`, `pac load` and `pac export-app-db` are completely
free — no key, no paid API.

---

## 📖 The pipeline, step by step

### 1. `pac discover` — go find the bakeries

Tiles all of Paris into a grid and queries the Google Places API cell by
cell (a single request only ever returns 20 results with no pagination, so
dense areas get automatically subdivided until nothing's missed).

```bash
uv run pac discover --dry-run                        # free preview: shows the plan, calls nothing
uv run pac discover --arrondissement 12 --limit 50    # dip a toe in one district
uv run pac discover                                   # the whole city, all 20 arrondissements
```

| Option | Effect |
|---|---|
| `--arrondissement N` (1-20) | Restrict to a single district (real bounding box, not eyeballed) |
| `--limit N` | Cap how many places to keep |
| `--dry-run` | Calls no API — just prints the tiling plan |
| `--cell-size-m` | Grid cell size (default 500m) |
| `--strict-bakery` / `--no-strict-bakery` | Keep only `primaryType == "bakery"` (**on** by default — otherwise ~30% of results turn out to be supermarkets and restaurants with "bakery" as a footnote) |

Writes to `data/raw/places/places.jsonl`.

> **💸 What this costs**: Google charges **$32 per 1000 Nearby Search
> requests**, with **5000 free per month**. Covering all of Paris takes
> roughly 700–2900 calls depending on how much subdividing the dense areas
> need — comfortably free in most cases. Still: always sanity-check with
> `--dry-run` first, and keep an eye on *Billing → Budgets & alerts* in
> Google Cloud Console so nobody gets a surprise invoice over a pastry
> ranking.

### 2. `pac reviews` — send in the (headless) tourists

Opens a real headless browser per bakery and scrolls through its Google
Maps reviews panel like a very patient, very fast human. (The official
reviews API only hands over 5 reviews per place — nowhere near enough to
say anything meaningful. Full story in **How it works internally** below.)

```bash
uv run pac reviews --limit 20 --max-reviews-per-place 50   # quick test
uv run pac reviews                                          # the full crawl

# or skip discover entirely and point at specific places
uv run pac reviews --place-ids "ChIJ...,ChIJ..." --max-reviews-per-place 100
```

| Option | Effect |
|---|---|
| `--place-ids "id1,id2,..."` | Process exactly these places instead of `places.jsonl` |
| `--limit N` | Cap how many places to process |
| `--max-reviews-per-place N` | Default 500; 0 = no limit |
| `--workers N` | Parallel browser contexts (default 8) |

Writes to `data/raw/reviews/<place_id>.jsonl`. Each place reports its
status as it finishes: `ok (N reviews)` or `no_reviews_tab` (auto-retried
up to 3 times — most of these are just places that genuinely have zero
reviews, not a bug chasing its tail).

> **⏱ How long this takes**: measured for real, ~35-40s per 100 reviews,
> up to ~120s for a place with the full 500 (a rare extreme — most places
> have far fewer). With 8 workers running in parallel over ~1000-1700
> places, budget a few hours and go make yourself a coffee — no need to
> babysit it, since running the command again later just resumes where it
> left off (idempotent per place).

> **⚠️ Glass-fragile by design**: this crawl leans on how the Google Maps
> page currently behaves, not a documented stable API. If Google reshuffles
> its UI one day, `_open_reviews_tab` in `src/pac/reviews.py` is exhibit A.

### 3. `pac load` — pour everything into DuckDB

```bash
uv run pac load
uv run pac stats     # a quick gut check: place count, review count, % with usable text
```

Reads every `.jsonl` file under `data/raw/` and inserts it into
`data/pac.duckdb` (`ON CONFLICT DO NOTHING` — replay it as many times as
you like, nothing duplicates). This is the *only* command that writes to
the database; the app and any exploring you do are always read-only.

### 4. `pac score` — where the magic (and the LLM bill) happens

```bash
uv run pac score --dry-run   # see how many mentions are waiting, no API calls yet
uv run pac score             # classify for real + aggregate + print a mini leaderboard
```

| Option | Effect |
|---|---|
| `--dry-run` | No API calls — just shows how many mentions are pending |
| `--workers N` | Concurrency for LLM calls (default 8) |

Idempotent per review: run it again after a fresh `pac reviews` + `pac
load` and it only classifies the new arrivals. The full method is unpacked
in **How the score is computed** below, for the curious.

### 5. `pac export-app-db` — trim the database down for the app

```bash
uv run pac export-app-db
```

Derives `data/pac_app.duckdb` from `data/pac.duckdb`: same places and
scores, but only the review text the app will actually show (reviews
matching a retained pain-au-chocolat/viennoiserie mention) — dropping the
other ~90% shrinks the file roughly 6-10x. Re-run it any time after a fresh
`pac score` to refresh what the app shows.

> **🥐 There's also a Next.js + MapLibre frontend** in `web/`, a faster
> alternative to the Streamlit app meant for deployment on Vercel — same
> data, same features, no server/database at runtime (everything is static
> JSON, regenerated by `pac export-web-json` from `data/pac_app.duckdb`).
> See `web/README.md`. Both frontends coexist; neither replaces the other.

```bash
uv run pac export-web-json           # regenerate web/public/data/ for the Next.js frontend
```

### 6. Back to the app

```bash
uv run streamlit run app.py          # or just wait -- data cache expires after 60s
```

The app only ever reads `data/pac_app.duckdb` (see **Just want to browse
the map?** above for what it looks like) — nothing you did in steps 1-5
shows up until step 5's export has run (and up to 60s of caching after that).

---

## 🔬 How it works internally

**Why a whole headless browser just to read reviews?**
The official Places API (New) hands over a measly 5 reviews per place —
useless for anything statistical. The old unofficial endpoints people used
to scrape (`listugcposts`, `GetLocalBoqProxy`) are dead. Google's current
protocol (`MapsUgcPostService.ListUgcPosts` via `batchexecute`) flatly
refuses to be replayed by hand, even with a perfectly valid session — the
real page has to trigger its own requests by scrolling, and we just quietly
watch and record what flies by. All of that fragile plumbing is fenced off
in `src/pac/protocol.py` (low-level decoding) and `src/pac/parse.py` (field
extraction) — that's the first place to look if Google ever changes the
rules of the game.

**How the score out of 10 actually gets computed** (`src/pac/score.py`):

1. Reviews mentioning "pain au chocolat" / "chocolatine" (and spelling
   variants) get flagged by keyword — deliberately *not* just "chocolat",
   which would sweep in every hot chocolate and chocolate croissant in
   town.
2. An LLM (via OpenRouter) reads each mention and decides: is this really
   about the **taste/quality**, or just the **price**? (Remember the €3.90
   rant above — that's exactly the trap this step exists to dodge.) Price
   complaints get excluded entirely, never counted as a negative.
3. Surviving mentions are weighted by how credible the reviewer looks (log
   of their total review count, capped so power-users can't single-
   handedly swing a score) and by recency (older reviews fade
   exponentially).
4. Everything's combined into a weighted average, with a light nudge
   toward the *Paris-wide* average of all mentions — never toward that
   specific bakery's own Google rating (a beloved bakery can absolutely
   have a forgettable pain au chocolat, and the score should say so).
5. A targeted double-check sends any mention where the sentiment strongly
   disagrees with its review's star rating through a second, stronger
   model — as an independent second opinion, never as a tie-breaker that
   defers back to the star rating.
6. Zero relevant mentions for a bakery? It gets `score_10 = NULL`. No
   guessing, no made-up "probably fine" default.

---

## 🗂 Project structure

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
  export_app_db.py  # derives the slim pac_app.duckdb from pac.duckdb
  export_web_json.py  # derives web/public/data/*.json from pac_app.duckdb
  cli.py        # `pac discover|reviews|load|score|export-app-db|export-web-json|stats`
  webapp/       # theme.py, data.py, map_view.py, geocode.py -- app.py's logic
app.py          # Streamlit entry point
web/            # Next.js + MapLibre frontend (Vercel), reads only web/public/data/
tests/          # pytest, fixtures captured from real data
spikes/         # one-off diagnostic scripts (not part of the pipeline)
data/           # generated -- pac_app.duckdb is committed (see .gitignore), the rest isn't
```

## 🆘 Troubleshooting

| Symptom | Likely cause |
|---|---|
| `pac discover` fails with an auth error | `GOOGLE_MAPS_API_KEY` missing/invalid in `.env`, or "Places API (New)" isn't enabled on the Google Cloud project |
| `pac score`: `OPENROUTER_API_KEY manquant` | Double-check the exact variable name in `.env` (yes, `OPENROUTER_API_KAY` typos happen to the best of us) |
| Lots of `no_reviews_tab` | Normal at ~10-15% (places with genuinely no reviews); if it's way higher than that, Google may have changed its UI — check `_open_reviews_tab` in `reviews.py` |
| Streamlit app says data "doesn't exist yet" | `data/pac_app.duckdb` is missing -- it ships committed in the repo, so this should only happen if you deleted it; run `pac export-app-db` (needs a `pac.duckdb` to export from, see the pipeline section) |
| `duckdb.Error` on app startup | `pac_app.duckdb` is briefly locked by a `pac export-app-db` running in the background — retry in a few seconds |
| App doesn't reflect a fresh `pac score` | Run `pac export-app-db` to regenerate `pac_app.duckdb`, then reload the browser (60s cache) |

---

<p align="center"><i>Now go find your croissant's chocolate-filled cousin. 🥐</i></p>
