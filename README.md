# 🥐 pain-au-chocolat

Où trouver le meilleur pain au chocolat de Paris — un pipeline qui récolte
les boulangeries de Paris et leurs avis Google, puis calcule une note /10
spécifique à la qualité du pain au chocolat (pas la note globale de la
boulangerie), affichée sur une carte interactive.

```
pac discover  →  pac reviews  →  pac load  →  pac score  →  streamlit run app.py
 (Places API)    (Playwright)     (DuckDB)     (OpenRouter)    (carte + classement)
```

Chaque étape est indépendante, idempotente, et écrit dans `data/pac.duckdb`.
On peut relancer n'importe laquelle sans casser les autres, et l'app lit
toujours l'état courant de la base — pas besoin d'attendre que tout le
pipeline soit "fini" pour regarder les résultats.

---

## 1. Installation

Prérequis : Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo>
cd pain-au-chocolat
uv sync                          # installe toutes les dépendances
uv run playwright install chromium   # navigateur headless pour la phase avis
```

Copier le fichier d'exemple et renseigner les clés :

```bash
cp .env.example .env
```

| Variable | Requise pour | Où l'obtenir |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | `pac discover` | [Google Cloud Console](https://console.cloud.google.com) → activer **Places API (New)** → Credentials → Create API key. Facturation à activer sur le projet (voir § Coûts). |
| `OPENROUTER_API_KEY` | `pac score` | [openrouter.ai/keys](https://openrouter.ai/keys) |

`pac reviews` et `pac load` ne nécessitent **aucune clé** (pas d'API
payante — le crawl des avis se fait via un navigateur headless).

Vérifier que tout est en place :

```bash
uv run pac --help
uv run pytest tests/ -q     # 20 tests, doivent tous passer, 0 dépendance réseau
```

---

## 2. Le pipeline, étape par étape

### 2.1 `pac discover` — trouver les boulangeries

Interroge l'API Google Places en pavant Paris (une seule requête ne
renvoie que 20 résultats max, sans pagination — le pavage compense cette
limite avec subdivision automatique des zones denses).

```bash
# Toujours commencer par un dry-run : affiche le nombre de cellules/appels
# prévus, sans toucher à l'API (donc sans rien coûter).
uv run pac discover --dry-run

# Test rapide sur un seul arrondissement avant de lancer tout Paris
uv run pac discover --arrondissement 12 --limit 50

# Paris entier
uv run pac discover
```

| Option | Effet |
|---|---|
| `--arrondissement N` (1-20) | Restreint à un seul arrondissement (bbox réelle, pas une approximation) |
| `--limit N` | Plafonne le nombre de lieux gardés |
| `--dry-run` | N'appelle pas l'API, affiche juste le plan de pavage |
| `--cell-size-m` | Taille de cellule du pavage (défaut 500m) |
| `--strict-bakery` / `--no-strict-bakery` | Ne garde que `primaryType == "bakery"` (défaut **activé** — sans ça, ~30% de bruit type supermarché/restaurant qui a juste "bakery" en type secondaire) |

Écrit dans `data/raw/places/places.jsonl`.

**Coût** : tarif officiel Google actuel — **32 $/1000 requêtes Nearby
Search**, avec **5000 requêtes gratuites par mois**. Paris entier nécessite
de l'ordre de 700 à 2900 appels selon la densité des zones (subdivisions) —
largement dans le palier gratuit dans l'immense majorité des cas. Toujours
vérifier `--dry-run` avant un run complet et surveiller *Facturation →
Budgets et alertes* dans la console Google Cloud.

### 2.2 `pac reviews` — récolter les avis

Ouvre un navigateur headless par lieu et fait défiler le panneau d'avis
Google Maps (l'API officielle des avis limite à 5 avis/lieu — insuffisant
ici ; voir § Comment ça marche pour le pourquoi de cette approche).

```bash
# Sur les lieux déjà découverts (data/raw/places/places.jsonl)
uv run pac reviews --limit 20 --max-reviews-per-place 50   # test rapide

uv run pac reviews                                          # run complet

# Ou sur une liste de place_id précise, sans passer par discover
uv run pac reviews --place-ids "ChIJ...,ChIJ..." --max-reviews-per-place 100
```

| Option | Effet |
|---|---|
| `--place-ids "id1,id2,..."` | Traite ces lieux précis plutôt que `places.jsonl` |
| `--limit N` | Plafonne le nombre de lieux traités |
| `--max-reviews-per-place N` | Défaut 500 ; 0 = illimité |
| `--workers N` | Contextes Playwright en parallèle (défaut 8) |

Écrit dans `data/raw/reviews/<place_id>.jsonl`. Chaque lieu affiche son
statut : `ok (N avis)` ou `no_reviews_tab` (avec reprise automatique sur 3
tentatives — la plupart des `no_reviews_tab` restants sont des lieux qui
n'ont simplement aucun avis, pas un bug).

**Temps** : mesuré en réel, ~35-40s pour 100 avis, jusqu'à ~120s pour un
lieu à 500 avis (cas extrême, la plupart des lieux ont beaucoup moins). Avec
8 workers en parallèle sur ~1000-1700 lieux : de l'ordre de quelques heures,
pas besoin de surveiller — relancer la commande plus tard reprend
naturellement là où c'est resté (idempotent par lieu).

**Fragilité connue** : ce crawl s'appuie sur le comportement observé de la
page Google Maps, pas une API stable documentée. Si Google change son
interface, `_open_reviews_tab` (`src/pac/reviews.py`) est le premier
endroit à regarder.

### 2.3 `pac load` — charger dans DuckDB

```bash
uv run pac load
uv run pac stats     # aperçu rapide : nb lieux, nb avis, % avec texte extrait
```

Lit tous les `.jsonl` sous `data/raw/` et les insère dans
`data/pac.duckdb` (`ON CONFLICT DO NOTHING` — rejouable sans créer de
doublons). C'est la seule commande qui écrit dans la base ; l'app Streamlit
et les requêtes d'exploration se font toujours en lecture seule.

### 2.4 `pac score` — noter la qualité du pain au chocolat

```bash
uv run pac score --dry-run   # combien de mentions seraient classifiées, sans appeler l'API
uv run pac score             # classification réelle + agrégation + mini leaderboard
```

| Option | Effet |
|---|---|
| `--dry-run` | N'appelle pas l'API, affiche juste le nombre de mentions en attente |
| `--workers N` | Concurrence des appels LLM (défaut 8) |

Idempotent par avis : relancer après un nouveau `pac reviews` + `pac load`
ne classifie que le delta. Voir § Comment ça marche pour le détail du
calcul.

### 2.5 L'application

```bash
uv run streamlit run app.py
```

Ouvre `http://localhost:8501` — carte de Paris avec toutes les
boulangeries (colorées par score, gris si pas encore de mentions
pain-au-chocolat), popup de détail au clic, onglet Classement (export CSV),
onglet Méthodologie. Se relit en direct sur `data/pac.duckdb` — pas besoin
de relancer l'app quand le pipeline continue de tourner en tâche de fond,
juste cliquer "🔄 Actualiser les données".

---

## 3. Comment ça marche (le nécessaire pour comprendre le code)

**Pourquoi Playwright et pas juste l'API Places pour les avis ?**
L'API officielle Places (New) plafonne à 5 avis par lieu — insuffisant.
Les endpoints non-officiels historiquement documentés
(`listugcposts`, `GetLocalBoqProxy`) sont obsolètes. Le protocole actuel de
Google (`MapsUgcPostService.ListUgcPosts` via `batchexecute`) refuse d'être
rejoué à la main même avec la bonne session — il faut laisser la vraie page
déclencher elle-même ses requêtes en scrollant, et les intercepter
passivement. Toute cette fragilité est isolée dans `src/pac/protocol.py`
(décodage bas niveau) et `src/pac/parse.py` (extraction des champs) —
c'est là qu'il faut regarder si Google change son format.

**Comment le score /10 est calculé** (`src/pac/score.py`) :
1. Les avis mentionnant "pain au chocolat" / "chocolatine" (et variantes)
   sont repérés par mot-clé — pas "chocolat" seul, trop bruyant.
2. Un LLM (OpenRouter) juge si la mention parle vraiment du **goût/qualité**
   de la pâtisserie ou seulement de son **prix** — piège réel trouvé dans
   les données (ex. avis 1★ qui se plaint du prix d'une chocolatine
   par ailleurs décrite comme excellente). Les mentions "prix" sont
   exclues, pas comptées comme négatives.
3. Pondération par crédibilité du contributeur (log du nb d'avis postés,
   plafonné) et par récence (décroissance exponentielle).
4. Agrégation en moyenne pondérée, avec un léger lissage vers la moyenne
   *parisienne* des mentions (pas vers la note Google du lieu lui-même —
   une boulangerie adorée peut avoir un mauvais pain au chocolat).
5. Une passe de vérification ciblée repasse par un second modèle plus
   capable les mentions où le sentiment contredit fortement la note de
   l'avis — sans jamais trancher en faveur de cette note (le second avis
   fait foi, indépendamment).
6. Zéro mention pertinente ⇒ `score_10 = NULL` (pas de valeur inventée).

---

## 4. Structure du projet

```
src/pac/
  config.py     # Settings (.env), bbox Paris + arrondissements
  grid.py       # pavage quadtree pour Nearby Search
  discover.py   # phase 1 : Places API
  protocol.py   # décodage bas niveau du protocole Google Maps (fragile, isolé)
  parse.py      # extraction des champs d'un avis brut (fragile, isolé)
  reviews.py    # phase 2 : crawl Playwright
  store.py      # schéma DuckDB + chargement des JSONL
  llm.py        # client OpenRouter minimal
  score.py      # extraction mentions -> classification -> agrégation
  cli.py        # `pac discover|reviews|load|score|stats`
  webapp/       # theme.py, data.py, map_view.py -- logique de app.py
app.py          # point d'entrée Streamlit
tests/          # pytest, fixtures réelles capturées en direct
spikes/         # scripts de diagnostic ponctuels (pas dans le pipeline)
data/           # généré, jamais commité (voir .gitignore)
```

## 5. Dépannage rapide

| Symptôme | Cause probable |
|---|---|
| `pac discover` échoue avec une erreur d'auth | `GOOGLE_MAPS_API_KEY` absente/invalide dans `.env`, ou API "Places API (New)" pas activée sur le projet Google Cloud |
| `pac score` : `OPENROUTER_API_KEY manquant` | Vérifier le nom exact de la variable dans `.env` (pas de faute de frappe type `OPENROUTER_API_KAY`) |
| Beaucoup de `no_reviews_tab` | Normal à ~10-15% (lieux sans avis réels) ; si c'est nettement plus, Google a peut-être changé son interface — vérifier `_open_reviews_tab` dans `reviews.py` |
| L'app Streamlit affiche "n'existe pas encore" | Lancer `pac load` au moins une fois |
| `duckdb.Error` au lancement de l'app | La base est momentanément verrouillée par un `pac load`/`pac score` en cours en tâche de fond — réessayer dans quelques secondes |
| L'app ne se met pas à jour après un nouveau crawl | Cliquer "🔄 Actualiser les données" (cache de 60s) |
