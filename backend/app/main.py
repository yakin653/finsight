"""
FinSight - API Backend.

Lancement :
    cd backend
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI

from app.routers import assets, insight, news, signal

app = FastAPI(
    title="FinSight API",
    description="API d analyse financiere : prix, ML, sentiment, LLM, signal.",
    version="0.3.0",
)


@app.get("/health", tags=["Health"])
def health():
    """Verifie que l API est en ligne."""
    return {"status": "ok", "service": "finsight-api"}


# --- Routers ---
app.include_router(assets.router)
app.include_router(insight.router)
app.include_router(news.router)
app.include_router(signal.router)
