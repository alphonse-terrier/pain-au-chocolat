"""Tests de l'agrégation pondérée (score.compute_scores) sur données
synthétiques -- pas besoin d'appeler l'API LLM pour vérifier le SQL de
pondération (cf. plan, section Vérification, point 1)."""

import duckdb
import pytest

import pac.score as score_module
from pac.score import ANOMALY_THRESHOLD, compute_scores, verify_anomalies
from pac.store import SCHEMA


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute(SCHEMA)
    yield c
    c.close()


def _insert_place(con, place_id, name):
    con.execute(
        "INSERT INTO places (place_id, name, rating) VALUES (?, ?, 4.0)", [place_id, name]
    )


def _insert_review(con, review_id, place_id, author_review_count, published_at, text="x", rating=None):
    con.execute(
        """INSERT INTO reviews (review_id, place_id, author_review_count, published_at, text, rating)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [review_id, place_id, author_review_count, published_at, text, rating],
    )


def _insert_mention(con, review_id, place_id, relevant, sentiment):
    con.execute(
        """INSERT INTO pac_mentions (review_id, place_id, relevant, sentiment, model)
           VALUES (?, ?, ?, ?, 'test')""",
        [review_id, place_id, relevant, sentiment],
    )
    con.execute(
        "INSERT INTO pac_mentions_raw (review_id, place_id, text, matched_term) VALUES (?, ?, 'x', 'chocolatine')",
        [review_id, place_id],
    )


def _insert_aspect(con, review_id, aspect, weight):
    con.execute(
        "INSERT INTO pac_mention_aspects (review_id, aspect, weight) VALUES (?, ?, ?)",
        [review_id, aspect, weight],
    )


NOW = 1_800_000_000  # epoch arbitraire fixe, utilisé comme "published_at" récent


def test_zero_relevant_mentions_gives_null_not_a_default(con):
    """Un lieu sans mention pertinente ne doit PAS recevoir un score par
    défaut proche de sa note globale -- c'est la décision explicite de
    l'utilisateur (pas de faux positif "boulangerie bien notée -> pain au
    chocolat noté haut par défaut")."""
    _insert_place(con, "p1", "Boulangerie Zéro Mention")
    compute_scores(con)
    row = con.execute("SELECT score_10, confidence FROM pac_scores WHERE place_id='p1'").fetchone()
    assert row == (None, "insufficient_data")


def test_irrelevant_mention_excluded_from_score(con):
    """Une mention relevant=false (ex: plainte sur le prix) ne doit pas
    influencer le score -- c'est le correctif direct au piège prix-vs-goût
    trouvé dans les données réelles."""
    _insert_place(con, "p1", "Boulangerie Test")
    _insert_review(con, "r1", "p1", author_review_count=10, published_at=NOW)
    _insert_mention(con, "r1", "p1", relevant=False, sentiment=-0.9)  # plainte prix, pas goût
    compute_scores(con)
    row = con.execute("SELECT score_10, n_relevant FROM pac_scores WHERE place_id='p1'").fetchone()
    assert row == (None, 0)


def test_positive_mentions_yield_high_score(con):
    _insert_place(con, "p1", "Bonne Boulangerie")
    for i in range(6):
        _insert_review(con, f"r{i}", "p1", author_review_count=20, published_at=NOW)
        _insert_mention(con, f"r{i}", "p1", relevant=True, sentiment=0.9)
    compute_scores(con)
    score, n, conf = con.execute(
        "SELECT score_10, n_relevant, confidence FROM pac_scores WHERE place_id='p1'"
    ).fetchone()
    assert score > 8.0
    assert n == 6
    assert conf == "high"


def test_reviewer_credibility_weight_is_capped(con):
    """Un contributeur à des milliers d'avis ne doit pas écraser un
    contributeur normal (cf. plan : P95 observé = 303 avis/auteur)."""
    _insert_place(con, "p1", "Boulangerie A")
    _insert_review(con, "r1", "p1", author_review_count=50_000, published_at=NOW)
    _insert_mention(con, "r1", "p1", relevant=True, sentiment=1.0)  # power user, très positif

    _insert_place(con, "p2", "Boulangerie B")
    for i in range(3):
        _insert_review(con, f"s{i}", "p2", author_review_count=15, published_at=NOW)
        _insert_mention(con, f"s{i}", "p2", relevant=True, sentiment=-0.8)  # avis normaux, négatifs

    compute_scores(con)
    score_a = con.execute("SELECT score_10 FROM pac_scores WHERE place_id='p1'").fetchone()[0]
    score_b = con.execute("SELECT score_10 FROM pac_scores WHERE place_id='p2'").fetchone()[0]
    # Le power user ne doit pas dominer au point de rendre p1 extrême malgré
    # le lissage : le plafond de poids garde le score dans une plage raisonnable.
    assert score_a > score_b  # le sens reste correct (positif > négatif)
    assert score_a < 10.0  # mais pas un 10/10 artificiel dû au seul poids du power user


def test_old_review_weighted_less_than_recent(con):
    ten_years_ago = NOW - 10 * 365 * 86400

    _insert_place(con, "p1", "Boulangerie Ancienne Bonne Note")
    _insert_review(con, "r_old", "p1", author_review_count=10, published_at=ten_years_ago)
    _insert_mention(con, "r_old", "p1", relevant=True, sentiment=0.9)  # vieux, positif
    _insert_review(con, "r_new", "p1", author_review_count=10, published_at=NOW)
    _insert_mention(con, "r_new", "p1", relevant=True, sentiment=-0.9)  # récent, négatif

    compute_scores(con)
    score = con.execute("SELECT score_10 FROM pac_scores WHERE place_id='p1'").fetchone()[0]
    # L'avis récent négatif doit peser plus que le vieil avis positif ->
    # score global tiré vers le bas (sous le neutre 5.0).
    assert score < 5.0


def test_score_never_shrinks_toward_place_overall_rating(con):
    """Décision explicite de l'utilisateur : le retrait bayésien lisse vers
    le prior global (moyenne des mentions sur tout Paris), jamais vers la
    note Google globale du lieu lui-même. Un lieu très bien noté globalement
    mais avec une seule mention très négative doit rester bas, pas être tiré
    vers le haut par sa note globale de 4.0/5."""
    _insert_place(con, "p1", "Boulangerie Adorée Mais Pain Au Chocolat Raté")
    con.execute("UPDATE places SET rating = 4.9 WHERE place_id = 'p1'")
    _insert_review(con, "r1", "p1", author_review_count=50, published_at=NOW)
    _insert_mention(con, "r1", "p1", relevant=True, sentiment=-0.95)

    compute_scores(con)
    score = con.execute("SELECT score_10 FROM pac_scores WHERE place_id='p1'").fetchone()[0]
    # Si le lissage tirait vers rating=4.9/5 (~8/10), le score serait poussé
    # bien au-dessus de 5 malgré l'avis très négatif -- ça ne doit pas arriver.
    assert score < 4.0


def test_verify_anomalies_selects_only_strong_disagreement(con, monkeypatch):
    """abs(sentiment - note_normalisée) > ANOMALY_THRESHOLD sélectionne bien
    les cas de désaccord fort, et seulement ceux-là."""
    _insert_place(con, "p1", "Boulangerie A")
    # 5★ (normalisé +1.0) mais sentiment très négatif -> désaccord fort (2.0 > seuil).
    _insert_review(con, "r_anomaly", "p1", author_review_count=10, published_at=NOW, rating=5)
    _insert_mention(con, "r_anomaly", "p1", relevant=True, sentiment=-1.0)
    # 5★ et sentiment positif -> cohérent, ne doit pas être sélectionné.
    _insert_review(con, "r_ok", "p1", author_review_count=10, published_at=NOW, rating=5)
    _insert_mention(con, "r_ok", "p1", relevant=True, sentiment=0.9)

    calls = []

    def fake_classify(client, review_id, place_id, text, term, model):
        calls.append(review_id)
        return {"review_id": review_id, "place_id": place_id, "relevant": True, "appreciated": False, "sentiment": -1.0, "signal_type": None, "aspects": {}, "llm_confidence": None, "reason": "second avis", "failed": False}

    monkeypatch.setattr(score_module, "_classify_one", fake_classify)
    n = verify_anomalies(con, workers=1, model="test-strong-model")

    assert calls == ["r_anomaly"]
    assert n == 1


def test_verify_anomalies_never_arbitrates_toward_rating(con, monkeypatch):
    """Le second avis fait foi tel quel -- verify_anomalies ne doit JAMAIS
    ajuster le résultat vers la note de l'avis (cf. plan, Context point 3 :
    un 5★ qui déplore une baisse de qualité est un cas légitime)."""
    _insert_place(con, "p1", "Boulangerie A")
    _insert_review(con, "r1", "p1", author_review_count=10, published_at=NOW, rating=5)
    _insert_mention(con, "r1", "p1", relevant=True, sentiment=-1.0)

    def fake_classify(client, review_id, place_id, text, term, model):
        # Le second modèle CONFIRME le sentiment négatif malgré la note 5★.
        return {"review_id": review_id, "place_id": place_id, "relevant": True, "appreciated": False, "sentiment": -0.9, "signal_type": None, "aspects": {}, "llm_confidence": None, "reason": "confirmé", "failed": False}

    monkeypatch.setattr(score_module, "_classify_one", fake_classify)
    verify_anomalies(con, workers=1, model="test-strong-model")

    row = con.execute(
        "SELECT sentiment, verified FROM pac_mentions WHERE review_id='r1'"
    ).fetchone()
    # Le sentiment négatif du second avis est conservé tel quel -- pas tiré
    # vers +1.0 (ce que donnerait un alignement sur la note 5★).
    assert row == (-0.9, True)


def test_verify_anomalies_is_idempotent(con, monkeypatch):
    """Une mention déjà vérifiée (verified=true) ne doit pas être
    re-sélectionnée lors d'un second appel -- même si son désaccord persiste."""
    _insert_place(con, "p1", "Boulangerie A")
    _insert_review(con, "r1", "p1", author_review_count=10, published_at=NOW, rating=5)
    _insert_mention(con, "r1", "p1", relevant=True, sentiment=-1.0)

    calls = []

    def fake_classify(client, review_id, place_id, text, term, model):
        calls.append(review_id)
        return {"review_id": review_id, "place_id": place_id, "relevant": True, "appreciated": False, "sentiment": -0.9, "signal_type": None, "aspects": {}, "llm_confidence": None, "reason": "x", "failed": False}

    monkeypatch.setattr(score_module, "_classify_one", fake_classify)
    verify_anomalies(con, workers=1, model="test-strong-model")
    n_second_pass = verify_anomalies(con, workers=1, model="test-strong-model")

    assert calls == ["r1"]  # un seul appel au total, pas deux
    assert n_second_pass == 0


def test_verify_anomalies_does_not_clobber_on_technical_failure(con, monkeypatch):
    """Bug réel rencontré et corrigé : un échec technique du second modèle
    (ex. JSON mal formé) ne doit jamais écraser une classification valide
    existante par le résultat par défaut "non pertinent, sentiment=0"."""
    _insert_place(con, "p1", "Boulangerie A")
    _insert_review(con, "r1", "p1", author_review_count=10, published_at=NOW, rating=5)
    _insert_mention(con, "r1", "p1", relevant=True, sentiment=-1.0)

    def fake_classify_failing(client, review_id, place_id, text, term, model):
        return {
            "review_id": review_id, "place_id": place_id,
            "relevant": False, "sentiment": 0.0, "reason": "classification échouée: boom",
            "failed": True,
        }

    monkeypatch.setattr(score_module, "_classify_one", fake_classify_failing)
    n = verify_anomalies(con, workers=1, model="test-strong-model")

    row = con.execute(
        "SELECT relevant, sentiment, verified FROM pac_mentions WHERE review_id='r1'"
    ).fetchone()
    assert n == 0
    # La classification originale doit être intacte, pas écrasée par l'échec.
    assert row == (True, -1.0, False)


def test_classify_one_handles_null_sentiment_from_model(monkeypatch):
    """Bug réel corrigé : le modèle renvoie souvent littéralement
    "sentiment": null quand relevant=false (le prompt ne précise pas quoi
    mettre dans ce cas). float(result.get("sentiment", 0.0)) ne protège
    que si la clé est ABSENTE -- avec la clé présente à None, .get()
    retournait None malgré le défaut et float(None) plantait, faisant
    passer une vraie classification "non pertinent" pour un échec
    technique (failed=True) au lieu d'un jugement réel (failed=False).
    Vérifié en conditions réelles : 19849/24501 mentions d'un
    `pac reclassify` complet ont été touchées par exactement ce bug."""
    import httpx

    def fake_classify_json(client, system_prompt, user_prompt, model=None):
        return {"relevant": False, "sentiment": None, "reason": "parle du prix, pas du goût"}

    monkeypatch.setattr(score_module, "classify_json", fake_classify_json)

    result = score_module._classify_one(
        client=httpx.Client(), review_id="r1", place_id="p1", text="cher", term="chocolatine", model="test-model"
    )

    assert result["failed"] is False
    assert result["relevant"] is False
    assert result["sentiment"] == 0.0


def test_mention_with_identified_aspect_weighted_more_than_vague_mention(con):
    """Une mention qui identifie un critère précis (pac_mention_aspects)
    doit peser un peu plus qu'une mention tout aussi crédible/récente mais
    vague -- ASPECT_SPECIFICITY_BONUS (cf. plan). Deux lieux avec les mêmes
    deux sentiments opposés (+0.8/-0.8, même crédibilité/fraîcheur) :
    seul le lieu dont la mention positive a un aspect détecté doit finir
    au-dessus du neutre."""
    _insert_place(con, "p1", "Boulangerie Avec Aspect")
    _insert_review(con, "p1-pos", "p1", author_review_count=20, published_at=NOW)
    _insert_mention(con, "p1-pos", "p1", relevant=True, sentiment=0.8)
    _insert_aspect(con, "p1-pos", "chocolate_quantity", 1.0)
    _insert_review(con, "p1-neg", "p1", author_review_count=20, published_at=NOW)
    _insert_mention(con, "p1-neg", "p1", relevant=True, sentiment=-0.8)

    _insert_place(con, "p2", "Boulangerie Sans Aspect")
    _insert_review(con, "p2-pos", "p2", author_review_count=20, published_at=NOW)
    _insert_mention(con, "p2-pos", "p2", relevant=True, sentiment=0.8)
    _insert_review(con, "p2-neg", "p2", author_review_count=20, published_at=NOW)
    _insert_mention(con, "p2-neg", "p2", relevant=True, sentiment=-0.8)

    compute_scores(con)
    score_1 = con.execute("SELECT score_10 FROM pac_scores WHERE place_id='p1'").fetchone()[0]
    score_2 = con.execute("SELECT score_10 FROM pac_scores WHERE place_id='p2'").fetchone()[0]
    # p2 a deux mentions de poids strictement égal et de signe opposé -> se
    # neutralise exactement. p1's mention positive pèse plus (aspect
    # détecté) -> penche du côté positif, donc au-dessus de p2.
    assert score_1 > score_2


def test_aspect_score_requires_minimum_mentions(con):
    """Un score par aspect ne doit apparaître qu'à partir de
    MIN_ASPECT_MENTIONS mentions -- pas un chiffre décidé par un ou deux
    avis (cf. plan)."""
    _insert_place(con, "p1", "Boulangerie A")
    for i in range(2):
        _insert_review(con, f"r{i}", "p1", author_review_count=20, published_at=NOW)
        _insert_mention(con, f"r{i}", "p1", relevant=True, sentiment=0.8)
        _insert_aspect(con, f"r{i}", "lamination", 1.0)

    compute_scores(con)
    row = con.execute(
        "SELECT * FROM pac_place_aspects WHERE place_id='p1' AND aspect='lamination'"
    ).fetchone()
    assert row is None  # seulement 2 mentions -> pas encore de score affiché

    _insert_review(con, "r2", "p1", author_review_count=20, published_at=NOW)
    _insert_mention(con, "r2", "p1", relevant=True, sentiment=0.8)
    _insert_aspect(con, "r2", "lamination", 1.0)

    compute_scores(con)
    n_mentions = con.execute(
        "SELECT n_mentions FROM pac_place_aspects WHERE place_id='p1' AND aspect='lamination'"
    ).fetchone()[0]
    assert n_mentions == 3


def test_aspect_score_reflects_weighted_sentiment(con):
    """Le score par aspect doit refléter le sentiment des mentions qui
    citent CE critère précis, indépendamment des mentions qui ne le citent
    pas (cf. plan : un score par critère, pas une redite du score global)."""
    _insert_place(con, "p1", "Boulangerie Chocolat Généreux Feuilletage Raté")
    # 3 mentions positives sur la quantité de chocolat.
    for i in range(3):
        _insert_review(con, f"choc{i}", "p1", author_review_count=20, published_at=NOW)
        _insert_mention(con, f"choc{i}", "p1", relevant=True, sentiment=0.9)
        _insert_aspect(con, f"choc{i}", "chocolate_quantity", 1.0)
    # 3 mentions négatives sur le feuilletage -- ne doit pas polluer le
    # score "chocolate_quantity" ci-dessus.
    for i in range(3):
        _insert_review(con, f"lam{i}", "p1", author_review_count=20, published_at=NOW)
        _insert_mention(con, f"lam{i}", "p1", relevant=True, sentiment=-0.9)
        _insert_aspect(con, f"lam{i}", "lamination", 1.0)

    compute_scores(con)
    choc_score = con.execute(
        "SELECT score_10 FROM pac_place_aspects WHERE place_id='p1' AND aspect='chocolate_quantity'"
    ).fetchone()[0]
    lam_score = con.execute(
        "SELECT score_10 FROM pac_place_aspects WHERE place_id='p1' AND aspect='lamination'"
    ).fetchone()[0]
    assert choc_score > 8.0
    assert lam_score < 2.0
