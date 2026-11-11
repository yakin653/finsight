"""Inscription, session par cookie httpOnly, profil."""
from __future__ import annotations

import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    AlertRule,
    Conversation,
    Message,
    Notification,
    PasswordReset,
    PushSubscription,
    User,
    UserProfile,
    UserSymbol,
)
from ..profiles import ALERT_KINDS, HORIZONS, LEVELS, RISKS, clean_list, clean_prefs, default_notif_prefs
from ..passwords import change_password, consume_reset, issue_code, mail_mode, verify_code
from ..security import (
    COOKIE,
    allow,
    burn_password_check,
    clear_cookie,
    client_key,
    cookie_kwargs,
    get_current_user,
    hash_password,
    oauth_state,
    oauth_state_matches,
    set_session_cookie,
    verify_password,
)

router = APIRouter()
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False


class ForgotIn(BaseModel):
    email: str = Field(max_length=120)


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class VerifyCodeIn(BaseModel):
    email: str = Field(max_length=120)
    code: str = Field(min_length=6, max_length=6)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)


class ProfileIn(BaseModel):
    level: str
    horizon: str
    risk_tolerance: str
    goals: list[str] = []
    sectors: list[str] = []
    favorite_symbols: list[str] = []
    news_keywords: list[str] = []
    language: str = "fr"
    notif_prefs: dict = {}
    onboarding_completed: bool = False


class WatchIn(BaseModel):
    symbols: list[str] = []


class AlertIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=15)
    kind: str
    threshold: float | None = None


def _public_user(user: User, profile: UserProfile | None) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "onboarding_completed": bool(profile and profile.onboarding_completed),
        "profile": _public_profile(profile),
    }


def _public_profile(profile: UserProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "level": profile.level,
        "horizon": profile.horizon,
        "risk_tolerance": profile.risk_tolerance,
        "goals": profile.goals or [],
        "sectors": profile.sectors or [],
        "favorite_symbols": profile.favorite_symbols or [],
        "news_keywords": profile.news_keywords or [],
        "language": profile.language,
        "notif_prefs": profile.notif_prefs or default_notif_prefs(),
        "onboarding_completed": profile.onboarding_completed,
    }


def _cookie(response: Response, user: User, remember: bool = True) -> None:
    set_session_cookie(response, user.id, remember, int(user.token_version or 0))


def google_enabled() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


_RESET_MESSAGE = "Si un compte existe pour cet e-mail, un code de réinitialisation a été préparé."


@router.post("/auth/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if not allow(client_key(request, "register"), 10, 60):
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessaie dans une minute.")
    email = body.email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="Adresse e-mail invalide.")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet e-mail.")
    user = User(id=str(uuid.uuid4()), email=email, password_hash=hash_password(body.password), display_name=body.display_name.strip())
    profile = UserProfile(user_id=user.id, notif_prefs=default_notif_prefs(), goals=[], sectors=[], favorite_symbols=[], news_keywords=[])
    db.add(user)
    db.add(profile)
    db.commit()
    _cookie(response, user, True)
    return _public_user(user, profile)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if not allow(client_key(request, "login"), 10, 60):
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessaie dans une minute.")
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        burn_password_check(body.password)
        raise HTTPException(status_code=401, detail="E-mail ou mot de passe incorrect.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou mot de passe incorrect.")
    profile = db.get(UserProfile, user.id)
    _cookie(response, user, body.remember)
    return _public_user(user, profile)


@router.get("/auth/providers")
def providers():
    # mail : « smtp » (vraie boîte), « local » (boîte de test) ou « logs » (aucun serveur).
    return {"google": google_enabled(), "mail": mail_mode()}


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    # Compteur distinct de celui de la connexion.
    if not allow(client_key(request, "forgot"), 5, 60):
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessaie dans une minute.")
    email = body.email.strip().lower()
    # Par e-mail, que le compte existe ou non : borne le nombre de codes émis, d'où que vienne la demande.
    if not allow(f"forgot-email:{email}", 5, 900):
        raise HTTPException(status_code=429, detail="Trop de codes demandés pour cet e-mail. Réessaie dans un quart d'heure.")
    user = db.query(User).filter(User.email == email).first()
    # Même coût que l'e-mail existe ou non : une empreinte, puis éventuellement l'enregistrement du code.
    hash_password("marketpulse-forgot-balance")
    if user is not None:
        issue_code(db, user)
    return {"detail": _RESET_MESSAGE}


@router.post("/auth/verify-code")
def verify_code_route(body: VerifyCodeIn, request: Request, response: Response, db: Session = Depends(get_db)):
    # Le code tient en 6 chiffres : il est détruit au 5e échec (passwords.verify_code).
    # Ce compteur par adresse IP et par e-mail laisse la place à un second code, pas plus.
    email = body.email.strip().lower()
    if not allow(f"verify:{client_key(request, 'code')}:{email}", 10, 600):
        raise HTTPException(status_code=429, detail="Trop de tentatives. Demande un nouveau code.")
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_code(db, user, body.code):
        raise HTTPException(status_code=401, detail="Code invalide ou expiré.")
    # Le code prouve la boîte e-mail : session directe, les autres sessions sont fermées (token_version déjà incrémentée).
    profile = db.get(UserProfile, user.id)
    _cookie(response, user, True)
    return _public_user(user, profile)


@router.post("/auth/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    if not consume_reset(db, body.token, body.password):
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré.")
    return {"ok": True}


@router.get("/auth/google/start")
def google_start():
    if not google_enabled():
        raise HTTPException(status_code=404, detail="Google n'est pas configuré.")
    state = oauth_state()
    redirect = os.getenv("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/") + "/api/auth/google/callback"
    query = urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": redirect,
        "state": state,
    })
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    response = RedirectResponse(url)
    response.set_cookie("mp_oauth_state", state, max_age=600, **cookie_kwargs())
    return response


@router.get("/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", db: Session = Depends(get_db)):
    if not google_enabled():
        raise HTTPException(status_code=404, detail="Google n'est pas configuré.")
    if not oauth_state_matches(request.cookies.get("mp_oauth_state"), state):
        raise HTTPException(status_code=400, detail="Session Google invalide.")
    redirect_uri = os.getenv("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/") + "/api/auth/google/callback"
    token = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    if token.status_code != 200:
        raise HTTPException(status_code=400, detail="Google a refusé la connexion.")
    info = httpx.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {token.json().get('access_token', '')}"},
        timeout=15,
    )
    if info.status_code != 200:
        raise HTTPException(status_code=400, detail="Profil Google illisible.")
    payload = info.json()
    email = str(payload.get("email") or "").lower()
    subject = str(payload.get("sub") or "")
    if payload.get("email_verified") is not True or not _EMAIL.match(email) or not subject:
        raise HTTPException(status_code=400, detail="Le profil Google n'est pas vérifié.")
    user = db.query(User).filter(User.google_sub == subject).first()
    if user is None:
        existing = db.query(User).filter(User.email == email).first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet e-mail. Connecte-toi avec le mot de passe.")
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(24)),
            display_name=str(payload.get("name") or email.split("@")[0])[:80],
            google_sub=subject,
            token_version=0,
        )
        db.add(user)
        db.add(UserProfile(user_id=user.id, notif_prefs=default_notif_prefs(), goals=[], sectors=[], favorite_symbols=[], news_keywords=[]))
        db.commit()
        db.refresh(user)
    destination = os.getenv("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/") + "/dashboard"
    response = RedirectResponse(destination)
    _cookie(response, user, True)
    clear_cookie(response, "mp_oauth_state")
    return response


@router.post("/auth/logout")
def logout(response: Response):
    clear_cookie(response, COOKIE)
    return {"ok": True}


@router.post("/me/password")
def update_password(body: PasswordChangeIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect.")
    change_password(db, user, body.password)
    _cookie(response, user, True)
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _public_user(user, db.get(UserProfile, user.id))


@router.get("/me/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profil introuvable.")
    return _public_profile(profile)


@router.put("/me/profile")
def put_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.level not in LEVELS or body.horizon not in HORIZONS or body.risk_tolerance not in RISKS:
        raise HTTPException(status_code=400, detail="Niveau, horizon ou tolérance inconnu.")
    if body.language not in {"fr", "en"}:
        raise HTTPException(status_code=400, detail="Langue inconnue.")
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    profile.level = body.level
    profile.horizon = body.horizon
    profile.risk_tolerance = body.risk_tolerance
    profile.goals = clean_list(body.goals, limit=8, item_max=80)
    profile.sectors = clean_list(body.sectors, limit=8, item_max=40)
    profile.favorite_symbols = [item.upper() for item in clean_list(body.favorite_symbols, limit=20, item_max=15)]
    profile.news_keywords = clean_list(body.news_keywords, limit=12, item_max=40)
    profile.language = body.language
    profile.notif_prefs = clean_prefs(body.notif_prefs)
    profile.onboarding_completed = body.onboarding_completed
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _public_profile(profile)


@router.put("/me/watchlist")
def put_watchlist(body: WatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    symbols = [item.upper() for item in clean_list(body.symbols, limit=30, item_max=15)]
    db.query(UserSymbol).filter(UserSymbol.user_id == user.id).delete()
    for symbol in symbols:
        db.add(UserSymbol(user_id=user.id, symbol=symbol))
    db.commit()
    return {"symbols": symbols}


@router.get("/me/alerts")
def list_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(AlertRule).filter(AlertRule.user_id == user.id).all()
    return [{"id": row.id, "symbol": row.symbol, "kind": row.kind, "threshold": row.threshold, "enabled": row.enabled} for row in rows]


@router.post("/me/alerts")
def add_alert(body: AlertIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.kind not in ALERT_KINDS:
        raise HTTPException(status_code=400, detail="Type d'alerte inconnu.")
    rule = AlertRule(id=str(uuid.uuid4()), user_id=user.id, symbol=body.symbol.strip().upper(), kind=body.kind, threshold=body.threshold, enabled=True)
    db.add(rule)
    db.commit()
    return {"id": rule.id, "symbol": rule.symbol, "kind": rule.kind, "threshold": rule.threshold, "enabled": True}


@router.patch("/me/alerts/{alert_id}")
def update_alert(alert_id: str, enabled: bool = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.query(AlertRule).filter(AlertRule.id == alert_id, AlertRule.user_id == user.id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Alerte introuvable.")
    rule.enabled = enabled
    db.commit()
    return {"id": rule.id, "enabled": rule.enabled}


@router.delete("/me/alerts/{alert_id}")
def delete_alert(alert_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.query(AlertRule).filter(AlertRule.id == alert_id, AlertRule.user_id == user.id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Alerte introuvable.")
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.delete("/me")
def delete_me(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Supprime le compte et les données qui lui sont liées."""
    conversation_ids = [row[0] for row in db.query(Conversation.id).filter(Conversation.user_id == user.id).all()]
    if conversation_ids:
        db.query(Message).filter(Message.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.user_id == user.id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id == user.id).delete(synchronize_session=False)
    db.query(PushSubscription).filter(PushSubscription.user_id == user.id).delete(synchronize_session=False)
    db.query(AlertRule).filter(AlertRule.user_id == user.id).delete(synchronize_session=False)
    db.query(UserSymbol).filter(UserSymbol.user_id == user.id).delete(synchronize_session=False)
    db.query(UserProfile).filter(UserProfile.user_id == user.id).delete(synchronize_session=False)
    db.query(PasswordReset).filter(PasswordReset.user_id == user.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()
    clear_cookie(response, COOKIE)
    return {"ok": True}
