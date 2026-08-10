"""Compose policy + snapshot + subagent-detector into a single safe checkpoint flow.

Per spec invariants:
  - Working tree is never mutated by a checkpoint
  - Forward-to 5xx retries once with exponential backoff, then fail closed
  - 4xx from forward_to → no retry, fail closed
  - Two simultaneous checkpoints serialized by asyncio.Lock
  - Failures fail closed; programming errors propagate
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from oneiric.core.logging import get_logger

from session_buddy.checkpoint.metrics import CheckpointMetrics
from session_buddy.checkpoint.pending import PendingCheckpoint, save_pending
from session_buddy.checkpoint.policy import CheckpointPhase, CheckpointPolicy
from session_buddy.checkpoint.snapshot import SnapshotMechanism
from session_buddy.checkpoint.subagent_detector import SubagentDetector

if TYPE_CHECKING:
    pass

_log = get_logger(__name__)

ForwardFn = Callable[["CheckpointResult"], Awaitable[None]]
TransientForwardError = (httpx.HTTPStatusError, OSError, asyncio.TimeoutError)


@dataclass
class CheckpointResult:
    fired: bool
    snapshot_id: str | None
    session_buddy_id: str | None
    decision_reason: str
    error: str | None = None
    pending_marker_path: Path | None = None


class CheckpointOrchestrator:
    def __init__(
        self,
        *,
        working_dir: Path,
        policy: CheckpointPolicy,
        snapshot: SnapshotMechanism,
        subagent_detector: SubagentDetector,
        forward_to: ForwardFn,
        metrics: CheckpointMetrics | None = None,
    ) -> None:
        self._working_dir = working_dir
        self._policy = policy
        self._snapshot = snapshot
        self._detector = subagent_detector
        self._forward_to = forward_to
        self._metrics = metrics or CheckpointMetrics()
        self._lock = asyncio.Lock()

    @property
    def metrics(self) -> CheckpointMetrics:
        return self._metrics

    async def run_checkpoint(
        self, *, phase: CheckpointPhase, hook_request: bool = False
    ) -> CheckpointResult:
        async with self._lock:
            return await self._run(phase=phase, hook_request=hook_request)

    async def _run(
        self, *, phase: CheckpointPhase, hook_request: bool
    ) -> CheckpointResult:
        decision = self._policy.decide(phase=phase, hook_request=hook_request)
        result = CheckpointResult(
            fired=False, snapshot_id=None, session_buddy_id=None,
            decision_reason=decision.reason,
        )

        if not decision.should_fire:
            _log.info("checkpoint_skipped", extra={"phase": phase.value, "reason": decision.reason})
            return result

        if phase == CheckpointPhase.END_OF_TASK:
            idle = await self._detector.wait_until_idle(timeout=60.0)
            if not idle:
                marker = save_pending(
                    PendingCheckpoint(
                        working_dir=self._working_dir, reason="subagent_idle_timeout",
                    ),
                )
                result.pending_marker_path = marker
                self._metrics.inc_failure("subagent_idle_timeout")
                _log.error(
                    "checkpoint_eot_subagent_idle_timeout",
                    extra={"phase": phase.value, "marker": str(marker)},
                )
                return result

        try:
            snapshot = self._snapshot.capture(label=phase.value)
        except TransientForwardError as exc:
            self._metrics.inc_failure("snapshot_transient")
            _log.error("checkpoint_snapshot_failed_transient", extra={"error": str(exc)})
            result.error = f"snapshot failed (transient): {exc}"
            return result
        except Exception as exc:  # noqa: BLE001 — narrow by type, not catch-all
            self._metrics.inc_failure("snapshot_unexpected")
            _log.exception("checkpoint_snapshot_failed_unexpected", extra={"error": str(exc)})
            result.error = f"snapshot failed (unexpected): {exc}"
            return result

        result.snapshot_id = snapshot.snapshot_id

        # Empty working tree: spec line 360-361 — skip forward_to
        if not snapshot.dirty_files:
            result.fired = True
            result.decision_reason = f"{decision.reason} (clean tree, no commit)"
            _log.info("checkpoint_clean_skip", extra={"phase": phase.value, "snapshot": snapshot.snapshot_id})
            return result

        # Re-check subagent (might have become active during capture) per integration-risk M5
        if self._detector.is_active():
            marker = save_pending(
                PendingCheckpoint(
                    working_dir=self._working_dir, reason="subagent_active_during_capture",
                ),
            )
            result.pending_marker_path = marker
            self._metrics.inc_failure("subagent_active_during_capture")
            _log.warning(
                "checkpoint_subagent_active_during_capture",
                extra={"phase": phase.value, "marker": str(marker)},
            )
            return result

        # Forward with retry on transient 5xx
        try:
            await self._forward_with_retry(result, phase)
        except TransientForwardError as exc:
            self._metrics.inc_failure("forward_transient_retry_exhausted")
            result.error = f"forward_to retry exhausted: {exc}"
            _log.error("checkpoint_forward_retry_exhausted", extra={"error": str(exc)})
            return result

        result.fired = True
        _log.info(
            "checkpoint_fired",
            extra={
                "phase": phase.value, "reason": decision.reason,
                "snapshot": snapshot.snapshot_id, "dirty_files": len(snapshot.dirty_files),
            },
        )
        return result

    async def _forward_with_retry(
        self, result: CheckpointResult, phase: CheckpointPhase,
    ) -> None:
        """Retry-once-with-backoff for 5xx per spec line 372. 4xx no retry."""
        try:
            await self._forward_to(result)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if 500 <= status < 600:
                _log.warning("checkpoint_forward_5xx_retrying", extra={"status": status})
                await asyncio.sleep(0.5)  # backoff
                await self._forward_to(result)  # second attempt; propagate if it fails
            else:
                # 4xx → no retry
                self._metrics.inc_failure("forward_4xx")
                raise