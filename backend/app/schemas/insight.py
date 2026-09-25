"""Schémas Pydantic pour la route /insight."""
from datetime import datetime
from pydantic import BaseModel, Field


class SentimentInfo(BaseModel):
    score_moyen: float
    interpretation: str
    nombre_articles: int


class InsightResponse(BaseModel):
    symbol: str
    date: datetime
    prix_actuel: float
    tendance: str
    ma20: float
    ma50: float
    volatilite_annualisee: float
    max_drawdown_historique: float
    sentiment_30j: SentimentInfo
    probabilite_hausse_modele_ml: float | None = Field(
        None, description="Probabilité de hausse selon le modèle ML, entre 0 et 1"
    )
    analyse_llm: str = Field(..., description="Analyse en français générée par Ollama")
    disclaimer: str