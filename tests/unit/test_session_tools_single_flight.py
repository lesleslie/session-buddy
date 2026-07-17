"""Unit tests for single-flight coalescing in checkpoint_session_tool.

When multiple Claude Code sessions end within the same second, the
`Stop` hook fires `sb_checkpoint.py` for each one — multiple concurrent
calls to `tools/call "checkpoint"` with the same arguments. Without
single-flight, each call invokes `_checkpoint_impl` independently,
running the (heavy) crackerjack + git subprocess chain N times in
parallel — saturating the worker thread pool and timing out.

These tests pin the coalescing behavior:
- N concurrent identical calls share ONE underlying execution
- Coalesced callers receive the same result as the leader
- After completion, the in-flight registry is clean (next call runs fresh)
- Different (working_directory, is_manual) keys do NOT coalesce

The fixture rewrites `_checkpoint_impl` with a deterministic mock
that counts invocations and introduces a small delay so concurrent
gather() actually overlaps.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


# We patch the import target inside ``session_buddy.mcp.tools.session``.
# The actual production function is named ``_checkpoint_impl`` in
# ``session_tools.py``; we patch it via attribute assignment so the
# production module retains its own reference.


@pytest.fixture
def single_flight():
    """Import the production single-flight helper.

    Importing here (not at module top) lets the fixture fail with a
    useful ImportError message if the production symbol is renamed.
    """
    from session_buddy.mcp.tools.session.session_tools import (
        _in_flight_checkpoints,
        _single_flight_checkpoint,
    )

    # Test isolation: the in-flight registry is module-level state.
    # Different tests share it; without clearing, a stale entry from
    # a prior test can make subsequent identical calls coalesce onto
    # a future bound to the wrong loop (RuntimeError on await).
    _in_flight_checkpoints.clear()
    return _single_flight_checkpoint


@pytest.mark.asyncio
async def test_single_flight_collapses_identical_concurrent_calls(
    single_flight,
) -> None:
    """4 concurrent identical calls must invoke the underlying impl exactly once."""
    call_count = 0

    async def slow_impl(working_directory):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)  # ensure callers actually overlap
        return f"result-for-{working_directory}"

    with patch(
        "session_buddy.mcp.tools.session.session_tools._checkpoint_impl",
        new=slow_impl,
    ):
        results = await asyncio.gather(*[single_flight("/proj") for _ in range(4)])

    assert call_count == 1, (
        f"expected exactly 1 underlying call (single-flight), got {call_count}"
    )
    assert results == ["result-for-/proj"] * 4


@pytest.mark.asyncio
async def test_single_flight_distinct_working_directory_does_not_coalesce(
    single_flight,
) -> None:
    """Different working_directory keys must NOT coalesce."""
    call_count = 0

    async def slow_impl(working_directory):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.02)
        return f"result-for-{working_directory}"

    with patch(
        "session_buddy.mcp.tools.session.session_tools._checkpoint_impl",
        new=slow_impl,
    ):
        results = await asyncio.gather(
            single_flight("/proj-a"),
            single_flight("/proj-b"),
        )

    assert call_count == 2, (
        f"distinct keys should run independently; got {call_count}"
    )
    assert results == ["result-for-/proj-a", "result-for-/proj-b"]


@pytest.mark.asyncio
async def test_single_flight_registry_clears_after_completion(
    single_flight,
) -> None:
    """After the leader completes, the in-flight registry must be empty so a
    subsequent identical call runs a fresh computation (no stale cache)."""
    call_count = 0

    async def slow_impl(working_directory):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return f"call-{call_count}"

    with patch(
        "session_buddy.mcp.tools.session.session_tools._checkpoint_impl",
        new=slow_impl,
    ):
        first = await single_flight("/proj")
        second = await single_flight("/proj")

    assert call_count == 2, (
        "second identical call after first completes must run fresh (no stale reuse)"
    )
    assert first == "call-1"
    assert second == "call-2"


@pytest.mark.asyncio
async def test_single_flight_propagates_exception_to_all_waiters(single_flight) -> None:
    """If the leader raises, every coalesced waiter must see the same exception."""
    call_count = 0

    async def failing_impl(working_directory):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.02)
        raise RuntimeError("downstream blew up")

    with patch(
        "session_buddy.mcp.tools.session.session_tools._checkpoint_impl",
        new=failing_impl,
    ):
        coros = [single_flight("/proj") for _ in range(3)]
        results = await asyncio.gather(*coros, return_exceptions=True)

    assert call_count == 1
    assert all(isinstance(r, RuntimeError) for r in results)
    assert all(str(r) == "downstream blew up" for r in results)


@pytest.mark.asyncio
async def test_single_flight_concurrent_waiters_get_same_return_value(
    single_flight,
) -> None:
    """All coalesced waiters must receive the same value object the leader returned."""
    sentinel = object()

    async def impl_returning_sentinel(working_directory):
        await asyncio.sleep(0.05)
        return sentinel

    with patch(
        "session_buddy.mcp.tools.session.session_tools._checkpoint_impl",
        new=impl_returning_sentinel,
    ):
        results = await asyncio.gather(*[single_flight("/proj") for _ in range(5)])

    assert results == [sentinel] * 5
