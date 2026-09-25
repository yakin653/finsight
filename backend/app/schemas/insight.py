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
    volatilite_annualisee_pct: float = Field(..., description="Volatilité annualisée en %")
    max_drawdown_pct: float = Field(..., description="Max drawdown en %")
    sentiment_30j: SentimentInfo
    probabilite_hausse_pct: float | None = Field(
        None, description="Probabilité de hausse selon le modèle ML, en %"
    )
    analyse_llm: str
    disclaimer: str