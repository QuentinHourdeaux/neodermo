"""Neodermo application package."""

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from neodermo.config import CONFIGS
from neodermo.extensions import db, migrate

__version__ = "0.1.0"

# src/neodermo/__init__.py -> repo root, so relative sqlite paths stay stable.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app(config_name: str | None = None) -> Flask:
    """Build and return a configured Flask app.

    A new app is created each call so tests and the migration CLI do not
    share one global instance.
    """
    name = config_name or os.environ.get("NEODERMO_ENV", "development")
    if name not in CONFIGS:
        raise RuntimeError(f"Unknown config {name!r}. Use development or testing.")

    if name != "testing":
        load_dotenv()

    app = Flask(__name__)
    app.config.from_object(CONFIGS[name])

    if name != "testing":
        secret_key = os.environ.get("SECRET_KEY")
        database_url = os.environ.get("DATABASE_URL")
        if not secret_key or not database_url:
            raise RuntimeError(
                "SECRET_KEY and DATABASE_URL must be set. "
                "Copy .env.example to .env."
            )
        app.config["SECRET_KEY"] = secret_key
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        _ensure_sqlite_parent(database_url)

    db.init_app(app)
    migrate.init_app(app, db)

    # Import the models package so later table classes register on db.
    from neodermo import models  # noqa: F401
    from neodermo.api.health import bp as health_bp

    app.register_blueprint(health_bp, url_prefix="/api")

    return app


def _ensure_sqlite_parent(database_url: str) -> None:
    """Create the directory for a file-backed SQLite URL if needed."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return
    raw_path = database_url.removeprefix(prefix)
    if raw_path == ":memory:":
        return
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
