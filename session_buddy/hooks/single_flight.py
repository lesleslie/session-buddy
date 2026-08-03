"""Session-Buddy hook single-flight gate.

Drops the second of two rapid hook invocations within a TTL window, keyed
by ``(project_path, agent_idx)``. Pure in-process state — no new schema,
no external dependencies beyond ``asyncio`` and the stdlib.

This is the *outer* gate. The existing ``_single_flight_checkpoint``
helper in
``session_buddy/mcp/tools/session/session_tools.py`` already collapses
*concurrent* identical in-flight requests into one underlying execution;
this module deduplicates *sequential* hook retries (PreCompact, PostToolUse)
that fire back-to-back within ``ttl_seconds``.

Spec:
    docs/superpowers/specs/2026-07-29-session-buddy-extension-design.md (Q3)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


class HookSingleFlight:
    """Time-based dedup gate for hook callbacks.

    A call is dropped (returns ``False``, factory not invoked) when the
    same ``key`` was seen within ``ttl_seconds``. Otherwise the factory
    runs and the timestamp updates — the next call within TTL will be
    dropped.

    All access to ``_last_seen`` is serialised through a single
    :class:`asyncio.Lock`. No loop-bound globals; the lock is created
    lazily on the first call, so test isolation is preserved across
    pytest-asyncio's per-test event loops.
    """

    def __init__(self, ttl_seconds: float = 5.0) -> None:
        self._ttl = ttl_seconds
        self._last_seen: dict[tuple[str, int], float] = {}
        self._lock: asyncio.Lock | None = None

    async def __call__(
        self,
        key: tuple[str, int],
        coro_factory: Callable[[], Awaitable[Any]],
    ) -> bool:
        lock = self._lock
        if lock is None:
            lock = self._lock = asyncio.Lock()

        async with lock:
            now = time.monotonic()
            last = self._last_seen.get(key)
            if last is not None and (now - last) < self._ttl:
                return False
            self._last_seen[key] = now

        await coro_factory()
        return True
