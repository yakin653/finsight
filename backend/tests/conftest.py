"""Configuration pytest : fixtures partagées."""
import os

# Avant l'import de l'application : base locale, pas de téléchargement Yahoo.
os.environ.setdefault("DISABLE_RATE_LIMIT", "1")
# Aucun test ne doit joindre un vrai serveur d'e-mail, même si la machine en a un de configuré.
os.environ["SMTP_HOST"] = ""
os.environ.setdefault("MARKET_REFRESH_ON_START", "0")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:monmdp@localhost:5432/finsight",
)

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Un client HTTP de test pour l'API FastAPI."""
    return TestClient(app)
