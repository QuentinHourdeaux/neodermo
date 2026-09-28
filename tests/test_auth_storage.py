"""Additive auth migration, database invariants, and persisted credentials."""

import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import upgrade
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from neodermo import PROJECT_ROOT
from neodermo.extensions import db
from neodermo.models import (
    Assessment, AuthSession, Establishment, PasswordResetToken, Patient,
    PatientStay, User, Wound,
)

BASE_REVISION = "20260927T101720610587Z"
AUTH_REVISION = "20260928T114743281689Z"


@pytest.mark.parametrize("populated", [False, True])
def test_auth_migration_preserves_domain_data_and_matches_models(file_app_factory, populated):
    app = file_app_factory()
    with app.app_context():
        upgrade(directory=str(PROJECT_ROOT / "migrations"), revision=BASE_REVISION)
        if populated:
            patient = Patient(name="Fictional migration patient")
            stay = PatientStay(
                patient=patient, establishment=Establishment(name="Fictional clinic"),
                start_date=date(2026, 1, 1),
            )
            assessment = Assessment(
                wound=Wound(patient=patient), observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
            db.session.add_all([stay, assessment])
            db.session.commit()
        tables = ("establishments", "patients", "patient_stays", "wounds", "assessments")
        before = {table: db.session.execute(text(f"SELECT * FROM {table}")).all() for table in tables}
        db.session.remove()

        upgrade(directory=str(PROJECT_ROOT / "migrations"))
        upgrade(directory=str(PROJECT_ROOT / "migrations"))

        assert {table: db.session.execute(text(f"SELECT * FROM {table}")).all() for table in tables} == before
        assert db.session.scalar(text("SELECT version_num FROM alembic_version")) == AUTH_REVISION
        assert set(inspect(db.engine).get_table_names()) == set(tables) | {
            "alembic_version", "users", "sessions", "password_reset_tokens",
        }
        with db.engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), db.metadata) == []


def _credential(model, user_id, token="fictional random token"):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    values = dict(
        user_id=user_id, token_digest=hashlib.sha256(token.encode()).hexdigest(),
        created_at=now, expires_at=now + timedelta(hours=1),
    )
    if model is AuthSession:
        values["csrf_secret"] = "c" * 43
    return model(**values)


@pytest.mark.parametrize("model", [AuthSession, PasswordResetToken])
def test_credential_storage_constraints_and_user_cascade(migrated_file_app, model):
    with migrated_file_app.app_context():
        user = User(email=" DEMO@Example.com ", password_hash="fictional hash fixture")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        token = "fictional raw token must not be stored"
        row = _credential(model, user_id, token)
        db.session.add(row)
        db.session.commit()
        row_id = row.id
        db.session.expire_all()
        saved = db.session.get(model, row_id)
        assert saved.created_at.tzinfo is UTC
        assert saved.expires_at > saved.created_at
        assert saved.token_digest == hashlib.sha256(token.encode()).hexdigest()
        assert token not in str(db.session.execute(text(f"SELECT * FROM {model.__tablename__}")).all())
        assert user.email == "demo@example.com"

        db.session.add(_credential(model, user_id, token))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        db.session.add(_credential(model, "missing-user", "another token"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        invalid = [
            ("token_digest", "not-a-digest"), ("token_digest", "g" * 64),
            ("expires_at", "2025-01-01T00:00:00.000000Z"),
            ("created_at", "2026-02-30T00:00:00.000000Z"),
        ]
        if model is AuthSession:
            invalid.append(("csrf_secret", "bad secret"))
        for column, value in invalid:
            with pytest.raises(IntegrityError):
                db.session.execute(
                    text(f"UPDATE {model.__tablename__} SET {column} = :value WHERE id = :id"),
                    {"value": value, "id": row_id},
                )
                db.session.commit()
            db.session.rollback()
        db.session.delete(db.session.get(User, user_id))
        db.session.commit()
        assert db.session.scalar(select(model)) is None


def test_user_email_uniqueness_and_fictional_multiple_users(migrated_file_app):
    with migrated_file_app.app_context():
        db.session.add_all([
            User(email="first@example.com", password_hash="fictional fixture hash"),
            User(email="second@example.com", password_hash="fictional fixture hash"),
        ])
        db.session.commit()
        db.session.add(User(email=" FIRST@example.com ", password_hash="fictional fixture hash"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        assert len(db.session.scalars(select(User)).all()) == 2
