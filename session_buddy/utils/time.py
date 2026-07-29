from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current instant as an aware UTC datetime."""
    return datetime.now(UTC)


def parse_utc_timestamp(value: str | datetime) -> datetime:
    """Parse a timestamp and normalize it to aware UTC.

    Naive legacy values are interpreted as UTC to preserve existing stored data.
    """
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
