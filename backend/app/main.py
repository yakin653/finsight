import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .database import Base, SessionLocal, engine
from .jobs import run_market_jobs
from .market_refresh import ensure_market_data
from .models import (  # noqa: F401 — enregistre les tables
    AlertRule,
    AppMeta,
    Conversation,
    MarketData,
    Message,
    NewsItem,
    Notification,
    PasswordReset,
    PushSubscription,
    User,
    UserProfile,
    UserSymbol,
)
from .routers import assets, auth, chat, inbox, lab

Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub VARCHAR"))
    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0"))
    connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_google_sub ON users (google_sub) WHERE google_sub IS NOT NULL"))

ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if origin.strip()
]


def _origin_allowed(origin: str) -> bool:
    if origin in ORIGINS:
        return True
    # Déploiements Vercel (preview et prod) : https://….vercel.app
    return origin.startswith("https://") and origin.endswith(".vercel.app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = SessionLocal()
    try:
        ensure_market_data(db)
    finally:
        db.close()
    scheduler = None
    if not os.getenv("PYTEST_CURRENT_TEST"):
        from apscheduler.schedulers.background import BackgroundScheduler

        from .passwords import mail_status

        # Dit d'emblée où partent les e-mails (sans aucun identifiant).
        print(mail_status(), flush=True)

        from .market_refresh import refresh_all_quotes

        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(run_market_jobs, "interval", minutes=15, id="market-jobs", replace_existing=True)
        # Après la clôture du marché américain, du lundi au vendredi.
        scheduler.add_job(
            refresh_all_quotes,
            "cron",
            day_of_week="mon-fri",
            hour=21,
            minute=30,
            id="yahoo-daily",
            replace_existing=True,
        )
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="MarketPulse API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _referer_is_local(referer: str) -> bool:
    if any(referer == origin or referer.startswith(f"{origin}/") for origin in ORIGINS):
        return True
    return referer.startswith("https://") and ".vercel.app/" in referer


@app.middleware("http")
async def reject_foreign_origin(request: Request, call_next):
    """Une requête qui modifie l'état doit venir du site."""
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return await call_next(request)
    origin = request.headers.get("origin")
    if origin is not None:
        if origin == "null" or not _origin_allowed(origin):
            return JSONResponse(status_code=403, content={"detail": "Origine refusée."})
        return await call_next(request)
    if request.cookies.get("mp_session"):
        site = (request.headers.get("sec-fetch-site") or "").lower()
        referer = request.headers.get("referer") or ""
        if site == "same-origin" or _referer_is_local(referer):
            return await call_next(request)
        return JSONResponse(status_code=403, content={"detail": "Origine refusée."})
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


app.include_router(assets.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(inbox.router)
app.include_router(lab.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "marketpulse"}
