"""Expired credential cleanup keeps live access and is safe to repeat."""

import hashlib
from datetime import timedelta

from sqlalchemy import select

from neodermo.extensions import db
from neodermo.models import AuthSession, PasswordResetToken, User
from neodermo.models.types import utc_now


def _credential(model, user_id, name, created_at, expires_at):
    values = {
        "user_id": user_id,
        "token_digest": hashlib.sha256(name.encode()).hexdigest(),
        "created_at": created_at,
        "expires_at": expires_at,
    }
    if model is AuthSession:
        values["csrf_secret"] = "c" * 43
    return model(**values)


def test_cleanup_deletes_only_expired_credentials(migrated_file_app, monkeypatch):
    cutoff = utc_now().replace(microsecond=0)
    monkeypatch.setattr("neodermo.auth.cleanup.utc_now", lambda: cutoff)
    with migrated_file_app.app_context():
        user = User(email="fictional@example.com", password_hash="fictional hash")
        db.session.add(user)
        db.session.flush()
        for model in (AuthSession, PasswordResetToken):
            db.session.add_all([
                _credential(model, user.id, f"{model.__name__}-old",
                            cutoff - timedelta(hours=2), cutoff - timedelta(hours=1)),
                _credential(model, user.id, f"{model.__name__}-boundary",
                            cutoff - timedelta(hours=1), cutoff),
                _credential(model, user.id, f"{model.__name__}-live",
                            cutoff, cutoff + timedelta(hours=1)),
            ])
        db.session.commit()
        user_id = user.id

    runner = migrated_file_app.test_cli_runner()
    first = runner.invoke(args=["auth", "cleanup"])
    assert first.exit_code == 0, first.output
    assert first.output.strip() == "Deleted 2 expired sessions and 2 expired reset tokens."
    second = runner.invoke(args=["auth", "cleanup"])
    assert second.exit_code == 0, second.output
    assert second.output.strip() == "Deleted 0 expired sessions and 0 expired reset tokens."

    with migrated_file_app.app_context():
        assert db.session.get(User, user_id) is not None
        for model in (AuthSession, PasswordResetToken):
            rows = db.session.scalars(select(model)).all()
            assert len(rows) == 1
            assert rows[0].expires_at == cutoff + timedelta(hours=1)


def test_cleanup_missing_migrations_has_safe_error(app):
    result = app.test_cli_runner().invoke(args=["auth", "cleanup"])
    assert result.exit_code != 0
    assert "Check database availability and migrations" in result.output
    assert "sqlite" not in result.output.lower()
