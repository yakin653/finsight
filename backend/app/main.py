"""
FinSight — API Backend.

Lancement :
    cd backend
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI

from app.routers import assets, insight

app = FastAPI(
    title="FinSight API",
    description="API d'analyse financière : prix, ML, sentiment, LLM.",
    version="0.1.0",
)


@app.get("/health", tags=["Health"])
def health():
    """Vérifie que l'API est en ligne."""
    return {"status": "ok", "service": "finsight-api"}


# --- Routers ---
app.include_router(assets.router)
app.include_router(insight.router)