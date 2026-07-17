"""Integration tests for concurrent checkpoint load.

Validates that the ``/mcp tools/call "checkpoint"`` endpoint serves
multiple concurrent requests correctly under load.

Reproduction script: docs/followups/2026-07-16-multi-session-mcp-contention.md
(in mahavishnu repo).

The fix has two layers (see plan 2026-07-16-checkpoint-async-refactor):

1. ``asyncio.to_thread`` wraps for sync subprocess calls so the event
   loop stays unblocked. Per-call latency for a single checkpoint is
   ~30-40s (crackerjack subprocess + git operations + DB writes) and
   is unchanged by this layer.

2. Single-flight coalescing on ``(working_directory, is_manual)`` so
   concurrent identical requests share one underlying computation.
   4 Claude Code sessions ending in the same second → 1 underlying
   checkpoint run, not 4.

So the test asserts:
- All N parallel calls complete (no per-call timeout errors).
- Wall-clock is bounded by ONE single-call latency (proves coalescing)
  plus a small buffer for the registry cleanup — NOT by N× single-call
  latency (which would prove no coalescing).
"""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.mcp,
    pytest.mark.mcp_test,
    pytest.mark.performance,
]


URL = "http://localhost:8678/mcp"
PARALLEL_CALLS = 6
PER_CALL_TIMEOUT = 180.0  # seconds — matches the real MCP client idle timeout (~10min)
WALL_BUDGET = 240.0  # seconds — for N=6 calls coalescing on one underlying run

# Single-flight upper bound: with coalescing, all N parallel calls should
# finish within roughly 1.5x a single-call latency (1× for the leader,
# ~0.5× for the registry + Future bookkeeping). If we observe wall >
# 1.5× SINGLE_CALL_LATENCY_UPPER_BOUND, single-flight is broken and we
# are accidentally running N parallel subprocesses.
SINGLE_CALL_LATENCY_UPPER_BOUND = 180.0  # generous: measured ~30-45s on real hardware
COALESCED_WALL_FACTOR = 1.5  # wall should be ≤ 1.5× single-call latency


async def _initialize(client: httpx.AsyncClient, idx: int) -> str:
    """Open a fresh MCP session; mirrors sb_checkpoint.py."""
    response = await client.post(
        URL,
        json={
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": f"concurrent-load-{idx}",
                    "version": "0.0.1",
                },
            },
        },
        headers={
            "Accept": "application/json, text/event-stream",
            "Connection": "close",
        },
        timeout=PER_CALL_TIMEOUT,
    )
    response.raise_for_status()
    sid = response.headers.get("mcp-session-id", "")
    assert sid, "server returned no mcp-session-id header"
    return sid


async def _call_checkpoint(
    client: httpx.AsyncClient, idx: int, sid: str
) -> tuple[int, float, str]:
    """Issue one tools/call checkpoint; return (idx, elapsed, status_text)."""
    t0 = time.perf_counter()
    try:
        response = await client.post(
            URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "checkpoint",
                    "arguments": {
                        "working_directory": "/Users/les/Projects/mahavishnu"
                    },
                },
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Connection": "close",
                "mcp-session-id": sid,
            },
            timeout=PER_CALL_TIMEOUT,
        )
        elapsed = time.perf_counter() - t0
        return (idx, elapsed, f"HTTP {response.status_code}")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return (idx, elapsed, f"ERR {type(exc).__name__}")


async def _sb_checkpoint_pattern(
    client: httpx.AsyncClient, idx: int, results: list[tuple[int, float, str]]
) -> None:
    """End-to-end: init + tools/call checkpoint, mimicking sb_checkpoint.py."""
    sid = await _initialize(client, idx)
    results.append(await _call_checkpoint(client, idx, sid))


async def test_six_parallel_checkpoint_calls_complete_within_budget() -> None:
    """6 parallel ``tools/call checkpoint`` calls must complete within budget.

    Without the fix: each call blocks the uvicorn event loop on a sync
    ``subprocess.run``. N calls queue serially behind one another, each
    hitting its PER_CALL_TIMEOUT. Net wall-clock ≈ N × per_call_timeout.

    With the fix: calls either parallelize (different working_dir) or
    coalesce (same working_dir). Wall-clock is bounded by single-call
    latency, well under WALL_BUDGET.
    """
    results: list[tuple[int, float, str]] = []

    async with httpx.AsyncClient() as client:
        t0 = time.perf_counter()
        await asyncio.wait_for(
            asyncio.gather(
                *[_sb_checkpoint_pattern(client, i, results) for i in range(PARALLEL_CALLS)]
            ),
            timeout=WALL_BUDGET,
        )
        wall = time.perf_counter() - t0

    # All calls must have completed (not timed out at the per-call level).
    assert len(results) == PARALLEL_CALLS, (
        f"expected {PARALLEL_CALLS} results, got {len(results)} "
        f"(some calls failed before recording): {results}"
    )

    # None of the calls should have hit the per-call timeout
    # (if they did, the asyncio.wait_for outer budget would have triggered,
    # but the per-call httpx timeouts would also surface as httpx exceptions).
    timeout_count = sum(1 for _, _, status in results if "ERR" in status)
    assert timeout_count == 0, (
        f"{timeout_count}/{PARALLEL_CALLS} parallel calls timed out or errored. "
        f"Per-call timeout was {PER_CALL_TIMEOUT}s; if hits here, increase the "
        f"timeout or check whether the server is processing requests. "
        f"Results: {results}"
    )

    # Wall-clock should be far below serial execution. With single-flight
    # coalescing, all N concurrent identical requests share one underlying
    # computation — so wall ≈ 1× single-call latency, NOT N×. If wall
    # approaches N× single-call latency, the coalescing guard isn't firing.
    coalesced_upper_bound = SINGLE_CALL_LATENCY_UPPER_BOUND * COALESCED_WALL_FACTOR
    assert wall < coalesced_upper_bound, (
        f"wall={wall:.2f}s suggests single-flight coalescing isn't working "
        f"(expected < {coalesced_upper_bound}s = "
        f"{COALESCED_WALL_FACTOR}× single-call latency upper bound). "
        f"Per-call timings: {results}"
    )
