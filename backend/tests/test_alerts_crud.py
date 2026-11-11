"""CRUD des alertes pour la démonstration du module."""
from fastapi.testclient import TestClient

from app.main import app

ORIGIN = {"Origin": "http://localhost:3000"}
client = TestClient(app)


def _register():
    email = f"alert-{id(object())}@example.com"
    res = client.post("/auth/register", json={"email": email, "password": "Secret123", "display_name": "Alert"}, headers=ORIGIN)
    assert res.status_code == 200
    return res


def test_alert_create_list_toggle_delete():
    _register()
    created = client.post("/me/alerts", json={"symbol": "AAPL", "kind": "mm20", "threshold": None}, headers=ORIGIN)
    assert created.status_code == 200
    alert_id = created.json()["id"]

    listed = client.get("/me/alerts", headers=ORIGIN)
    assert listed.status_code == 200
    assert any(row["id"] == alert_id for row in listed.json())

    paused = client.patch(f"/me/alerts/{alert_id}", params={"enabled": False}, headers=ORIGIN)
    assert paused.status_code == 200
    assert paused.json()["enabled"] is False

    deleted = client.delete(f"/me/alerts/{alert_id}", headers=ORIGIN)
    assert deleted.status_code == 200
    leftover = client.get("/me/alerts", headers=ORIGIN)
    assert all(row["id"] != alert_id for row in leftover.json())
