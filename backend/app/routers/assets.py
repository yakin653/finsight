from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai_analyst import comment
from ..analysis import LIMITES, asset_summary, compose_review, history_points
from ..database import get_db
from ..market_refresh import (
    DEFAULT_SYMBOLS,
    SYMBOL_RE,
    name_for,
    origin_for,
    refresh_symbols,
    replace_symbol,
    resolve_listing,
    set_meta,
)
from ..models import MarketData, UserProfile
from ..security import get_optional_user

router = APIRouter()


def normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not SYMBOL_RE.match(cleaned):
        raise HTTPException(status_code=400, detail="Symbole invalide.")
    return cleaned


def _rows(db: Session, symbol: str) -> list[MarketData]:
    return (
        db.query(MarketData)
        .filter(MarketData.symbol == symbol)
        .order_by(MarketData.date.asc())
        .all()
    )


def _series(rows: list[MarketData]):
    closes, volumes, dates = [], [], []
    for row in rows:
        if row.close is None:
            continue
        closes.append(float(row.close))
        volumes.append(float(row.volume or 0.0))
        dates.append(row.date)
    return closes, volumes, dates


def _summary_or_404(db: Session, symbol: str) -> dict:
    rows = _rows(db, symbol)
    closes, volumes, dates = _series(rows)
    if not closes:
        raise HTTPException(status_code=404, detail="Symbole introuvable.")
    as_of = dates[-1].isoformat() if hasattr(dates[-1], "isoformat") else str(dates[-1])
    summary = asset_summary(symbol, closes, volumes, as_of=as_of, origine=origin_for(db, symbol))
    summary["nom"] = name_for(db, symbol)
    return summary


@router.get("/assets")
def get_assets(db: Session = Depends(get_db)):
    symbols = db.query(MarketData.symbol).distinct().all()
    return sorted({row[0] for row in symbols})


@router.get("/assets/overview")
def get_overview(db: Session = Depends(get_db)):
    symbols = sorted({row[0] for row in db.query(MarketData.symbol).distinct().all()})
    return [_summary_or_404(db, symbol) for symbol in symbols]


@router.post("/assets/refresh")
def refresh_market(db: Session = Depends(get_db)):
    existing = [row[0] for row in db.query(MarketData.symbol).distinct().all()]
    symbols = list(dict.fromkeys([*existing, *DEFAULT_SYMBOLS]))
    return refresh_symbols(db, symbols)


@router.post("/assets/add/{query}")
def add_asset(query: str, db: Session = Depends(get_db)):
    query = query.strip()
    if not query or len(query) > 60:
        raise HTTPException(status_code=400, detail="Saisis un nom ou un symbole, par exemple Amazon ou AMZN.")
    found = resolve_listing(query)
    if not found:
        raise HTTPException(
            status_code=404,
            detail="Aucune cotation trouvée pour cette recherche. Vérifie le nom ou le symbole. Aucun cours n'a été inventé.",
        )
    symbol = found["symbol"]
    if not _rows(db, symbol):
        replace_symbol(db, symbol, found["bars"], "yahoo")
    if found.get("name"):
        set_meta(db, f"name:{symbol}", found["name"])
        db.commit()
    return _summary_or_404(db, symbol)


@router.get("/assets/{symbol}")
def get_asset(symbol: str, db: Session = Depends(get_db)):
    return _summary_or_404(db, normalize_symbol(symbol))


@router.get("/assets/{symbol}/history")
def get_history(symbol: str, limit: int = 120, db: Session = Depends(get_db)):
    symbol = normalize_symbol(symbol)
    closes, _volumes, dates = _series(_rows(db, symbol))
    if not closes:
        raise HTTPException(status_code=404, detail="Symbole introuvable.")
    points = history_points(closes, dates, limit)
    return {"symbol": symbol, "points": points, "count": len(points)}


@router.get("/insight/{symbol}")
def get_insight(symbol: str, db: Session = Depends(get_db)):
    summary = _summary_or_404(db, normalize_symbol(symbol))
    return {
        "symbol": summary["symbol"],
        "probabilite_hausse_pct": summary["probabilite_hausse_pct"],
        "ml_disponible": summary["ml_disponible"],
        "message": summary["ml_message"],
        "baseline_toujours_hausse_pct": summary["baseline_toujours_hausse_pct"],
        "precision_modele_pct": summary["precision_modele_pct"],
        "nb_observations": summary["nb_observations"],
        "avertissement": LIMITES,
    }


@router.post("/assets/{symbol}/ai-review")
async def ai_review(symbol: str, db: Session = Depends(get_db), user=Depends(get_optional_user)):
    symbol = normalize_symbol(symbol)
    rows = _rows(db, symbol)
    closes, volumes, dates = _series(rows)
    if not closes:
        raise HTTPException(status_code=404, detail="Symbole introuvable.")
    as_of = dates[-1].isoformat() if hasattr(dates[-1], "isoformat") else str(dates[-1])
    package = compose_review(
        symbol,
        closes,
        volumes,
        as_of=as_of,
        origine=origin_for(db, symbol),
    )
    if user is not None:
        profile = db.get(UserProfile, user.id)
        if profile is not None:
            package["niveau"] = profile.level
    commentary = await comment(package)
    package["commentaire"] = commentary
    package["review"] = commentary.get("texte") or package["review"]
    return package
