"""Exercise the auth contract through independent browsers and a migrated database."""

import sqlite3
from datetime import timedelta

import pytest
from flask import jsonify
from sqlalchemy import select

from neodermo.auth.passwords import hash_new_password
from neodermo.auth.sessions import COOKIE_NAME, auth_now, token_digest
from neodermo.extensions import db
from neodermo.models import AuthSession, User

EMAIL = "operator@example.com"
PASSWORD = "A long example passphrase 2026!"
ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture
def operator_app(migrated_file_app):
    with migrated_file_app.app_context():
        user = User(email=EMAIL, password_hash=hash_new_password(PASSWORD))
        db.session.add(user)
        db.session.commit()
    return migrated_file_app


def login(client, *, email=EMAIL, password=PASSWORD, origin=ORIGIN):
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}, headers=origin,
    )


def test_login_status_logout_and_copied_cookie_revocation(operator_app):
    browser = operator_app.test_client()
    assert browser.get("/api/auth/session").json == {"authenticated": False}
    response = login(browser)
    assert response.status_code == 200
    assert response.json.keys() == {"authenticated", "csrf_token"}
    assert response.json["authenticated"] is True
    assert response.headers["Cache-Control"] == "no-store"
    cookie = browser.get_cookie(COOKIE_NAME).value
    assert response.headers["Set-Cookie"].startswith(f"{COOKIE_NAME}=")
    for flag in ("HttpOnly", "SameSite=Lax", "Path=/", "Max-Age=43200"):
        assert flag in response.headers["Set-Cookie"]
    assert "Domain=" not in response.headers["Set-Cookie"]
    assert "Secure" not in response.headers["Set-Cookie"]  # isolated loopback test app

    with operator_app.app_context():
        row = db.session.scalar(select(AuthSession))
        assert row.token_digest == token_digest(cookie)
        assert cookie not in row.token_digest
        assert row.csrf_secret == response.json["csrf_token"]

    status = browser.get("/api/auth/session")
    assert status.status_code == 200
    assert status.json == {
        "authenticated": True,
        "user": {"id": row.user_id, "email": EMAIL},
        "csrf_token": response.json["csrf_token"],
    }
    copied_browser = operator_app.test_client()
    copied_browser.set_cookie(COOKIE_NAME, cookie)
    assert copied_browser.get("/api/auth/session").json["authenticated"] is True

    logout = browser.post(
        "/api/auth/logout", headers={**ORIGIN, "X-CSRF-Token": status.json["csrf_token"]},
    )
    assert logout.status_code == 204
    assert logout.headers["Cache-Control"] == "no-store"
    assert browser.get_cookie(COOKIE_NAME) is None
    assert copied_browser.get("/api/auth/session").json == {"authenticated": False}
    with operator_app.app_context():
        assert db.session.scalar(select(AuthSession)) is None


def test_relogin_rotates_only_presented_session(operator_app):
    first = operator_app.test_client()
    second = operator_app.test_client()
    assert login(first).status_code == 200
    old = first.get_cookie(COOKIE_NAME).value
    assert login(second).status_code == 200
    independent = second.get_cookie(COOKIE_NAME).value
    replacement = login(first)
    assert replacement.status_code == 200
    new = first.get_cookie(COOKIE_NAME).value
    assert len({old, independent, new}) == 3
    with operator_app.app_context():
        digests = set(db.session.scalars(select(AuthSession.token_digest)))
    assert digests == {token_digest(independent), token_digest(new)}
    assert second.get("/api/auth/session").json["authenticated"] is True


def test_failed_login_does_not_replace_existing_session(operator_app):
    browser = operator_app.test_client()
    assert login(browser).status_code == 200
    old = browser.get_cookie(COOKIE_NAME).value
    for email, password in ((EMAIL, "Wrong example passphrase 2026!"),
                            ("missing@example.com", PASSWORD)):
        response = login(browser, email=email, password=password)
        assert response.status_code == 401
        assert response.json == {"error": {"code": "invalid_credentials"}}
        assert response.headers["Cache-Control"] == "no-store"
        assert browser.get_cookie(COOKIE_NAME).value == old
    assert browser.get("/api/auth/session").json["authenticated"] is True


def test_session_survives_app_restart(operator_app, file_app_factory):
    browser = operator_app.test_client()
    assert login(browser).status_code == 200
    cookie = browser.get_cookie(COOKIE_NAME).value
    restarted = file_app_factory()
    new_browser = restarted.test_client()
    new_browser.set_cookie(COOKIE_NAME, cookie)
    assert new_browser.get("/api/auth/session").json["authenticated"] is True


def test_session_status_is_bound_to_cookie_user(operator_app):
    other_email = "other@example.com"
    with operator_app.app_context():
        other = User(email=other_email, password_hash=hash_new_password(PASSWORD))
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    first = operator_app.test_client()
    second = operator_app.test_client()
    assert login(first).status_code == 200
    assert login(second, email=other_email).status_code == 200
    assert first.get("/api/auth/session").json["user"]["email"] == EMAIL
    assert second.get("/api/auth/session").json["user"] == {
        "id": other_id, "email": other_email,
    }
    assert second.get("/api/auth/session?email=" + EMAIL).status_code == 400


def test_expired_forged_and_deleted_user_sessions_are_rejected(operator_app):
    browser = operator_app.test_client()
    now = None
    with operator_app.app_context():
        now = auth_now()
    operator_app.config["AUTH_NOW"] = lambda: now
    assert login(browser).status_code == 200
    cookie = browser.get_cookie(COOKIE_NAME).value
    operator_app.config["AUTH_NOW"] = lambda: now + timedelta(seconds=43200)
    assert browser.get("/api/auth/session").json == {"authenticated": False}
    assert browser.get_cookie(COOKIE_NAME) is None

    browser.set_cookie(COOKIE_NAME, "A" * 43)
    assert browser.get("/api/auth/session").json == {"authenticated": False}
    browser.set_cookie(COOKIE_NAME, cookie)
    operator_app.config["AUTH_NOW"] = lambda: now
    with operator_app.app_context():
        user = db.session.scalar(select(User))
        db.session.delete(user)
        db.session.commit()
    assert browser.get("/api/auth/session").json == {"authenticated": False}


def test_orphaned_session_does_not_authenticate(operator_app):
    browser = operator_app.test_client()
    assert login(browser).status_code == 200
    with operator_app.app_context():
        database_path = db.engine.url.database
        user_id = db.session.scalar(select(User.id))
        db.session.remove()
    # Simulate database corruption from a writer that bypassed SQLite's FK setting.
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    with operator_app.app_context():
        assert db.session.scalar(select(AuthSession.id)) is not None
    assert browser.get("/api/auth/session").json == {"authenticated": False}


def test_api_protection_origin_csrf_and_default_route(operator_app):
    @operator_app.get("/api/probe")
    def probe():
        return jsonify({"private": True})

    @operator_app.post("/api/probe")
    def mutate_probe():
        return jsonify({"changed": True})

    browser = operator_app.test_client()
    assert browser.get("/api/probe").status_code == 401
    assert browser.get("/api/health").status_code == 200
    for bad_origin in ({}, {"Origin": "null"}, {"Origin": "http://evil.test"},
                       {"Origin": "http://localhost:5000"}):
        assert login(browser, origin=bad_origin).status_code == 403
    assert login(browser).status_code == 200
    csrf = browser.get("/api/auth/session").json["csrf_token"]
    assert browser.get("/api/probe").json == {"private": True}
    assert browser.post("/api/probe", headers=ORIGIN).status_code == 403
    assert browser.post(
        "/api/probe", headers={**ORIGIN, "X-CSRF-Token": "wrong"}
    ).status_code == 403
    assert browser.post(
        "/api/probe", headers={"X-CSRF-Token": csrf}
    ).status_code == 403
    response = browser.post(
        "/api/probe", headers={**ORIGIN, "X-CSRF-Token": csrf}
    )
    assert response.json == {"changed": True}
    assert response.headers["Cache-Control"] == "no-store"
    assert operator_app.test_client().open("/api/probe", method="OPTIONS").status_code == 401


@pytest.mark.parametrize("body", [
    '{"email":"operator@example.com","password":"ok","other":1}',
    '{"email":"operator@example.com","email":"other@example.com","password":"ok"}',
    '{"email":3,"password":"ok"}',
    "[]", "null", "{invalid}",
])
def test_login_rejects_malformed_or_ambiguous_json(operator_app, body):
    response = operator_app.test_client().post(
        "/api/auth/login", data=body, content_type="application/json", headers=ORIGIN,
    )
    assert response.status_code == 400
    assert response.json == {"error": {"code": "invalid_request"}}
    assert response.headers["Cache-Control"] == "no-store"


def test_login_rejects_oversize_and_non_json(operator_app):
    browser = operator_app.test_client()
    assert browser.post(
        "/api/auth/login", data="a" * 8193,
        content_type="application/json", headers=ORIGIN,
    ).status_code == 400
    assert browser.post(
        "/api/auth/login", data="email=x&password=y", headers=ORIGIN,
    ).status_code == 400
    assert browser.get("/api/auth/session?user_id=other").status_code == 400


def test_logout_requires_origin_and_csrf(operator_app):
    browser = operator_app.test_client()
    assert login(browser).status_code == 200
    cookie = browser.get_cookie(COOKIE_NAME).value
    assert browser.post("/api/auth/logout", headers=ORIGIN).status_code == 403
    assert browser.post("/api/auth/logout", headers={"Origin": "null"}).status_code == 403
    assert browser.get_cookie(COOKIE_NAME).value == cookie
    assert browser.get("/api/auth/session").json["authenticated"] is True


def test_secure_cookie_on_https_configuration(operator_app):
    operator_app.config["AUTH_COOKIE_SECURE"] = True
    response = login(operator_app.test_client())
    assert response.status_code == 200
    assert "Secure" in response.headers["Set-Cookie"]
