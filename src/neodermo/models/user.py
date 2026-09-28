"""Locally provisioned account identity and password hash storage."""

from datetime import datetime

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, validates

from neodermo.auth.validation import normalize_email
from neodermo.extensions import db
from neodermo.models.types import UTCDateTime, new_id, utc_now, utc_text_check


class User(db.Model):
    """Account identity; provisioning, not a table constraint, limits operators."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "length(email) BETWEEN 3 AND 254 AND email = trim(email) "
            "AND email = lower(email)", name="email_normalized",
        ),
        CheckConstraint("length(password_hash) > 0", name="password_hash_present"),
        utc_text_check("created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)

    @validates("email")
    def _normalize_email(self, key: str, value: str) -> str:
        return normalize_email(value)
