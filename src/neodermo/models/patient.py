"""Patient cases independent of their stays and locations."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from neodermo.extensions import db
from neodermo.models.enums import Sex, stored_enum
from neodermo.models.types import (
    UTCDateTime,
    new_id,
    new_patient_reference,
    utc_now,
    utc_text_check,
)


class Patient(db.Model):
    """A stable case whose wound history survives changes of stay."""

    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0 AND name = trim(name)", name="name_present"),
        utc_text_check("created_at"),
        utc_text_check("updated_at"),
        utc_text_check("archived_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    reference: Mapped[str] = mapped_column(
        String(15), unique=True, nullable=False, default=new_patient_reference
    )
    birth_date: Mapped[date | None] = mapped_column(Date)
    sex: Mapped[Sex | None] = mapped_column(stored_enum(Sex, "patient_sex"))
    allergies: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    stays: Mapped[list[PatientStay]] = relationship(back_populates="patient")
    wounds: Mapped[list[Wound]] = relationship(back_populates="patient")

    @validates("name")
    def _strip_name(self, key: str, value: str) -> str:
        return value.strip()

    @validates("allergies")
    def _normalize_allergies(self, key: str, value: str | None) -> str:
        return value.strip() if value else ""
