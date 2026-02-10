"""MCP Server module - imports and exports the mcp instance.

This module imports the mcp instance from server_optimized and registers
all tool modules.
"""

from ..server_optimized import mcp

# Import and register all tool modules
from .tools import (
    register_access_log_tools,
    register_admin_shell_tracking_tools,
    register_akosha_tools,
    register_bottleneck_tools,
    register_cache_tools,
    register_code_graph_tools,
    register_conscious_agent_tools,
    register_conversation_tools,
    register_crackerjack_tools,
    register_extraction_tools,
    register_feature_flags_tools,
    register_hooks_tools,
    register_intent_tools,
    register_knowledge_graph_tools,
    register_llm_tools,
    register_memory_health_tools,
    register_migration_tools,
    register_monitoring_tools,
    register_oneiric_discovery_tools,
    register_phase3_knowledge_graph_tools,
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

# Register all extracted tool modules
# Type ignore: mcp is MockFastMCP|FastMCP union in tests, both have compatible interface
register_access_log_tools(mcp)  # type: ignore[argument-type]
register_admin_shell_tracking_tools(mcp)  # type: ignore[argument-type]
register_akosha_tools(mcp)  # type: ignore[argument-type]
register_bottleneck_tools(mcp)  # type: ignore[argument-type]
register_cache_tools(mcp)  # type: ignore[argument-type]
register_code_graph_tools(mcp)  # type: ignore[argument-type]
register_conversation_tools(mcp)  # type: ignore[argument-type]
register_conscious_agent_tools(mcp)  # type: ignore[argument-type]
register_crackerjack_tools(mcp)  # type: ignore[argument-type]
register_extraction_tools(mcp)  # type: ignore[argument-type]
register_feature_flags_tools(mcp)  # type: ignore[argument-type]
register_hooks_tools(mcp)  # type: ignore[argument-type]
register_intent_tools(mcp)  # type: ignore[argument-type]
register_knowledge_graph_tools(mcp)  # type: ignore[argument-type]
register_phase3_knowledge_graph_tools(mcp)  # type: ignore[argument-type]
register_llm_tools(mcp)  # type: ignore[argument-type]
register_migration_tools(mcp)  # type: ignore[argument-type]
register_monitoring_tools(mcp)  # type: ignore[argument-type]
register_prompt_tools(mcp)  # type: ignore[argument-type]
register_search_tools(mcp)  # type: ignore[argument-type]
register_serverless_tools(mcp)  # type: ignore[argument-type]

register_pool_tools(mcp)  # type: ignore[argument-type]
register_session_analytics_tools(mcp)  # type: ignore[argument-type]
register_session_tools(mcp)  # type: ignore[argument-type]
register_team_tools(mcp)  # type: ignore[argument-type]
register_workflow_metrics_tools(mcp)  # type: ignore[argument-type]
register_memory_health_tools(mcp)  # type: ignore[argument-type]

# Register Oneiric integration tools
register_oneiric_discovery_tools(mcp)  # type: ignore[argument-type]

# Register Prometheus metrics tools
register_prometheus_metrics_tools(mcp)  # type: ignore[argument-type]

__all__ = ["mcp"]
