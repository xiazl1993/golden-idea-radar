from __future__ import annotations

from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """Return UTC as a naive datetime for cross-dialect SQLAlchemy comparisons."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
