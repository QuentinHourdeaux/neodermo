"""One-time reset tokens, bounded recovery responses, and atomic password reset."""

import secrets
import smtplib
import time
from datetime import timedelta

from flask import current_app
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from neodermo.auth import mail
from neodermo.auth.passwords import hash_new_password
from neodermo.auth.sessions import auth_now, token_digest
from neodermo.extensions import db
from neodermo.models import AuthSession, PasswordResetToken, User
from neodermo.models.types import new_id

RESET_LIFETIME_SECONDS = 1800


class InvalidResetToken(Exception):
    """The submitted token has no current reset authority."""


class RecoveryUnavailable(Exception):
    """Storage could not complete a reset; retry without exposing details."""


def request_recovery(email: str) -> None:
    """Issue and mail a token only for a known account, with a common response floor.

    Both branches generate a token and construct a message. A token becomes
    valid only after local SMTP accepts the message, so failed delivery cannot
    leave a usable credential. The HTTP response is always the same.
    """
    clock = current_app.config.get("RECOVERY_MONOTONIC", time.monotonic)
    sleep = current_app.config.get("RECOVERY_SLEEP", time.sleep)
    started = clock()
    now = auth_now()
    token = secrets.token_urlsafe(32)
    digest = token_digest(token)
    message = mail.recovery_message(email, token)
    try:
        user = db.session.execute(
            select(User.id, User.password_hash).where(User.email == email)
        ).one_or_none()
        db.session.remove()
        if user is not None:
            user_id, original_hash = user
            try:
                mail.send_mail(message)
            except (OSError, smtplib.SMTPException):
                current_app.logger.warning("Recovery mail delivery failed.")
            else:
                with db.engine.begin() as connection:
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                    if connection.scalar(
                        select(User.password_hash).where(User.id == user_id)
                    ) != original_hash:
                        return
                    connection.execute(
                        insert(PasswordResetToken).values(
                            id=new_id(), token_digest=digest, user_id=user_id,
                            created_at=now,
                            expires_at=now + timedelta(seconds=RESET_LIFETIME_SECONDS),
                        )
                    )
    except SQLAlchemyError:
        db.session.remove()
        current_app.logger.warning("Recovery storage operation failed.")
    finally:
        remaining = current_app.config["RECOVERY_RESPONSE_FLOOR_SECONDS"] - (clock() - started)
        if remaining > 0:
            sleep(remaining)


def reset_password(token: str, new_password: str) -> None:
    """Consume one live token and revoke every session in a single SQLite write.

    Expensive hashing happens before BEGIN IMMEDIATE. The token is checked
    again under the write lock, so concurrent submissions have one winner.
    """
    digest = token_digest(token)
    if digest is None:
        raise InvalidResetToken
    try:
        row = db.session.execute(
            select(PasswordResetToken, User)
            .join(User, PasswordResetToken.user_id == User.id)
            .where(PasswordResetToken.token_digest == digest)
        ).one_or_none()
        if row is None or row.PasswordResetToken.expires_at <= auth_now():
            raise InvalidResetToken
        password_hash = hash_new_password(new_password)
        db.session.remove()

        with db.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            locked = connection.execute(
                select(PasswordResetToken.user_id, User.email)
                .join(User, PasswordResetToken.user_id == User.id)
                .where(
                    PasswordResetToken.token_digest == digest,
                    PasswordResetToken.expires_at > auth_now(),
                )
            ).one_or_none()
            if locked is None:
                raise InvalidResetToken
            user_id, email = locked
            connection.execute(
                update(User).where(User.id == user_id).values(password_hash=password_hash)
            )
            connection.execute(
                delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
            )
            connection.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    except SQLAlchemyError:
        db.session.remove()
        current_app.logger.warning("Password reset storage operation failed.")
        raise RecoveryUnavailable from None

    try:
        mail.send_mail(mail.password_changed_message(email))
    except (OSError, smtplib.SMTPException):
        current_app.logger.warning("Password change confirmation delivery failed.")
