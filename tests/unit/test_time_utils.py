from datetime import UTC, datetime

import pytest

from session_buddy.utils.time import parse_utc_timestamp, utc_now


def test_utc_now_returns_aware_utc() -> None:
    value = utc_now()
    assert value.tzinfo is UTC


def test_parse_utc_timestamp_adds_utc_to_legacy_naive_value() -> None:
    value = parse_utc_timestamp('2026-07-27T12:00:00')
    assert value == datetime(2026, 7, 27, 12, tzinfo=UTC)


def test_parse_utc_timestamp_converts_offset_value_to_utc() -> None:
    value = parse_utc_timestamp('2026-07-27T05:00:00-07:00')
    assert value == datetime(2026, 7, 27, 12, tzinfo=UTC)


def test_parse_utc_timestamp_accepts_datetime() -> None:
    value = parse_utc_timestamp(datetime(2026, 7, 27, 12, tzinfo=UTC))
    assert value.tzinfo is UTC


def test_parse_utc_timestamp_adds_utc_to_naive_datetime() -> None:
    value = parse_utc_timestamp(datetime(2026, 7, 27, 12))  # noqa: DTZ001
    assert value == datetime(2026, 7, 27, 12, tzinfo=UTC)


def test_parse_utc_timestamp_rejects_empty_text() -> None:
    with pytest.raises(ValueError):
        parse_utc_timestamp('')
