"""Règles de recommandation et validation du texte LLM. Aucun chiffre n'est inventé."""
from app.analysis import ML_DOWN, ML_UP, compose_review, decide, predict_probability
from app.ai_analyst import validate_llm_text
from app.market_refresh import pick_quotes


def _uptrend(n=80):
    closes = [100 + i * 0.4 for i in range(n)]
    volumes = [1_000_000 + i * 100 for i in range(n)]
    return closes, volumes


def _downtrend(n=80):
    closes = [200 - i * 0.4 for i in range(n)]
    volumes = [1_000_000 + i * 100 for i in range(n)]
    return closes, volumes


def _ml(probability, disponible=True):
    return {
        "disponible": disponible,
        "probabilite_hausse_pct": probability,
        "modele": "RandomForestClassifier",
        "baseline_toujours_hausse_pct": 52.9,
        "precision_modele_pct": 52.7,
        "message": "test",
    }


def test_insufficient_history_has_no_recommendation_and_no_fake_probability():
    closes = [10, 11, 12, 13, 14]
    package = compose_review("TEST", closes, [100] * 5, as_of="2024-01-05", ml_override=_ml(None, False))
    assert package["status"] == "insufficient_data"
    assert package["recommandation"]["decision"] is None
    assert package["recommandation"]["note_sur_5"] is None
    assert package["ml"]["probabilite_hausse_pct"] is None
    assert package["observe"]["ma20"] is None
    assert "Aucune recommandation" in package["review"]


def test_aligned_bullish_signals_recommend_buy():
    closes, volumes = _uptrend()
    package = compose_review("AAPL", closes, volumes, ml_override=_ml(ML_UP + 5))
    assert package["recommandation"]["decision"] == "ACHAT"
    assert package["recommandation"]["note_sur_5"] == 5
    assert package["recommandation"]["base"] == "modele_ml_et_moyennes_mobiles"
    assert "ACHAT" in package["review"]
    assert "conseil d'investissement" in package["limites"]


def test_divergence_forces_hold_and_caps_the_note():
    closes, volumes = _uptrend()
    package = compose_review("AAPL", closes, volumes, ml_override=_ml(ML_DOWN - 5))
    assert package["recommandation"]["decision"] == "CONSERVATION"
    assert package["recommandation"]["note_sur_5"] == 2


def test_aligned_bearish_signals_recommend_sell():
    closes, volumes = _downtrend()
    package = compose_review("TSLA", closes, volumes, ml_override=_ml(ML_DOWN - 5))
    assert package["recommandation"]["decision"] == "VENTE"
    assert package["recommandation"]["note_sur_5"] == 5


def test_high_volatility_blocks_a_buy():
    ind = {
        "n": 80,
        "prix": 120.0,
        "ma20": 110.0,
        "ma50": 100.0,
        "volatilite_annualisee_pct": 60.0,
        "max_drawdown_pct": -5.0,
    }
    rules = decide(ind, 70.0)
    assert rules["decision"] == "CONSERVATION"
    assert rules["risque_eleve"] is True


def test_without_model_the_technical_rule_is_explicit():
    closes, volumes = _uptrend()
    package = compose_review("MSFT", closes, volumes, ml_override=_ml(None, False))
    assert package["ml"]["probabilite_hausse_pct"] is None
    assert package["recommandation"]["base"] == "moyennes_mobiles"
    assert package["recommandation"]["decision"] == "ACHAT"


def test_model_probability_is_deterministic_and_bounded():
    closes, volumes = _uptrend(90)
    first = predict_probability(closes, volumes)
    second = predict_probability(closes, volumes)
    assert first == second
    if first["disponible"]:
        assert 0 <= first["probabilite_hausse_pct"] <= 100
    else:
        assert first["probabilite_hausse_pct"] is None


def test_short_series_never_invents_a_probability():
    result = predict_probability([1, 2, 3], [10, 10, 10])
    assert result["disponible"] is False
    assert result["probabilite_hausse_pct"] is None


def test_llm_validator_rejects_new_percentages_and_refusals():
    source = "AAPL clôture à 100.00 USD. Probabilité de hausse de 61.0 %. Recommandation : ACHAT."
    assert validate_llm_text(
        "AAPL reste au-dessus de ses moyennes. Recommandation : ACHAT. La probabilité citée est 61.0 %.",
        symbol="AAPL",
        decision="ACHAT",
        source_text=source,
    )
    assert not validate_llm_text(
        "AAPL va monter. Recommandation : ACHAT. La probabilité réelle est 95.0 % selon moi.",
        symbol="AAPL",
        decision="ACHAT",
        source_text=source,
    )
    assert not validate_llm_text(
        "I can't provide that kind of financial view for AAPL even if the recommendation is ACHAT.",
        symbol="AAPL",
        decision="ACHAT",
        source_text=source,
    )


def test_company_name_resolves_to_the_main_listing():
    hits = pick_quotes({
        "quotes": [
            {"symbol": "SAMZN=F", "quoteType": "FUTURE", "shortname": "Futures", "score": 10},
            {"symbol": "AMZN", "quoteType": "EQUITY", "shortname": "Amazon.com, Inc.", "score": 300000},
            {"symbol": "AMZN.TO", "quoteType": "EQUITY", "shortname": "Amazon CDR", "score": 20000},
        ]
    })
    assert hits[0]["symbol"] == "AMZN"
    assert "Amazon" in hits[0]["name"]
    assert all(hit["symbol"] != "SAMZN=F" for hit in hits)

def test_model_metrics_do_not_need_the_model_file(tmp_path, monkeypatch):
    """evaluation.json est suivi par Git, pas le modèle : un clone neuf doit lire les métriques."""
    import json

    from app.metrics_file import read_model_metrics

    (tmp_path / "evaluation.json").write_text(
        json.dumps({"modele": "RandomForest", "precision_modele": 0.5, "baseline_toujours_hausse": 0.6}),
        encoding="utf-8",
    )
    monkeypatch.setenv("ML_MODELS_DIR", str(tmp_path))
    metrics = read_model_metrics()
    assert metrics["precision_modele_pct"] == 50.0
    assert metrics["baseline_toujours_hausse_pct"] == 60.0
    assert metrics["avantage_prouve"] is False
