"""Tests d'integration de l'API FastAPI."""


def test_health(client):
    """La route /health doit repondre 200 et un statut ok."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "service" in body


def test_list_assets(client):
    """La route /assets renvoie une liste de symboles."""
    r = client.get("/assets")
    assert r.status_code == 200
    symbols = r.json()
    assert isinstance(symbols, list)
    assert len(symbols) > 0
    assert "AAPL" in symbols


def test_get_asset_aapl(client):
    """La route /assets/AAPL renvoie les infos du symbole."""
    r = client.get("/assets/AAPL")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "AAPL"
    assert data["prix_actuel"] > 0
    assert data["tendance"] in ("haussière", "baissière", "neutre", "indéterminée")
    assert "probabilite_hausse_pct" in data
    again = client.get("/assets/AAPL").json()
    assert again["probabilite_hausse_pct"] == data["probabilite_hausse_pct"]
    assert again["prix_actuel"] == data["prix_actuel"]


def test_get_asset_unknown(client):
    """Un symbole inconnu renvoie 404."""
    r = client.get("/assets/UNKNOWN_XYZ")
    assert r.status_code == 404


def test_get_history(client):
    """La route /history renvoie des points de prix."""
    r = client.get("/assets/AAPL/history?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "AAPL"
    assert data["count"] > 0
    assert len(data["points"]) == data["count"]
    assert "close" in data["points"][0]
    dates = [point["date"] for point in data["points"]]
    assert dates == sorted(dates)
    full = client.get("/assets/AAPL/history?limit=500")
    assert full.status_code == 200
    assert data["points"][-1]["date"] == full.json()["points"][-1]["date"]


def test_overview(client):
    r = client.get("/assets/overview")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["symbol"] == "AAPL" for row in rows)


def test_insight_is_deterministic(client):
    first = client.get("/insight/AAPL")
    second = client.get("/insight/AAPL")
    assert first.status_code == 200
    assert first.json() == second.json()
    assert "probabilite_hausse_pct" in first.json()


def test_ai_review_unknown(client):
    r = client.post("/assets/UNKNOWN_XYZ/ai-review")
    assert r.status_code == 404


def test_ai_review_insufficient_history(client):
    from datetime import date, timedelta

    from app.database import SessionLocal
    from app.models import MarketData

    db = SessionLocal()
    try:
        db.query(MarketData).filter(MarketData.symbol == "ZZTEST").delete()
        start = date(2024, 1, 1)
        for i in range(5):
            day = start + timedelta(days=i)
            db.add(MarketData(
                id=f"ZZTEST-{day.isoformat()}",
                symbol="ZZTEST",
                date=day,
                open=10,
                high=11,
                low=9,
                close=10 + i,
                volume=1000,
            ))
        db.commit()
        response = client.post("/assets/ZZTEST/ai-review")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "insufficient_data"
        assert body["recommandation"]["decision"] is None
        assert body["ml"]["probabilite_hausse_pct"] is None
        assert body["commentaire"]["source"] == "fallback"
        assert "review" in body
    finally:
        db.query(MarketData).filter(MarketData.symbol == "ZZTEST").delete()
        db.commit()
        db.close()


def test_ai_review_ollama_timeout_uses_fallback(client, monkeypatch):
    async def broken(_prompt: str) -> str:
        raise TimeoutError("ollama timeout")

    monkeypatch.setattr("app.ai_analyst.ask_ollama", broken)
    response = client.post("/assets/AAPL/ai-review")
    assert response.status_code == 200
    body = response.json()
    assert body["commentaire"]["source"] == "fallback"
    assert body["symbol"] == "AAPL"
    assert "review" in body and len(body["review"]) > 40


def test_ai_review_ollama_refusal_uses_fallback(client, monkeypatch):
    async def refusal(_prompt: str) -> str:
        return "I can't help with financial recommendations for AAPL. Please consult someone else today."

    monkeypatch.setattr("app.ai_analyst.ask_ollama", refusal)
    response = client.post("/assets/AAPL/ai-review")
    assert response.status_code == 200
    assert response.json()["commentaire"]["source"] == "fallback"


def test_ai_review_accepts_grounded_ollama_text(client, monkeypatch):
    async def echo(_prompt: str) -> str:
        return (
            "AAPL fait l'objet d'une reformulation limitée aux éléments déjà établis. "
            "La recommandation ACHAT, la recommandation CONSERVATION ou la recommandation VENTE "
            "est reprise telle quelle, sans nouveau pourcentage et sans événement extérieur."
        )

    monkeypatch.setattr("app.ai_analyst.ask_ollama", echo)
    response = client.post("/assets/AAPL/ai-review")
    assert response.status_code == 200
    body = response.json()
    assert body["commentaire"]["source"] == "ollama"
    assert body["review"] == body["commentaire"]["texte"]
