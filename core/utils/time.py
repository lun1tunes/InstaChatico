from __future__ import annotations
from datetime import datetime, timezone


def now_utc() -> datetime:
    """Return timezone-aware UTC datetime.

    Preferred over deprecated/naive utcnow().
    """
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Convert any datetime to timezone-aware UTC.

    - Naive datetimes are treated as UTC and marked accordingly.
    - Aware datetimes are converted to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(dt: datetime | None = None) -> str:
    """Return ISO-8601 string in UTC for the given datetime (or now)."""
    return (dt or now_utc()).astimezone(timezone.utc).isoformat()


