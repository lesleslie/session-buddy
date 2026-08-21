"""Tool profile definitions for session-buddy MCP server.

Maps ``mcp_common.tools.ToolProfile`` levels to the specific
``register_*()`` functions that should be called at startup.

Profiles
--------
MINIMAL
    Core session lifecycle plus health.  ~3 tools in
    ``MINIMAL_REGISTRATIONS``; health is added via
    ``SESSION_BUDDY_MANDATORY_GROUPS`` so the W0 helper registers it
    at every profile.
STANDARD
    Daily-development essentials on top of MINIMAL.  ~15 tools
    (``STANDARD_REGISTRATIONS``).
FULL
    Every register function in ``REGISTRATION_MAP`` (~35 tools) via
    the ``ALL_TOOLS`` sentinel and ``register_all_fn``.

Configuration
-------------
The active profile is read from the ``SESSION_BUDDY_TOOL_PROFILE``
environment variable.  ``ToolProfile.from_env`` handles missing or
invalid values by falling back to ``ToolProfile.FULL``.

W0 helper integration (mcp-common >=0.18.0)
-------------------------------------------
This module exposes the ``REGISTRATION_MAP`` consumed by
:meth:`mcp_common.tools.dispatch._apply_tool_profile` plus the
``SESSION_BUDDY_MANDATORY_GROUPS`` set of registration_map keys that
are registered at every profile regardless of tier.

session-buddy is env-only (no YAML ``tool_profile`` override), so
``settings_yaml_loader`` is intentionally NOT defined -- callers pass
``yaml_loader=None`` to the helper.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from mcp_common.tools import ToolProfile
from mcp_common.tools.dispatch import ALL_TOOLS

if TYPE_CHECKING:
    from mcp_common.fastmcp import FastMCP


# ---------------------------------------------------------------------------
# Profile tiers
#
# Health tools (``register_health_tools_sb``) are NOT listed here -- they
# are declared in SESSION_BUDDY_MANDATORY_GROUPS below so the W0 helper
# always registers them at every profile without duplication.
# ---------------------------------------------------------------------------

MINIMAL_REGISTRATIONS: list[str | Callable] = [
    # Session lifecycle -- start / end / status / checkpoint
    "register_session_tools",
    # Basic search
    "register_search_tools",
    # Pre-compact hook (needed by Claude Code context management)
    "register_hooks_tools",
]

STANDARD_REGISTRATIONS: list[str | Callable] = MINIMAL_REGISTRATIONS + [
    "register_conversation_tools",
    "register_extraction_tools",
    "register_knowledge_graph_tools",
    "register_cache_tools",
    "register_intent_tools",
    "register_crackerjack_tools",
    "register_feature_flags_tools",
    "register_monitoring_tools",
    "register_access_log_tools",
    "register_channel_session_state_tools",
    "register_channel_tracking_tools",
    "register_cross_repo_work_tools",
]

# FULL uses the ALL_TOOLS sentinel so the W0 helper invokes
# ``register_all_fn`` once instead of iterating the per-profile list.
from mcp_common.baseline_tools import register_baseline_tools


# ``register_all_fn`` (defined in server.py) iterates ``REGISTRATION_MAP``
# minus the mandatory groups (which the helper re-registers in its
# mandatory_groups pass).

# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

PROFILE_REGISTRATIONS: dict[ToolProfile, list[str | Callable] | type[ALL_TOOLS]] = {
    ToolProfile.MINIMAL: MINIMAL_REGISTRATIONS,
    ToolProfile.STANDARD: STANDARD_REGISTRATIONS,
    ToolProfile.FULL: ALL_TOOLS,
}


# ---------------------------------------------------------------------------
# REGISTRATION_MAP: str (function name) -> Callable[[FastMCP], None]
#
# Each entry is invoked by the W0 helper with the FastMCP server as its
# only positional argument. ``register_channel_tracking_tools`` requires
# an extra ``dhara_publisher`` kwarg; this module pre-builds the
# publisher at import time and captures it in a closure so the helper
# can call this wrapper with just the server.
# ---------------------------------------------------------------------------

from . import (
    register_access_log_tools,
    register_admin_shell_tracking_tools,
    register_akosha_tools,
    register_bottleneck_tools,
    register_cache_tools,
    register_channel_session_state_tools,
    register_code_analysis_tools,
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
    register_phase4_tools,
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
from .monitoring.prometheus_metrics_tools import register_prometheus_metrics_tools
from .session.channel_tracking_tools import (
    _make_dhara_publisher,
    register_channel_tracking_tools,
)

# Build a single Dhara publisher at module load so every
# ``register_channel_tracking_tools`` invocation shares the same
# httpx.AsyncClient (avoids the per-call socket churn the legacy loop
# avoided by pre-building).
_dhara_publisher = _make_dhara_publisher()


def _register_channel_tracking(server: FastMCP) -> None:
    """Wrap register_channel_tracking_tools with the pre-built publisher."""
    register_channel_tracking_tools(server, dhara_publisher=_dhara_publisher)


REGISTRATION_MAP: dict[str, Callable[[FastMCP], Any]] = {
    "register_access_log_tools": register_access_log_tools,
    "register_admin_shell_tracking_tools": register_admin_shell_tracking_tools,
    "register_akosha_tools": register_akosha_tools,
    "register_bottleneck_tools": register_bottleneck_tools,
    "register_cache_tools": register_cache_tools,
    "register_channel_session_state_tools": register_channel_session_state_tools,
    "register_channel_tracking_tools": _register_channel_tracking,
    "register_code_analysis_tools": register_code_analysis_tools,
    "register_code_graph_tools": register_code_graph_tools,
    "register_conscious_agent_tools": register_conscious_agent_tools,
    "register_conversation_tools": register_conversation_tools,
    "register_crackerjack_tools": register_crackerjack_tools,
    "register_cross_repo_work_tools": register_cross_repo_work_tools,
    "register_export_tools": register_export_tools,
    "register_extraction_tools": register_extraction_tools,
    "register_baseline_tools": register_baseline_tools,
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
    "register_prompt_tools": register_prompt_tools,
    "register_prometheus_metrics_tools": register_prometheus_metrics_tools,
    "register_search_tools": register_search_tools,
    "register_serverless_tools": register_serverless_tools,
    "register_session_analytics_tools": register_session_analytics_tools,
    "register_session_tools": register_session_tools,
    "register_team_tools": register_team_tools,
    "register_workflow_metrics_tools": register_workflow_metrics_tools,
    "register_worktree_tools": register_worktree_tools,
}


# ---------------------------------------------------------------------------
# Mandatory registrations (always-on, registered at every profile).
#
# Health endpoints are consumed by Kubernetes probes, load balancers,
# and other infrastructure that does not understand profiles. The W0
# helper re-registers these after the per-profile pass so they appear
# at MINIMAL/STANDARD even if the profile list omits them.
# ---------------------------------------------------------------------------

SESSION_BUDDY_MANDATORY_GROUPS: set[str] = {
    "register_baseline_tools",
    "register_health_tools_sb",
}


def get_active_profile(env_var: str = "SESSION_BUDDY_TOOL_PROFILE") -> ToolProfile:
    """Read the active tool profile from environment."""
    return ToolProfile.from_env(env_var)
