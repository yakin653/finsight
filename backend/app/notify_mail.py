"""Copie des notifications par e-mail, pour les comptes qui l'ont demandé (prefs["email"]).

L'envoi part du serveur : il ne dépend pas d'une session ouverte dans le navigateur.
Les messages partent un par un (Gmail refuse souvent plusieurs SMTP en parallèle).
"""
from __future__ import annotations

import queue
import threading
import time
from datetime import date

from sqlalchemy.orm import Session

from .models import User, UserProfile
from .passwords import _try_send, mail_mode, public_site_url

# Au plus 10 e-mails par compte et par jour : Yahoo peut renvoyer beaucoup de titres d'un coup.
MAX_PER_DAY = 10
# En mémoire, par processus : un redémarrage remet les compteurs à zéro (comme le rate limit).
_SENT: dict[tuple[str, date], int] = {}
_MAIL_Q: queue.Queue[tuple[str, str, str]] = queue.Queue()
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def _one_line(text: str) -> str:
    """Les titres viennent de l'extérieur : pas de saut de ligne dans un en-tête de message."""
    return " ".join(str(text).split())


def _take_slot(user_id: str, today: date) -> bool:
    for key in [key for key in _SENT if key[1] != today]:
        del _SENT[key]
    count = _SENT.get((user_id, today), 0)
    if count >= MAX_PER_DAY:
        return False
    _SENT[(user_id, today)] = count + 1
    return True


def _worker() -> None:
    while True:
        email, subject, text = _MAIL_Q.get()
        try:
            _try_send(email, subject, text)
        finally:
            _MAIL_Q.task_done()
            # Gmail : espacer les envois évite les pertes silencieuses.
            time.sleep(1.5)


def _ensure_worker() -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        threading.Thread(target=_worker, name="marketpulse-mail", daemon=True).start()
        _WORKER_STARTED = True


def email_notification(db: Session, user_id: str, title: str, body: str, today: date | None = None) -> str:
    """Envoie la notification par e-mail si le compte l'a activé.

    Retourne : desactive, sans_serveur, limite ou en_cours (file d'attente, n'bloque pas la requête).
    """
    profile = db.get(UserProfile, user_id)
    if profile is None or (profile.notif_prefs or {}).get("email") is not True:
        return "desactive"
    if mail_mode() == "logs":
        return "sans_serveur"
    user = db.get(User, user_id)
    if user is None or not user.email:
        return "desactive"
    if not _take_slot(user_id, today or date.today()):
        return "limite"
    subject = "MarketPulse — " + _one_line(title)[:120]
    text = (
        f"{_one_line(title)}\n\n{body.strip()}\n\n"
        f"Ouvrir dans ton compte : {public_site_url()}/notifications\n\n"
        "C'est la même notification que dans MarketPulse (Profil → "
        "« Recevoir aussi mes notifications par e-mail »). "
        "Ce n'est pas un conseil en investissement."
    )
    _ensure_worker()
    _MAIL_Q.put((user.email, subject, text))
    return "en_cours"
