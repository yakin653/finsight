"""Mots de passe, jeton de session et limitation de débit."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from secrets import compare_digest
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

COOKIE = "mp_session"
ALGO = "HS256"
TOKEN_HOURS = 24 * 7

# Compteur en mémoire : suffisant pour un seul processus uvicorn.
_HITS: dict[str, list[float]] = {}


def secret() -> str:
    return os.getenv("JWT_SECRET", "change-me-marketpulse-dev-secret-32b")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except ValueError:
        return False


def cookie_secure() -> bool:
    return os.getenv("COOKIE_SECURE", "false").lower() == "true"


def cookie_samesite() -> str:
    value = os.getenv("COOKIE_SAMESITE", "lax").lower()
    return value if value in {"lax", "strict", "none"} else "lax"


def cookie_kwargs() -> dict:
    return {"httponly": True, "samesite": cookie_samesite(), "secure": cookie_secure(), "path": "/"}


def make_token(user_id: str, hours: int = TOKEN_HOURS, version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=hours)
    return jwt.encode({"sub": user_id, "ver": version, "exp": expire}, secret(), algorithm=ALGO)


def set_session_cookie(response, user_id: str, remember: bool, version: int = 0) -> None:
    """Cookie du site. « Se souvenir » pose Max-Age ; sinon le cookie meurt avec le navigateur."""
    hours = 24 * 30 if remember else 12
    token = make_token(user_id, hours, version)
    options = cookie_kwargs()
    if remember:
        options["max_age"] = hours * 3600
    response.set_cookie(COOKIE, token, **options)


def clear_cookie(response, name: str) -> None:
    flags = cookie_kwargs()
    response.delete_cookie(name, path="/", secure=flags["secure"], httponly=True, samesite=flags["samesite"])


def read_token(token: str) -> tuple[str, int] | None:
    try:
        payload = jwt.decode(token, secret(), algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    if not isinstance(subject, str):
        return None
    version = payload.get("ver", 0)
    return subject, version if isinstance(version, int) else 0


def oauth_state() -> str:
    """Jeton aléatoire signé, à mettre dans le cookie et dans l'URL Google."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    return jwt.encode({"purpose": "google", "nonce": os.urandom(16).hex(), "exp": expire}, secret(), algorithm=ALGO)


def oauth_state_matches(stored: str | None, received: str) -> bool:
    if not stored or not received or len(stored) != len(received):
        return False
    if not compare_digest(stored, received):
        return False
    try:
        payload = jwt.decode(stored, secret(), algorithms=[ALGO])
    except jwt.PyJWTError:
        return False
    return payload.get("purpose") == "google"


# Empreinte fixe : un e-mail inconnu coûte le même contrôle qu'un mot de passe faux.
_DUMMY_HASH = bcrypt.hashpw(b"marketpulse-timing-placeholder", bcrypt.gensalt()).decode("utf-8")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def allow(key: str, limit: int, window_seconds: float, now: float | None = None) -> bool:
    """True si la clé n'a pas dépassé `limit` appels sur la fenêtre."""
    if os.getenv("DISABLE_RATE_LIMIT") == "1":
        return True
    moment = time.time() if now is None else now
    recent = [stamp for stamp in _HITS.get(key, []) if moment - stamp < window_seconds]
    if len(recent) >= limit:
        _HITS[key] = recent
        return False
    recent.append(moment)
    _HITS[key] = recent
    return True


def client_key(request: Request, name: str) -> str:
    host = request.client.host if request.client else "local"
    return f"{name}:{host}"


def user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    parsed = read_token(token)
    if parsed is None:
        return None
    user_id, version = parsed
    user = db.get(User, user_id)
    if user is None or int(user.token_version or 0) != version:
        return None
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_request(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return user_from_request(request, db)
