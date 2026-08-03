"""Unit tests for ``session_buddy.hooks.single_flight.HookSingleFlight``.

Spec: docs/superpowers/specs/2026-07-29-session-buddy-extension-design.md (Q3).

The hook single-flight gate deduplicates *sequential* calls within a TTL
window for a given ``(project_path, agent_idx)`` key. Concurrent calls
collapse inside the existing ``_single_flight_checkpoint`` path; this
gate is the outer, time-based layer that suppresses noisy retries from
hook events (PreCompact, PostToolUse, etc.) firing back-to-back within
5 seconds.
"""

from __future__ import annotations

import asyncio

import pytest

from session_buddy.hooks.single_flight import HookSingleFlight

pytestmark = pytest.mark.unit


async def test_hook_single_flight_drops_second_within_ttl() -> None:
    flight = HookSingleFlight(ttl_seconds=5.0)
    ran: list[str] = []

    async def coro() -> None:
        ran.append("first")

    # First call within TTL: runs.
    assert await flight(("proj", 1), coro) is True
    # Second call within TTL: dropped.
    assert await flight(("proj", 1), coro) is False
    assert ran == ["first"]


async def test_hook_single_flight_allows_second_after_ttl() -> None:
    flight = HookSingleFlight(ttl_seconds=0.1)
    ran: list[str] = []

    async def coro() -> None:
        ran.append("x")

    assert await flight(("proj", 1), coro) is True
    await asyncio.sleep(0.15)
    assert await flight(("proj", 1), coro) is True
    assert ran == ["x", "x"]


async def test_hook_single_flight_distinct_keys_dont_block() -> None:
    flight = HookSingleFlight(ttl_seconds=5.0)
    ran: list[str] = []

    async def coro_a() -> None:
        ran.append("a")

    async def coro_b() -> None:
        ran.append("b")

    assert await flight(("proj", 1), coro_a) is True
    assert await flight(("proj", 2), coro_b) is True
    assert sorted(ran) == ["a", "b"]


async def test_hook_single_flight_preserves_return_when_dropped() -> None:
    flight = HookSingleFlight(ttl_seconds=5.0)
    calls = {"n": 0}

    async def coro() -> None:
        calls["n"] += 1

    assert await flight(("proj", 1), coro) is True
    # Second call dropped, no exception raised, factory not called.
    assert await flight(("proj", 1), coro) is False
    assert calls["n"] == 1
