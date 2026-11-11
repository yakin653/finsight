"""Intentions du chat, validation, et règles de notification."""
import os

from app.chat_engine import detect_intent, template_answer, validate_chat_answer
from app.delivery import delivery_mode, in_quiet_hours, matches_interest
from app.security import _HITS, allow


def test_intent_rules():
    assert detect_intent("Quel est le prix de AAPL ?") == "prix"
    assert detect_intent("La tendance est-elle au-dessus de la MM20 ?") == "tendance"
    assert detect_intent("Quel est le risque et la volatilité ?") == "risque"
    assert detect_intent("Explique le Pulse Score") == "pulse"
    assert detect_intent("Compare AAPL et MSFT") == "comparaison"
    assert detect_intent("Des news sur Apple ?") == "news"
    assert detect_intent("C'est quoi la MM20 ?") == "glossaire"
    assert detect_intent("Quelle est la météo à Tunis ?") == "hors_sujet"


def test_chat_validator_rejects_invented_percent_and_advice():
    facts = '{"symbol": "AAPL", "prix": 100.0, "variation": 1.2}'
    assert validate_chat_answer("AAPL clôture à 100 USD, variation 1.2 %.", facts, ["AAPL"])
    assert not validate_chat_answer("AAPL va monter de 95 %.", facts, ["AAPL"])
    assert not validate_chat_answer("AAPL : tu devrais acheter maintenant.", facts, ["AAPL"])
    assert not validate_chat_answer("TSLA vaut 100 USD.", facts, ["AAPL"])


def test_template_fallback_does_not_invent_a_price():
    text = template_answer("prix", {"symbol": "AAPL", "prix": None, "date": None, "variation": None}, "debutant")
    assert "AAPL" in text
    assert "non calculé" in text
    assert "conseil" in text


def test_quiet_hours_and_delivery():
    assert in_quiet_hours(22, 7, 23) is True
    assert in_quiet_hours(22, 7, 12) is False
    assert delivery_mode({"frequence": "instantane", "quiet_start": 22, "quiet_end": 7}, 23) == "skip"
    assert delivery_mode({"frequence": "quotidien", "heure": 8, "quiet_start": 22, "quiet_end": 7}, 8) == "digest"
    assert delivery_mode({"frequence": "quotidien", "heure": 8, "quiet_start": 22, "quiet_end": 7}, 9) == "skip"
    assert matches_interest("AAPL", "Autre sujet", ["AAPL"], []) is True
    assert matches_interest("MSFT", "résultats apple", [], ["apple"]) is True
    assert matches_interest("MSFT", "banque", ["AAPL"], ["apple"]) is False


def test_anomalies_refuse_a_short_series():
    from app.anomaly_calc import detect_points

    result = detect_points([100.0 + index for index in range(59)], [f"2024-01-{index:02d}" for index in range(1, 60)])
    assert result["status"] == "insufficient_data"


def test_register_login_and_delete(client):
    import uuid

    email = f"revue-{uuid.uuid4().hex[:8]}@example.com"
    created = client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Revue"})
    assert created.status_code == 200
    assert created.json()["onboarding_completed"] is False
    assert client.get("/auth/me").status_code == 200
    assert client.delete("/me", headers={"Origin": "http://localhost:3000"}).status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_rate_limit_blocks_the_third_call(monkeypatch):
    monkeypatch.delenv("DISABLE_RATE_LIMIT", raising=False)
    os.environ.pop("DISABLE_RATE_LIMIT", None)
    _HITS.clear()
    assert allow("demo", 2, 60, now=1_000) is True
    assert allow("demo", 2, 60, now=1_001) is True
    assert allow("demo", 2, 60, now=1_002) is False
