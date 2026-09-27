"""Dated wound observations and their multiselect findings."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.types import TypeDecorator

from neodermo.extensions import db
from neodermo.models.enums import (
    Evolution,
    ExudateLevel,
    Odor,
    PeriwoundSkin,
    WoundColor,
    WoundEdge,
    WoundTissue,
    stored_enum,
)
from neodermo.models.types import UTCDateTime, new_id, utc_now, utc_text_check


class FindingList(TypeDecorator[list[StrEnum]]):
    """Store an enum list as JSON and validate every value on each write."""

    impl = JSON
    cache_ok = True

    def __init__(self, enum_class: type[StrEnum], field_name: str):
        super().__init__()
        self.enum_class = enum_class
        self.field_name = field_name

    def process_bind_param(self, values: list[StrEnum], dialect) -> list[str]:
        if not isinstance(values, list):
            raise ValueError(f"{self.field_name} must be a list")
        try:
            stored = [self.enum_class(value).value for value in values]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{self.field_name} contains an invalid value") from exc
        if len(stored) != len(set(stored)):
            raise ValueError(f"{self.field_name} contains a duplicate value")
        return stored

    def process_result_value(self, values: list[str], dialect) -> list[StrEnum]:
        if not isinstance(values, list):
            raise ValueError(f"Stored {self.field_name} must be a list")
        return [self.enum_class(value) for value in values]


class Assessment(db.Model):
    """One observation of one wound at a nurse-selected time."""

    __tablename__ = "assessments"
    __table_args__ = (
        utc_text_check("observed_at"),
        utc_text_check("created_at"),
        CheckConstraint(
            "length_cm IS NULL OR "
            "(length_cm >= 0 AND length_cm = CAST(length_cm AS NUMERIC) "
            "AND length_cm = ROUND(length_cm, 2))",
            name="length_valid_centimeters",
        ),
        CheckConstraint(
            "width_cm IS NULL OR "
            "(width_cm >= 0 AND width_cm = CAST(width_cm AS NUMERIC) "
            "AND width_cm = ROUND(width_cm, 2))",
            name="width_valid_centimeters",
        ),
        CheckConstraint(
            "depth_cm IS NULL OR "
            "(depth_cm >= 0 AND depth_cm = CAST(depth_cm AS NUMERIC) "
            "AND depth_cm = ROUND(depth_cm, 2))",
            name="depth_valid_centimeters",
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
    wound_edges: Mapped[list[WoundEdge]] = mapped_column(
        MutableList.as_mutable(FindingList(WoundEdge, "wound_edges")),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    wound_tissue: Mapped[list[WoundTissue]] = mapped_column(
        MutableList.as_mutable(FindingList(WoundTissue, "wound_tissue")),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    periwound_skin: Mapped[list[PeriwoundSkin]] = mapped_column(
        MutableList.as_mutable(FindingList(PeriwoundSkin, "periwound_skin")),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )

    wound: Mapped[Wound] = relationship(back_populates="assessments")

    @validates("length_cm", "width_cm", "depth_cm")
    def _validate_measurement(self, key: str, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{key} must be a decimal number") from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError(f"{key} must be nonnegative and finite")
        if amount.as_tuple().exponent < -2:
            raise ValueError(f"{key} must have at most two decimal places")
        return amount
