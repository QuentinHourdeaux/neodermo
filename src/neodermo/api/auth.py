"""HTTP translation for current-user login, status, and logout."""

import hashlib
import json

from flask import Blueprint, g, jsonify, make_response, request

from neodermo.auth.policy import error_response
from neodermo.auth.recovery import (
    InvalidResetToken, RecoveryUnavailable,
    request_recovery, reset_password as complete_password_reset,
)
from neodermo.auth.sessions import (
    COOKIE_NAME, clear_session_cookie, issue_session, lookup_session,
    revoke_session, set_session_cookie, token_digest, SessionUnavailable,
)
from neodermo.auth.validation import normalize_email

bp = Blueprint("auth", __name__)
_MAX_AUTH_JSON_BYTES = 8192


class _InvalidJSON(Exception):
    """Reject ambiguous JSON objects without reflecting input."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidJSON
        result[key] = value
    return result


def _object_body(expected: set[str]) -> dict[str, str] | None:
    """Read bounded JSON with exactly the expected string fields."""
    if request.mimetype != "application/json":
        return None
    if request.content_length is not None and request.content_length > _MAX_AUTH_JSON_BYTES:
        return None
    body = request.stream.read(_MAX_AUTH_JSON_BYTES + 1)
    if len(body) > _MAX_AUTH_JSON_BYTES:
        return None
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (ValueError, RecursionError, _InvalidJSON):
        return None
    if type(value) is not dict or value.keys() != expected:
        return None
    if any(type(item) is not str for item in value.values()):
        return None
    return value


def _email_input(
    cache_name: str, expected: set[str]
) -> tuple[dict[str, str] | None, str | None]:
    """Parse once so an email limit and its route see the same bounded body."""
    cached = getattr(g, cache_name, None)
    if cached is None:
        body = _object_body(expected)
        email = None
        if body is not None:
            try:
                email = normalize_email(body["email"])
            except (ValueError, UnicodeError):
                pass
        cached = body, email
        setattr(g, cache_name, cached)
    return cached


def _login_input() -> tuple[dict[str, str] | None, str | None]:
    return _email_input("login_input", {"email", "password"})


def login_email_bucket() -> str:
    """Use a digest of normalized email, never the submitted spelling."""
    _, email = _login_input()
    return hashlib.sha256(email.encode("ascii")).hexdigest() if email else "invalid"


def login_email_unavailable() -> bool:
    """Malformed or unaddressed requests are limited by client address only."""
    return _login_input()[1] is None


def _forgot_input() -> tuple[dict[str, str] | None, str | None]:
    return _email_input("forgot_input", {"email"})


def forgot_email_bucket() -> str:
    _, email = _forgot_input()
    return hashlib.sha256(email.encode("ascii")).hexdigest() if email else "invalid"


def forgot_email_unavailable() -> bool:
    return _forgot_input()[1] is None


def _reset_input() -> tuple[dict[str, str] | None, str | None]:
    """Share a validated token digest, never the raw token, with the limiter."""
    if not hasattr(g, "reset_input"):
        body = _object_body({"token", "new_password"})
        digest = token_digest(body["token"]) if body is not None else None
        g.reset_input = body, digest
    return g.reset_input


def reset_token_bucket() -> str:
    return _reset_input()[1] or "invalid"


def reset_token_unavailable() -> bool:
    return _reset_input()[1] is None


@bp.post("/login")
def login():
    """Exchange valid credentials for a fresh database session and CSRF token."""
    body, email = _login_input()
    if body is None or email is None or not 15 <= len(body["password"]) <= 128:
        return error_response("invalid_request", 400)
    try:
        body["password"].encode("utf-8")
    except (ValueError, UnicodeError):
        return error_response("invalid_request", 400)

    try:
        issued = issue_session(email, body["password"], request.cookies.get(COOKIE_NAME))
    except SessionUnavailable:
        return error_response("temporarily_unavailable", 503)
    if issued is None:
        return error_response("invalid_credentials", 401)
    response = make_response(jsonify({
        "authenticated": True, "csrf_token": issued.csrf_token,
    }))
    set_session_cookie(response, issued)
    return response


@bp.get("/session")
def session_status():
    """Describe only the current browser's session without creating one."""
    if request.args or request.content_length not in (None, 0):
        return error_response("invalid_request", 400)
    resolved = lookup_session(request.cookies.get(COOKIE_NAME))
    if resolved is None:
        response = make_response(jsonify({"authenticated": False}))
        if COOKIE_NAME in request.cookies:
            clear_session_cookie(response)
        return response
    session, user = resolved
    return jsonify({
        "authenticated": True,
        "user": {"id": user.id, "email": user.email},
        "csrf_token": session.csrf_secret,
    })


@bp.post("/logout")
def logout():
    """Revoke only the current database session and clear its cookie."""
    if request.content_length not in (None, 0):
        return error_response("invalid_request", 400)
    revoke_session(g.current_session)
    response = make_response("", 204)
    clear_session_cookie(response)
    return response


@bp.post("/forgot-password")
def forgot_password():
    """Start mail-only recovery with no account-existence signal in the response."""
    body, email = _forgot_input()
    if body is None or email is None:
        return error_response("invalid_request", 400)
    request_recovery(email)
    return jsonify({"message": "If the account exists, recovery instructions will be sent."}), 202


@bp.post("/reset-password")
def reset_password():
    """Consume a one-time token, change its user's password, and log them out."""
    body, digest = _reset_input()
    if body is None:
        return error_response("invalid_request", 400)
    if digest is None:
        return error_response("invalid_reset_token", 400)
    try:
        complete_password_reset(body["token"], body["new_password"])
    except InvalidResetToken:
        return error_response("invalid_reset_token", 400)
    except ValueError:
        return error_response("invalid_request", 400)
    except RecoveryUnavailable:
        return error_response("temporarily_unavailable", 503)
    return "", 204
