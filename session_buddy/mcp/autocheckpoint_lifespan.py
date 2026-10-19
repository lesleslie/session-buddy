"""AutoCheckpointLoop wiring for the MCP server lifespan.

The ``AutoCheckpointLoop`` (defined in
``session_buddy.core.auto_checkpoint_loop``) fires the
``CheckpointOrchestrator`` at ``settings.session.auto_checkpoint_interval``
(analytics-only by default) or
``settings.session.midpoint_commit_interval_s`` when
``settings.session.midpoint_commits_enabled`` is True. On every tick it
also drains any ``~/.session-buddy/pending/*.json`` markers created by
subagent-timeout events. All behavior is opt-in — deployments that do
not flip the flag see no difference.

This module was extracted from
``session_buddy/mcp/server.py:_lifespan_with_dhara_cleanup`` after that
wrapper was deleted in commit c820d210 (the wrapper was dead code in
production: no production caller imports ``session_buddy.mcp.server``,
so the module-load side-effect that installed the wrapper as the
canonical ``mcp`` lifespan never ran). The helpers below are now wired
into the canonical ``session_lifecycle`` in
``session_buddy/server_optimized.py``.

See ``docs/plans/2026-10-18-session-buddy-autocheckpoint-loop-move.md``
for the audit trail.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from session_buddy.core.session_manager import (
    validate_orchestrator_working_dir,
)

if TYPE_CHECKING:
    from session_buddy.checkpoint import CheckpointOrchestrator, MidpointCriteria
    from session_buddy.core.auto_checkpoint_loop import AutoCheckpointLoop

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point: start the loop and return it (or None when disabled).
#
# Callers (the ``session_lifecycle`` in ``server_optimized.py``) wrap the
# returned loop in a ``try/finally`` so ``stop()`` runs even if the lifespan
# exits via exception. Per Finding C-7, the working-dir resolver raises a
# dedicated exception (not a stringly-typed RuntimeError) so the
# ``auto_checkpoint_loop_tick_error`` log line carries a stable type.
# ---------------------------------------------------------------------------


class OrchestratorCwdInvalid(Exception):
    """Raised when ``os.getcwd()`` fails validation inside the lifespan.

    The AutoCheckpointLoop's tick error handler catches this and logs it;
    the orchestrator is never constructed. We use a dedicated exception
    class (not a stringly-typed RuntimeError) so the
    ``auto_checkpoint_loop_tick_error`` log line carries a stable type.
    """


async def start_autocheckpoint_loop(settings: Any) -> AutoCheckpointLoop | None:
    """Start the AutoCheckpointLoop and return it, or ``None`` if disabled.

    Resolves the mode-gate (``get_mode().get_config().enable_auto_checkpoint``,
    defaulting to ``True`` when the modes subsystem is unavailable) and the
    effective interval (10-min midpoint-commit interval vs 30-min
    analytics-only auto-checkpoint interval) from ``settings``.

    Returns the started ``AutoCheckpointLoop`` (caller's responsibility to
    ``stop()`` it) or ``None`` when the loop is disabled (mode off or
    interval <= 0).

    Failure modes are best-effort by design:
    * Missing ``get_mode`` (legacy mode config) → loop is enabled (True).
    * Missing quality provider → QualityDeltaSignal stays inactive.
    * Invalid cwd → ``OrchestratorCwdInvalid`` propagates; the
      ``AutoCheckpointLoop.start`` call is what actually surfaces the
      exception via the working-dir resolver.
    """
    from session_buddy.checkpoint import (
        DirtyFilesSignal,
        MidpointCriteria,
        TimeElapsedSignal,
    )
    from session_buddy.core.auto_checkpoint_loop import (
        AutoCheckpointLoop,
        QualityDeltaSignal,
        _midpoint_commit_forward,
    )

    # Mode-based gate: Lite mode (enable_auto_checkpoint=False) skips the
    # loop entirely.
    try:
        from session_buddy.modes import get_mode

        mode_cfg = get_mode().get_config()
        loop_enabled = getattr(mode_cfg, "enable_auto_checkpoint", True)
    except Exception:  # noqa: BLE001 - best-effort mode gate, default to enabled
        loop_enabled = True

    # Effective interval: midpoint-commit interval (commits on) vs
    # auto_checkpoint_interval (analytics-only).
    effective_interval = (
        settings.session.midpoint_commit_interval_s
        if settings.session.midpoint_commits_enabled
        else settings.session.auto_checkpoint_interval
    )

    if not loop_enabled or effective_interval <= 0:
        return None

    # Build the quality-delta signal if a provider is configured.
    # Best-effort: when no quality source is configured, the signal
    # stays inactive.
    quality_provider = _build_quality_provider()
    signals: list = [
        TimeElapsedSignal(min_seconds=300.0),
        DirtyFilesSignal(min_count=5),
    ]
    if quality_provider is not None:
        signals.append(
            QualityDeltaSignal(
                min_delta=settings.session.midpoint_commit_min_quality_delta,
                quality_provider=quality_provider,
            )
        )
    midpoint_criteria = MidpointCriteria(signals=signals)

    # forward_to factory: real commit when enabled, no-op otherwise.
    def forward_to_factory(working_dir: Path):
        if settings.session.midpoint_commits_enabled:

            async def forward(_result: Any) -> None:
                await _midpoint_commit_forward(working_dir)

            return forward
        return _noop_forward

    def _validate_or_raise() -> Path:
        validated = validate_orchestrator_working_dir(logger=logger)
        if validated is None:
            raise OrchestratorCwdInvalid(Path.cwd())
        return validated

    auto_loop: AutoCheckpointLoop = AutoCheckpointLoop(
        interval_s=effective_interval,
        working_dir_resolver=_validate_or_raise,
        orch_factory=lambda wd: _build_orchestrator(
            wd, midpoint_criteria, forward_to_factory
        ),
        pending_consume_fn=_consume_pending,
    )
    await auto_loop.start()
    return auto_loop


# ---------------------------------------------------------------------------
# Module-private helpers used by ``start_autocheckpoint_loop`` and the
# ``_consume_pending`` marker-drain path.
# ---------------------------------------------------------------------------


async def _noop_forward(_result: Any) -> None:
    """Analytics-only tick: forward_to is a no-op. Snapshot was already captured."""


def _make_end_of_task_forward(working_dir: Path):
    """Build a forward that commits via the legacy git commit path.

    Mirrors ``_midpoint_commit_forward`` in ``auto_checkpoint_loop.py``:
    the commit runs unconditionally after a successful snapshot capture,
    using ``create_checkpoint_commit`` directly so we bypass the
    SessionManager ceremony (cross-repo accounting, conversation
    storage) that the timer-driven forward also skips.
    """

    async def _end_of_task_forward(_result: Any) -> None:
        from session_buddy.utils.git_worktrees import create_checkpoint_commit

        await asyncio.to_thread(
            create_checkpoint_commit,
            working_dir,
            working_dir.name,
            0,  # quality_score placeholder — end-of-task drain doesn't compute it
        )

    return _end_of_task_forward


async def _consume_pending(marker: Path) -> None:
    """Drain a pending-checkpoint marker by re-firing the orchestrator.

    Uses the shared ``consume_pending_marker`` helper so the lifespan
    loop and ``SessionLifecycleManager.end_session`` behave identically.

    Finding C-7: the pending marker's ``working_dir`` is read from disk
    and would otherwise flow directly into ``_build_orchestrator``
    without validation. A stale or hostile marker pointing at a path
    that has since vanished (or never existed) would still construct
    ``LockfileSignalSource`` there. Validate first; if the path is not
    a usable directory, consume the marker so we don't keep retrying
    it, and skip orchestrator construction.
    """
    from session_buddy.checkpoint import (
        MidpointCriteria,
        consume_pending_marker,
    )
    from session_buddy.checkpoint.pending import load_pending

    pending = load_pending(marker)
    if pending is None:
        # Marker could not be loaded (corrupt JSON etc.); drop it.
        marker.unlink(missing_ok=True)
        return

    validated = validate_orchestrator_working_dir(pending.working_dir, logger=logger)
    if validated is None:
        logger.warning(
            "checkpoint_orchestrator_pending_path_invalid marker=%s working_dir=%s",
            marker,
            pending.working_dir,
        )
        # Drop the marker so we don't keep retrying an invalid path.
        marker.unlink(missing_ok=True)
        return

    async def _build(wd: Path) -> CheckpointOrchestrator:
        return _build_orchestrator(
            wd,
            MidpointCriteria(signals=[]),
            _make_end_of_task_forward,
        )

    await consume_pending_marker(marker, build_orchestrator=_build)


def _build_quality_provider():
    """Return a (prev_score, curr_score) provider or None if no source available.

    Best-effort: returns None when no quality source is configured, which
    makes the QualityDeltaSignal stay inactive (its ``is_active()``
    returns False when the provider returns (None, None)).

    Note: ``session_buddy.core.quality_cache.get_last_and_current`` was
    the candidate provider but never landed in the tree. Until that
    module ships, no provider is wired and the signal stays inactive by
    design.
    """
    # The previous try/except ImportError wrapper masked the fact that
    # ``session_buddy.core.quality_cache`` was never implemented.
    # Returning None here is the documented best-effort contract and
    # keeps the QualityDeltaSignal path self-inert until a real
    # provider ships.


def _build_orchestrator(
    working_dir: Path,
    midpoint_criteria: MidpointCriteria,
    forward_to_factory,
) -> CheckpointOrchestrator:
    from session_buddy.checkpoint import (
        CheckpointOrchestrator,
        CheckpointPolicy,
        LockfileSignalSource,
        SnapshotMechanism,
        SubagentDetector,
        WorkingTreeInspector,
    )

    lockfile = working_dir / ".session-buddy" / "subagent.lock"
    detector = SubagentDetector(working_dir, LockfileSignalSource(lockfile))
    snapshot = SnapshotMechanism(working_dir)
    inspector = WorkingTreeInspector(working_dir)
    policy = CheckpointPolicy(
        midpoint_enabled=True,
        midpoint_criteria=midpoint_criteria,
        subagent_detector=detector,
        working_tree=inspector,
    )
    return CheckpointOrchestrator(
        working_dir=working_dir,
        policy=policy,
        snapshot=snapshot,
        subagent_detector=detector,
        forward_to=forward_to_factory(working_dir),
    )
