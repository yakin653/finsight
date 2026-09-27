"""Configuration pytest : fixtures partag?es."""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Un client HTTP de test pour l'API FastAPI."""
    return TestClient(app)
