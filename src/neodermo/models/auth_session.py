"""Persistent opaque bearer sessions; only token digests are stored."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from neodermo.extensions import db
from neodermo.models.types import UTCDateTime, new_id, utc_now, utc_text_check


class AuthSession(db.Model):
    """A revocable browser session independent of Flask's signed cookie."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "length(token_digest) = 64 AND token_digest NOT GLOB '*[^0-9a-f]*'",
            name="token_digest_sha256",
        ),
        CheckConstraint(
            "length(csrf_secret) = 43 AND csrf_secret NOT GLOB '*[^A-Za-z0-9_-]*'",
            name="csrf_secret_format",
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
    csrf_secret: Mapped[str] = mapped_column(String(43), nullable=False)
