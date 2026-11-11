"""Titres Yahoo Finance. Le corps des articles n'est jamais téléchargé."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .market_refresh import YAHOO_HEADERS

SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"


def fetch_headlines(symbol: str) -> list[dict]:
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers=YAHOO_HEADERS) as client:
            response = client.get(
                SEARCH_URL,
                params={"q": symbol, "quotesCount": 0, "newsCount": 8, "enableFuzzyQuery": "false"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    rows = []
    for item in payload.get("news") or []:
        url = item.get("link") or item.get("url")
        title = item.get("title")
        if not url or not title:
            continue
        stamp = item.get("providerPublishTime")
        published = None
        if isinstance(stamp, (int, float)):
            published = datetime.fromtimestamp(stamp, tz=timezone.utc)
        rows.append({
            "symbol": symbol.upper(),
            "title": str(title)[:240],
            "publisher": str(item.get("publisher") or "")[:80],
            "url": str(url)[:500],
            "published_at": published,
        })
    return rows
