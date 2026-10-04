"""Schemas Pydantic pour la route /signal."""
from pydantic import BaseModel, Field


class SignalComponent(BaseModel):
    score: float
    reason: str


class SignalComponents(BaseModel):
    technique: SignalComponent
    sentiment: SignalComponent
    ml: SignalComponent


class SignalResponse(BaseModel):
    symbol: str
    signal: str = Field(..., description="'ACHAT' | 'VENTE' | 'NEUTRE'")
    emoji: str
    color: str
    score: float
    max_score: float
    confidence_pct: float = Field(..., description="Confiance en % (0-100)")
    components: SignalComponents