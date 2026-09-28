"""Default API identity, Origin, CSRF, and current workspace access policy."""

import secrets

from flask import Flask, Response, g, jsonify, request

from neodermo.auth.sessions import COOKIE_NAME, lookup_session, valid_token_format
from neodermo.models import User

_PUBLIC_ENDPOINTS = frozenset({
    ("health.health", "GET"),
    ("auth.session_status", "GET"),
    ("auth.login", "POST"),
    ("auth.forgot_password", "POST"),
    ("auth.reset_password", "POST"),
})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def error_response(code: str, status: int) -> tuple[Response, int]:
    """Return a small error without reflecting credentials or request content."""
    return jsonify({"error": {"code": code}}), status


def operator_may_access_workspace(user: User) -> bool:
    """The current policy grants a signed-in operator the shared workspace."""
    return isinstance(user, User)


def install_auth_policy(app: Flask) -> None:
    """Protect every API endpoint unless its endpoint and method are public."""

    @app.before_request
    def protect_api():
        if request.path != "/api" and not request.path.startswith("/api/"):
            return None
        if request.method not in _SAFE_METHODS:
            origin = request.headers.get("Origin")
            if origin not in app.config["TRUSTED_FRONTEND_ORIGINS"]:
                return error_response("invalid_origin", 403)
        if (request.endpoint, request.method) in _PUBLIC_ENDPOINTS:
            return None

        resolved = lookup_session(request.cookies.get(COOKIE_NAME))
        if resolved is None:
            return error_response("unauthenticated", 401)
        g.current_session, g.current_user = resolved
        if not operator_may_access_workspace(g.current_user):
            return error_response("forbidden", 403)
        if request.method not in _SAFE_METHODS:
            header = request.headers.get("X-CSRF-Token", "")
            if not valid_token_format(header) or not secrets.compare_digest(
                header, g.current_session.csrf_secret
            ):
                return error_response("invalid_csrf", 403)
        return None

    @app.after_request
    def prevent_api_caching(response: Response) -> Response:
        if request.path == "/api" or request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
