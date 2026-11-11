"""Détection d'anomalies dans les prix historiques avec Isolation Forest."""

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sklearn.ensemble import IsolationForest


def detect_anomalies(
    engine: Engine,
    symbol: str,
    limit: int = 500,
) -> dict:
    """Détecte les variations inhabituelles d'un actif."""

    limit = max(30, min(limit, 2000))

    query = text("""
        SELECT "Date", "Close", "Volume"
        FROM market_data
        WHERE symbol = :symbol
        ORDER BY "Date" DESC
        LIMIT :limit
    """)

    df = pd.read_sql(
        query,
        engine,
        params={"symbol": symbol.upper(), "limit": limit},
        parse_dates=["Date"],
    )

    if df.empty:
        return {
            "symbol": symbol.upper(),
            "count": 0,
            "anomaly_count": 0,
            "points": [],
        }

    df = df.sort_values("Date").reset_index(drop=True)
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    df = df.dropna(subset=["Date", "Close"])
    df = df[df["Close"] > 0].reset_index(drop=True)

    if len(df) < 30:
        raise ValueError(
            "Au moins 30 observations valides sont nécessaires."
        )

    # Rendements journaliers et volatilité récente.
    df["return_pct"] = df["Close"].pct_change() * 100
    df["volatility"] = df["return_pct"].rolling(10, min_periods=5).std()

    features = df[["return_pct", "volatility"]].replace(
        [float("inf"), float("-inf")], float("nan")
    )
    features = features.fillna(0.0)

    model = IsolationForest(
        n_estimators=200,
        contamination=0.03,
        random_state=42,
    )

    predictions = model.fit_predict(features)
    scores = model.decision_function(features)

    df["anomaly"] = predictions == -1
    df["score"] = scores

    points = []
    for _, row in df.iterrows():
        points.append({
            "date": row["Date"].isoformat(),
            "close": float(row["Close"]),
            "anomaly": bool(row["anomaly"]),
            "score": float(row["score"]),
            "return_pct": (
                None if pd.isna(row["return_pct"])
                else float(row["return_pct"])
            ),
        })

    return {
        "symbol": symbol.upper(),
        "count": len(points),
        "anomaly_count": sum(p["anomaly"] for p in points),
        "points": points,
    }
