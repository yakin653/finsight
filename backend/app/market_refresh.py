"""Chargement des cours : Yahoo Finance si possible, simulation seulement en dernier recours."""
from __future__ import annotations

import os
import random
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from .models import AppMeta, MarketData

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "BTC-USD"]
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=6mo"
SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,14}$")
QUOTE_TYPES = {"EQUITY", "ETF", "CRYPTOCURRENCY", "INDEX"}
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketPulse/1.0; educational)"}


def get_meta(db: Session, key: str) -> str | None:
    row = db.get(AppMeta, key)
    return None if row is None else row.value


def set_meta(db: Session, key: str, value: str) -> None:
    row = db.get(AppMeta, key)
    if row is None:
        db.add(AppMeta(key=key, value=value))
    else:
        row.value = value


def fetch_yahoo_bars(symbol: str) -> list[dict]:
    url = YAHOO_URL.format(symbol=quote(symbol, safe="-."))
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers=YAHOO_HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return []
    block = result[0]
    timestamps = block.get("timestamp") or []
    quote_block = ((block.get("indicators") or {}).get("quote") or [{}])[0]
    by_date: dict[date, dict] = {}
    for index, ts in enumerate(timestamps):
        closes = quote_block.get("close") or []
        if index >= len(closes) or closes[index] is None:
            continue
        close = float(closes[index])
        day = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()

        def pick(name: str, fallback: float) -> float:
            seq = quote_block.get(name) or []
            if index < len(seq) and seq[index] is not None:
                return float(seq[index])
            return fallback

        by_date[day] = {
            "date": day,
            "open": pick("open", close),
            "high": pick("high", close),
            "low": pick("low", close),
            "close": close,
            "volume": pick("volume", 0.0),
        }
    return [by_date[day] for day in sorted(by_date)]


def replace_symbol(db: Session, symbol: str, bars: list[dict], origin: str) -> None:
    db.query(MarketData).filter(MarketData.symbol == symbol).delete(synchronize_session=False)
    for bar in bars:
        day = bar["date"]
        db.add(MarketData(
            id=f"{symbol}-{day.isoformat()}",
            symbol=symbol,
            date=day,
            open=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            volume=bar["volume"],
        ))
    set_meta(db, f"origin:{symbol}", origin)
    set_meta(db, f"updated:{symbol}", date.today().isoformat())
    set_meta(db, "refreshed_at", datetime.now(timezone.utc).isoformat())
    db.commit()


def refresh_symbols(db: Session, symbols: list[str]) -> dict:
    updated: list[str] = []
    failed: list[str] = []
    for symbol in symbols:
        bars = fetch_yahoo_bars(symbol)
        if len(bars) < 20:
            failed.append(symbol)
            continue
        try:
            replace_symbol(db, symbol, bars, "yahoo")
            updated.append(symbol)
            print(f"Cours Yahoo enregistrés pour {symbol} ({len(bars)} séances).")
        except Exception as exc:
            db.rollback()
            failed.append(symbol)
            print(f"Échec d'enregistrement pour {symbol} : {type(exc).__name__}")
    return {"updated": updated, "failed": failed}


def seed_simulation(db: Session) -> None:
    """Dernier recours si Yahoo est injoignable et que la base est vide."""
    if db.query(MarketData).count() > 0:
        return
    today = date.today()
    symbols = DEFAULT_SYMBOLS
    for symbol in symbols:
        base = random.uniform(100, 500)
        for i in range(60):
            day = today - timedelta(days=60 - i)
            price = base + random.uniform(-10, 10)
            db.add(MarketData(
                id=f"{symbol}-{day.isoformat()}",
                symbol=symbol,
                date=day,
                open=price - 2,
                high=price + 5,
                low=price - 5,
                close=price,
                volume=float(random.randint(1000, 50000)),
            ))
        set_meta(db, f"origin:{symbol}", "simulation")
    db.commit()
    print("Base vide et Yahoo indisponible : séries simulées insérées, marquées comme telles.")


def expected_session(day: date) -> date:
    """Dernier jour du lundi au vendredi, aujourd'hui compris."""
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def quotes_are_stale(db: Session, today: date | None = None) -> bool:
    """Vrai si le dernier horodatage est antérieur au dernier jour de bourse."""
    moment = today or date.today()
    limit = expected_session(moment)
    raw = get_meta(db, "refreshed_at")
    if raw and "T" in raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return True
        return parsed.date() < limit
    updated = [row.value for row in db.query(AppMeta).filter(AppMeta.key.like("updated:%")).all()]
    if not updated:
        return db.query(MarketData).count() > 0
    latest = max(updated)[:10]
    try:
        return date.fromisoformat(latest) < limit
    except ValueError:
        return True


def refresh_all_quotes() -> None:
    """Relit Yahoo pour les symboles déjà en base. Appelé au démarrage et les jours de bourse."""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        existing = [row[0] for row in db.query(MarketData.symbol).distinct().all()]
        symbols = list(dict.fromkeys([*existing, *DEFAULT_SYMBOLS]))
        if symbols:
            refresh_symbols(db, symbols)
    except Exception as exc:
        db.rollback()
        print(f"Rafraîchissement Yahoo interrompu : {type(exc).__name__}")
    finally:
        db.close()


def ensure_market_data(db: Session) -> None:
    """Au démarrage, remplace les séries non sourcées par Yahoo. Jamais pendant pytest."""
    count = db.query(MarketData).count()
    skip_network = os.getenv("MARKET_REFRESH_ON_START", "1") == "0" or bool(os.getenv("PYTEST_CURRENT_TEST"))
    if skip_network:
        if count == 0:
            seed_simulation(db)
        return

    if count == 0:
        result = refresh_symbols(db, DEFAULT_SYMBOLS)
        if not result["updated"]:
            seed_simulation(db)
        return

    existing = [row[0] for row in db.query(MarketData.symbol).distinct().all()]
    pending = []
    for symbol in dict.fromkeys([*existing, *DEFAULT_SYMBOLS]):
        if get_meta(db, f"origin:{symbol}") != "yahoo":
            pending.append(symbol)
    if pending:
        refresh_symbols(db, pending)
    if quotes_are_stale(db):
        symbols = list(dict.fromkeys([*existing, *DEFAULT_SYMBOLS]))
        refresh_symbols(db, symbols)


def origin_for(db: Session, symbol: str) -> str:
    return get_meta(db, f"origin:{symbol}") or "simulation"


def name_for(db: Session, symbol: str) -> str | None:
    return get_meta(db, f"name:{symbol}")


def pick_quotes(payload: dict) -> list[dict]:
    """Garde les actions, ETF et cryptos, du plus pertinent au moins pertinent."""
    chosen = []
    for item in payload.get("quotes") or []:
        if item.get("quoteType") not in QUOTE_TYPES:
            continue
        symbol = str(item.get("symbol") or "").upper()
        if not SYMBOL_RE.match(symbol):
            continue
        chosen.append({
            "symbol": symbol,
            "name": (item.get("shortname") or item.get("longname") or symbol)[:120],
            "score": float(item.get("score") or 0),
        })
    chosen.sort(key=lambda row: row["score"], reverse=True)
    unique = []
    seen = set()
    for row in chosen:
        if row["symbol"] in seen:
            continue
        seen.add(row["symbol"])
        unique.append(row)
    return unique[:4]


def search_quotes(query: str) -> list[dict]:
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers=YAHOO_HEADERS) as client:
            response = client.get(
                SEARCH_URL,
                params={
                    "q": query,
                    "quotesCount": 8,
                    "newsCount": 0,
                    "enableFuzzyQuery": "true",
                    "lang": "en-US",
                    "region": "US",
                },
            )
            response.raise_for_status()
            return pick_quotes(response.json())
    except (httpx.HTTPError, ValueError):
        return []


def resolve_listing(query: str) -> dict | None:
    """Symbole exact si les cours existent, sinon recherche par nom (amazon -> AMZN)."""
    text = query.strip()
    ticker = text.upper()
    if SYMBOL_RE.match(ticker):
        bars = fetch_yahoo_bars(ticker)
        if len(bars) >= 20:
            name = next((hit["name"] for hit in search_quotes(text) if hit["symbol"] == ticker), None)
            return {"symbol": ticker, "name": name, "bars": bars}
    for hit in search_quotes(text):
        bars = fetch_yahoo_bars(hit["symbol"])
        if len(bars) >= 20:
            return {"symbol": hit["symbol"], "name": hit["name"], "bars": bars}
    return None
