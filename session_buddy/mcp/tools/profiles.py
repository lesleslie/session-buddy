"""Tool profile definitions for session-buddy MCP server.

Maps ``mcp_common.tools.ToolProfile`` levels to the specific
``register_*()`` functions that should be called at startup.

Profiles
--------
MINIMAL
    Core session lifecycle plus health.  ~12 tools.
STANDARD
    Daily-development essentials on top of MINIMAL.  ~35 tools.
FULL
    Every register function currently called in ``server.py`` -- the
    pre-profile default with all ~171 tools.

Configuration
-------------
The active profile is read from the ``SESSION_BUDDY_TOOL_PROFILE``
environment variable.  ``ToolProfile.from_env`` handles missing or
invalid values by falling back to ``ToolProfile.FULL``.
"""

from __future__ import annotations

from mcp_common.tools import ToolProfile

# ---------------------------------------------------------------------------
# Profile tiers
# ---------------------------------------------------------------------------

MINIMAL_REGISTRATIONS: list[str] = [
    # Health -- required by infrastructure probes
    "register_health_tools_sb",
    # Session lifecycle -- start / end / status / checkpoint
    "register_session_tools",
    # Basic search
    "register_search_tools",
    # Pre-compact hook (needed by Claude Code context management)
    "register_hooks_tools",
]

STANDARD_REGISTRATIONS: list[str] = MINIMAL_REGISTRATIONS + [
    "register_conversation_tools",
    "register_extraction_tools",
    "register_knowledge_graph_tools",
    "register_cache_tools",
    "register_intent_tools",
    "register_crackerjack_tools",
    "register_feature_flags_tools",
    "register_monitoring_tools",
    "register_access_log_tools",
]

FULL_REGISTRATIONS: list[str] = STANDARD_REGISTRATIONS + [
    "register_bottleneck_tools",
    "register_session_analytics_tools",
    "register_workflow_metrics_tools",
    "register_memory_health_tools",
    "register_phase3_knowledge_graph_tools",
    "register_phase4_tools",
    "register_conscious_agent_tools",
    "register_migration_tools",
    "register_pool_tools",
    "register_serverless_tools",
    "register_team_tools",
    "register_llm_tools",
    "register_prompt_tools",
    "register_code_graph_tools",
    "register_code_analysis_tools",
    "register_oneiric_discovery_tools",
    "register_admin_shell_tracking_tools",
    "register_akosha_tools",
    "register_prometheus_metrics_tools",
]

# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

PROFILE_REGISTRATIONS: dict[ToolProfile, list[str]] = {
    ToolProfile.MINIMAL: MINIMAL_REGISTRATIONS,
    ToolProfile.STANDARD: STANDARD_REGISTRATIONS,
    ToolProfile.FULL: FULL_REGISTRATIONS,
}

# Mandatory registrations that happen regardless of profile.
# Health endpoints are consumed by Kubernetes probes, load balancers,
# and other infrastructure that does not understand profiles.
MANDATORY_REGISTRATIONS: list[str] = [
    "register_health_tools_sb",
]


def get_active_profile(env_var: str = "SESSION_BUDDY_TOOL_PROFILE") -> ToolProfile:
    """Read the active tool profile from environment."""
    return ToolProfile.from_env(env_var)
