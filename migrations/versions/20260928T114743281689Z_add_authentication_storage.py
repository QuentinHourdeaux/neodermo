"""Add authentication storage without changing domain tables.

Revision ID: 20260928T114743281689Z
Revises: 20260927T101720610587Z
"""

import sqlalchemy as sa
from alembic import op

revision = "20260928T114743281689Z"
down_revision = "20260927T101720610587Z"
branch_labels = None
depends_on = None


def _utc_check(column: str) -> sa.CheckConstraint:
    """Freeze the UTC storage check so later model changes cannot alter history."""
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


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.CheckConstraint(
            "length(email) BETWEEN 3 AND 254 AND email = trim(email) "
            "AND email = lower(email)", name="email_normalized",
        ),
        sa.CheckConstraint("length(password_hash) > 0", name="password_hash_present"),
        _utc_check("created_at"),
    )
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("expires_at", sa.String(27), nullable=False),
        sa.CheckConstraint(
            "length(token_digest) = 64 AND token_digest NOT GLOB '*[^0-9a-f]*'",
            name="token_digest_sha256",
        ),
        sa.CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        _utc_check("created_at"),
        _utc_check("expires_at"),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"]
    )
    op.create_index(
        "ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"]
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("expires_at", sa.String(27), nullable=False),
        sa.Column("csrf_secret", sa.String(43), nullable=False),
        sa.CheckConstraint(
            "length(token_digest) = 64 AND token_digest NOT GLOB '*[^0-9a-f]*'",
            name="token_digest_sha256",
        ),
        sa.CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        sa.CheckConstraint(
            "length(csrf_secret) = 43 AND csrf_secret NOT GLOB '*[^A-Za-z0-9_-]*'",
            name="csrf_secret_format",
        ),
        _utc_check("created_at"),
        _utc_check("expires_at"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(
        "ix_password_reset_tokens_expires_at", table_name="password_reset_tokens"
    )
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("users")
