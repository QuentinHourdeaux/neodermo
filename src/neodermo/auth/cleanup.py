"""Remove expired credentials without touching live sessions or users."""

from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from neodermo.extensions import db
from neodermo.models import AuthSession, PasswordResetToken
from neodermo.models.types import utc_now


class CleanupUnavailable(Exception):
    """Credential storage could not complete cleanup."""


def cleanup_expired() -> tuple[int, int]:
    """Delete credentials expired at one UTC cutoff in a single transaction."""
    cutoff = utc_now()
    try:
        with db.engine.begin() as connection:
            sessions = connection.execute(
                delete(AuthSession).where(AuthSession.expires_at <= cutoff)
            ).rowcount
            reset_tokens = connection.execute(
                delete(PasswordResetToken).where(PasswordResetToken.expires_at <= cutoff)
            ).rowcount
    except SQLAlchemyError:
        raise CleanupUnavailable from None
    return sessions, reset_tokens
