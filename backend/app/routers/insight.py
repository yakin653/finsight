"""Route /insight/{symbol} — analyse complète (ML + sentiment + LLM)."""
from fastapi import APIRouter, HTTPException

from app.schemas.insight import InsightResponse
from app.services import insight_service

router = APIRouter(prefix="/insight", tags=["Insight"])


@router.get("/{symbol}", response_model=InsightResponse)
def get_insight(symbol: str):
    """
    Analyse complète d'un actif :
    - Prix et tendance
    - Probabilité ML
    - Sentiment des news
    - Explication en français générée par un LLM local (Ollama/Qwen2.5)

    ⚠️  Peut prendre 30-90 secondes (le LLM tourne sur CPU).
    """
    try:
        return insight_service.get_insight(symbol.upper())
    except SystemExit as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération : {e}")