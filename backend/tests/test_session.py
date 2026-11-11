"""Session, origine, réinitialisation et règles Google simulées."""
import smtplib
import time
import uuid
from datetime import date
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.market_refresh import expected_session, get_meta, quotes_are_stale, set_meta
from app.models import AppMeta, User
from app.passwords import (
    _code_hash,
    deliver_code,
    deliver_reset,
    issue_code,
    issue_reset,
    mail_mode,
    mail_status,
    public_reset_link,
)
from app.security import _HITS

ORIGIN = {"Origin": "http://localhost:3000"}


class _GoogleResponse:
    def __init__(self, body: dict):
        self.status_code = 200
        self._body = body

    def json(self):
        return self._body


def test_expected_session_skips_the_weekend():
    assert expected_session(date(2026, 11, 4)) == date(2026, 11, 4)
    assert expected_session(date(2026, 11, 7)) == date(2026, 11, 6)


def test_old_timestamp_is_stale_and_restored():
    db = SessionLocal()
    previous = get_meta(db, "refreshed_at")
    try:
        set_meta(db, "refreshed_at", "2026-10-29T00:00:00+00:00")
        db.commit()
        assert quotes_are_stale(db, today=date(2026, 11, 4)) is True
        set_meta(db, "refreshed_at", "2026-11-04T12:00:00+00:00")
        db.commit()
        assert quotes_are_stale(db, today=date(2026, 11, 4)) is False
    finally:
        if previous is None:
            db.query(AppMeta).filter(AppMeta.key == "refreshed_at").delete()
        else:
            set_meta(db, "refreshed_at", previous)
        db.commit()
        db.close()


def test_origin_rules(client):
    payload = {"email": "personne@example.com", "password": "motdepasse"}
    assert client.post("/auth/login", json=payload, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/auth/login", json=payload, headers={"Origin": "null"}).status_code == 403
    assert client.post("/auth/login", json=payload, headers={"Origin": "http://localhost:3000"}).status_code == 401
    assert client.post("/auth/login", json=payload, headers={"Origin": "http://127.0.0.1:3000"}).status_code == 401
    bare = TestClient(app)
    assert bare.post("/auth/login", json=payload).status_code == 401
    with_cookie = TestClient(app)
    with_cookie.cookies.set("mp_session", "jeton-inconnu")
    assert with_cookie.post("/auth/login", json=payload).status_code == 403
    allowed = TestClient(app)
    allowed.cookies.set("mp_session", "jeton-inconnu")
    assert allowed.post("/auth/login", json=payload, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 401


def test_forgot_password_hides_whether_the_email_exists(client):
    missing_email = f"absent-{uuid.uuid4().hex}@example.com"
    email = f"reset-{uuid.uuid4().hex}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Reset"}, headers=ORIGIN).status_code == 200
    started = time.perf_counter()
    missing = client.post("/auth/forgot-password", json={"email": missing_email}, headers=ORIGIN)
    middle = time.perf_counter()
    present = client.post("/auth/forgot-password", json={"email": email}, headers=ORIGIN)
    finished = time.perf_counter()
    assert missing.status_code == present.status_code == 200
    assert missing.content == present.content
    assert abs((middle - started) - (finished - middle)) < 1.0


def test_forgot_rate_limit_does_not_block_login(client, monkeypatch):
    monkeypatch.delenv("DISABLE_RATE_LIMIT", raising=False)
    _HITS.clear()
    email = f"rate-{uuid.uuid4().hex}@example.com"
    codes = [client.post("/auth/forgot-password", json={"email": email}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 200, 200]
    assert client.post("/auth/forgot-password", json={"email": email}).status_code == 429
    assert client.post("/auth/login", json={"email": email, "password": "motdepasse"}).status_code == 401
    _HITS.clear()


def test_reset_link_uses_the_public_url_and_stays_out_of_production_logs(monkeypatch, capsys):
    monkeypatch.setenv("APP_PUBLIC_URL", "https://app.example")
    assert public_reset_link("abc") == "https://app.example/reset-password?token=abc"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEV_LOG_RESET_LINKS", raising=False)
    monkeypatch.setenv("SMTP_HOST", "")
    deliver_reset("a@example.com", "https://app.example/reset-password?token=secret-token")
    assert "secret-token" not in capsys.readouterr().out
    monkeypatch.setenv("DEV_LOG_RESET_LINKS", "true")
    deliver_reset("a@example.com", "https://app.example/reset-password?token=secret-token")
    assert "secret-token" in capsys.readouterr().out


def test_reset_invalidates_the_session_and_session_cookie_has_no_max_age(client):
    email = f"once-{uuid.uuid4().hex}@example.com"
    created = client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Once"}, headers=ORIGIN)
    assert created.status_code == 200
    assert "max-age" in created.headers["set-cookie"].lower()
    assert "httponly" in created.headers["set-cookie"].lower()
    assert "samesite=lax" in created.headers["set-cookie"].lower()
    assert "path=/" in created.headers["set-cookie"].lower()
    assert client.get("/auth/me").status_code == 200
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).one()
    token = issue_reset(db, user)
    db.close()
    assert client.post("/auth/reset-password", json={"token": token, "password": "nouveau123"}, headers=ORIGIN).status_code == 200
    assert client.get("/auth/me").status_code == 401
    logged = client.post("/auth/login", json={"email": email, "password": "nouveau123", "remember": False}, headers=ORIGIN)
    assert logged.status_code == 200
    assert "max-age" not in logged.headers["set-cookie"].lower()
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/reset-password", json={"token": token, "password": "encoreune1"}, headers=ORIGIN).status_code == 400


def test_code_login_connects_directly_and_closes_other_sessions(client):
    email = f"code-{uuid.uuid4().hex}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Code"}, headers=ORIGIN).status_code == 200
    old_cookie = client.cookies.get("mp_session")
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).one()
    code = issue_code(db, user)
    db.close()
    assert len(code) == 6 and code.isdigit()
    assert client.post("/auth/verify-code", json={"email": email, "code": "000000" if code != "000000" else "111111"}, headers=ORIGIN).status_code == 401
    connected = client.post("/auth/verify-code", json={"email": email, "code": code}, headers=ORIGIN)
    assert connected.status_code == 200
    assert "httponly" in connected.headers["set-cookie"].lower()
    assert client.get("/auth/me").status_code == 200
    # Le code est à usage unique, et la session d'avant le code est fermée.
    assert client.post("/auth/verify-code", json={"email": email, "code": code}, headers=ORIGIN).status_code == 401
    other = TestClient(app)
    other.cookies.set("mp_session", old_cookie)
    assert other.get("/auth/me").status_code == 401


def test_new_code_invalidates_the_previous_one(client):
    email = f"codes-{uuid.uuid4().hex}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Codes"}, headers=ORIGIN).status_code == 200
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).one()
    first = issue_code(db, user)
    second = issue_code(db, user)
    db.close()
    if first != second:
        assert client.post("/auth/verify-code", json={"email": email, "code": first}, headers=ORIGIN).status_code == 401
    assert client.post("/auth/verify-code", json={"email": email, "code": second}, headers=ORIGIN).status_code == 200


class _FakeSMTP:
    """Serveur SMTP simulé : note les étapes, ne touche pas au réseau."""

    events: list = []
    sent: list = []
    login_error: Exception | None = None

    def __init__(self, host, port, timeout=None, **_kwargs):
        _FakeSMTP.events.append(("connect", host, port, timeout))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def ehlo(self):
        return None

    def has_extn(self, name):
        return name == "starttls"

    def starttls(self, context=None):
        _FakeSMTP.events.append(("starttls", context is not None))

    esmtp_features = {"auth": "LOGIN PLAIN XOAUTH2"}
    user = ""
    password = ""

    def auth_plain(self, _challenge=None):
        return ""

    def auth(self, mechanism, _authobject):
        # Une seule méthode est tentée : un refus doit remonter tel quel.
        _FakeSMTP.events.append(("auth", mechanism))
        if _FakeSMTP.login_error is not None:
            raise _FakeSMTP.login_error
        _FakeSMTP.events.append(("login", self.user))

    def login(self, _user, _password):
        raise AssertionError("login() enchaîne plusieurs méthodes : auth('PLAIN') est attendu")

    def send_message(self, message):
        _FakeSMTP.events.append(("send",))
        _FakeSMTP.sent.append(message)


def _fake_smtp(monkeypatch, login_error: Exception | None = None) -> str:
    """Branche le faux serveur et rend le mot de passe factice utilisé."""
    password = f"factice-{uuid.uuid4().hex}"
    _FakeSMTP.events, _FakeSMTP.sent, _FakeSMTP.login_error = [], [], login_error
    monkeypatch.setattr("app.passwords.smtplib.SMTP", _FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "envoi@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", password)
    monkeypatch.setenv("SMTP_FROM", "marketpulse@localhost")
    return password


def _random_code() -> str:
    return f"{uuid.uuid4().int % 1_000_000:06d}"


def test_code_email_goes_through_smtp_with_tls_and_login(monkeypatch, capsys):
    password = _fake_smtp(monkeypatch)
    code = _random_code()
    assert deliver_code("destinataire@example.com", code) is True
    assert [event[0] for event in _FakeSMTP.events] == ["connect", "starttls", "auth", "login", "send"]
    assert _FakeSMTP.events[0] == ("connect", "smtp.example.com", 587, 15)
    assert _FakeSMTP.events[1] == ("starttls", True)
    assert _FakeSMTP.events[2] == ("auth", "PLAIN")
    assert _FakeSMTP.events[3] == ("login", "envoi@example.com")
    message = _FakeSMTP.sent[0]
    assert message["To"] == "destinataire@example.com"
    # Un relais réel refuse @localhost : l'expéditeur devient le compte d'envoi.
    assert message["From"] == "envoi@example.com"
    assert code in message.get_content()
    logged = capsys.readouterr().out
    assert "d***@example.com" in logged
    assert code not in logged and password not in logged and "destinataire@" not in logged


def test_smtp_failure_is_reported_without_code_or_password(monkeypatch, capsys):
    password = _fake_smtp(monkeypatch, smtplib.SMTPAuthenticationError(535, b"refus"))
    code = _random_code()
    # L'échec ne remonte pas en exception : il est écrit, lisible, dans le journal.
    assert deliver_code("destinataire@example.com", code) is False
    assert _FakeSMTP.sent == []
    logged = capsys.readouterr().out
    assert "NON envoyé" in logged and "identifiants refusés" in logged
    assert code not in logged and password not in logged


def test_code_stays_out_of_production_logs_without_smtp(monkeypatch, capsys):
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEV_LOG_RESET_LINKS", raising=False)
    code = _random_code()
    assert deliver_code("destinataire@example.com", code) is False
    logged = capsys.readouterr().out
    assert code not in logged and "SMTP_HOST est vide" in logged
    monkeypatch.setenv("APP_ENV", "development")
    deliver_code("destinataire@example.com", code)
    assert code in capsys.readouterr().out


def test_mail_mode_is_reported_without_credentials(client, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "")
    assert mail_mode() == "logs"
    assert client.get("/auth/providers").json()["mail"] == "logs"
    monkeypatch.setenv("SMTP_HOST", "mailpit")
    assert mail_mode() == "local"
    password = _fake_smtp(monkeypatch)
    assert mail_mode() == "smtp"
    status = mail_status()
    assert "smtp.example.com:587" in status
    assert password not in status and "envoi@example.com" not in status


def test_code_is_destroyed_after_five_wrong_tries(client):
    email = f"essais-{uuid.uuid4().hex}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Essais"}, headers=ORIGIN).status_code == 200
    client.cookies.clear()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).one()
    code = issue_code(db, user)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post("/auth/verify-code", json={"email": email, "code": wrong}, headers=ORIGIN).status_code == 401
    # Le bon code ne passe plus : il a été détruit au 5e échec.
    assert client.post("/auth/verify-code", json={"email": email, "code": code}, headers=ORIGIN).status_code == 401
    fresh = issue_code(db, user)
    db.close()
    assert client.post("/auth/verify-code", json={"email": email, "code": fresh}, headers=ORIGIN).status_code == 200
    assert client.get("/auth/me").json()["email"] == email


def test_code_hash_is_bound_to_the_account():
    code = _random_code()
    assert _code_hash("compte-a", code) != _code_hash("compte-b", code)


def test_forgot_password_limits_codes_per_email(client, monkeypatch):
    monkeypatch.delenv("DISABLE_RATE_LIMIT", raising=False)
    _HITS.clear()
    email = f"flood-{uuid.uuid4().hex}@example.com"
    for _ in range(5):
        assert client.post("/auth/forgot-password", json={"email": email}).status_code == 200
    # Le compteur par adresse IP est vidé : seul celui de l'e-mail peut encore refuser.
    for key in [key for key in _HITS if key.startswith("forgot:")]:
        del _HITS[key]
    assert client.post("/auth/forgot-password", json={"email": email}).status_code == 429
    assert client.post("/auth/forgot-password", json={"email": f"autre-{uuid.uuid4().hex}@example.com"}).status_code == 200
    _HITS.clear()


def test_profile_can_be_saved_and_completes_the_onboarding(client):
    email = f"profil-{uuid.uuid4().hex}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Profil"}, headers=ORIGIN).status_code == 200
    assert client.get("/auth/me").json()["onboarding_completed"] is False
    payload = {
        "level": "debutant",
        "horizon": "long",
        "risk_tolerance": "prudent",
        "favorite_symbols": ["aapl"],
        "language": "fr",
        "onboarding_completed": True,
    }
    saved = client.put("/me/profile", json=payload, headers=ORIGIN)
    assert saved.status_code == 200
    assert saved.json()["favorite_symbols"] == ["AAPL"]
    assert client.get("/auth/me").json()["onboarding_completed"] is True
    assert client.get("/me/profile").json()["risk_tolerance"] == "prudent"
    assert client.put("/me/profile", json={**payload, "level": "inconnu"}, headers=ORIGIN).status_code == 400
    assert client.delete("/me", headers=ORIGIN).status_code == 200


def test_password_change_invalidates_the_previous_token(client):
    email = f"change-{uuid.uuid4().hex}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Change"}, headers=ORIGIN).status_code == 200
    old = client.cookies.get("mp_session")
    changed = client.post("/me/password", json={"current_password": "motdepasse", "password": "autrepass1"}, headers=ORIGIN)
    assert changed.status_code == 200
    other = TestClient(app)
    other.cookies.set("mp_session", old)
    assert other.get("/auth/me").status_code == 401
    assert client.get("/auth/me").status_code == 200


def test_login_unknown_email_takes_about_as_long_as_a_wrong_password(client):
    email = f"timing-{uuid.uuid4().hex}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Timing"}, headers=ORIGIN).status_code == 200
    client.cookies.clear()
    started = time.perf_counter()
    unknown = client.post("/auth/login", json={"email": f"no-{uuid.uuid4().hex}@example.com", "password": "motdepasse"})
    middle = time.perf_counter()
    wrong = client.post("/auth/login", json={"email": email, "password": "mauvais12"})
    finished = time.perf_counter()
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]
    assert abs((middle - started) - (finished - middle)) < 0.75


def _google(monkeypatch, profile: dict):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-test")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret-test")
    monkeypatch.setattr("app.routers.auth.httpx.post", lambda *args, **kwargs: _GoogleResponse({"access_token": "token"}))
    monkeypatch.setattr("app.routers.auth.httpx.get", lambda *args, **kwargs: _GoogleResponse(profile))


def test_google_state_email_and_no_automatic_merge(client, monkeypatch):
    google_email = f"google-{uuid.uuid4().hex}@example.com"
    verified = {"email": google_email, "email_verified": True, "sub": f"sub-{uuid.uuid4().hex}", "name": "Neuf"}
    _google(monkeypatch, verified)
    start = client.get("/auth/google/start", follow_redirects=False)
    assert start.status_code == 307
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    assert client.cookies.get("mp_oauth_state") == state
    refused = client.get("/auth/google/callback?code=abc&state=autre", follow_redirects=False)
    assert refused.status_code == 400
    unverified = TestClient(app)
    unverified.cookies.set("mp_oauth_state", state)
    monkeypatch.setattr(
        "app.routers.auth.httpx.get",
        lambda *args, **kwargs: _GoogleResponse({**verified, "email_verified": False}),
    )
    assert unverified.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False).status_code == 400
    monkeypatch.setattr("app.routers.auth.httpx.get", lambda *args, **kwargs: _GoogleResponse(verified))
    created = client.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert created.status_code == 307
    db = SessionLocal()
    row = db.query(User).filter(User.email == google_email).one()
    assert row.google_sub == verified["sub"]
    db.close()

    email = f"deja-{uuid.uuid4().hex}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": "motdepasse", "display_name": "Deja"}, headers=ORIGIN).status_code == 200
    again = client.get("/auth/google/start", follow_redirects=False)
    second = parse_qs(urlparse(again.headers["location"]).query)["state"][0]
    monkeypatch.setattr(
        "app.routers.auth.httpx.get",
        lambda *args, **kwargs: _GoogleResponse({"email": email, "email_verified": True, "sub": "sub-autre", "name": "Deja"}),
    )
    merged = client.get(f"/auth/google/callback?code=abc&state={second}", follow_redirects=False)
    assert merged.status_code == 409
    db = SessionLocal()
    kept = db.query(User).filter(User.email == email).one()
    assert kept.google_sub is None
    db.close()
