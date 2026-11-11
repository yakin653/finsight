"""Réinitialisation : le jeton ou le code en clair ne quitte le serveur que par e-mail ou par le journal de dev."""
from __future__ import annotations

import hashlib
import os
import secrets
import smtplib
import ssl
import threading
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from .models import PasswordReset, User

RESET_MINUTES = 30


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_reset_link(token: str) -> str:
    """L'adresse vient de APP_PUBLIC_URL, jamais de l'en-tête Host."""
    base = os.getenv("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/reset-password?token={token}"


def log_reset_links() -> bool:
    if os.getenv("DEV_LOG_RESET_LINKS", "").lower() == "true":
        return True
    return os.getenv("APP_ENV", "development").lower() != "production"


def issue_reset(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    row = PasswordReset(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=_hash(token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_MINUTES),
    )
    db.add(row)
    db.commit()
    link = public_reset_link(token)
    threading.Thread(target=deliver_reset, args=(user.email, link), daemon=True).start()
    return token


SMTP_TIMEOUT = 15
# Boîtes de test : le message est capturé sur la machine, il n'atteint aucune vraie boîte.
_LOCAL_HOSTS = {"mailpit", "mailhog", "localhost", "127.0.0.1"}


def _smtp_target() -> tuple[str, int]:
    host = os.getenv("SMTP_HOST", "").strip()
    try:
        port = int(os.getenv("SMTP_PORT", "").strip() or 587)
    except ValueError:
        port = 587
    return host, port


def mail_mode() -> str:
    """logs : aucun serveur ; local : boîte de test (Mailpit) ; smtp : vraie boîte du destinataire."""
    host = _smtp_target()[0].lower()
    if not host:
        return "logs"
    return "local" if host in _LOCAL_HOSTS else "smtp"


def mail_status() -> str:
    """Une ligne pour le journal de démarrage. Aucun identifiant n'y figure."""
    host, port = _smtp_target()
    mode = mail_mode()
    if mode == "logs":
        return "E-mails : aucun serveur (SMTP_HOST vide). En développement, le code est écrit dans ce journal."
    if mode == "local":
        return f"E-mails : boîte de test locale {host}:{port}. Rien n'arrive dans une vraie boîte mail."
    account = "compte défini" if os.getenv("SMTP_USER", "").strip() else "SANS compte (SMTP_USER vide)"
    return f"E-mails : envoi réel via {host}:{port}, {account}."


def _sender() -> str:
    sender = os.getenv("SMTP_FROM", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    # Un relais réel refuse souvent un expéditeur @localhost : on prend alors le compte d'envoi.
    if (not sender or sender.endswith("@localhost")) and "@" in user:
        return user
    return sender or "marketpulse@localhost"


def _mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


def _send_email(email: str, subject: str, body: str) -> None:
    host, port = _smtp_target()
    user = os.getenv("SMTP_USER", "").strip()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _sender()
    message["To"] = email
    message.set_content(body)
    context = ssl.create_default_context()
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=context)
    else:
        smtp = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
    with smtp:
        if port != 465:
            smtp.ehlo()
            if smtp.has_extn("starttls"):
                smtp.starttls(context=context)
                smtp.ehlo()
            elif user:
                raise smtplib.SMTPNotSupportedError("STARTTLS absent : les identifiants ne partent pas en clair.")
        if user:
            _login(smtp, user, os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(message)


def _login(smtp: smtplib.SMTP, user: str, password: str) -> None:
    """Une seule tentative. smtplib.login() en enchaîne plusieurs : après un premier refus (535),
    Gmail coupe la connexion et l'erreur visible devient « déconnecté » au lieu de « identifiants refusés »."""
    methods = str(smtp.esmtp_features.get("auth", "")).upper().split()
    if "PLAIN" in methods:
        smtp.user, smtp.password = user, password
        smtp.auth("PLAIN", smtp.auth_plain)
    else:
        smtp.login(user, password)


def _explain(error: Exception) -> str:
    """Cause lisible. Ni le contenu du message ni un identifiant n'est recopié."""
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "identifiants refusés (SMTP_USER / SMTP_PASSWORD ; Gmail exige un mot de passe d'application)"
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return "le serveur ne propose pas de connexion chiffrée (STARTTLS)"
    if isinstance(error, smtplib.SMTPSenderRefused):
        return "expéditeur refusé (SMTP_FROM)"
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "destinataire refusé par le serveur"
    if isinstance(error, ssl.SSLError):
        return "échec TLS (certificat ou port : 587 pour STARTTLS, 465 pour SSL)"
    if isinstance(error, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return "serveur injoignable ou connexion coupée (SMTP_HOST / SMTP_PORT)"
    if isinstance(error, OSError) and not isinstance(error, smtplib.SMTPException):
        return "serveur injoignable (SMTP_HOST / SMTP_PORT)"
    return f"erreur {type(error).__name__}"


def _try_send(email: str, subject: str, body: str) -> str | None:
    """None si le serveur a accepté le message, sinon la cause. Ne lève jamais."""
    host, port = _smtp_target()
    try:
        _send_email(email, subject, body)
    except Exception as error:  # noqa: BLE001 — le fil d'envoi ne doit pas tomber en silence
        reason = _explain(error)
        print(f"E-mail NON envoyé à {_mask(email)} via {host}:{port} : {reason}.", flush=True)
        return reason
    print(f"E-mail accepté par {host}:{port} pour {_mask(email)}.", flush=True)
    return None


def send_test(email: str) -> tuple[bool, str]:
    """Message de diagnostic, sans code ni lien (voir app/mailcheck.py)."""
    if mail_mode() == "logs":
        return False, "SMTP_HOST est vide : aucun e-mail ne peut partir."
    reason = _try_send(
        email,
        "MarketPulse — test d'envoi",
        "Ce message confirme que l'envoi d'e-mails de MarketPulse fonctionne.",
    )
    if reason is not None:
        return False, f"Échec : {reason}."
    if mail_mode() == "local":
        return True, "Accepté par la boîte de test locale (http://localhost:8025), pas par une vraie boîte."
    return True, "Accepté par le serveur d'envoi. Vérifie la boîte de réception et le dossier Spam."


def _deliver(email: str, subject: str, body: str, dev_line: str) -> bool:
    if mail_mode() == "logs":
        if log_reset_links():
            print(dev_line, flush=True)
        else:
            print(f"E-mail NON envoyé à {_mask(email)} : SMTP_HOST est vide.", flush=True)
        return False
    return _try_send(email, subject, body) is None


def deliver_reset(email: str, link: str) -> bool:
    return _deliver(
        email,
        "MarketPulse — réinitialisation du mot de passe",
        "Un lien de réinitialisation a été demandé. Il expire dans 30 minutes.\n\n"
        f"{link}\n\n"
        "Si tu n'es pas à l'origine de cette demande, ignore ce message.",
        f"Réinitialisation (développement) : {link}",
    )


CODE_MINUTES = 10
MAX_CODE_TRIES = 5
# Essais ratés par code, en mémoire : suffisant pour un seul processus uvicorn.
_CODE_FAILS: dict[str, int] = {}


def _code_hash(user_id: str, code: str) -> str:
    # Lié au compte : deux comptes peuvent recevoir le même code sans heurter l'unicité de token_hash.
    return _hash(f"code:{user_id}:{code}")


def issue_code(db: Session, user: User) -> str:
    """Code à 6 chiffres : seule l'empreinte est stockée, les anciens codes sont invalidés."""
    from sqlalchemy.exc import IntegrityError

    now = datetime.now(timezone.utc)
    db.query(PasswordReset).filter(
        PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)
    ).update({"used_at": now})
    db.commit()
    user_id, email = user.id, user.email
    for _attempt in range(5):
        code = f"{secrets.randbelow(1_000_000):06d}"
        db.add(
            PasswordReset(
                id=str(uuid.uuid4()),
                user_id=user_id,
                token_hash=_code_hash(user_id, code),
                expires_at=now + timedelta(minutes=CODE_MINUTES),
            )
        )
        try:
            db.commit()
        except IntegrityError:  # même code déjà émis pour ce compte : on en tire un autre
            db.rollback()
            continue
        threading.Thread(target=deliver_code, args=(email, code), daemon=True).start()
        return code
    # Aucun code enregistré : on n'envoie rien plutôt qu'un code qui ne marcherait pas.
    print(f"Code non émis pour {_mask(email)} : enregistrement impossible.", flush=True)
    return ""


def verify_code(db: Session, user: User, code: str) -> bool:
    """Vrai si le code est le dernier émis, vivant et correct. Le consomme et ferme les autres sessions."""
    now = datetime.now(timezone.utc)
    row = (
        db.query(PasswordReset)
        .filter(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .order_by(PasswordReset.expires_at.desc())
        .first()
    )
    if row is None:
        return False
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        return False
    if not secrets.compare_digest(row.token_hash, _code_hash(user.id, code.strip())):
        # Un code à 6 chiffres ne supporte pas l'essai en série : il est détruit au 5e échec,
        # quelle que soit l'adresse IP d'où viennent les essais.
        if len(_CODE_FAILS) > 10_000:
            _CODE_FAILS.clear()
        fails = _CODE_FAILS.get(row.id, 0) + 1
        _CODE_FAILS[row.id] = fails
        if fails >= MAX_CODE_TRIES:
            _CODE_FAILS.pop(row.id, None)
            row.used_at = now
            db.commit()
        return False
    _CODE_FAILS.pop(row.id, None)
    row.used_at = now
    user.token_version = int(user.token_version or 0) + 1
    db.commit()
    return True


def deliver_code(email: str, code: str) -> bool:
    return _deliver(
        email,
        "MarketPulse — ton code de connexion",
        f"Ton code MarketPulse : {code}\n\n"
        f"Il expire dans {CODE_MINUTES} minutes et ne sert qu'une fois.\n"
        "Saisis-le sur la page « Mot de passe oublié » pour te connecter directement.\n\n"
        "Si tu n'es pas à l'origine de cette demande, ignore ce message.",
        f"Code de réinitialisation (développement) : {code}",
    )


def consume_reset(db: Session, token: str, password: str) -> bool:
    from .security import hash_password

    row = db.query(PasswordReset).filter(PasswordReset.token_hash == _hash(token)).first()
    now = datetime.now(timezone.utc)
    if row is None or row.used_at is not None:
        return False
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        return False
    user = db.get(User, row.user_id)
    if user is None:
        return False
    user.password_hash = hash_password(password)
    user.token_version = int(user.token_version or 0) + 1
    row.used_at = now
    db.commit()
    return True


def change_password(db: Session, user: User, password: str) -> None:
    from .security import hash_password

    user.password_hash = hash_password(password)
    user.token_version = int(user.token_version or 0) + 1
    db.commit()
    db.refresh(user)
