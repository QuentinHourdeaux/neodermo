"""Health endpoint."""

from flask import Blueprint
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

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
    except DatabaseError:
        # OperationalError (unreachable file) and DatabaseError (corrupt
        # file) both belong here. A narrower catch lets Flask's debugger
        # return HTML with paths when DEBUG is on.
        return {"status": "unavailable", "database": "error"}, 503
