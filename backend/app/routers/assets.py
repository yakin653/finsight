"""Routes /assets — informations sur les actifs."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from app.db.database import engine as db_engine
from app.services import data_service
from app.schemas.asset import AssetInfo, AssetHistory

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("", response_model=list[str])
def list_assets():
    """Liste tous les symboles disponibles en base."""
    return data_service.get_available_symbols(db_engine)


@router.get("/{symbol}", response_model=AssetInfo)
def get_asset(symbol: str):
    """Prix actuel + tendance pour un symbole."""
    info = data_service.get_asset_info(db_engine, symbol.upper())
    if info is None:
        raise HTTPException(status_code=404, detail=f"Symbole '{symbol}' introuvable")
    return info


@router.get("/{symbol}/history", response_model=AssetHistory)
def get_history(symbol: str, limit: int = 500):
    """Historique des prix (les `limit` derniers points)."""
    data = data_service.get_asset_history(db_engine, symbol.upper(), limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Symbole '{symbol}' introuvable")
    return data