"""Dated wound observations and their multiselect findings."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from neodermo.extensions import db
from neodermo.models.enums import (
    Evolution,
    ExudateLevel,
    FindingCategory,
    FindingValue,
    Odor,
    WoundColor,
    stored_enum,
)
from neodermo.models.types import UTCDateTime, new_id, utc_now


class Assessment(db.Model):
    """One observation of one wound at a nurse-selected time."""

    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(
            "length_cm IS NULL OR "
            "(length_cm >= 0 AND length_cm = CAST(length_cm AS NUMERIC))",
            name="length_nonnegative",
        ),
        CheckConstraint(
            "width_cm IS NULL OR "
            "(width_cm >= 0 AND width_cm = CAST(width_cm AS NUMERIC))",
            name="width_nonnegative",
        ),
        CheckConstraint(
            "depth_cm IS NULL OR "
            "(depth_cm >= 0 AND depth_cm = CAST(depth_cm AS NUMERIC))",
            name="depth_nonnegative",
        ),
        CheckConstraint("infection IS NULL OR infection IN (0, 1)", name="infection_boolean"),
        Index("ix_assessments_wound_observed", "wound_id", "observed_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    wound_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wounds.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    evolution: Mapped[Evolution | None] = mapped_column(
        stored_enum(Evolution, "assessment_evolution")
    )
    observations: Mapped[str | None] = mapped_column(Text)
    care_performed: Mapped[str | None] = mapped_column(Text)
    expected_outcome: Mapped[str | None] = mapped_column(Text)
    exudate_level: Mapped[ExudateLevel | None] = mapped_column(
        stored_enum(ExudateLevel, "assessment_exudate_level")
    )
    wound_color: Mapped[WoundColor | None] = mapped_column(
        stored_enum(WoundColor, "assessment_wound_color")
    )
    odor: Mapped[Odor | None] = mapped_column(stored_enum(Odor, "assessment_odor"))
    infection: Mapped[bool | None] = mapped_column()
    length_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2, asdecimal=True))
    width_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2, asdecimal=True))
    depth_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2, asdecimal=True))
    remarks: Mapped[str | None] = mapped_column(Text)

    wound: Mapped[Wound] = relationship(back_populates="assessments")
    findings: Mapped[list[AssessmentFinding]] = relationship(back_populates="assessment")


class AssessmentFinding(db.Model):
    """One selected edge, tissue, or periwound value on an assessment."""

    __tablename__ = "assessment_findings"
    __table_args__ = (
        CheckConstraint(
            "(category = 'wound_edges' AND value IN "
            "('hollowed', 'maceration', 'hyperkeratosis', 'eczema', "
            "'epithelialization', 'normal')) OR "
            "(category = 'wound_tissue' AND value IN "
            "('layer', 'epithelialization', 'granulation', 'necrosis', 'intact')) OR "
            "(category = 'periwound_skin' AND value IN "
            "('redness', 'warmth', 'swelling', 'normal', 'eczema'))",
            name="valid_category_value",
        ),
    )

    assessment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessments.id", ondelete="RESTRICT"), primary_key=True
    )
    category: Mapped[FindingCategory] = mapped_column(
        stored_enum(FindingCategory, "assessment_finding_category"), primary_key=True
    )
    value: Mapped[FindingValue] = mapped_column(
        stored_enum(FindingValue, "assessment_finding_value"), primary_key=True
    )

    assessment: Mapped[Assessment] = relationship(back_populates="findings")
