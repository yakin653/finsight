"""Notifications dans l'application et abonnement Web Push."""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import NewsItem, Notification, PushSubscription, User
from ..security import get_current_user

router = APIRouter()


class PushIn(BaseModel):
    endpoint: str = Field(min_length=8, max_length=500)
    p256dh: str = Field(min_length=8, max_length=200)
    auth: str = Field(min_length=4, max_length=80)


@router.get("/news/items")
def news_items(symbol: str, db: Session = Depends(get_db)):
    symbol = symbol.strip().upper()
    rows = (
        db.query(NewsItem)
        .filter(NewsItem.symbol == symbol)
        .order_by(NewsItem.published_at.desc())
        .limit(20)
        .all()
    )
    return {
        "symbol": symbol,
        "items": [
            {
                "title": row.title,
                "publisher": row.publisher,
                "url": row.url,
                "published_at": row.published_at.isoformat() if row.published_at else None,
                "sentiment": row.sentiment,
            }
            for row in rows
        ],
    }


@router.get("/notifications")
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    unread = sum(1 for row in rows if row.read_at is None)
    return {
        "unread": unread,
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "body": row.body,
                "symbol": row.symbol,
                "kind": row.kind,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "read": row.read_at is not None,
            }
            for row in rows
        ],
    }


@router.post("/notifications/{note_id}/read")
def mark_read(note_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    row = db.get(Notification, note_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification introuvable.")
    row.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.get("/push/public-key")
def public_key():
    key = os.getenv("VAPID_PUBLIC_KEY", "")
    return {"public_key": key or None, "configured": bool(key and os.getenv("VAPID_PRIVATE_KEY"))}


@router.post("/push/subscribe")
def subscribe(body: PushIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not os.getenv("VAPID_PUBLIC_KEY"):
        raise HTTPException(status_code=503, detail="Les clés VAPID ne sont pas configurées. Les notifications dans l'application restent disponibles.")
    existing = db.query(PushSubscription).filter_by(endpoint=body.endpoint).first()
    if existing:
        existing.user_id = user.id
        existing.p256dh = body.p256dh
        existing.auth = body.auth
    else:
        db.add(PushSubscription(id=str(uuid.uuid4()), user_id=user.id, endpoint=body.endpoint, p256dh=body.p256dh, auth=body.auth))
    db.commit()
    return {"ok": True}


@router.post("/push/test")
def push_test(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..jobs import send_push

    note = Notification(
        id=str(uuid.uuid4()),
        user_id=user.id,
        kind="test",
        title="Notification de test",
        body="Ceci est un essai MarketPulse. Ce n'est pas une alerte de marché.",
    )
    db.add(note)
    db.commit()
    send_push(db, user.id, note.title, note.body, "/notifications")
    try:
        import pywebpush  # noqa: F401
        library = True
    except ImportError:
        library = False
    configured = bool(os.getenv("VAPID_PRIVATE_KEY") and os.getenv("VAPID_PUBLIC_KEY"))
    from ..notify_mail import email_notification

    mail = email_notification(db, user.id, note.title, note.body)
    mail_text = {
        "en_cours": " E-mail envoyé à ton adresse (boîte de test locale si le serveur d'envoi est Mailpit).",
        "sans_serveur": " E-mail non envoyé : aucun serveur d'envoi n'est configuré (SMTP_HOST vide).",
        "limite": " E-mail non envoyé : limite de 10 par jour atteinte.",
        "desactive": "",
    }[mail]
    push_text = "Notification enregistrée." if configured and library else "Push indisponible : clé VAPID ou bibliothèque absente. La notification est dans l'application."
    return {
        "ok": True,
        "dans_l_application": True,
        "push": configured and library,
        "email": mail,
        "detail": push_text + mail_text,
    }


@router.delete("/push/unsubscribe")
def unsubscribe(body: PushIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(PushSubscription).filter_by(endpoint=body.endpoint, user_id=user.id).first()
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}
