"""Health endpoint."""

from flask import Blueprint
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from neodermo.extensions import db

bp = Blueprint("health", __name__)


def check_database() -> dict[str, str]:
    """Run a trivial connectivity query.

    Returns a generic payload. Never include paths, env values,
    or exception text that could leak configuration.
    """
    db.session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@bp.get("/health")
def health() -> tuple[dict[str, str], int]:
    """Return database connectivity without exposing configuration."""
    try:
        return check_database(), 200
    except OperationalError:
        return {"status": "unavailable", "database": "error"}, 503
