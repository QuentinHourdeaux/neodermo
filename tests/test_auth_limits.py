"""Rate-limit behavior at the public login boundary."""

import time

import pytest

from neodermo import create_app
from neodermo.auth.passwords import hash_new_password
from neodermo.extensions import db
from neodermo.models import User

EMAIL = "operator@example.com"
PASSWORD = "A long example passphrase 2026!"
WRONG_PASSWORD = "A wrong example passphrase 2026!"
ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture
def operator_app(migrated_file_app):
    with migrated_file_app.app_context():
        db.session.add(User(email=EMAIL, password_hash=hash_new_password(PASSWORD)))
        db.session.commit()
    return migrated_file_app


def attempt(client, email, *, remote="127.0.0.1", forwarded=None):
    headers = dict(ORIGIN)
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": WRONG_PASSWORD},
        headers=headers,
        environ_overrides={"REMOTE_ADDR": remote},
    )


def malformed(client, *, remote="127.0.0.1", forwarded=None):
    headers = dict(ORIGIN)
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    return client.post(
        "/api/auth/login", data="{bad", content_type="application/json",
        headers=headers, environ_overrides={"REMOTE_ADDR": remote},
    )


def test_known_and_unknown_accounts_have_the_same_limit(operator_app):
    client = operator_app.test_client()
    for email in (EMAIL, "missing@example.com"):
        for _ in range(5):
            response = attempt(client, email)
            assert response.status_code == 401
            assert response.json == {"error": {"code": "invalid_credentials"}}
        blocked = attempt(client, email)
        assert blocked.status_code == 429
        assert blocked.json == {"error": {"code": "rate_limited"}}
        assert int(blocked.headers["Retry-After"]) > 0
        assert blocked.headers["Cache-Control"] == "no-store"


def test_email_bucket_is_shared_across_addresses_but_other_email_is_free(operator_app):
    client = operator_app.test_client()
    for remote in ("127.0.0.1",) * 3 + ("127.0.0.2",) * 2:
        assert attempt(client, EMAIL, remote=remote).status_code == 401
    assert attempt(client, EMAIL, remote="127.0.0.3").status_code == 429
    assert attempt(client, "other@example.com", remote="127.0.0.3").status_code == 401


def test_email_bucket_uses_normalized_address(operator_app):
    client = operator_app.test_client()
    for spelling in ("Operator@Example.com", " operator@example.com ", EMAIL,
                     "OPERATOR@example.com", "operator@EXAMPLE.COM"):
        assert attempt(client, spelling).status_code == 401
    assert attempt(client, EMAIL).status_code == 429


def test_address_bucket_spans_different_email_addresses(operator_app):
    client = operator_app.test_client()
    for index in range(30):
        assert attempt(client, f"person{index}@example.com").status_code == 401
    assert attempt(client, "another@example.com").status_code == 429


def test_address_bucket_counts_malformed_requests_and_ignores_forwarded_headers():
    app = create_app("testing")
    client = app.test_client()
    for index in range(30):
        assert malformed(client, forwarded=f"192.0.2.{index + 1}").status_code == 400
    blocked = malformed(client, forwarded="192.0.2.99")
    assert blocked.status_code == 429
    assert blocked.json == {"error": {"code": "rate_limited"}}
    assert int(blocked.headers["Retry-After"]) > 0
    assert malformed(client, remote="127.0.0.2").status_code == 400
    # A new app has an independent memory store, as a process restart would.
    assert malformed(create_app("testing").test_client()).status_code == 400
    limiter = next(iter(app.extensions["limiter"]))
    for key in list(limiter.storage.expirations):
        limiter.storage.expirations[key] = time.time() - 1
    assert malformed(client).status_code == 400


def test_blocked_login_never_runs_password_verification(operator_app, monkeypatch):
    client = operator_app.test_client()
    for _ in range(5):
        assert attempt(client, EMAIL).status_code == 401

    def fail_if_called(*_args):
        raise AssertionError("password verification should not run")

    monkeypatch.setattr("neodermo.api.auth.issue_session", fail_if_called)
    assert attempt(client, EMAIL).status_code == 429


def test_limit_recovers_after_window_expires(operator_app):
    client = operator_app.test_client()
    for _ in range(5):
        assert attempt(client, EMAIL).status_code == 401
    assert attempt(client, EMAIL).status_code == 429

    limiter = next(iter(operator_app.extensions["limiter"]))
    # Advance the in-memory fixed-window store without sleeping for a minute.
    for key in list(limiter.storage.expirations):
        limiter.storage.expirations[key] = time.time() - 1

    assert attempt(client, EMAIL).status_code == 401
