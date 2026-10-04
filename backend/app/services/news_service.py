"""Logique metier : lecture des news depuis PostgreSQL."""
import pandas as pd
from sqlalchemy.engine import Engine


def _dominant_label(row) -> str:
    """Renvoie le label dominant (positive / neutral / negative)."""
    scores = {"positive": row["pos"], "neutral": row["neu"], "negative": row["neg"]}
    return max(scores, key=scores.get)


def get_news(engine: Engine, symbol: str, days: int = 30, limit: int = 50) -> dict | None:
    """
    Renvoie les news d'un symbole sur N jours, triees par date desc,
    avec leur sentiment dominant.
    """
    query = f"""
        SELECT date, headline, source, url, pos, neu, neg
        FROM news
        WHERE symbol = '{symbol}'
          AND date >= NOW() - INTERVAL '{days} days'
        ORDER BY date DESC
        LIMIT {limit}
    """
    df = pd.read_sql(query, engine, parse_dates=["date"])

    if df.empty:
        # On renvoie quand meme une reponse vide structuree
        return {
            "symbol": symbol,
            "count": 0,
            "days": days,
            "sentiment_score": 0.0,
            "interpretation": "neutre",
            "news": [],
        }

    # Score de sentiment global : moyenne de (pos - neg)
    sent_score = float((df["pos"] - df["neg"]).mean())

    if sent_score > 0.1:
        interpretation = "positif"
    elif sent_score < -0.1:
        interpretation = "negatif"
    else:
        interpretation = "neutre"

    # Construit la liste des news
    news_list = []
    for _, row in df.iterrows():
        news_list.append({
            "date": row["date"],
            "headline": row["headline"],
            "source": row["source"],
            "url": row["url"],
            "pos": float(row["pos"]),
            "neu": float(row["neu"]),
            "neg": float(row["neg"]),
            "sentiment": _dominant_label(row),
        })

    return {
        "symbol": symbol,
        "count": len(news_list),
        "days": days,
        "sentiment_score": round(sent_score, 4),
        "interpretation": interpretation,
        "news": news_list,
    }