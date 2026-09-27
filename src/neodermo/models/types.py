"""Small persistence types shared by the domain models."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, String
from sqlalchemy.types import TypeDecorator


def new_id() -> str:
    """Generate a stable, opaque record identifier."""
    return str(uuid4())


def new_patient_reference() -> str:
    """Generate a short case reference unrelated to patient details."""
    return f"ND-{uuid4().hex[:12].upper()}"


def utc_now() -> datetime:
    """Return an aware server timestamp in UTC."""
    return datetime.now(UTC)


def utc_text_check(column: str) -> CheckConstraint:
    """Require the canonical UTC text that UTCDateTime writes in SQLite."""
    pattern = (
        "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T"
        "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]."
        "[0-9][0-9][0-9][0-9][0-9][0-9]Z"
    )
    return CheckConstraint(
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


class UTCDateTime(TypeDecorator[datetime]):
    """Store aware datetimes as canonical, sortable UTC text in SQLite.

    SQLite's ordinary DATETIME storage omits offset information. Requiring
    aware input and storing a fixed-width UTC value keeps observation times
    unambiguous and makes chronological ordering reliable.
    """

    impl = String(27)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A timezone-aware datetime is required")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )

    def process_result_value(self, value: str | None, dialect) -> datetime | None:
        if value is None:
            return None
        if not value.endswith("Z"):
            raise ValueError("Stored datetime must be in UTC")
        return datetime.fromisoformat(f"{value[:-1]}+00:00")
