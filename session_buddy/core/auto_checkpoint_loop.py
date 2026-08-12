"""Background asyncio timer that fires CheckpointOrchestrator at
`settings.auto_checkpoint_interval` seconds, AND drains pending-checkpoint
markers from prior subagent-timeout events.

Closes the gap where `auto_checkpoint_interval=1800` was defined but never
consumed. Also consumes `~/.session-buddy/pending/*.json` markers — each
represents an end-of-task checkpoint that was deferred when a subagent was
still active.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from oneiric.core.logging import get_logger

from session_buddy.checkpoint.scrubbing import safe_transient_info

if TYPE_CHECKING:
    from session_buddy.checkpoint import CheckpointOrchestrator

_log = get_logger(__name__)


class AutoCheckpointLoop:
    def __init__(
        self,
        *,
        interval_s: int,
        working_dir_resolver: Callable[[], Path],
        orch_factory: Callable[[Path], CheckpointOrchestrator],
        pending_consume_fn: Callable[[Path], Awaitable[None]] | None = None,
        forward_to_factory: Callable[[Path], object] | None = None,
    ) -> None:
        if interval_s < 0:
            raise ValueError("interval_s must be >= 0")
        self._interval_s = interval_s
        self._resolver = working_dir_resolver
        self._orch_factory = orch_factory
        self._pending_consume_fn = pending_consume_fn
        # forward_to_factory is accepted for API parity with the lifespan
        # wiring in :mod:`session_buddy.mcp.server` (the lifespan builds the
        # orchestrator with the resolved forward-fn before passing it in via
        # orch_factory). The loop itself does not invoke it directly.
        self._forward_to_factory = forward_to_factory
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        if self._interval_s == 0:
            _log.info("auto_checkpoint_loop_disabled", extra={"reason": "interval=0"})
            return
        if self._task is not None and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(), name="auto-checkpoint-loop")
        _log.info(
            "auto_checkpoint_loop_started", extra={"interval_s": self._interval_s}
        )

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
            _log.debug(
                "auto_checkpoint_loop_stop_completed",
                extra=safe_transient_info(exc),
            )
        self._task = None
        _log.info("auto_checkpoint_loop_stopped")

    async def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self._drain_pending()
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "auto_checkpoint_loop_tick_error", extra=safe_transient_info(exc)
                )
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_s)

    async def _tick(self) -> None:
        from session_buddy.checkpoint import CheckpointPhase

        working_dir = self._resolver()
        orch = self._orch_factory(working_dir)
        await orch.run_checkpoint(phase=CheckpointPhase.MIDPOINT_TIME)

    async def _drain_pending(self) -> None:
        if self._pending_consume_fn is None:
            return
        from session_buddy.checkpoint.pending import PENDING_DIR

        if not PENDING_DIR.exists():
            return
        for marker in PENDING_DIR.glob("*.json"):
            try:
                await self._pending_consume_fn(marker)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "pending_consume_failed",
                    extra={"marker": str(marker)} | safe_transient_info(exc),
                )


async def _midpoint_commit_forward(working_dir: Path) -> None:
    """When midpoint_commits_enabled=True, route through the legacy git commit path.

    Reuses session_buddy's create_checkpoint_commit utility directly. Skips
    the SessionManager ceremony (cross-repo accounting, conversation
    storage) — those are bound to a conversation_id that the timer doesn't
    have. Midpoint commits are local, periodic, low-stakes.
    """
    import asyncio

    from session_buddy.utils.git_worktrees import create_checkpoint_commit

    await asyncio.to_thread(
        create_checkpoint_commit,
        working_dir,
        working_dir.name,
        0,  # quality_score placeholder — midpoint doesn't compute it
    )


@dataclass
class QualityDeltaSignal:
    """New value-add signal: fires when quality score delta exceeds threshold.

    Pairs with settings.midpoint_commit_min_quality_delta (default 10).
    Inactive when no quality source is wired — the provider returns (None, None).
    """

    min_delta: int = 10
    quality_provider: Callable[[], tuple[int | None, int | None]] | None = None

    def is_active(self, _working_tree: object) -> bool:
        if self.quality_provider is None:
            return False
        prev, curr = self.quality_provider()
        if prev is None or curr is None:
            return False
        return abs(curr - prev) >= self.min_delta

    def describe(self) -> str:
        return f"{self.min_delta}+ quality score delta"


__all__ = [
    "AutoCheckpointLoop",
    "QualityDeltaSignal",
    "_midpoint_commit_forward",
]
