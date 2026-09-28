"""Independent address and target limits for public recovery endpoints."""

import time

from neodermo.auth.passwords import hash_new_password
from neodermo.extensions import db
from neodermo.models import User

ORIGIN = {"Origin": "http://localhost"}
PASSWORD = "A new example passphrase 2026!"


def forgot(client, email, *, remote="127.0.0.1", forwarded=None):
    headers = dict(ORIGIN)
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    return client.post(
        "/api/auth/forgot-password", json={"email": email}, headers=headers,
        environ_overrides={"REMOTE_ADDR": remote},
    )


def reset(client, token, *, remote="127.0.0.1", forwarded=None):
    headers = dict(ORIGIN)
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    return client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": PASSWORD},
        headers=headers, environ_overrides={"REMOTE_ADDR": remote},
    )


def test_forgot_known_and_unknown_email_limits_are_equal(migrated_file_app, monkeypatch):
    app = migrated_file_app
    app.config["RECOVERY_RESPONSE_FLOOR_SECONDS"] = 0
    outbox = []
    monkeypatch.setattr("neodermo.auth.mail.send_mail", outbox.append)
    with app.app_context():
        db.session.add(User(
            email="operator@example.com", password_hash=hash_new_password(PASSWORD),
        ))
        db.session.commit()
    client = app.test_client()
    for email in ("operator@example.com", "missing@example.com"):
        for index in range(3):
            assert forgot(client, email, remote=f"127.0.0.{index + 1}").status_code == 202
        blocked = forgot(client, email, remote="127.0.0.4")
        assert blocked.status_code == 429
        assert blocked.json == {"error": {"code": "rate_limited"}}
        assert int(blocked.headers["Retry-After"]) > 0
    assert len(outbox) == 3


def test_forgot_address_limit_spans_emails_and_malformed_requests(migrated_file_app):
    app = migrated_file_app
    app.config["RECOVERY_RESPONSE_FLOOR_SECONDS"] = 0
    client = app.test_client()
    for index in range(9):
        assert forgot(client, f"missing{index}@example.com").status_code == 202
    assert client.post(
        "/api/auth/forgot-password", data="{bad", content_type="application/json",
        headers=ORIGIN,
    ).status_code == 400
    blocked = forgot(client, "another@example.com")
    assert blocked.status_code == 429
    assert blocked.headers["Cache-Control"] == "no-store"
    assert forgot(client, "another@example.com", remote="127.0.0.2").status_code == 202


def test_reset_token_limit_spans_addresses_and_address_limit_ignores_forwarding(
    migrated_file_app
):
    app = migrated_file_app
    client = app.test_client()
    token = "A" * 43
    for index in range(5):
        assert reset(client, token, remote=f"127.0.0.{index + 1}").status_code == 400
    blocked = reset(client, token, remote="127.0.0.6")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert reset(client, "B" * 43, remote="127.0.0.6").status_code == 400

    for index in range(20):
        response = client.post(
            "/api/auth/reset-password", data="{bad", content_type="application/json",
            headers={**ORIGIN, "X-Forwarded-For": f"192.0.2.{index + 1}"},
            environ_overrides={"REMOTE_ADDR": "127.0.0.20"},
        )
        assert response.status_code == 400
    assert reset(client, "C" * 43, remote="127.0.0.20", forwarded="192.0.2.99").status_code == 429

    limiter = next(iter(app.extensions["limiter"]))
    for key in list(limiter.storage.expirations):
        limiter.storage.expirations[key] = time.time() - 1
    assert reset(client, token, remote="127.0.0.20").status_code == 400
