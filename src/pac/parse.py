"""Extraction de champs structurés depuis les tableaux JSON bruts renvoyés
par /MapsUgcPostService.ListUgcPosts (cf. protocol.py pour le contexte).

Statut des champs (important, à lire avant de faire confiance à la sortie) :

- review_id, author_name, author_id, author_profile_url, published_at,
  review_text : positions vérifiées sur des avis réels capturés en direct
  (tests/fixtures/resp_wiz_*.txt), avec heuristiques de repli documentées
  ci-dessous.
- rating (note en étoiles) : **calibré et vérifié** (spikes/calibrate_rating.py) :
  entry[2][0][0] correspond à la note affichée dans le DOM sur 9/9
  échantillons croisés (voir tests/fixtures/dom_ratings.json +
  raw_payload_for_rating.json). `_rating_candidates()` reste disponible en
  champ de secours/debug si un cas réel s'écarte de ce chemin.
- author_review_count (nombre total d'avis postés par l'auteur, tous lieux
  confondus) : vérifié à la même occasion, entry[1][4][5][5].

Toute correction doit être accompagnée d'un nouveau cas dans
tests/fixtures/ et d'un test dans tests/test_parse.py.
"""

from dataclasses import dataclass, field


@dataclass
class ParsedReview:
    review_id: str
    author_name: str | None
    author_id: str | None
    author_profile_url: str | None
    author_review_count: int | None  # nb total d'avis postés par l'auteur, tous lieux
    published_at: float | None  # epoch seconds, None si non résolu
    relative_time_text: str | None  # texte affiché ("il y a 3 mois"), langue = hl
    text: str | None
    rating: int | None  # note en étoiles (1-5), calibrée contre le DOM réel
    rating_candidates: list = field(default_factory=list)  # secours/debug


def _walk(node, path=()):
    """Parcourt récursivement une structure JSON imbriquée en yield-ant
    (chemin, valeur) pour chaque feuille -- utilisé par les heuristiques de
    repli ci-dessous plutôt que des index en dur, pour tolérer les entrées
    dont la forme varie (avis avec/sans photo, avec/sans Q&A guidée...)."""
    if isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (i,))
    else:
        yield path, node


def _find_review_text(entry) -> str | None:
    """Le texte de l'avis vit dans une liste [texte, None|str, [0, n]] où le
    3e élément est une plage de surlignage (offsets de correspondance de
    recherche) sur un EXTRAIT tronqué du texte, pas forcément le texte en
    entier -- vérifié en direct (spikes de diagnostic, cf. plan "Améliorer
    la précision du score pain au chocolat") : n == len(texte) pour un texte
    court ("Très bon !", n=10), mais n < len(texte) pour un texte long
    (ex. n=240 alors que le texte fait 414 caractères, tronqué à ~230-240).

    D'où l'invariant correct : offset == [0, n] avec 0 < n <= len(texte),
    jamais n == len(texte) strictement (un ancien correctif l'exigeait à
    tort et cassait les avis longs). Un ancien seuil `len(texte) > 15`
    excluait en plus à tort les avis courts -- remplacé par cet invariant
    structurel."""
    if not isinstance(entry, list):
        return None

    def scan(node):
        if isinstance(node, list):
            if (
                2 <= len(node) <= 3
                and isinstance(node[0], str)
                and node[0]
                and not node[0].startswith(("http://", "https://", "//"))
                and isinstance(node[-1], list)
                and len(node[-1]) == 2
                and node[-1][0] == 0
                and isinstance(node[-1][1], int)
                and 0 < node[-1][1] <= len(node[0])
            ):
                return node[0]
            for child in node:
                found = scan(child)
                if found:
                    return found
        return None

    return scan(entry)


def _find_author_block(entry) -> tuple[str | None, str | None, str | None, int | None]:
    """Bloc auteur observé en entry[1][4][5] = [name, avatar_url,
    [profile_url], author_id, None, review_count, ...]. On tente cette
    position directe, avec repli sur None si absente (entrées "post
    marchand" où l'auteur est le nom de la boulangerie elle-même).

    review_count (block[5]) = nombre total d'avis postés par l'auteur, tous
    lieux confondus (ex. "10 avis", "Local Guide · 1,2 k avis") -- vérifié
    par calibrate_rating.py sur 9 échantillons réels."""
    try:
        block = entry[1][4][5]
        name = block[0] if isinstance(block[0], str) else None
        profile_url = block[2][0] if isinstance(block[2], list) and block[2] else None
        author_id = block[3] if isinstance(block[3], str) else None
        review_count = block[5] if isinstance(block[5], int) else None
        return name, author_id, profile_url, review_count
    except (IndexError, TypeError, KeyError):
        return None, None, None, None


def _find_rating(entry) -> int | None:
    """Note en étoiles (1-5), calibrée par croisement avec le DOM réel
    (spikes/calibrate_rating.py, tests/fixtures/dom_ratings.json) :
    entry[2][0][0] correspond à la note affichée sur 9/9 échantillons."""
    try:
        value = entry[2][0][0]
    except (IndexError, TypeError, KeyError):
        return None
    return value if isinstance(value, int) and 1 <= value <= 5 else None


def _rating_candidates(entry) -> list[int]:
    """Liste les petits entiers 1-5 trouvés dans l'entrée -- pour calibrage
    manuel, PAS pour extraction automatique (cf. docstring du module)."""
    candidates = []
    for _, v in _walk(entry):
        if isinstance(v, int) and 1 <= v <= 5:
            candidates.append(v)
    return candidates


def parse_review_entry(entry) -> ParsedReview | None:
    """Parse une entrée brute de la liste obj[2] (cf. protocol.decode_batchexecute).

    Renvoie None si l'entrée n'a manifestement pas la forme d'un avis
    exploitable (defensive: on préfère sauter une entrée plutôt que produire
    un enregistrement à moitié faux)."""
    if not isinstance(entry, list) or len(entry) < 2:
        return None

    review_id = entry[0] if isinstance(entry[0], str) else None
    if not review_id:
        return None

    meta = entry[1] if isinstance(entry[1], list) else []
    published_at = None
    if len(meta) > 2 and isinstance(meta[2], int):
        published_at = meta[2] / 1_000_000  # microsecondes -> secondes
    relative_time_text = meta[6] if len(meta) > 6 and isinstance(meta[6], str) else None

    author_name, author_id, author_profile_url, author_review_count = _find_author_block(entry)
    text = _find_review_text(entry)

    return ParsedReview(
        review_id=review_id,
        author_name=author_name,
        author_id=author_id,
        author_profile_url=author_profile_url,
        author_review_count=author_review_count,
        published_at=published_at,
        relative_time_text=relative_time_text,
        text=text,
        rating=_find_rating(entry),
        rating_candidates=_rating_candidates(entry),
    )


def parse_ugc_posts_payload(payload) -> tuple[list[ParsedReview], str | None]:
    """Extrait (avis_parsés, curseur_page_suivante) depuis le payload décodé
    d'une réponse /MapsUgcPostService.ListUgcPosts.

    Forme observée : payload = [None, next_cursor, [entrées...], ...].
    """
    if not isinstance(payload, list) or len(payload) < 3:
        return [], None
    next_cursor = payload[1] if isinstance(payload[1], str) else None
    raw_entries = payload[2] if isinstance(payload[2], list) else []
    # Chaque entrée arrive enveloppée dans une liste à un seul élément
    # ([entrée] plutôt que entrée directement) -- déballage systématique.
    raw_entries = [e[0] if isinstance(e, list) and len(e) == 1 else e for e in raw_entries]
    parsed = [r for r in (parse_review_entry(e) for e in raw_entries) if r is not None]
    return parsed, next_cursor
