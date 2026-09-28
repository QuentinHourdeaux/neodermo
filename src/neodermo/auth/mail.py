"""Send recovery notices only to the configured loopback SMTP capture inbox."""

import smtplib
from email.message import EmailMessage

from flask import current_app

_SENDER = "Neodermo <no-reply@localhost>"


def recovery_message(recipient: str, token: str) -> EmailMessage:
    """Build a plain-text API instruction, without a nonexistent UI link."""
    message = EmailMessage()
    message["From"] = _SENDER
    message["To"] = recipient
    message["Subject"] = "Neodermo password reset"
    message.set_content(
        "A password reset was requested for your Neodermo operator account.\n\n"
        "Send a POST request to /api/auth/reset-password with JSON containing "
        "this token and your new password:\n"
        f"token: {token}\n\n"
        "The token expires in 30 minutes and can be used once. "
        "If you did not request this, ignore this message.\n"
    )
    return message


def password_changed_message(recipient: str) -> EmailMessage:
    """Confirm a completed reset without including a password or token."""
    message = EmailMessage()
    message["From"] = _SENDER
    message["To"] = recipient
    message["Subject"] = "Neodermo password changed"
    message.set_content(
        "Your Neodermo operator password was changed. "
        "If this was unexpected, contact your local administrator.\n"
    )
    return message


def send_mail(message: EmailMessage) -> None:
    """Deliver through local SMTP with a bounded socket timeout."""
    with smtplib.SMTP(
        current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"],
        timeout=current_app.config["SMTP_TIMEOUT_SECONDS"],
    ) as client:
        client.send_message(message)
