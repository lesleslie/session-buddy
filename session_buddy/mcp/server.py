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
from typing import Any

from ..server_optimized import mcp
from mcp_common.tools import ToolProfile

from .tools.profiles import (
    FULL_REGISTRATIONS,
    MANDATORY_REGISTRATIONS,
    PROFILE_REGISTRATIONS,
)

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
    register_code_analysis_tools,  # Tree-sitter integration
    register_code_graph_tools,
    register_conscious_agent_tools,
    register_conversation_tools,
    register_crackerjack_tools,
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
    register_oneiric_discovery_tools,
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
)

# Import Prometheus metrics tools
from .tools.monitoring import register_prometheus_metrics_tools

# Import discovery tools (always registered)
from .tools.discovery_tools import register_discovery_tools

# ---------------------------------------------------------------------------
# Registry: map function name -> callable
# ---------------------------------------------------------------------------

_ALL_REGISTERS: dict[str, Any] = {
    "register_access_log_tools": register_access_log_tools,
    "register_admin_shell_tracking_tools": register_admin_shell_tracking_tools,
    "register_akosha_tools": register_akosha_tools,
    "register_bottleneck_tools": register_bottleneck_tools,
    "register_cache_tools": register_cache_tools,
    "register_code_analysis_tools": register_code_analysis_tools,
    "register_code_graph_tools": register_code_graph_tools,
    "register_conscious_agent_tools": register_conscious_agent_tools,
    "register_conversation_tools": register_conversation_tools,
    "register_crackerjack_tools": register_crackerjack_tools,
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
    "register_oneiric_discovery_tools": register_oneiric_discovery_tools,
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

for _name in _names_to_register:
    _fn = _ALL_REGISTERS.get(_name)
    if _fn is None:
        logger.warning("profile references unknown register function: %s", _name)
        _skipped.append(_name)
        continue
    _fn(mcp)  # type: ignore[argument-type]
    _registered.append(_name)

# Always register the discovery meta-tool
register_discovery_tools(mcp)  # type: ignore[argument-type]

logger.info(
    "tool profile=%s registered=%d skipped=%d discovery=enabled",
    _active_profile.value,
    len(_registered),
    len(_skipped),
)

if _skipped:
    logger.warning("skipped unknown registration functions: %s", _skipped)

__all__ = ["mcp"]
