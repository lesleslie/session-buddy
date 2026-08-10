"""MCP Server module - imports and exports the mcp instance.

This module imports the mcp instance from server_optimized and registers
tool modules based on the active ``ToolProfile``.

Profile configuration
---------------------
The profile is read from the ``SESSION_BUDDY_TOOL_PROFILE`` environment
variable.  When unset or invalid the default is ``FULL`` (all tools).

    SESSION_BUDDY_TOOL_PROFILE=minimal   # ~12 tools
    SESSION_BUDDY_TOOL_PROFILE=standard  # ~35 tools
    SESSION_BUDDY_TOOL_PROFILE=full      # all tools (default)
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from mcp_common.tools import ToolProfile

from ..server_optimized import mcp
from .tools.profiles import (
    MANDATORY_REGISTRATIONS,
    PROFILE_REGISTRATIONS,
)
from .tools.session.channel_tracking_tools import _make_dhara_publisher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import every registration function that *could* be called.
# Keeping them all imported avoids import errors when a profile references
# a function that would otherwise be lazy-loaded.
# ---------------------------------------------------------------------------

from .tools import (
    register_access_log_tools,
    register_admin_shell_tracking_tools,
    register_akosha_tools,
    register_bottleneck_tools,
    register_cache_tools,
    register_channel_tracking_tools,
    register_code_analysis_tools,  # Tree-sitter integration
    register_code_graph_tools,
    register_conscious_agent_tools,
    register_conversation_tools,
    register_crackerjack_tools,
    register_cross_repo_work_tools,
    register_export_tools,
    register_extraction_tools,
    register_feature_flags_tools,
    register_health_tools_sb,
    register_hooks_tools,
    register_intent_tools,
    register_knowledge_graph_tools,
    register_llm_tools,
    register_memory_health_tools,
    register_migration_tools,
    register_monitoring_tools,
    register_phase3_knowledge_graph_tools,
    register_phase4_tools,  # Phase 4 Skills Analytics
    register_pool_tools,
    register_prompt_tools,
    register_search_tools,
    register_serverless_tools,
    register_session_analytics_tools,
    register_session_tools,
    register_team_tools,
    register_workflow_metrics_tools,
    register_worktree_tools,
)

# Import discovery tools (always registered)
from .tools.discovery_tools import register_discovery_tools

# Import Prometheus metrics tools
from .tools.monitoring.prometheus_metrics_tools import (
    register_prometheus_metrics_tools,
)

# ---------------------------------------------------------------------------
# Registry: map function name -> callable
# ---------------------------------------------------------------------------

_ALL_REGISTERS: dict[str, Any] = {
    "register_access_log_tools": register_access_log_tools,
    "register_admin_shell_tracking_tools": register_admin_shell_tracking_tools,
    "register_channel_tracking_tools": register_channel_tracking_tools,
    "register_akosha_tools": register_akosha_tools,
    "register_bottleneck_tools": register_bottleneck_tools,
    "register_cache_tools": register_cache_tools,
    "register_code_analysis_tools": register_code_analysis_tools,
    "register_code_graph_tools": register_code_graph_tools,
    "register_conscious_agent_tools": register_conscious_agent_tools,
    "register_conversation_tools": register_conversation_tools,
    "register_crackerjack_tools": register_crackerjack_tools,
    "register_cross_repo_work_tools": register_cross_repo_work_tools,
    "register_export_tools": register_export_tools,
    "register_extraction_tools": register_extraction_tools,
    "register_feature_flags_tools": register_feature_flags_tools,
    "register_health_tools_sb": register_health_tools_sb,
    "register_hooks_tools": register_hooks_tools,
    "register_intent_tools": register_intent_tools,
    "register_knowledge_graph_tools": register_knowledge_graph_tools,
    "register_llm_tools": register_llm_tools,
    "register_memory_health_tools": register_memory_health_tools,
    "register_migration_tools": register_migration_tools,
    "register_monitoring_tools": register_monitoring_tools,
    "register_phase3_knowledge_graph_tools": register_phase3_knowledge_graph_tools,
    "register_phase4_tools": register_phase4_tools,
    "register_pool_tools": register_pool_tools,
    "register_prometheus_metrics_tools": register_prometheus_metrics_tools,
    "register_prompt_tools": register_prompt_tools,
    "register_search_tools": register_search_tools,
    "register_serverless_tools": register_serverless_tools,
    "register_session_analytics_tools": register_session_analytics_tools,
    "register_session_tools": register_session_tools,
    "register_team_tools": register_team_tools,
    "register_workflow_metrics_tools": register_workflow_metrics_tools,
    "register_worktree_tools": register_worktree_tools,
}

# ---------------------------------------------------------------------------
# Resolve the active profile and register tools
# ---------------------------------------------------------------------------

_active_profile = ToolProfile.from_env("SESSION_BUDDY_TOOL_PROFILE")
_registration_list = PROFILE_REGISTRATIONS[_active_profile]

# Deduplicate: mandatory registrations may overlap with profile list.
_names_to_register = list(dict.fromkeys(MANDATORY_REGISTRATIONS + _registration_list))

_skipped: list[str] = []
_registered: list[str] = []

# Build the Dhara publisher once before the loop so the same instance is
# reused for every iteration (avoids creating a new httpx.AsyncClient per
# call and ensures idempotent wiring).
_dhara_publisher = _make_dhara_publisher()

for _name in _names_to_register:
    _fn = _ALL_REGISTERS.get(_name)
    if _fn is None:
        logger.warning("profile references unknown register function: %s", _name)
        _skipped.append(_name)
        continue
    if _fn is register_channel_tracking_tools:
        _fn(mcp, dhara_publisher=_dhara_publisher)
    else:
        _fn(mcp)
    _registered.append(_name)

# Always register the discovery meta-tool
register_discovery_tools(mcp)

logger.info(
    "tool profile=%s registered=%d skipped=%d discovery=enabled",
    _active_profile.value,
    len(_registered),
    len(_skipped),
)

if _skipped:
    logger.warning("skipped unknown registration functions: %s", _skipped)

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
from session_buddy.checkpoint import (  # noqa: E402
    CheckpointOrchestrator,
    CheckpointPhase,
    CheckpointPolicy,
    DirtyFilesSignal,
    LockfileSignalSource,
    MidpointCriteria,
    SnapshotMechanism,
    SubagentDetector,
    TimeElapsedSignal,
    WorkingTreeInspector,
)


async def _noop_forward(_result: Any) -> None:
    """Analytics-only tick: forward_to is a no-op. Snapshot was already captured."""
    return None


async def _consume_pending(marker: Path) -> None:
    """Drain a pending-checkpoint marker by re-firing the orchestrator."""
    from session_buddy.checkpoint import (
        consume_pending as _consume_pending_marker,
        load_pending as _load_pending_marker,
    )

    pending = _load_pending_marker(marker)
    if pending is None:
        marker.unlink(missing_ok=True)
        return
    # Pending drain ALWAYS uses end-of-task semantics (commits when policy fires).
    orch = _build_orchestrator(
        pending.working_dir,
        MidpointCriteria(signals=[]),
        lambda _wd: _end_of_task_forward,
    )
    await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    _consume_pending_marker(marker)


async def _end_of_task_forward(_result: Any) -> None:
    """Pending-drain forward: routes through the legacy git commit path."""


def _build_quality_provider():
    """Return a (prev_score, curr_score) provider or None if no source available.

    Best-effort: returns None when no quality source is configured, which
    makes the QualityDeltaSignal stay inactive (its ``is_active()`` returns
    False when the provider returns (None, None)).
    """
    try:
        from session_buddy.core.quality_cache import get_last_and_current

        return get_last_and_current
    except ImportError:
        return None


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
    except Exception:
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
            auto_loop = AutoCheckpointLoop(
                interval_s=effective_interval,
                working_dir_resolver=lambda: Path(os.getcwd()),
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
            try:
                await _dhara_publisher.aclose()
            except AttributeError:
                with suppress(Exception):
                    pass


mcp._lifespan = _lifespan_with_dhara_cleanup

__all__ = ["mcp"]
