"""Wounds belonging to a patient case."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from neodermo.extensions import db
from neodermo.models.types import UTCDateTime, new_id, utc_now


class Wound(db.Model):
    """A wound whose nullable closure time determines whether it is open."""

    __tablename__ = "wounds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    placement: Mapped[str | None] = mapped_column(String(200))
    treatment_start_date: Mapped[date | None] = mapped_column(Date)
    wound_type: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    patient: Mapped[Patient] = relationship(back_populates="wounds")
    assessments: Mapped[list[Assessment]] = relationship(back_populates="wound")
