"""Test configuration isolation and persistence across application instances."""

from unittest.mock import patch

import pytest
from flask_migrate import upgrade
from sqlalchemy import select, text

from neodermo import PROJECT_ROOT, create_app
from neodermo.extensions import db
from neodermo.models import Patient


@pytest.mark.parametrize("runtime_configured", [False, True])
def test_file_test_app_ignores_runtime_environment(
    file_app_factory, tmp_path, monkeypatch, runtime_configured
):
    runtime_path = tmp_path / "runtime-must-not-open.sqlite"
    if runtime_configured:
        runtime_path.write_bytes(b"runtime sentinel")
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{runtime_path}")
        monkeypatch.setenv("SECRET_KEY", "runtime-secret-must-not-be-used")
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("NEODERMO_ENV", "development")

    with patch("neodermo.load_dotenv", side_effect=AssertionError("dotenv loaded")):
        app = file_app_factory()
        assert app.test_client().get("/api/health").status_code == 200
        with app.app_context():
            assert db.engine.url.database == str(tmp_path / "test.sqlite")

    assert app.testing
    assert not app.debug
    assert app.config["SECRET_KEY"] == "test"
    if runtime_configured:
        assert runtime_path.read_bytes() == b"runtime sentinel"
    else:
        assert not runtime_path.exists()


def test_test_overrides_cannot_change_runtime_configuration():
    with patch("neodermo.load_dotenv", side_effect=AssertionError("dotenv loaded")):
        with pytest.raises(ValueError, match="requires the testing configuration"):
            create_app("development", test_config={"TESTING": True})


def test_migrated_data_survives_new_app_and_repeated_upgrade(
    migrated_file_app, file_app_factory
):
    with migrated_file_app.app_context():
        patient = Patient(name="Fictional persistence example")
        db.session.add(patient)
        db.session.commit()
        patient_id = patient.id
        revision = db.session.scalar(text("SELECT version_num FROM alembic_version"))
        original_engine = db.engine
        db.session.remove()
        original_engine.dispose()

    restarted_app = file_app_factory()
    with restarted_app.app_context():
        assert db.engine is not original_engine
        upgrade(directory=str(PROJECT_ROOT / "migrations"))
        saved = db.session.get(Patient, patient_id)
        assert saved.name == "Fictional persistence example"
        assert db.session.scalar(text("SELECT version_num FROM alembic_version")) == revision
        assert db.session.scalar(text("PRAGMA foreign_keys")) == 1

        saved.allergies = "Fictional allergy"
        db.session.commit()

    with migrated_file_app.app_context():
        assert db.session.scalar(select(Patient)).allergies == "Fictional allergy"
        assert db.session.scalar(text("PRAGMA foreign_keys")) == 1
