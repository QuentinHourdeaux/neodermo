"""Add the initial wound-care domain schema.

Revision ID: 20260927T101720610587Z
Revises:
Create Date: 2026-09-27T10:17:20.610920+00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260927T101720610587Z"
down_revision = None
branch_labels = None
depends_on = None


def _choice(name: str, *values: str) -> sa.Enum:
    """Create a portable string enum with a named CHECK constraint."""
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def _utc_check(column: str) -> sa.CheckConstraint:
    """Require the fixed-width UTC form written by UTCDateTime."""
    pattern = (
        "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T"
        "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]."
        "[0-9][0-9][0-9][0-9][0-9][0-9]Z"
    )
    return sa.CheckConstraint(
        f"{column} IS NULL OR ("
        f"length({column}) = 27 AND {column} GLOB '{pattern}' "
        f"AND CAST(substr({column}, 1, 4) AS INTEGER) BETWEEN 1 AND 9999 "
        f"AND coalesce(date(substr({column}, 1, 10), '+0 days') = "
        f"substr({column}, 1, 10), 0) "
        f"AND CAST(substr({column}, 12, 2) AS INTEGER) BETWEEN 0 AND 23 "
        f"AND CAST(substr({column}, 15, 2) AS INTEGER) BETWEEN 0 AND 59 "
        f"AND CAST(substr({column}, 18, 2) AS INTEGER) BETWEEN 0 AND 59)",
        name=f"{column}_utc_format",
    )


def _measurement_check(column: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} IS NULL OR "
        f"({column} >= 0 AND {column} = CAST({column} AS NUMERIC) "
        f"AND {column} = ROUND({column}, 2))",
        name=f"{column.removesuffix('_cm')}_valid_centimeters",
    )


def upgrade() -> None:
    op.create_table(
        "establishments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("phone_number", sa.String(50)),
        sa.Column("email", sa.String(254)),
        sa.Column("notes", sa.Text()),
        sa.CheckConstraint(
            "length(trim(name)) > 0 AND name = trim(name)", name="name_present"
        ),
    )
    op.create_table(
        "patients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("reference", sa.String(15), nullable=False, unique=True),
        sa.Column("birth_date", sa.Date()),
        sa.Column("sex", _choice("patient_sex", "male", "female")),
        sa.Column("allergies", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("updated_at", sa.String(27), nullable=False),
        sa.Column("archived_at", sa.String(27)),
        sa.CheckConstraint(
            "length(trim(name)) > 0 AND name = trim(name)", name="name_present"
        ),
        _utc_check("created_at"),
        _utc_check("updated_at"),
        _utc_check("archived_at"),
    )
    op.create_table(
        "patient_stays",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patients.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "establishment_id",
            sa.String(36),
            sa.ForeignKey("establishments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("service", sa.String(200)),
        sa.Column("room", sa.String(50)),
        sa.Column("bed", sa.String(50)),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date()),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="valid_date_range"
        ),
    )
    op.create_index(
        "ix_patient_stays_establishment_id", "patient_stays", ["establishment_id"]
    )
    op.create_index(
        "uq_patient_stays_current_patient",
        "patient_stays",
        ["patient_id"],
        unique=True,
        sqlite_where=sa.text("end_date IS NULL"),
        postgresql_where=sa.text("end_date IS NULL"),
    )
    op.create_table(
        "wounds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patients.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("placement", sa.String(200)),
        sa.Column("treatment_start_date", sa.Date()),
        sa.Column("wound_type", sa.String(200)),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("closed_at", sa.String(27)),
        _utc_check("created_at"),
        _utc_check("closed_at"),
    )
    op.create_index("ix_wounds_patient_id", "wounds", ["patient_id"])

    op.create_table(
        "assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "wound_id",
            sa.String(36),
            sa.ForeignKey("wounds.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.String(27), nullable=False),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column(
            "evolution", _choice("assessment_evolution", "improved", "unchanged", "worsened")
        ),
        sa.Column("observations", sa.Text()),
        sa.Column("care_performed", sa.Text()),
        sa.Column("expected_outcome", sa.Text()),
        sa.Column(
            "exudate_level", _choice("assessment_exudate_level", "dry", "moist", "wet")
        ),
        sa.Column(
            "wound_color", _choice("assessment_wound_color", "red", "black", "yellow")
        ),
        sa.Column("odor", _choice("assessment_odor", "none", "mild", "strong")),
        sa.Column("infection", sa.Boolean()),
        sa.Column("length_cm", sa.Numeric(10, 2)),
        sa.Column("width_cm", sa.Numeric(10, 2)),
        sa.Column("depth_cm", sa.Numeric(10, 2)),
        sa.Column("remarks", sa.Text()),
        sa.Column("wound_edges", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("wound_tissue", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("periwound_skin", sa.JSON(), nullable=False, server_default="[]"),
        _utc_check("observed_at"),
        _utc_check("created_at"),
        sa.CheckConstraint("infection IS NULL OR infection IN (0, 1)", name="infection_boolean"),
        _measurement_check("length_cm"),
        _measurement_check("width_cm"),
        _measurement_check("depth_cm"),
    )
    op.create_index(
        "ix_assessments_wound_observed", "assessments", ["wound_id", "observed_at", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_assessments_wound_observed", table_name="assessments")
    op.drop_table("assessments")
    op.drop_index("ix_wounds_patient_id", table_name="wounds")
    op.drop_table("wounds")
    op.drop_index("uq_patient_stays_current_patient", table_name="patient_stays")
    op.drop_index("ix_patient_stays_establishment_id", table_name="patient_stays")
    op.drop_table("patient_stays")
    op.drop_table("patients")
    op.drop_table("establishments")
