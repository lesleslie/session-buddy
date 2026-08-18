"""MCP Server module - imports and exports the mcp instance.

This module imports the mcp instance from server_optimized and registers
tool modules based on the active ``ToolProfile`` via the W0 helper in
``mcp_common.tools.dispatch``.

Profile configuration
---------------------
The profile is read from the ``SESSION_BUDDY_TOOL_PROFILE`` environment
variable.  When unset or invalid the default is ``FULL`` (all tools).

    SESSION_BUDDY_TOOL_PROFILE=minimal   # minimal core + mandatory health
    SESSION_BUDDY_TOOL_PROFILE=standard  # daily-development essentials
    SESSION_BUDDY_TOOL_PROFILE=full      # all tools (default)

W0 helper integration
---------------------
Tool registration is delegated to ``_apply_tool_profile`` from
``mcp-common>=0.18.0``. ``REGISTRATION_MAP`` and
``SESSION_BUDDY_MANDATORY_GROUPS`` are defined in
``session_buddy/mcp/tools/profiles.py``. ``admin_shell_tracking_tools``
is registered at FULL profile via the same mechanism (preserves
pre-refactor behavior).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from mcp_common.tools.dispatch import _apply_tool_profile

from ..server_optimized import mcp
from .tools.profiles import (
    PROFILE_REGISTRATIONS,
    REGISTRATION_MAP,
    SESSION_BUDDY_MANDATORY_GROUPS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path validation (Finding C-7): shared with SessionLifecycleManager so the
# two call sites cannot drift. Imported at module level (not lazily) because
# the symbol is referenced in the lifespan closure below.
from session_buddy.checkpoint.pending import load_pending as _load_pending
from session_buddy.core.session_manager import (
    validate_orchestrator_working_dir,
)

# ---------------------------------------------------------------------------
# W0 helper wiring
# ---------------------------------------------------------------------------


def _register_all_tool_groups(server: Any) -> None:
    """Bulk register every tool group at FULL profile.

    The W0 helper invokes this once when ``PROFILE_REGISTRATIONS[FULL]``
    is ``ALL_TOOLS``. We skip the mandatory groups because the helper
    re-registers them in its mandatory_groups pass; running them here
    would create duplicate tool registration warnings from FastMCP.
    """
    for name, fn in REGISTRATION_MAP.items():
        if name in SESSION_BUDDY_MANDATORY_GROUPS:
            continue
        fn(server)


# Apply the profile at module load. ``_apply_tool_profile`` is async; the
# helper raises if called from inside a running event loop, so wrap with
# ``asyncio.run`` (which spins a fresh loop and is safe at module-import
# time when no loop is running). session-buddy is env-only so
# ``yaml_loader=None`` -- no settings/local.yaml lookup.
asyncio.run(
    _apply_tool_profile(
        mcp,
        profile_env_var="SESSION_BUDDY_TOOL_PROFILE",
        registrations=PROFILE_REGISTRATIONS,
        registration_map=REGISTRATION_MAP,
        register_all_fn=_register_all_tool_groups,
        mandatory_groups=SESSION_BUDDY_MANDATORY_GROUPS,
        essential_tool_names=set(),
        yaml_loader=None,
    )
)

# ---------------------------------------------------------------------------
# AutoCheckpointLoop + pending-marker drain wiring (Task 9).
#
# We replace the lifespan with one that starts a background AutoCheckpointLoop
# on entry and stops it on exit (try/finally shape). The loop fires the
# CheckpointOrchestrator at ``settings.auto_checkpoint_interval`` (analytics-only
# by default) or ``settings.midpoint_commit_interval_s`` when
# ``settings.midpoint_commits_enabled`` is True. On every tick it also drains
# any ``~/.session-buddy/pending/*.json`` markers created by subagent-timeout
# events. All new behavior is opt-in -- deployments that do not flip the flag
# see no difference.
# ---------------------------------------------------------------------------

# Late imports for the helper functions (after registration block above).
from session_buddy.checkpoint import (
    CheckpointOrchestrator,
    CheckpointPolicy,
    DirtyFilesSignal,
    LockfileSignalSource,
    MidpointCriteria,
    SnapshotMechanism,
    SubagentDetector,
    TimeElapsedSignal,
    WorkingTreeInspector,
)


class _OrchestratorCwdInvalid(Exception):
    """Raised when ``os.getcwd()`` fails validation inside the lifespan.

    Finding C-7: The AutoCheckpointLoop's tick error handler catches this
    and logs it; the orchestrator is never constructed. We use a
    dedicated exception class (not a stringly-typed RuntimeError) so the
    ``auto_checkpoint_loop_tick_error`` log line carries a stable type.
    """


async def _noop_forward(_result: Any) -> None:
    """Analytics-only tick: forward_to is a no-op. Snapshot was already captured."""


async def _consume_pending(marker: Path) -> None:
    """Drain a pending-checkpoint marker by re-firing the orchestrator.

    Uses the shared ``consume_pending_marker`` helper so the lifespan loop
    and ``SessionLifecycleManager.end_session`` behave identically.

    Finding C-7: the pending marker's ``working_dir`` is read from
    disk and would otherwise flow directly into ``_build_orchestrator``
    without validation. A stale or hostile marker pointing at a path
    that has since vanished (or never existed) would still construct
    ``LockfileSignalSource`` there. Validate first; if the path is not
    a usable directory, consume the marker so we don't keep retrying
    it, and skip orchestrator construction.
    """
    from session_buddy.checkpoint import consume_pending_marker

    pending = _load_pending(marker)
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


def _make_end_of_task_forward(working_dir: Path):
    """Build a forward that commits via the legacy git commit path.

    Mirrors ``_midpoint_commit_forward`` in ``auto_checkpoint_loop.py``:
    the commit runs unconditionally after a successful snapshot capture,
    using ``create_checkpoint_commit`` directly so we bypass the
    SessionManager ceremony (cross-repo accounting, conversation storage)
    that the timer-driven forward also skips.
    """

    async def _end_of_task_forward(_result: Any) -> None:
        import asyncio

        from session_buddy.utils.git_worktrees import create_checkpoint_commit

        await asyncio.to_thread(
            create_checkpoint_commit,
            working_dir,
            working_dir.name,
            0,  # quality_score placeholder — end-of-task drain doesn't compute it
        )

    return _end_of_task_forward


def _build_quality_provider():
    """Return a (prev_score, curr_score) provider or None if no source available.

    Best-effort: returns None when no quality source is configured, which
    makes the QualityDeltaSignal stay inactive (its ``is_active()`` returns
    False when the provider returns (None, None)).

    Note: ``session_buddy.core.quality_cache.get_last_and_current`` was the
    candidate provider but never landed in the tree. Until that module ships,
    no provider is wired and the signal stays inactive by design.
    """
    # The previous try/except ImportError wrapper masked the fact that
    # ``session_buddy.core.quality_cache`` was never implemented. Returning
    # None here is the documented best-effort contract and keeps the
    # QualityDeltaSignal path self-inert until a real provider ships.


def _build_orchestrator(
    working_dir: Path,
    midpoint_criteria: MidpointCriteria,
    forward_to_factory,
) -> CheckpointOrchestrator:
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


_original_lifespan = mcp._lifespan


@asynccontextmanager
async def _lifespan_with_dhara_cleanup(app: Any) -> AsyncGenerator[None]:
    from session_buddy.core.auto_checkpoint_loop import (
        AutoCheckpointLoop,
        QualityDeltaSignal,
        _midpoint_commit_forward,
    )
    from session_buddy.settings import get_settings

    settings = get_settings()

    # Mode-based gate: Lite mode (enable_auto_checkpoint=False) skips the loop entirely
    try:
        from session_buddy.modes import get_mode

        mode_cfg = get_mode().get_config()
        loop_enabled = getattr(mode_cfg, "enable_auto_checkpoint", True)
    except Exception:  # noqa: BLE001 - best-effort mode gate, default to enabled
        loop_enabled = True

    # Effective interval: 10 min (commits) vs 30 min (analytics-only)
    effective_interval = (
        settings.midpoint_commit_interval_s
        if getattr(settings, "midpoint_commits_enabled", False)
        else settings.auto_checkpoint_interval
    )

    # Build the quality-delta signal if a provider is configured.
    # Best-effort: when no quality source is configured, the signal stays inactive.
    quality_provider = _build_quality_provider()
    signals: list = [
        TimeElapsedSignal(min_seconds=300.0),
        DirtyFilesSignal(min_count=5),
    ]
    if quality_provider is not None:
        signals.append(
            QualityDeltaSignal(
                min_delta=getattr(settings, "midpoint_commit_min_quality_delta", 10),
                quality_provider=quality_provider,
            )
        )
    midpoint_criteria = MidpointCriteria(signals=signals)

    # forward_to factory: real commit when enabled, no-op otherwise.
    def forward_to_factory(working_dir: Path):
        if getattr(settings, "midpoint_commits_enabled", False):

            async def forward(_result: Any) -> None:
                await _midpoint_commit_forward(working_dir)

            return forward
        return _noop_forward

    auto_loop: AutoCheckpointLoop | None = None
    async with _original_lifespan(app):
        if loop_enabled and effective_interval > 0:
            # Finding C-7: validate cwd before it reaches the orchestrator.
            # Without this, a ``cd /`` would let ``LockfileSignalSource``
            # create ``/.session-buddy/subagent.lock`` at filesystem root.
            # The validation function is module-level so it cannot drift
            # from ``SessionLifecycleManager._validate_orchestrator_path``
            # (both share one definition).

            def _validate_or_raise() -> Path:
                validated = validate_orchestrator_working_dir(logger=logger)
                if validated is None:
                    raise _OrchestratorCwdInvalid(Path.cwd())
                return validated

            auto_loop = AutoCheckpointLoop(
                interval_s=effective_interval,
                working_dir_resolver=_validate_or_raise,
                orch_factory=lambda wd: _build_orchestrator(
                    wd, midpoint_criteria, forward_to_factory
                ),
                pending_consume_fn=_consume_pending,
            )
            await auto_loop.start()
        try:
            yield
        finally:
            if auto_loop is not None:
                await auto_loop.stop()
            # Close the Dhara publisher if one was wired. Blanket suppression
            # preserves the pre-Task-9 behavior: any shutdown-time error
            # (network blip, closed loop, etc.) must not break lifespan exit.
            if _dhara_publisher is not None:
                with suppress(Exception):
                    await _dhara_publisher.aclose()


# CAUTION (I-10): This module-load side-effect is what prevents
# `_lifespan_with_dhara_cleanup(mcp)` from recursing into itself — it
# captures `mcp._lifespan` (the FastMCP default) at import time and
# delegates to that captured reference. Calling the wrapping function
# directly would recurse indefinitely. The wrap is intentionally one-shot
# at module load; any future lifespan override must follow the same
# capture-then-delegate pattern, not nest re-invocations.
mcp._lifespan = _lifespan_with_dhara_cleanup

__all__ = ["mcp"]
