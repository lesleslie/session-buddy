"""Unit tests for ``session_buddy.mcp.tools.tasks_security``.

Per the Task 3 brief, these tests pin:

- ``RateLimiter`` sliding-window quota: over quota blocks, per-caller
  isolation holds, and ``RateLimitError`` carries the configured
  limit + window so callers can surface a useful message.
- ``enforce_visibility_filter`` allows owners (private/team), blocks
  non-owners on private/team, and lets anyone through on public.
- Spec §Input Limits constants are pinned to the documented values.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from session_buddy.mcp.tools.tasks_models import Task, new_task_id
from session_buddy.mcp.tools.tasks_security import (
    MAX_CONTENT_BYTES,
    MAX_METADATA_BYTES,
    MAX_TAG_LEN,
    MAX_TAGS,
    RateLimiter,
    RateLimitError,
    enforce_visibility_filter,
)


def _make_task(**overrides: object) -> Task:
    base: dict[str, object] = {
        "id": new_task_id(),
        "content": "x",
        "owner": "user:alice@example.com",
        "visibility": "private",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "tags": ["task", "private"],
    }
    base.update(overrides)
    return Task(**base)  # type: ignore[arg-type]


def test_rate_limiter_blocks_over_quota() -> None:
    rl = RateLimiter(limit=2, window_seconds=60)
    rl.check("caller_1")
    rl.check("caller_1")
    with pytest.raises(RateLimitError):
        rl.check("caller_1")  # 3rd hits limit


def test_rate_limiter_resets_after_window() -> None:
    # Brief's original draft was a no-op test (called check() three times
    # at the same real-clock instant — third call still blocked). Fixed
    # by pinning each call to an explicit ``now`` so we can advance the
    # sliding window past window_seconds.
    rl = RateLimiter(limit=2, window_seconds=1)
    rl.check("caller_1", now=1000.0)
    rl.check("caller_1", now=1000.5)
    with pytest.raises(RateLimitError):
        rl.check("caller_1", now=1000.9)  # still inside window → blocked
    # Advance past window_seconds: window_start = 1002.0 - 1 = 1001.0
    # Both prior entries (1000.0, 1000.5) drop; new entry admitted.
    rl.check("caller_1", now=1002.0)


def test_rate_limiter_per_caller_isolation() -> None:
    rl = RateLimiter(limit=1, window_seconds=60)
    rl.check("caller_A")
    with pytest.raises(RateLimitError):
        rl.check("caller_A")  # 2nd call from A blocked
    rl.check("caller_B")  # B unaffected — separate bucket


def test_rate_limit_error_carries_quota_info() -> None:
    rl = RateLimiter(limit=1, window_seconds=60)
    rl.check("caller_1", now=1000.0)
    with pytest.raises(RateLimitError) as excinfo:
        rl.check("caller_1", now=1000.5)
    msg = str(excinfo.value)
    # Caller + limit + window + retry hint all surfaced for ops debugging.
    assert "caller_1" in msg
    assert "1" in msg  # limit
    assert "60" in msg  # window_seconds


def test_enforce_visibility_filter_blocks_private_for_non_owner() -> None:
    task = _make_task(visibility="private")
    assert enforce_visibility_filter("user:alice@example.com", task) is True
    assert enforce_visibility_filter("user:bob@example.com", task) is False


def test_enforce_visibility_filter_treats_team_as_private_in_v1() -> None:
    # Spec v1: team visibility == private (no team ACL yet; v1.1 follow-up).
    task = _make_task(visibility="team")
    assert enforce_visibility_filter("user:alice@example.com", task) is True
    assert enforce_visibility_filter("user:bob@example.com", task) is False


def test_enforce_visibility_filter_allows_public_for_anyone() -> None:
    task = _make_task(visibility="public", owner=None)
    assert enforce_visibility_filter("user:anyone@example.com", task) is True
    assert enforce_visibility_filter("user:stranger@example.com", task) is True


def test_input_cap_constants_match_spec() -> None:
    assert MAX_CONTENT_BYTES == 4096
    assert MAX_METADATA_BYTES == 1024
    assert MAX_TAGS == 32
    assert MAX_TAG_LEN == 64
