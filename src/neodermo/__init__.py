"""Neodermo application package."""

import os
from collections.abc import Mapping
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask

from neodermo.config import CONFIGS
from neodermo.extensions import db, migrate

__version__ = "0.1.0"

# src/neodermo/__init__.py -> repo root, so relative sqlite paths stay stable.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app(
    config_name: str | None = None,
    *,
    test_config: Mapping[str, object] | None = None,
) -> Flask:
    """Build and return a configured Flask app.

    A new app is created each call so tests and the migration CLI do not
    share one global instance. Testing overrides are applied before extensions
    initialize, without loading runtime environment configuration.
    """
    name = config_name or os.environ.get("NEODERMO_ENV", "development")
    if name not in CONFIGS:
        raise RuntimeError(f"Unknown config {name!r}. Use development or testing.")
    if test_config is not None and name != "testing":
        raise ValueError("test_config requires the testing configuration.")

    if name != "testing":
        load_dotenv()

    app = Flask(__name__)
    app.config.from_object(CONFIGS[name])
    if test_config is not None:
        app.config.from_mapping(test_config)

    if name != "testing":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL must be set. Copy .env.example to .env.")
        app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_sqlite_url(database_url)
        app.config["TRUSTED_FRONTEND_ORIGINS"] = tuple(
            origin.strip() for origin in
            os.environ.get("TRUSTED_FRONTEND_ORIGINS", "http://127.0.0.1:5000").split(",")
        )
        try:
            app.config["SESSION_LIFETIME_SECONDS"] = int(
                os.environ.get("SESSION_LIFETIME_SECONDS", "43200")
            )
        except ValueError:
            raise RuntimeError("SESSION_LIFETIME_SECONDS must be a positive integer.") from None
        app.config["AUTH_COOKIE_SECURE"] = not (
            os.environ.get("ALLOW_INSECURE_LOOPBACK_COOKIE") == "1"
        )

    _validate_auth_config(app, name)

    db.init_app(app)
    migrate.init_app(app, db)

    # Import the models package so later table classes register on db.
    from neodermo import models  # noqa: F401
    from neodermo.api.auth import bp as auth_bp
    from neodermo.api.health import bp as health_bp
    from neodermo.auth.cli import auth_cli
    from neodermo.auth.limits import install_auth_limits
    from neodermo.auth.passwords import init_passwords
    from neodermo.auth.policy import install_auth_policy

    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.cli.add_command(auth_cli)
    init_passwords(app)
    install_auth_limits(app)
    install_auth_policy(app)

    return app


def _validate_auth_config(app: Flask, name: str) -> None:
    """Reject origin/cookie settings that would weaken request protection."""
    lifetime = app.config["SESSION_LIFETIME_SECONDS"]
    if type(lifetime) is not int or lifetime <= 0:
        raise RuntimeError("SESSION_LIFETIME_SECONDS must be a positive integer.")
    origins = app.config["TRUSTED_FRONTEND_ORIGINS"]
    if not isinstance(origins, (tuple, list)) or not origins:
        raise RuntimeError("TRUSTED_FRONTEND_ORIGINS must list exact origins.")
    for origin in origins:
        if not isinstance(origin, str) or not origin or origin == "null":
            raise RuntimeError("TRUSTED_FRONTEND_ORIGINS must list exact origins.")
        try:
            parts = urlsplit(origin)
            port = parts.port
        except ValueError:
            raise RuntimeError("TRUSTED_FRONTEND_ORIGINS contains an invalid origin.") from None
        if (parts.scheme not in ("http", "https") or not parts.hostname or
                parts.username or parts.password or port == 0 or
                origin != f"{parts.scheme}://{parts.netloc}"):
            raise RuntimeError("TRUSTED_FRONTEND_ORIGINS must list exact origins.")
    if type(app.config["AUTH_COOKIE_SECURE"]) is not bool:
        raise RuntimeError("AUTH_COOKIE_SECURE must be a boolean.")
    if not app.config["AUTH_COOKIE_SECURE"]:
        if name not in ("development", "testing") or any(
            urlsplit(origin).scheme != "http" or not _is_loopback(urlsplit(origin).hostname)
            for origin in origins
        ):
            raise RuntimeError("Insecure auth cookies require a loopback HTTP origin.")


def _is_loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return bool(host and ip_address(host).is_loopback)
    except ValueError:
        return False


def _resolve_sqlite_url(database_url: str) -> str:
    """Make file-backed SQLite URLs absolute and create their directory.

    Relative paths are resolved from the repo root so the Flask CLI and
    Alembic open the same file regardless of the process working directory.
    """
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return database_url
    raw_path = database_url.removeprefix(prefix)
    if raw_path == ":memory:":
        return database_url
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"
