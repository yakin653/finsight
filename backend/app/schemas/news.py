"""Schemas Pydantic pour la route /news."""
from datetime import datetime
from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    date: datetime
    headline: str
    source: str | None = None
    url: str | None = None
    pos: float = Field(..., description="Score positif FinBERT (0-1)")
    neu: float = Field(..., description="Score neutre FinBERT (0-1)")
    neg: float = Field(..., description="Score negatif FinBERT (0-1)")
    sentiment: str = Field(..., description="'positive' | 'neutral' | 'negative'")


class NewsResponse(BaseModel):
    symbol: str
    count: int
    days: int
    sentiment_score: float = Field(..., description="Score moyen pos - neg sur la periode")
    interpretation: str = Field(..., description="'positif' | 'neutre' | 'negatif'")
    news: list[NewsItem]