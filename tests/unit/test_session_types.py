from __future__ import annotations

from datetime import datetime


def test_session_type_dataclasses_store_values() -> None:
    from session_buddy.session_types import (
        RecurrenceInterval,
        SQLCondition,
        TimeRange,
    )

    start = datetime(2026, 1, 1, 10, 0, 0)
    end = datetime(2026, 1, 1, 11, 0, 0)

    time_range = TimeRange(start=start, end=end)
    condition = SQLCondition(
        condition="created_at >= ?",
        params=[start],
    )
    recurrence = RecurrenceInterval(frequency="daily", interval=3)

    assert time_range.start == start
    assert time_range.end == end
    assert condition.condition == "created_at >= ?"
    assert condition.params == [start]
    assert recurrence.frequency == "daily"
    assert recurrence.interval == 3
