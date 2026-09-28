"""Shared pytest fixtures.

A fixture is a reusable setup function. pytest injects it into tests
that name it as an argument — similar to a beforeEach that returns a value.
"""

from collections.abc import Callable, Iterator

import pytest
from flask import Flask
from flask_migrate import upgrade

from neodermo import PROJECT_ROOT, create_app
from neodermo.extensions import db


@pytest.fixture
def app():
    """Build a testing app that uses in-memory SQLite."""
    return create_app("testing")


@pytest.fixture
def client(app):
    """In-process HTTP client. No real port is opened."""
    return app.test_client()


@pytest.fixture
def file_app_factory(tmp_path) -> Iterator[Callable[[], Flask]]:
    """Build independent apps sharing one temporary SQLite file per test.

    Call again to simulate an application restart or use a separate database
    connection. Migrations are explicit so tests can inspect upgrade behavior.
    """
    database_path = tmp_path / "test.sqlite"
    apps = []

    def build_app() -> Flask:
        app = create_app(
            "testing",
            test_config={"SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}"},
        )
        apps.append(app)
        return app

    yield build_app

    for app in apps:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


@pytest.fixture
def migrated_file_app(file_app_factory) -> Flask:
    """Build a file-backed test app upgraded through the real migrations."""
    app = file_app_factory()
    with app.app_context():
        upgrade(directory=str(PROJECT_ROOT / "migrations"))
    return app
