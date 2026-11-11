"""Route /signal/{symbol} - signal ACHAT/VENTE/NEUTRE."""
from fastapi import APIRouter, HTTPException

from app.db.database import engine as db_engine
from app.schemas.signal import SignalResponse
from app.services import signal_service

router = APIRouter(prefix="/signal", tags=["Signal"])


@router.get("/{symbol}", response_model=SignalResponse)
def get_signal(symbol: str):
    """
    Genere un signal ACHAT/VENTE/NEUTRE pour un symbole en combinant :
    - Tendance technique (MA20 vs MA50)
    - Sentiment des news (FinBERT)
    - Probabilite du modele ML (si disponible)
    """
    data = signal_service.get_signal(db_engine, symbol.upper())
    if data is None:
        raise HTTPException(status_code=404, detail=f"Symbole '{symbol}' introuvable")
    return data
