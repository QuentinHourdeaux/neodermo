"""Establishments associated with patient stays."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from neodermo.extensions import db
from neodermo.models.types import new_id


class Establishment(db.Model):
    """A care establishment that may host many patient stays."""

    __tablename__ = "establishments"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0 AND name = trim(name)", name="name_present"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    phone_number: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(254))
    notes: Mapped[str | None] = mapped_column(Text)

    stays: Mapped[list[PatientStay]] = relationship(back_populates="establishment")

    @validates("name")
    def _strip_name(self, key: str, value: str) -> str:
        return value.strip()
