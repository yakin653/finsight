from fastapi import APIRouter, HTTPException, Query

from app.db.database import engine
from app.services.anomaly_service import detect_anomalies

router = APIRouter(prefix="/anomalies", tags=["Anomalies"])


@router.get("/{symbol}")
def get_anomalies(
    symbol: str,
    limit: int = Query(default=500, ge=30, le=2000),
):
    try:
        result = detect_anomalies(engine, symbol.upper(), limit)
        if result["count"] == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Aucune donnée trouvée pour {symbol}",
            )
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
