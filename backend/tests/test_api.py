"""Tests d'intégration de l'API FastAPI."""


def test_health(client):
    """La route /health doit répondre 200 et un statut ok."""
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
    # Sans accent pour eviter les problemes d'encodage
    assert data["tendance"].startswith("haussi") or data["tendance"].startswith("baissi")


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