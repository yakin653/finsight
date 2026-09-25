"""Schémas Pydantic pour les routes /assets."""
from datetime import datetime
from pydantic import BaseModel, Field


class AssetInfo(BaseModel):
    symbol: str
    prix_actuel: float
    date: datetime
    tendance: str = Field(..., description="'haussière' ou 'baissière'")
    ma20: float
    ma50: float


class PricePoint(BaseModel):
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class AssetHistory(BaseModel):
    symbol: str
    points: list[PricePoint]
    count: int