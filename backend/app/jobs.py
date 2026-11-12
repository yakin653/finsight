"""Collecte des titres et évaluation des alertes. Ne bloque pas une requête."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from .analysis import compute_indicators
from .database import SessionLocal
from .delivery import delivery_mode, matches_interest
from .models import AlertRule, MarketData, NewsItem, Notification, PushSubscription, UserProfile, UserSymbol
from .news_feed import fetch_headlines
from .notify_mail import email_notification


def watched_symbols(db) -> list[str]:
    symbols = {row[0] for row in db.query(UserSymbol.symbol).distinct().all()}
    for profile in db.query(UserProfile).all():
        for symbol in profile.favorite_symbols or []:
            symbols.add(str(symbol).upper())
    return sorted(symbols)


def store_headlines(db, symbol: str) -> list[NewsItem]:
    created: list[NewsItem] = []
    for row in fetch_headlines(symbol):
        if db.query(NewsItem).filter(NewsItem.url == row["url"]).first():
            continue
        # FinBERT est dans legacy/ml/src/sentiment.py : trop lourd pour le démarrage Docker.
        item = NewsItem(id=str(uuid.uuid4()), sentiment=None, fetched_at=datetime.now(timezone.utc), **row)
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        created.append(item)
    return created


def _notify(db, user_id: str, title: str, body: str, symbol: str | None, news_id: str | None, kind: str) -> Notification | None:
    if news_id and db.query(Notification).filter_by(user_id=user_id, news_id=news_id, kind=kind).first():
        return None
    row = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        news_id=news_id,
        kind=kind,
        title=title[:180],
        body=body[:500],
        symbol=symbol,
    )
    db.add(row)
    db.commit()
    # Toutes les notifications (titres, résumé, alerte, briefing) passent ici : une seule règle pour l'e-mail.
    email_notification(db, user_id, row.title, row.body)
    return row


def dispatch_news(db, items: list[NewsItem]) -> None:
    now = datetime.now(timezone.utc)
    profiles = db.query(UserProfile).all()
    for profile in profiles:
        favorites = list(profile.favorite_symbols or [])
        favorites += [row.symbol for row in db.query(UserSymbol).filter_by(user_id=profile.user_id).all()]
        mode = delivery_mode(profile.notif_prefs or {}, now.hour)
        if mode == "skip":
            continue
        matched = [item for item in items if matches_interest(item.symbol, item.title, favorites, profile.news_keywords or [])]
        if mode == "instant":
            for item in matched:
                note = _notify(db, profile.user_id, item.title, item.publisher or item.symbol, item.symbol, item.id, "news")
                if note:
                    send_push(db, profile.user_id, note.title, note.body, f"/asset/{item.symbol}")
        elif matched:
            already = (
                db.query(Notification)
                .filter(Notification.user_id == profile.user_id, Notification.kind == "digest", Notification.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0))
                .first()
            )
            if already:
                continue
            body = " ; ".join(item.title for item in matched[:5])
            note = _notify(db, profile.user_id, "Résumé des titres", body, None, None, "digest")
            if note:
                send_push(db, profile.user_id, note.title, note.body, "/notifications")


def _closes(db, symbol: str) -> tuple[list[float], list]:
    rows = db.query(MarketData).filter(MarketData.symbol == symbol).order_by(MarketData.date.asc()).all()
    closes = [float(row.close) for row in rows if row.close is not None]
    return closes, rows


def _crossed(closes: list[float], window: int) -> bool:
    if len(closes) < window + 1:
        return False
    previous = sum(closes[-window - 1 : -1]) / window
    current = sum(closes[-window:]) / window
    return (closes[-2] - previous) * (closes[-1] - current) < 0


def evaluate_alerts(db) -> None:
    today = datetime.now(timezone.utc).date()
    for rule in db.query(AlertRule).filter(AlertRule.enabled.is_(True)).all():
        if rule.last_fired_on == today:
            continue
        closes, _rows = _closes(db, rule.symbol)
        if len(closes) < 20:
            continue
        indicators = compute_indicators(closes, [0.0] * len(closes))
        message = None
        if rule.kind == "mm20" and _crossed(closes, 20):
            message = f"{rule.symbol} a franchi sa MM20."
        elif rule.kind == "mm50" and _crossed(closes, 50):
            message = f"{rule.symbol} a franchi sa MM50."
        elif rule.kind == "repli":
            limit = rule.threshold if rule.threshold is not None else 15
            drawdown = indicators.get("max_drawdown_pct")
            if drawdown is not None and abs(drawdown) >= limit:
                message = f"{rule.symbol} : repli maximal de {drawdown:.1f} %, seuil {limit:.0f} %."
        elif rule.kind == "volatilite":
            limit = rule.threshold if rule.threshold is not None else 45
            vol = indicators.get("volatilite_annualisee_pct")
            if vol is not None and vol >= limit:
                message = f"{rule.symbol} : volatilité annualisée {vol:.1f} %, seuil {limit:.0f} %."
        if not message:
            continue
        note = _notify(db, rule.user_id, "Alerte de cours", message, rule.symbol, None, f"alert:{rule.id}")
        if note:
            rule.last_fired_on = today
            db.commit()
            send_push(db, rule.user_id, note.title, note.body, f"/asset/{rule.symbol}")


def send_push(db, user_id: str, title: str, body: str, url: str) -> None:
    private = os.getenv("VAPID_PRIVATE_KEY", "")
    public = os.getenv("VAPID_PUBLIC_KEY", "")
    subject = os.getenv("VAPID_SUBJECT", "mailto:marketpulse@localhost")
    if not private or not public:
        return
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return
    import json

    payload = json.dumps({"title": title, "body": body, "url": url})
    for sub in db.query(PushSubscription).filter_by(user_id=user_id).all():
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload,
                vapid_private_key=private,
                vapid_claims={"sub": subject},
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {404, 410}:
                db.delete(sub)
                db.commit()


def _briefing_text(db, profile: UserProfile) -> str:
    symbols = list(profile.favorite_symbols or [])
    symbols += [row.symbol for row in db.query(UserSymbol).filter_by(user_id=profile.user_id).all()]
    parts = []
    for symbol in list(dict.fromkeys(symbols))[:6]:
        rows = db.query(MarketData).filter(MarketData.symbol == symbol).order_by(MarketData.date.desc()).limit(2).all()
        if len(rows) == 2 and rows[0].close and rows[1].close:
            change = (float(rows[0].close) / float(rows[1].close) - 1) * 100
            parts.append(f"{symbol} {change:.2f} % sur la dernière séance")
    news = db.query(NewsItem).order_by(NewsItem.published_at.desc()).limit(3).all()
    titles = "; ".join(item.title for item in news) if news else "aucun titre récent"
    body = "Mouvements suivis : " + (", ".join(parts) if parts else "aucune série en commun") + ". Titres : " + titles + "."
    return body + " Ceci décrit le passé. Ce n'est pas un conseil."


def _polish_briefing(text: str) -> str:
    """Reformule le briefing. Si Ollama échoue ou invente, on garde le texte Python."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return text
    try:
        import httpx

        from .ai_analyst import OLLAMA_MODEL, ollama_generate_url
        from .chat_engine import validate_chat_answer

        response = httpx.post(
            ollama_generate_url(),
            json={
                "model": os.getenv("OLLAMA_MODEL", OLLAMA_MODEL),
                "prompt": (
                    "Reformule ce briefing en français, sans chiffre nouveau et sans conseil d'achat ou de vente.\n"
                    + text
                ),
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 180},
            },
            timeout=httpx.Timeout(8.0, connect=2.0),
        )
        answer = str(response.json().get("response") or "").strip()
        if validate_chat_answer(answer, text, [], text):
            return answer
    except Exception:
        return text
    return text


def _daily_briefings(db) -> None:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for profile in db.query(UserProfile).all():
        hour = int((profile.notif_prefs or {}).get("heure") or 8)
        if hour != now.hour:
            continue
        already = (
            db.query(Notification)
            .filter(Notification.user_id == profile.user_id, Notification.kind == "briefing", Notification.created_at >= start)
            .first()
        )
        if already:
            continue
        _notify(db, profile.user_id, "Ma journée", _polish_briefing(_briefing_text(db, profile)), None, None, "briefing")


def run_market_jobs() -> None:
    db = SessionLocal()
    try:
        fresh: list[NewsItem] = []
        for symbol in watched_symbols(db):
            fresh.extend(store_headlines(db, symbol))
        if fresh:
            dispatch_news(db, fresh)
        evaluate_alerts(db)
        from .market_refresh import set_meta

        set_meta(db, "news_job_at", datetime.now(timezone.utc).isoformat())
        db.commit()
        _daily_briefings(db)
    except Exception as exc:
        print(f"Tâche planifiée interrompue : {type(exc).__name__}")
        db.rollback()
    finally:
        db.close()
