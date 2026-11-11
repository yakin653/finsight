"""Métriques, risque de portefeuille et anomalies. Lecture seule."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

import os

import httpx

from ..anomaly_calc import detect_points
from ..compare_calc import compare_frame, stress_frame
from ..database import get_db
from ..knowledge import get_fiche, list_fiches, search_fiches
from ..metrics_file import read_model_metrics
from ..models import AppMeta, MarketData, User, UserProfile, UserSymbol
from ..portfolio_calc import portfolio_risk
from ..security import get_current_user

router = APIRouter()


def _series(db: Session, symbol: str) -> list[tuple]:
    rows = (
        db.query(MarketData)
        .filter(MarketData.symbol == symbol)
        .order_by(MarketData.date.asc())
        .all()
    )
    return [(row.date, float(row.close)) for row in rows if row.close is not None and row.date is not None]


@router.get("/meta/freshness")
def freshness(db: Session = Depends(get_db)):
    """Âge de la dernière écriture de cours, lue dans app_meta."""
    row = db.get(AppMeta, "refreshed_at")
    if row is None:
        dated = db.query(AppMeta).filter(AppMeta.key.like("updated:%")).all()
        if not dated:
            return {"updated_at": None, "age_minutes": None}
        latest = max(item.value for item in dated)
        return {"updated_at": latest, "age_minutes": None, "label": f"cours du {latest}"}
    if "T" not in row.value:
        return {"updated_at": row.value, "age_minutes": None, "label": f"cours du {row.value}"}
    raw = row.value.replace("Z", "+00:00")
    moment = datetime.fromisoformat(raw)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    minutes = max(0, int((datetime.now(timezone.utc) - moment).total_seconds() // 60))
    return {"updated_at": row.value, "age_minutes": minutes, "label": f"mis à jour il y a {minutes} min"}


@router.get("/model/metrics")
def model_metrics():
    try:
        return read_model_metrics()
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Fichier d'évaluation introuvable.")


@router.get("/portfolio/risk")
def risk(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(UserProfile, user.id)
    symbols = set(profile.favorite_symbols or []) if profile else set()
    symbols.update(row.symbol for row in db.query(UserSymbol).filter_by(user_id=user.id).all())
    series = {symbol: _series(db, symbol) for symbol in sorted(symbols)}
    series = {symbol: points for symbol, points in series.items() if points}
    level = profile.level if profile else "intermediaire"
    return portfolio_risk(series, level)


@router.get("/compare")
def compare(symbols: str, db: Session = Depends(get_db)):
    names = [item.strip().upper() for item in symbols.split(",") if item.strip()][:4]
    if len(names) < 2:
        raise HTTPException(status_code=400, detail="Indique 2 à 4 symboles.")
    series = {name: _series(db, name) for name in names}
    return compare_frame(series)


@router.get("/portfolio/stress")
def stress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(UserProfile, user.id)
    symbols = set(profile.favorite_symbols or []) if profile else set()
    symbols.update(row.symbol for row in db.query(UserSymbol).filter_by(user_id=user.id).all())
    series = {symbol: _series(db, symbol) for symbol in sorted(symbols)}
    series = {symbol: points for symbol, points in series.items() if len(points) >= 2}
    return stress_frame(series)


@router.get("/knowledge")
def knowledge(q: str = ""):
    if q.strip():
        hits = search_fiches(q.strip(), 8)
        return {"fiches": [{"slug": hit["slug"], "title": hit["title"], "score": round(hit["score"], 3)} for hit in hits]}
    return {"fiches": list_fiches()}


@router.get("/knowledge/{slug}")
def knowledge_one(slug: str):
    doc = get_fiche(slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Fiche introuvable.")
    return doc


@router.get("/status")
def status(db: Session = Depends(get_db)):
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "indisponible"
    ollama = {"ok": False, "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b")}
    if not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            from ..ai_analyst import ollama_base

            tags = httpx.get(ollama_base() + "/api/tags", timeout=2.0)
            names = [str(item.get("name") or "") for item in tags.json().get("models") or []]
            ollama["ok"] = tags.status_code == 200 and any(ollama["model"].split(":")[0] in name for name in names)
            ollama["installes"] = names[:8]
        except (httpx.HTTPError, ValueError):
            ollama["ok"] = False
    fresh = freshness(db)
    try:
        metrics = read_model_metrics()
    except (FileNotFoundError, KeyError, TypeError, ValueError, OSError):
        metrics = None
    job = db.get(AppMeta, "news_job_at")
    return {
        "api": "ok",
        "database": database,
        "ollama": ollama,
        "yahoo": fresh,
        "modele": metrics,
        "news_job_at": job.value if job else None,
    }


@router.get("/anomalies/{symbol}")
def anomalies(symbol: str, db: Session = Depends(get_db)):
    points = _series(db, symbol.strip().upper())
    if not points:
        raise HTTPException(status_code=404, detail="Symbole introuvable.")
    closes = [price for _day, price in points]
    dates = [day.isoformat() for day, _price in points]
    found = detect_points(closes, dates)
    return {"symbol": symbol.strip().upper(), **found}
