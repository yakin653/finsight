"""POST /chat : intention, faits, reformulation validée, sinon gabarit."""
from __future__ import annotations

import json
import os
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai_analyst import OLLAMA_MODEL, ollama_base, ollama_generate_url
from ..chat_engine import (
    detect_intent,
    detect_mode,
    mentioned_symbols,
    offline_answer,
    resolve_message,
    system_prompt,
    validate_chat_answer,
)
from ..database import get_db
from ..metrics_file import read_model_metrics
from ..models import Conversation, MarketData, Message, NewsItem, User, UserProfile
from ..routers.assets import _summary_or_404
from ..security import allow, get_current_user

router = APIRouter()


class PulsePart(BaseModel):
    label: str = Field(max_length=40)
    note: int = Field(ge=0, le=100)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    symbol: str | None = Field(default=None, max_length=15)
    conversation_id: str | None = None
    pulse: list[PulsePart] = []


def _facts(db: Session, symbol: str | None, pulse: list[PulsePart], message: str) -> tuple[dict, list[str]]:
    facts: dict = {"message": message, "pulse": [part.model_dump() for part in pulse]}
    symbols: list[str] = []
    if not symbol:
        return facts, symbols
    summary = _summary_or_404(db, symbol)
    symbols.append(summary["symbol"])
    facts.update({
        "symbol": summary["symbol"],
        "prix": summary.get("prix_actuel"),
        "date": summary.get("date"),
        "variation": summary.get("variation_1j_pct"),
        "tendance": summary.get("tendance"),
        "ma20": summary.get("ma20"),
        "ma50": summary.get("ma50"),
        "volatilite": summary.get("volatilite_annualisee_pct"),
        "repli": summary.get("max_drawdown_pct"),
        "probabilite": summary.get("probabilite_hausse_pct"),
        "baseline": summary.get("baseline_toujours_hausse_pct"),
        "precision_modele": summary.get("precision_modele_pct"),
    })
    titles = (
        db.query(NewsItem)
        .filter(NewsItem.symbol == summary["symbol"])
        .order_by(NewsItem.published_at.desc())
        .limit(3)
        .all()
    )
    facts["titres"] = [row.title for row in titles]
    return facts, symbols


_model_name: dict[str, str] = {}


async def _model() -> str:
    """OLLAMA_MODEL, ou llama3.2:3b si le nom choisi n'est pas installé."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return OLLAMA_MODEL
    wanted = OLLAMA_MODEL
    if _model_name.get("ok") == wanted:
        return wanted
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            tags = await client.get(ollama_base() + "/api/tags")
            tags.raise_for_status()
            names = [str(item.get("name") or "") for item in tags.json().get("models") or []]
    except (httpx.HTTPError, ValueError, KeyError):
        return wanted
    if any(name == wanted or name.startswith(wanted + ":") or name.startswith(wanted) for name in names):
        _model_name["ok"] = wanted
        return wanted
    for name in names:
        if name.startswith("llama3.2"):
            _model_name["ok"] = name
            return name
    return wanted


async def _reformulate(level: str, facts: dict, symbols: list[str], sources_text: str) -> str | None:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None
    facts_text = json.dumps(facts, ensure_ascii=False, default=str)
    prompt = system_prompt(level) + "\nFaits JSON :\n" + facts_text
    if sources_text:
        prompt += "\nSOURCES (fiches, ne pas inventer au-delà) :\n" + sources_text[:4000]
    model = await _model()
    text = None
    for _attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
                response = await client.post(
                    ollama_generate_url(),
                    json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2, "num_predict": 220}},
                )
                response.raise_for_status()
                text = response.json().get("response")
            break
        except (httpx.HTTPError, ValueError, KeyError):
            text = None
    if not isinstance(text, str):
        return None
    text = text.strip()
    if validate_chat_answer(text, facts_text, symbols, sources_text):
        return text
    return None


def _metrics() -> dict | None:
    try:
        return read_model_metrics()
    except (FileNotFoundError, KeyError, TypeError, ValueError, OSError):
        return None


def _sparkline(db: Session, symbol: str | None) -> list[float]:
    if not symbol:
        return []
    rows = (
        db.query(MarketData)
        .filter(MarketData.symbol == symbol)
        .order_by(MarketData.date.desc())
        .limit(30)
        .all()
    )
    return [float(row.close) for row in reversed(rows) if row.close is not None]


def _load_symbols(db: Session, names: list[str]) -> list[dict]:
    rows = []
    for name in names:
        try:
            summary = _summary_or_404(db, name)
        except HTTPException:
            continue
        rows.append({
            "symbol": summary["symbol"],
            "prix": summary.get("prix_actuel"),
            "date": summary.get("date"),
            "variation": summary.get("variation_1j_pct"),
            "tendance": summary.get("tendance"),
            "ma20": summary.get("ma20"),
            "ma50": summary.get("ma50"),
            "volatilite": summary.get("volatilite_annualisee_pct"),
            "repli": summary.get("max_drawdown_pct"),
        })
    return rows


@router.post("/chat")
async def chat(body: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not allow(f"chat:{user.id}", 20, 60):
        raise HTTPException(status_code=429, detail="Limite de 20 messages par minute atteinte.")
    profile = db.get(UserProfile, user.id)
    level = profile.level if profile else "intermediaire"
    previous = None
    if body.conversation_id:
        last = (
            db.query(Message)
            .filter(Message.conversation_id == body.conversation_id, Message.role == "assistant")
            .order_by(Message.created_at.desc())
            .first()
        )
        if last and isinstance(last.payload, dict):
            previous = {"symbol": (last.payload.get("used_facts") or {}).get("symbol"), "intent": last.payload.get("intent")}
    message = resolve_message(body.message, previous)
    intent = detect_intent(message)
    mode = detect_mode(message)
    names = mentioned_symbols(message)
    symbol = body.symbol.strip().upper() if body.symbol else (names[0] if names else (previous or {}).get("symbol"))
    if symbol and symbol not in names:
        names = [symbol, *names]
    loaded = _load_symbols(db, names[:3])
    primary = loaded[0]["symbol"] if loaded else symbol
    try:
        facts, symbols = _facts(db, primary, body.pulse, message)
    except HTTPException:
        facts, symbols = {"message": message, "pulse": [part.model_dump() for part in body.pulse]}, []
    facts["comparables"] = loaded
    if len(loaded) >= 2:
        facts["autre"] = loaded[1]
        symbols = [row["symbol"] for row in loaded]
    metrics = _metrics()
    if metrics:
        facts["precision_modele"] = metrics.get("precision_modele_pct")
        facts["baseline"] = metrics.get("baseline_toujours_hausse_pct")
    draft = offline_answer(message, intent, facts, level, metrics)
    answer = await _reformulate(level, facts, symbols, draft.get("sources_text") or "")
    source = "llm"
    fiches = draft.get("fiches") or []
    if not answer:
        answer = draft["answer"]
        source = draft["source"]
    conversation = db.get(Conversation, body.conversation_id) if body.conversation_id else None
    if conversation is None or conversation.user_id != user.id:
        conversation = Conversation(id=str(uuid.uuid4()), user_id=user.id, title=body.message[:80])
        db.add(conversation)
        db.flush()
    payload = {"source": source, "intent": intent, "mode": mode, "fiches": fiches, "used_facts": facts}
    assistant = Message(id=str(uuid.uuid4()), conversation_id=conversation.id, role="assistant", content=answer, payload=payload)
    db.add(Message(id=str(uuid.uuid4()), conversation_id=conversation.id, role="user", content=body.message))
    db.add(assistant)
    db.commit()
    old = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .offset(20)
        .all()
    )
    for row in old:
        db.delete(row)
    db.commit()
    return {
        "answer": answer,
        "source": source,
        "intent": intent,
        "mode": mode,
        "fiches": fiches,
        "sparkline": _sparkline(db, primary),
        "used_facts": facts,
        "conversation_id": conversation.id,
        "message_id": assistant.id,
    }


class TitleIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class FeedbackIn(BaseModel):
    message_id: str = Field(min_length=8, max_length=80)
    vote: str = Field(pattern="^(up|down)$")


@router.get("/chat/conversations")
def conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.created_at.desc()).limit(40).all()
    return {"conversations": [{"id": row.id, "title": row.title} for row in rows]}


@router.patch("/chat/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, body: TitleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Conversation, conversation_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation introuvable.")
    row.title = body.title.strip()
    db.commit()
    return {"id": row.id, "title": row.title}


@router.delete("/chat/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Conversation, conversation_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation introuvable.")
    db.query(Message).filter(Message.conversation_id == row.id).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/chat/feedback")
def feedback(body: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    message = db.get(Message, body.message_id)
    if message is None or message.role != "assistant":
        raise HTTPException(status_code=404, detail="Message introuvable.")
    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Message introuvable.")
    payload = dict(message.payload or {})
    payload["feedback"] = body.vote
    message.payload = payload
    db.commit()
    return {"ok": True}


@router.get("/chat/{conversation_id}")
def history(conversation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation introuvable.")
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return {"conversation_id": conversation.id, "messages": [{"role": row.role, "content": row.content, "payload": row.payload} for row in rows]}
