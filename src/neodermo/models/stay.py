"""A patient's dated stay at one establishment."""

from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from neodermo.extensions import db
from neodermo.models.types import new_id


class PatientStay(db.Model):
    """Link a patient to an establishment without changing the patient case."""

    __tablename__ = "patient_stays"
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="valid_date_range"
        ),
        Index(
            "uq_patient_stays_current_patient",
            "patient_id",
            unique=True,
            sqlite_where=text("end_date IS NULL"),
            postgresql_where=text("end_date IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    establishment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("establishments.id", ondelete="RESTRICT"), nullable=False,
        index=True,
    )
    service: Mapped[str | None] = mapped_column(String(200))
    room: Mapped[str | None] = mapped_column(String(50))
    bed: Mapped[str | None] = mapped_column(String(50))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)

    patient: Mapped[Patient] = relationship(back_populates="stays")
    establishment: Mapped[Establishment] = relationship(back_populates="stays")

    @validates("service", "room", "bed")
    def _normalize_location(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None
