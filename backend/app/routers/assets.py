from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import MarketData

router = APIRouter()

@router.get("/assets")
def get_assets(db: Session = Depends(get_db)):
    symbols = db.query(MarketData.symbol).distinct().all()
    return [s[0] for s in symbols]

@router.get("/assets/{symbol}")
def get_asset(symbol: str, db: Session = Depends(get_db)):
    latest = db.query(MarketData).filter(MarketData.symbol == symbol).order_by(MarketData.date.desc()).first()
    if not latest:
        return {"error": "Symbole introuvable"}
    
    # Calcul basique des moyennes mobiles
    history = db.query(MarketData).filter(MarketData.symbol == symbol).order_by(MarketData.date.desc()).limit(50).all()
    ma20 = sum([h.close for h in history[:20]]) / 20 if len(history) >= 20 else latest.close
    ma50 = sum([h.close for h in history]) / len(history) if len(history) > 0 else latest.close
    
    tendance = "haussière" if latest.close > ma20 else "baissière"
    
    return {
        "symbol": symbol,
        "prix_actuel": latest.close,
        "date": latest.date,
        "tendance": tendance,
        "ma20": ma20,
        "ma50": ma50
    }

@router.get("/assets/{symbol}/history")
def get_history(symbol: str, limit: int = 30, db: Session = Depends(get_db)):
    history = db.query(MarketData).filter(MarketData.symbol == symbol).order_by(MarketData.date.asc()).limit(limit).all()
    return {
        "symbol": symbol,
        "points": [{"date": str(h.date), "open": h.open, "high": h.high, "low": h.low, "close": h.close, "volume": h.volume} for h in history],
        "count": len(history)
    }