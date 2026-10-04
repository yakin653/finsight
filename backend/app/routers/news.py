"""Route /news/{symbol} - actualites avec sentiment FinBERT."""
from fastapi import APIRouter, HTTPException, Query

from app.db.database import engine as db_engine
from app.schemas.news import NewsResponse
from app.services import news_service

router = APIRouter(prefix="/news", tags=["News"])


@router.get("/{symbol}", response_model=NewsResponse)
def get_news(
    symbol: str,
    days: int = Query(30, ge=1, le=365, description="Nombre de jours en arriere"),
    limit: int = Query(50, ge=1, le=200, description="Nombre max d'articles"),
):
    """
    Renvoie les news d'un symbole sur les N derniers jours,
    avec leur sentiment calcule par FinBERT.
    """
    data = news_service.get_news(db_engine, symbol.upper(), days=days, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Aucune news pour {symbol}")
    return data