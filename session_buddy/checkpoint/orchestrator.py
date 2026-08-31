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
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx2 as httpx
from oneiric.core.logging import get_logger

from session_buddy.checkpoint.metrics import CheckpointMetrics
from session_buddy.checkpoint.pending import PendingCheckpoint, save_pending
from session_buddy.checkpoint.policy import CheckpointPhase, CheckpointPolicy
from session_buddy.checkpoint.scrubbing import safe_error_message, safe_transient_info
from session_buddy.checkpoint.snapshot import SnapshotMechanism
from session_buddy.checkpoint.subagent_detector import SubagentDetector

_log = get_logger(__name__)

ForwardFn = Callable[["CheckpointResult"], Awaitable[None]]
# Narrow tuple per spec: subprocess + OS + ValueError + httpx 5xx are the
# transient errors the snapshot step may retry against. asyncio.TimeoutError
# is intentionally absent — the outer asyncio.wait_for budget (line 113)
# catches the run timeout independently, and nested asyncio.TimeoutError
# from snapshot.capture() is a programming error that must propagate.
TransientForwardError = (
    subprocess.SubprocessError,
    OSError,
    ValueError,
    httpx.HTTPStatusError,
)

# Default outer budget for the full checkpoint cycle. The detector's
# wait_until_idle timeout (60s by default) is nested inside, so this must
# exceed detector.idle_timeout + headroom for snapshot + forward + retries.
DEFAULT_RUN_TIMEOUT_S = 120.0


def _safe_http_error_info(exc: httpx.HTTPStatusError) -> dict[str, object]:
    """Operator-visible fields from HTTPStatusError. NEVER echoes URL path,
    query, userinfo, or response body. Includes only the status code and
    the request-target host (no path).
    """
    info: dict[str, object] = {"status": exc.response.status_code}
    request = getattr(exc, "request", None)
    if request is not None:
        try:
            host = request.url.host  # may raise or be empty for some schemes
        except AttributeError, ValueError, TypeError:
            host = None
        if host:
            info["host"] = host
    return info


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
        run_timeout: float = DEFAULT_RUN_TIMEOUT_S,
    ) -> None:
        self._working_dir = working_dir
        self._policy = policy
        self._snapshot = snapshot
        self._detector = subagent_detector
        self._forward_to = forward_to
        self._metrics = metrics or CheckpointMetrics()
        self._lock = asyncio.Lock()
        self._run_timeout = run_timeout

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
        """Outer wrapper that enforces a bounded total runtime.

        Per Finding 2 (fail-open-resource-cap): wait_until_idle(60s) only
        covers the idle-wait, not subsequent snapshot/forward work. A slow
        snapshot.capture or stuck forward_to could otherwise block the
        caller indefinitely. We wrap the whole implementation in
        asyncio.wait_for and fail closed on timeout — the working tree is
        never mutated by a checkpoint, so cancellation is safe.
        """
        try:
            return await asyncio.wait_for(
                self._run_impl(phase=phase, hook_request=hook_request),
                timeout=self._run_timeout,
            )
        except TimeoutError:
            self._metrics.inc_failure("orchestrator_timeout")
            _log.warning(
                "checkpoint_orchestrator_timeout",
                extra={"phase": phase.value, "timeout_s": self._run_timeout},
            )
            return CheckpointResult(
                fired=False,
                snapshot_id=None,
                session_buddy_id=None,
                decision_reason="orchestrator_timeout",
                error="orchestrator timeout",
            )

    async def _run_impl(
        self, *, phase: CheckpointPhase, hook_request: bool
    ) -> CheckpointResult:
        decision = self._policy.decide(phase=phase, hook_request=hook_request)
        result = CheckpointResult(
            fired=False,
            snapshot_id=None,
            session_buddy_id=None,
            decision_reason=decision.reason,
        )

        if not decision.should_fire:
            _log.info(
                "checkpoint_skipped",
                extra={"phase": phase.value, "reason": decision.reason},
            )
            return result

        if phase == CheckpointPhase.END_OF_TASK:
            # Derive the inner idle-wait timeout from the outer budget so a
            # configured run_timeout < 90s cannot deadlock waiting on a hard-coded
            # 60s idle timeout. We clamp to a floor of 1s so a tiny budget is
            # still meaningful (an idle detector usually returns in <1s on
            # already-idle working trees).
            idle_timeout = max(1.0, min(60.0, self._run_timeout - 30.0))
            idle = await self._detector.wait_until_idle(timeout=idle_timeout)
            if not idle:
                marker = save_pending(
                    PendingCheckpoint(
                        working_dir=self._working_dir,
                        reason="subagent_idle_timeout",
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
            # asyncio.TimeoutError is a subclass of OSError in Python 3.11+
            # (asyncio.TimeoutError is an alias for the built-in TimeoutError,
            # which inherits from OSError). The outer asyncio.wait_for budget
            # catches run timeouts independently; a nested timeout leaking
            # out of snapshot.capture() is a programming error and must
            # propagate per spec invariant. Re-raise explicitly so OSError
            # membership in the tuple does not also catch TimeoutError.
            if isinstance(exc, asyncio.TimeoutError):
                raise
            self._metrics.inc_failure("snapshot_transient")
            _log.error(
                "checkpoint_snapshot_failed_transient",
                extra=safe_transient_info(exc),
            )
            result.error = safe_error_message("snapshot failed (transient):", exc)
            return result
        # Programming errors (TypeError, AttributeError, KeyError, etc.) from
        # self._snapshot.capture() propagate per spec invariant "Failures
        # fail closed; programming errors propagate". The orchestrator's
        # caller (MCP checkpoint tool / lifespan tick) handles propagation
        # at its own boundary.

        result.snapshot_id = snapshot.snapshot_id

        # Empty working tree: spec line 360-361 — skip forward_to
        if not snapshot.dirty_files:
            result.fired = True
            result.decision_reason = f"{decision.reason} (clean tree, no commit)"
            _log.info(
                "checkpoint_clean_skip",
                extra={"phase": phase.value, "snapshot": snapshot.snapshot_id},
            )
            return result

        # Re-check subagent (might have become active during capture) per integration-risk M5
        if self._detector.is_active():
            marker = save_pending(
                PendingCheckpoint(
                    working_dir=self._working_dir,
                    reason="subagent_active_during_capture",
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
            result.error = safe_error_message("forward_to retry exhausted:", exc)
            _log.error(
                "checkpoint_forward_retry_exhausted",
                extra=safe_transient_info(exc),
            )
            return result

        result.fired = True
        _log.info(
            "checkpoint_fired",
            extra={
                "phase": phase.value,
                "reason": decision.reason,
                "snapshot": snapshot.snapshot_id,
                "dirty_files": len(snapshot.dirty_files),
            },
        )
        return result

    async def _forward_with_retry(
        self,
        result: CheckpointResult,
        phase: CheckpointPhase,
    ) -> None:
        """Retry-once-with-backoff for 5xx per spec line 372. 4xx no retry."""
        try:
            await self._forward_to(result)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if 500 <= status < 600:
                _log.warning(
                    "checkpoint_forward_5xx_retrying", extra={"status": status}
                )
                await asyncio.sleep(0.5)  # backoff
                await self._forward_to(result)  # second attempt; propagate if it fails
            else:
                # 4xx → no retry
                self._metrics.inc_failure("forward_4xx")
                raise
