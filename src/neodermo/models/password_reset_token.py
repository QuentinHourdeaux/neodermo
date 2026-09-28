"""Expiring one-time recovery credentials, stored only as digests."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from neodermo.extensions import db
from neodermo.models.types import UTCDateTime, new_id, utc_now, utc_text_check


class PasswordResetToken(db.Model):
    """Recovery authority bound to one user; deletion invalidates the token."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        CheckConstraint(
            "length(token_digest) = 64 AND token_digest NOT GLOB '*[^0-9a-f]*'",
            name="token_digest_sha256",
        ),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        utc_text_check("created_at"),
        utc_text_check("expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
