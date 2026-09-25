"""
FinSight — Récupération et scoring des news via Finnhub + FinBERT.

Usage :
    python data_pipeline/fetch_news.py --symbol AAPL --days 30
"""
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Ajouter ml/src au path pour importer sentiment.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml" / "src"))
from sentiment import score_text   # noqa: E402


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

if not FINNHUB_API_KEY:
    raise SystemExit("❌ FINNHUB_API_KEY manquante dans .env")


def fetch_finnhub_news(symbol: str, days: int = 30):
    """Récupère les news Finnhub pour un symbole sur N jours."""
    to_date = datetime.utcnow().date()
    from_date = to_date - timedelta(days=days)

    url = "https://finnhub.io/api/v1/company-news"
    params = {
        "symbol": symbol,
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "token": FINNHUB_API_KEY,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    news = r.json()
    print(f"📰 {len(news)} articles récupérés pour {symbol}")
    return news


def score_news(news_list):
    """Ajoute les scores FinBERT à chaque article."""
    scored = []
    for i, art in enumerate(news_list, 1):
        headline = art.get("headline", "").strip()
        if not headline:
            continue

        scores = score_text(headline)
        scored.append({
            "symbol":   art.get("related", "").split(",")[0] or "UNKNOWN",
            "date":     datetime.fromtimestamp(art["datetime"]),
            "headline": headline,
            "url":      art.get("url"),
            "source":   art.get("source"),
            "pos":      scores["positive"],
            "neu":      scores["neutral"],
            "neg":      scores["negative"],
        })

        if i % 10 == 0:
            print(f"   ... {i}/{len(news_list)} scorés")

    print(f"✅ {len(scored)} titres scorés")
    return scored


def store_news(engine, scored_news):
    """Insère les news scorées en base (ignore les doublons)."""
    if not scored_news:
        print("⚠️  Aucune news à insérer")
        return 0

    df = pd.DataFrame(scored_news)

    inserted = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            result = conn.execute(text("""
                INSERT INTO news (symbol, date, headline, url, source, pos, neu, neg)
                VALUES (:symbol, :date, :headline, :url, :source, :pos, :neu, :neg)
                ON CONFLICT (symbol, date, headline) DO NOTHING
            """), row.to_dict())
            inserted += result.rowcount

    print(f"💾 {inserted} nouvelles lignes insérées (doublons ignorés)")
    return inserted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="AAPL", help="Symbole boursier")
    parser.add_argument("--days",   type=int, default=30, help="Nombre de jours en arrière")
    args = parser.parse_args()

    print(f"🎯 Traitement {args.symbol} (derniers {args.days} jours)")

    engine = create_engine(DATABASE_URL)

    # 1. Récupération Finnhub
    news = fetch_finnhub_news(args.symbol, args.days)
    if not news:
        print("Aucune news à traiter.")
        return

    # 2. Scoring FinBERT
    scored = score_news(news)

    # 3. Insertion en base
    store_news(engine, scored)

    # 4. Résumé
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM news")).scalar()
        print(f"\n📊 Total de news en base : {total}")


if __name__ == "__main__":
    main()