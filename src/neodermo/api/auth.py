"""HTTP translation for current-user login, status, and logout."""

import json

from flask import Blueprint, g, jsonify, make_response, request

from neodermo.auth.policy import error_response
from neodermo.auth.sessions import (
    COOKIE_NAME, clear_session_cookie, issue_session, lookup_session,
    revoke_session, set_session_cookie,
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
    except (UnicodeError, json.JSONDecodeError, _InvalidJSON):
        return None
    if type(value) is not dict or value.keys() != expected:
        return None
    if any(type(item) is not str for item in value.values()):
        return None
    return value


@bp.post("/login")
def login():
    """Exchange valid credentials for a fresh database session and CSRF token."""
    body = _object_body({"email", "password"})
    if body is None or not 15 <= len(body["password"]) <= 128:
        return error_response("invalid_request", 400)
    try:
        email = normalize_email(body["email"])
        body["password"].encode("utf-8")
    except (ValueError, UnicodeError):
        return error_response("invalid_request", 400)

    issued = issue_session(email, body["password"], request.cookies.get(COOKIE_NAME))
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
