"""Recovery behavior through the HTTP API and a file-backed SQLite database."""

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from neodermo.auth.passwords import hash_new_password, verify_password
from neodermo.auth.sessions import auth_now, token_digest
from neodermo.extensions import db
from neodermo.models import AuthSession, PasswordResetToken, User

EMAIL = "operator@example.com"
OTHER_EMAIL = "other@example.com"
PASSWORD = "A long example passphrase 2026!"
NEW_PASSWORD = "A different secure phrase 2026!"
ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture
def recovery_app(migrated_file_app, monkeypatch):
    with migrated_file_app.app_context():
        db.session.add_all([
            User(email=EMAIL, password_hash=hash_new_password(PASSWORD)),
            User(email=OTHER_EMAIL, password_hash=hash_new_password(PASSWORD)),
        ])
        db.session.commit()
    migrated_file_app.config["RECOVERY_RESPONSE_FLOOR_SECONDS"] = 0
    outbox = []
    monkeypatch.setattr("neodermo.auth.mail.send_mail", outbox.append)
    return migrated_file_app, outbox


def forgot(client, email=EMAIL, *, remote="127.0.0.1"):
    return client.post(
        "/api/auth/forgot-password", json={"email": email}, headers=ORIGIN,
        environ_overrides={"REMOTE_ADDR": remote},
    )


def reset(client, token, password=NEW_PASSWORD, *, remote="127.0.0.1"):
    return client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": password}, headers=ORIGIN,
        environ_overrides={"REMOTE_ADDR": remote},
    )


def delivered_token(message):
    match = re.search(r"^token: ([A-Za-z0-9_-]{43})$", message.get_content(), re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_known_recovery_mails_distinct_usable_tokens_without_changing_account(
    recovery_app, caplog
):
    app, outbox = recovery_app
    client = app.test_client()
    assert client.post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=ORIGIN,
    ).status_code == 200
    with app.app_context():
        original_hash = db.session.scalar(select(User.password_hash).where(User.email == EMAIL))

    for _ in range(2):
        response = forgot(client)
        assert response.status_code == 202
        assert response.json == {
            "message": "If the account exists, recovery instructions will be sent."
        }
        assert response.headers["Cache-Control"] == "no-store"
    assert len(outbox) == 2
    assert all(message["To"] == EMAIL for message in outbox)
    assert all("/api/auth/reset-password" in message.get_content() for message in outbox)
    assert all("http" not in message.get_content() for message in outbox)
    tokens = [delivered_token(message) for message in outbox]
    assert tokens[0] != tokens[1]
    assert all(token not in caplog.text for token in tokens)
    assert PASSWORD not in caplog.text

    with app.app_context():
        rows = list(db.session.scalars(select(PasswordResetToken)))
        assert {row.token_digest for row in rows} == {token_digest(token) for token in tokens}
        assert all(row.expires_at - row.created_at == timedelta(minutes=30) for row in rows)
        assert db.session.scalar(
            select(User.password_hash).where(User.email == EMAIL)
        ) == original_hash
        assert db.session.scalar(select(AuthSession.id)) is not None
    assert client.get("/api/auth/session").json["authenticated"] is True


def test_unknown_recovery_has_identical_public_response_and_no_email_or_token(recovery_app):
    app, outbox = recovery_app
    client = app.test_client()
    known = forgot(client)
    unknown = forgot(client, "missing@example.com")
    assert unknown.status_code == known.status_code == 202
    assert unknown.json == known.json
    assert unknown.headers["Cache-Control"] == "no-store"
    assert len(outbox) == 1
    with app.app_context():
        assert len(list(db.session.scalars(select(PasswordResetToken)))) == 1


def test_delivery_failure_leaves_no_usable_token_and_does_not_expose_address(
    recovery_app, monkeypatch, caplog
):
    app, _outbox = recovery_app

    def fail(_message):
        raise OSError("private SMTP detail")

    monkeypatch.setattr("neodermo.auth.mail.send_mail", fail)
    response = forgot(app.test_client())
    assert response.status_code == 202
    assert response.json == {
        "message": "If the account exists, recovery instructions will be sent."
    }
    with app.app_context():
        assert db.session.scalar(select(PasswordResetToken)) is None
    assert "private SMTP detail" not in caplog.text
    assert EMAIL not in caplog.text


def test_storage_failure_after_mail_acceptance_leaves_no_usable_token(
    recovery_app, monkeypatch
):
    app, outbox = recovery_app
    with app.app_context():
        engine = db.engine
        with monkeypatch.context() as patch:
            def locked():
                raise OperationalError("BEGIN IMMEDIATE", None, Exception("database is locked"))

            patch.setattr(engine, "begin", locked)
            response = forgot(app.test_client())
    assert response.status_code == 202
    assert len(outbox) == 1
    with app.app_context():
        assert db.session.scalar(select(PasswordResetToken)) is None


def test_recovery_response_floor_covers_both_normal_paths(recovery_app, monkeypatch):
    app, outbox = recovery_app
    clock = [100.0]
    durations = []

    def monotonic():
        return clock[0]

    def sleep(seconds):
        clock[0] += seconds

    def send(message):
        outbox.append(message)
        clock[0] += 0.15

    app.config.update(
        RECOVERY_RESPONSE_FLOOR_SECONDS=0.5,
        RECOVERY_MONOTONIC=monotonic,
        RECOVERY_SLEEP=sleep,
    )
    monkeypatch.setattr("neodermo.auth.mail.send_mail", send)
    client = app.test_client()
    for index in range(4):
        started = clock[0]
        email = EMAIL if index % 2 == 0 else "missing@example.com"
        assert forgot(client, email, remote=f"127.0.0.{index + 1}").status_code == 202
        durations.append(clock[0] - started)
    assert durations == [0.5] * 4


def test_reset_is_one_time_and_revokes_only_bound_users_credentials(recovery_app):
    app, outbox = recovery_app
    first = app.test_client()
    second = app.test_client()
    other = app.test_client()
    for client, email in ((first, EMAIL), (second, EMAIL), (other, OTHER_EMAIL)):
        assert client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}, headers=ORIGIN,
        ).status_code == 200
    assert forgot(first).status_code == 202
    token = delivered_token(outbox[-1])
    assert forgot(first).status_code == 202
    assert forgot(other, OTHER_EMAIL).status_code == 202
    with app.app_context():
        other_id = db.session.scalar(select(User.id).where(User.email == OTHER_EMAIL))
        other_tokens_before = set(db.session.scalars(
            select(PasswordResetToken.token_digest).where(PasswordResetToken.user_id == other_id)
        ))

    response = reset(first, token)
    assert response.status_code == 204
    assert response.data == b""
    assert len(outbox) == 4  # three recovery notices and one confirmation
    assert outbox[-1]["Subject"] == "Neodermo password changed"
    assert token not in outbox[-1].get_content()
    assert first.get("/api/auth/session").json == {"authenticated": False}
    assert second.get("/api/auth/session").json == {"authenticated": False}
    assert other.get("/api/auth/session").json["authenticated"] is True
    assert reset(first, token).json == {"error": {"code": "invalid_reset_token"}}

    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == EMAIL))
        assert not verify_password(user.password_hash, PASSWORD)
        assert verify_password(user.password_hash, NEW_PASSWORD)
        assert db.session.scalar(
            select(PasswordResetToken.id).where(PasswordResetToken.user_id == user.id)
        ) is None
        assert db.session.scalar(
            select(AuthSession.id).where(AuthSession.user_id == user.id)
        ) is None
        assert set(db.session.scalars(
            select(PasswordResetToken.token_digest).where(PasswordResetToken.user_id == other_id)
        )) == other_tokens_before
    assert first.post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=ORIGIN,
    ).status_code == 401
    assert first.post(
        "/api/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD}, headers=ORIGIN,
    ).status_code == 200


def test_invalid_expired_and_replayed_tokens_share_one_error(recovery_app):
    app, outbox = recovery_app
    client = app.test_client()
    malformed = reset(client, "bad")
    unknown = reset(client, "A" * 43)
    assert forgot(client).status_code == 202
    token = delivered_token(outbox[0])
    with app.app_context():
        now = auth_now()
    app.config["AUTH_NOW"] = lambda: now + timedelta(minutes=31)
    expired = reset(client, token)
    for response in (malformed, unknown, expired):
        assert response.status_code == 400
        assert response.json == {"error": {"code": "invalid_reset_token"}}
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == EMAIL))
        assert verify_password(user.password_hash, PASSWORD)


def test_confirmation_delivery_failure_does_not_undo_reset(recovery_app, monkeypatch):
    app, outbox = recovery_app
    client = app.test_client()
    assert forgot(client).status_code == 202
    token = delivered_token(outbox[0])

    def fail(_message):
        raise OSError("capture inbox is unavailable")

    monkeypatch.setattr("neodermo.auth.mail.send_mail", fail)
    assert reset(client, token).status_code == 204
    assert reset(client, token).status_code == 400
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == EMAIL))
        assert verify_password(user.password_hash, NEW_PASSWORD)


def test_reset_rejects_weak_password_without_consuming_token(recovery_app):
    app, outbox = recovery_app
    client = app.test_client()
    assert forgot(client).status_code == 202
    token = delivered_token(outbox[0])
    invalid = reset(client, token, "password")
    assert invalid.status_code == 400
    assert invalid.json == {"error": {"code": "invalid_request"}}
    assert reset(client, token).status_code == 204


def test_storage_contention_returns_retryable_error_without_consuming_token(
    recovery_app, monkeypatch
):
    app, outbox = recovery_app
    client = app.test_client()
    assert forgot(client).status_code == 202
    token = delivered_token(outbox[0])
    with app.app_context():
        engine = db.engine
        with monkeypatch.context() as patch:
            def locked():
                raise OperationalError("BEGIN IMMEDIATE", None, Exception("database is locked"))

            patch.setattr(engine, "begin", locked)
            response = reset(client, token)
        assert response.status_code == 503
        assert response.json == {"error": {"code": "temporarily_unavailable"}}
        assert db.session.scalar(select(PasswordResetToken.token_digest)) == token_digest(token)
    assert reset(client, token).status_code == 204


def test_login_storage_contention_returns_retryable_error(recovery_app, monkeypatch):
    app, _outbox = recovery_app
    with app.app_context():
        engine = db.engine
        with monkeypatch.context() as patch:
            def locked():
                raise OperationalError("BEGIN IMMEDIATE", None, Exception("database is locked"))

            patch.setattr(engine, "begin", locked)
            response = app.test_client().post(
                "/api/auth/login", json={"email": EMAIL, "password": PASSWORD},
                headers=ORIGIN,
            )
        assert response.status_code == 503
        assert response.json == {"error": {"code": "temporarily_unavailable"}}
        assert db.session.scalar(select(AuthSession)) is None


def test_token_is_rechecked_for_expiry_inside_write_lock(recovery_app, monkeypatch):
    app, outbox = recovery_app
    client = app.test_client()
    assert forgot(client).status_code == 202
    token = delivered_token(outbox[0])
    with app.app_context():
        now = auth_now()
    original_hash = hash_new_password

    def expire_after_hash(password):
        result = original_hash(password)
        app.config["AUTH_NOW"] = lambda: now + timedelta(minutes=31)
        return result

    monkeypatch.setattr("neodermo.auth.recovery.hash_new_password", expire_after_hash)
    response = reset(client, token)
    assert response.status_code == 400
    assert response.json == {"error": {"code": "invalid_reset_token"}}
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == EMAIL))
        assert verify_password(user.password_hash, PASSWORD)


@pytest.mark.parametrize("path,body", [
    ("forgot-password", '{"email":"operator@example.com","other":"x"}'),
    ("forgot-password", '["operator@example.com"]'),
    pytest.param(
        "forgot-password", '{"email":' + '1' * 5000 + '}', id="forgot-large-json-integer"
    ),
    ("reset-password", '{"token":"x","new_password":"x","other":"x"}'),
    ("reset-password", '{"token":4,"new_password":"x"}'),
    pytest.param(
        "reset-password", '{"token":' + '1' * 5000 + ',"new_password":"x"}',
        id="reset-large-json-integer",
    ),
])
def test_recovery_rejects_unexpected_json_fields_and_types(recovery_app, path, body):
    app, outbox = recovery_app
    response = app.test_client().post(
        f"/api/auth/{path}", data=body, content_type="application/json", headers=ORIGIN,
    )
    assert response.status_code == 400
    assert response.json == {"error": {"code": "invalid_request"}}
    assert outbox == []


def test_concurrent_reset_has_exactly_one_winner(recovery_app, file_app_factory, monkeypatch):
    app, outbox = recovery_app
    assert forgot(app.test_client()).status_code == 202
    token = delivered_token(outbox[0])
    first_app, second_app = file_app_factory(), file_app_factory()
    barrier = threading.Barrier(2)
    original_hash = hash_new_password

    def hash_at_barrier(password):
        result = original_hash(password)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr("neodermo.auth.recovery.hash_new_password", hash_at_barrier)

    def submit(worker_app):
        return reset(worker_app.test_client(), token).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, (first_app, second_app)))
    assert sorted(statuses) == [204, 400]
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == EMAIL))
        assert verify_password(user.password_hash, NEW_PASSWORD)
        assert db.session.scalar(select(PasswordResetToken)) is None


def test_login_racing_reset_cannot_issue_old_password_session(
    recovery_app, file_app_factory, monkeypatch
):
    app, outbox = recovery_app
    assert forgot(app.test_client()).status_code == 202
    token = delivered_token(outbox[0])
    login_app = file_app_factory()
    ready = threading.Event()
    resume = threading.Event()
    from neodermo.auth import sessions
    original_verify = sessions.verify_password

    def pause_after_verification(password_hash, password):
        matched = original_verify(password_hash, password)
        ready.set()
        assert resume.wait(timeout=5)
        return matched

    monkeypatch.setattr("neodermo.auth.sessions.verify_password", pause_after_verification)

    def login_old_password():
        return login_app.test_client().post(
            "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=ORIGIN,
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(login_old_password)
        assert ready.wait(timeout=5)
        assert reset(app.test_client(), token).status_code == 204
        resume.set()
        result = pending.result(timeout=5)
    assert result.status_code == 401
    with app.app_context():
        assert db.session.scalar(select(AuthSession)) is None


def test_recovery_racing_reset_cannot_activate_a_pre_reset_token(
    recovery_app, file_app_factory, monkeypatch
):
    app, outbox = recovery_app
    assert forgot(app.test_client()).status_code == 202
    first_token = delivered_token(outbox[0])
    pending_app = file_app_factory()
    pending_app.config["RECOVERY_RESPONSE_FLOOR_SECONDS"] = 0
    ready = threading.Event()
    resume = threading.Event()

    def pause_recovery_mail(message):
        if message["Subject"] == "Neodermo password reset":
            ready.set()
            assert resume.wait(timeout=5)
        outbox.append(message)

    monkeypatch.setattr("neodermo.auth.mail.send_mail", pause_recovery_mail)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(forgot, pending_app.test_client())
        assert ready.wait(timeout=5)
        assert reset(app.test_client(), first_token).status_code == 204
        resume.set()
        assert pending.result(timeout=5).status_code == 202
    with app.app_context():
        assert db.session.scalar(select(PasswordResetToken)) is None
