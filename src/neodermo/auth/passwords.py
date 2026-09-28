"""Bounded password input, local blocklist screening, and Argon2id hashing."""

import gzip
import secrets
from functools import cache
from importlib.resources import files

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from flask import Flask, current_app

_hasher = PasswordHasher(
    time_cost=3, memory_cost=65536, parallelism=4,
    hash_len=32, salt_len=16, type=Type.ID,
)


def init_passwords(app: Flask) -> None:
    """Prepare one dummy hash per app for unknown-account verification."""
    app.extensions["auth_dummy_hash"] = _hasher.hash(secrets.token_urlsafe(32))


def validate_password_input(password: str) -> None:
    """Reject invalid input without changing spaces, Unicode, or case."""
    try:
        if not isinstance(password, str) or not 15 <= len(password) <= 128:
            raise ValueError
        password.encode("utf-8")
    except ValueError:
        raise ValueError("Password must contain 15–128 valid Unicode characters.") from None


@cache
def _common_passwords() -> frozenset[str]:
    data = files("neodermo.auth").joinpath("data/common-passwords.txt.gz").read_bytes()
    return frozenset(gzip.decompress(data).decode("utf-8").splitlines())


def hash_new_password(password: str) -> str:
    """Apply the shared provisioning/reset policy and hash the exact password."""
    validate_password_input(password)
    # Case-insensitive screening does not alter the password passed to Argon2.
    if password.lower() in _common_passwords():
        raise ValueError("Choose a password that is not commonly used.")
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Verify bounded input, doing dummy work when there is no account hash."""
    try:
        validate_password_input(password)
    except ValueError:
        return False
    target = password_hash if password_hash is not None else current_app.extensions["auth_dummy_hash"]
    try:
        matched = _hasher.verify(target, password)
    except (VerificationError, InvalidHashError):
        return False
    return password_hash is not None and matched
