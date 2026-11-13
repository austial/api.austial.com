from __future__ import annotations

from datetime import UTC, datetime


def now_utc() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """The ORM returns naive datetimes for UTC columns; make them aware again."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def to_db(value: datetime) -> datetime:
    """Store UTC as naive (the columns are timestamp without time zone)."""
    return as_utc(value).replace(tzinfo=None)


def iso(value: datetime) -> str:
    return as_utc(value).isoformat().replace("+00:00", "Z")


def parse_iso(text: str) -> datetime:
    return as_utc(datetime.fromisoformat(text))
