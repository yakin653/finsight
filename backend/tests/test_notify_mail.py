"""Notifications recopiées par e-mail, session ouverte ou non."""
import uuid
from datetime import date

import pytest

from app import notify_mail
from app.database import SessionLocal
from app.jobs import _notify
from app.models import Notification, User
from app.profiles import clean_prefs, default_notif_prefs

ORIGIN = {"Origin": "http://localhost:3000"}
PROFILE = {"level": "debutant", "horizon": "long", "risk_tolerance": "prudent", "language": "fr", "onboarding_completed": True}


class _SyncThread:
    """Exécute l'envoi tout de suite, pour pouvoir l'observer."""

    def __init__(self, target, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


@pytest.fixture
def sent(monkeypatch):
    messages: list[tuple[str, str, str]] = []
    monkeypatch.setenv("SMTP_HOST", "mailpit")
    monkeypatch.setattr(notify_mail, "_try_send", lambda email, subject, body: messages.append((email, subject, body)))
    monkeypatch.setattr(notify_mail.threading, "Thread", _SyncThread)
    notify_mail._SENT.clear()
    yield messages
    notify_mail._SENT.clear()


@pytest.fixture
def account(client):
    email = f"notif-{uuid.uuid4().hex}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Notif"}, headers=ORIGIN).status_code == 200
    db = SessionLocal()
    user_id = db.query(User).filter(User.email == email).one().id
    yield client, db, email, user_id
    db.close()
    client.delete("/me", headers=ORIGIN)


def _set_email(client, enabled):
    prefs = {"frequence": "instantane", "heure": 8, "quiet_start": 22, "quiet_end": 7, "email": enabled}
    assert client.put("/me/profile", json={**PROFILE, "notif_prefs": prefs}, headers=ORIGIN).status_code == 200


def test_email_option_is_off_by_default_and_must_be_a_boolean():
    assert default_notif_prefs()["email"] is False
    assert clean_prefs({"email": True})["email"] is True
    assert clean_prefs({"email": "oui"})["email"] is False
    assert clean_prefs(None)["email"] is False


def test_nothing_is_sent_while_the_option_is_off(sent, account):
    _client, db, _email, user_id = account
    assert notify_mail.email_notification(db, user_id, "Titre", "Corps") == "desactive"
    assert sent == []


def test_option_is_saved_through_the_profile_route(account):
    client, _db, _email, _user_id = account
    _set_email(client, True)
    assert client.get("/me/profile").json()["notif_prefs"]["email"] is True
    _set_email(client, False)
    assert client.get("/me/profile").json()["notif_prefs"]["email"] is False


def test_notification_is_mailed_without_any_session(sent, account):
    client, db, email, user_id = account
    _set_email(client, True)
    client.cookies.clear()  # déconnecté : le serveur n'a plus besoin du navigateur
    note = _notify(db, user_id, "Alerte de cours", "AAPL a franchi sa MM20.", "AAPL", None, "alert:test")
    assert note is not None
    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == email
    assert subject == "MarketPulse — Alerte de cours"
    assert "AAPL a franchi sa MM20." in body
    assert "/notifications" in body
    assert "pas un conseil" in body
    db.query(Notification).filter(Notification.user_id == user_id).delete()
    db.commit()


def test_subject_cannot_carry_a_line_break_from_a_headline(sent, account):
    client, db, _email, user_id = account
    _set_email(client, True)
    assert notify_mail.email_notification(db, user_id, "Titre\r\nBcc: autre@example.com", "Corps") == "en_cours"
    assert "\n" not in sent[0][1] and "\r" not in sent[0][1]


def test_at_most_ten_mails_per_day(sent, account):
    client, db, _email, user_id = account
    _set_email(client, True)
    today = date(2026, 11, 12)
    results = [notify_mail.email_notification(db, user_id, f"Titre {i}", "Corps", today=today) for i in range(12)]
    assert results[:10] == ["en_cours"] * 10
    assert results[10:] == ["limite", "limite"]
    assert len(sent) == 10
    assert notify_mail.email_notification(db, user_id, "Lendemain", "Corps", today=date(2026, 11, 13)) == "en_cours"


def test_no_mail_server_means_no_mail(sent, account, monkeypatch):
    client, db, _email, user_id = account
    _set_email(client, True)
    monkeypatch.setenv("SMTP_HOST", "")
    assert notify_mail.email_notification(db, user_id, "Titre", "Corps") == "sans_serveur"
    assert sent == []
