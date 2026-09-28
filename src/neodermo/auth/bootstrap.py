"""Provision exactly one operator through a serialized local operation."""

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError

from neodermo.auth.passwords import hash_new_password
from neodermo.auth.validation import normalize_email
from neodermo.extensions import db
from neodermo.models.user import User
from neodermo.models.types import new_id


class ProvisioningError(Exception):
    """A safe operator-facing provisioning failure without credential details."""


def operator_exists() -> bool:
    """Check before prompting; provision_operator repeats this under a lock."""
    try:
        with db.engine.connect() as connection:
            return connection.scalar(select(User.id).limit(1)) is not None
    except SQLAlchemyError:
        raise ProvisioningError("Cannot read operator storage. Check database migrations.") from None


def provision_operator(email: str, password: str) -> str:
    """Hash outside the lock, then atomically check and create the sole operator.

    SQLite BEGIN IMMEDIATE serializes this check across processes/connections.
    A separate connection avoids committing unrelated ORM work in db.session.
    """
    email = normalize_email(email)
    password_hash = hash_new_password(password)
    user_id = new_id()
    try:
        with db.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            if connection.scalar(select(User.id).limit(1)) is not None:
                raise ProvisioningError("An operator already exists; no account was created.")
            connection.execute(
                insert(User.__table__).values(
                    id=user_id, email=email, password_hash=password_hash,
                )
            )
    except SQLAlchemyError:
        raise ProvisioningError(
            "Could not provision the operator. Check migrations or database availability."
        ) from None
    return user_id
