"""Logique métier : lecture des prix depuis PostgreSQL."""
import pandas as pd
from sqlalchemy.engine import Engine


def get_available_symbols(engine: Engine) -> list[str]:
    """Renvoie la liste triée des symboles présents en base."""
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

    return {
        "symbol": symbol,
        "prix_actuel": float(last["Close"]),
        "date": last["Date"],
        "tendance": "haussière" if last["ma20"] > last["ma50"] else "baissière",
        "ma20": float(last["ma20"]),
        "ma50": float(last["ma50"]),
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

    # Remettre dans l'ordre chronologique pour les graphiques
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