"""Integration tests for concurrent checkpoint load.

Validates that the `/mcp tools/call "checkpoint"` endpoint can serve
multiple concurrent requests without serializing them on a sync lock
or blocking the asyncio event loop.

Reproduction script: docs/followups/2026-07-16-multi-session-mcp-contention.md
(in mahavishnu repo). Without the fix, 6 parallel calls timeout because
``crackerjack_integration.execute_command`` uses ``subprocess.run``
synchronously inside an async server, blocking uvicorn's event loop
for the duration of each crackerjack run.

With the fix (asyncio.create_subprocess_exec + single-flight coalescing
on (cmd, cwd)), concurrent calls either:
- Parallelize when their (cmd, cwd) keys differ, OR
- Coalesce into one subprocess when keys match.

Either outcome means the wall-clock for N parallel calls is bounded
by the single-call latency, not N times that.
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
PER_CALL_TIMEOUT = 30.0  # seconds — matches MCP client's default
WALL_BUDGET = 90.0  # seconds — for N=6 calls, this is well above single-call latency


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
        f"Without the fix this is expected; with the fix it indicates "
        f"crackerjack_integration is still serializing. Results: {results}"
    )

    # Wall-clock should be far below serial execution. With the fix,
    # 6 calls complete in roughly the same time as 1 (single-flight
    # coalescing) or up to N× faster than serial.
    serial_lower_bound = PARALLEL_CALLS * 5.0  # even a fast call takes >5s
    assert wall < serial_lower_bound, (
        f"wall={wall:.2f}s suggests serialization (expected < {serial_lower_bound}s). "
        f"Per-call timings: {results}"
    )
