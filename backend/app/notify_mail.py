"""Copie des notifications par e-mail, pour les comptes qui l'ont demandé (prefs["email"]).

L'envoi part du serveur : il ne dépend pas d'une session ouverte dans le navigateur.
"""
from __future__ import annotations

import threading
from datetime import date

from sqlalchemy.orm import Session

from .models import User, UserProfile
from .passwords import _try_send, mail_mode, public_site_url

# Au plus 10 e-mails par compte et par jour : Yahoo peut renvoyer beaucoup de titres d'un coup.
MAX_PER_DAY = 10
# En mémoire, par processus : un redémarrage remet les compteurs à zéro (comme le rate limit).
_SENT: dict[tuple[str, date], int] = {}


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


def email_notification(db: Session, user_id: str, title: str, body: str, today: date | None = None) -> str:
    """Envoie la notification par e-mail si le compte l'a activé.

    Retourne : desactive, sans_serveur, limite ou en_cours (l'envoi se fait dans un fil, il ne bloque rien).
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
        f"Ouvrir MarketPulse : {public_site_url()}/notifications\n\n"
        "Tu reçois ce message parce que les notifications par e-mail sont activées sur ton profil "
        "(Profil, « Recevoir aussi mes notifications par e-mail »). Ce n'est pas un conseil en investissement."
    )
    threading.Thread(target=_try_send, args=(user.email, subject, text), daemon=True).start()
    return "en_cours"
