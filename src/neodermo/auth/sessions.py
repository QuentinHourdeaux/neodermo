"""Database-backed browser sessions and their cookie transport."""

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from ipaddress import ip_address
from urllib.parse import urlsplit

from flask import Response, current_app, request
from sqlalchemy import delete, insert, select

from neodermo.auth.passwords import verify_password
from neodermo.auth.validation import normalize_email
from neodermo.extensions import db
from neodermo.models import AuthSession, User
from neodermo.models.types import new_id, utc_now

COOKIE_NAME = "neodermo_session"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z", re.ASCII)


@dataclass(frozen=True)
class IssuedSession:
    """Values needed to return a newly committed login, with secrets hidden in repr."""

    user_id: str
    email: str
    expires_at: datetime
    token: str = field(repr=False)
    csrf_token: str = field(repr=False)


def auth_now() -> datetime:
    """Use an injectable clock for expiry tests without sleeps."""
    return current_app.config.get("AUTH_NOW", utc_now)()


def token_digest(token: str | None) -> str | None:
    """Reject malformed cookies before hashing; never store the bearer value."""
    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def lookup_session(token: str | None) -> tuple[AuthSession, User] | None:
    """Resolve a live session and its user from the server-side database."""
    digest = token_digest(token)
    if digest is None:
        return None
    row = db.session.execute(
        select(AuthSession, User)
        .join(User, AuthSession.user_id == User.id)
        .where(AuthSession.token_digest == digest)
    ).one_or_none()
    if row is None or row.AuthSession.expires_at <= auth_now():
        return None
    return row.AuthSession, row.User


def issue_session(email: str, password: str, previous_token: str | None) -> IssuedSession | None:
    """Verify a password, then serialize session creation against password reset.

    The second password-hash read under BEGIN IMMEDIATE prevents a reset racing
    login from leaving a session authorized by an obsolete password.
    """
    user = db.session.scalar(select(User).where(User.email == email))
    if not verify_password(user.password_hash if user else None, password):
        return None
    user_id, verified_hash, saved_email = user.id, user.password_hash, user.email
    db.session.remove()

    now = auth_now()
    expires_at = now + timedelta(seconds=current_app.config["SESSION_LIFETIME_SECONDS"])
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
    old_digest = token_digest(previous_token)
    with db.engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        if connection.scalar(select(User.password_hash).where(User.id == user_id)) != verified_hash:
            return None
        if old_digest is not None:
            previous_id = connection.scalar(
                select(AuthSession.id)
                .join(User, AuthSession.user_id == User.id)
                .where(
                    AuthSession.token_digest == old_digest,
                    AuthSession.expires_at > now,
                )
            )
            if previous_id is not None:
                connection.execute(delete(AuthSession).where(AuthSession.id == previous_id))
        connection.execute(
            insert(AuthSession).values(
                id=new_id(), token_digest=digest, user_id=user_id,
                created_at=now, expires_at=expires_at, csrf_secret=csrf_token,
            )
        )
    return IssuedSession(user_id, saved_email, expires_at, raw_token, csrf_token)


def revoke_session(session: AuthSession) -> None:
    """Delete only the current browser session; other devices remain signed in."""
    db.session.delete(session)
    db.session.commit()


def _loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return bool(host and ip_address(host).is_loopback)
    except ValueError:
        return False


def _cookie_secure() -> bool:
    if current_app.config["AUTH_COOKIE_SECURE"] or request.is_secure:
        return True
    try:
        host = urlsplit(f"http://{request.host}").hostname
    except ValueError:
        return True
    return not (
        _loopback(host) and _loopback(request.remote_addr)
    )


def set_session_cookie(response: Response, issued: IssuedSession) -> None:
    """Transport the raw token once, with the scope of the database session."""
    response.set_cookie(
        COOKIE_NAME, issued.token,
        max_age=current_app.config["SESSION_LIFETIME_SECONDS"],
        expires=issued.expires_at, path="/", httponly=True,
        secure=_cookie_secure(), samesite="Lax",
    )


def clear_session_cookie(response: Response) -> None:
    """Expire the same cookie scope used on login."""
    response.delete_cookie(
        COOKIE_NAME, path="/", secure=_cookie_secure(),
        httponly=True, samesite="Lax",
    )
