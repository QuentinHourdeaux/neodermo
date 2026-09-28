"""Per-app, in-memory limits for expensive public authentication requests."""

from flask import Flask, Response, jsonify
from flask_limiter import Limiter, RequestLimit
from flask_limiter.util import get_remote_address


def _limit_response(_limit: RequestLimit) -> Response:
    response = jsonify({"error": {"code": "rate_limited"}})
    response.status_code = 429
    return response


def install_auth_limits(app: Flask) -> Limiter:
    """Limit login by independent connection-address and email buckets.

    Each app gets its own memory store. The browser cannot select the address
    by sending forwarded headers, and malformed requests still use that bucket.
    """
    from neodermo.api.auth import login_email_bucket, login_email_unavailable

    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri="memory://",
        headers_enabled=True,
        retry_after="delta-seconds",
        on_breach=_limit_response,
    )
    view = app.view_functions["auth.login"]
    view = limiter.limit("30/minute", scope="login-address")(view)
    view = limiter.limit(
        "5/minute", key_func=login_email_bucket,
        exempt_when=login_email_unavailable, scope="login-email",
    )(view)
    app.view_functions["auth.login"] = view
    limiter.init_app(app)
    return limiter
