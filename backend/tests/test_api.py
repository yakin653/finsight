"""Tests d'int?gration de l'API FastAPI."""
import pytest


# --- /health ---

def test_health(client):
    """La route /health doit r?pondre 200 et un statut ok."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "service" in body


# --- /assets ---

def test_list_assets(client):
    """La route /assets renvoie une liste de symboles."""
    r = client.get("/assets")
    assert r.status_code == 200
    symbols = r.json()
    assert isinstance(symbols, list)
    assert len(symbols) > 0
    assert "AAPL" in symbols


# --- /assets/{symbol} ---

def test_get_asset_aapl(client):
    """La route /assets/AAPL renvoie les infos du symbole."""
    r = client.get("/assets/AAPL")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "AAPL"
    assert data["prix_actuel"] > 0
    assert data["tendance"] in ("haussière", "baissière")


def test_get_asset_unknown(client):
    """Un symbole inconnu renvoie 404."""
    r = client.get("/assets/UNKNOWN_XYZ")
    assert r.status_code == 404


# --- /assets/{symbol}/history ---

def test_get_history(client):
    """La route /history renvoie des points de prix."""
    r = client.get("/assets/AAPL/history?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "AAPL"
    assert data["count"] == 10
    assert len(data["points"]) == 10
    assert "close" in data["points"][0]
