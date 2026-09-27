"""Logique metier : lecture des prix depuis PostgreSQL."""
import math

import pandas as pd
from sqlalchemy.engine import Engine


def _safe_float(x):
    """Renvoie None si x est NaN, sinon x en float."""
    if x is None:
        return None
    try:
        f = float(x)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def get_available_symbols(engine: Engine) -> list[str]:
    """Renvoie la liste triee des symboles presents en base."""
    df = pd.read_sql("SELECT DISTINCT symbol FROM market_data ORDER BY symbol", engine)
    return df["symbol"].tolist()


def get_asset_info(engine: Engine, symbol: str) -> dict | None:
    """Prix actuel + tendance (MA20/MA50) pour un symbole."""
    df = pd.read_sql(
        f"SELECT * FROM market_data WHERE symbol = '{symbol}' ORDER BY \"Date\"",
        engine,
        parse_dates=["Date"],
    )
    if df.empty:
        return None

    df["ma20"] = df["Close"].rolling(20).mean()
    df["ma50"] = df["Close"].rolling(50).mean()
    last = df.iloc[-1]

    ma20 = _safe_float(last["ma20"])
    ma50 = _safe_float(last["ma50"])

    if ma20 is None or ma50 is None:
        tendance = "indeterminee"
    else:
        tendance = "haussiere" if ma20 > ma50 else "baissiere"

    return {
        "symbol": symbol,
        "prix_actuel": float(last["Close"]),
        "date": last["Date"],
        "tendance": tendance,
        "ma20": ma20 if ma20 is not None else 0.0,
        "ma50": ma50 if ma50 is not None else 0.0,
    }


def get_asset_history(engine: Engine, symbol: str, limit: int = 500) -> dict | None:
    """Historique des prix (les `limit` derniers points)."""
    df = pd.read_sql(
        f"""SELECT "Date", "Open", "High", "Low", "Close", "Volume"
            FROM market_data WHERE symbol = '{symbol}'
            ORDER BY "Date" DESC LIMIT {limit}""",
        engine,
        parse_dates=["Date"],
    )
    if df.empty:
        return None

    df = df.sort_values("Date").reset_index(drop=True)

    return {
        "symbol": symbol,
        "count": len(df),
        "points": [
            {
                "date": row["Date"],
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            }
            for _, row in df.iterrows()
        ],
    }
