"""Compatibility layer for session_buddy.tools.

This module provides backward compatibility imports from the new MCP tools location
(session_buddy/mcp/tools/) to the old session_buddy.tools location.

Note: Some tools in the new location use @mcp.tool() decorators directly
and don't have register_* functions. This compatibility layer only exports
what actually exists.
"""

# Advanced tools
from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
    register_conscious_agent_tools,
)
from session_buddy.mcp.tools.advanced.entity_extraction_tools import (
    register_extraction_tools,
)
from session_buddy.mcp.tools.advanced.fingerprint_tools import (
    register_fingerprint_tools,
)
from session_buddy.mcp.tools.advanced.intent_detection_tools import (
    register_intent_tools,
)

# Collaboration tools
from session_buddy.mcp.tools.collaboration.knowledge_graph_tools import (
    register_knowledge_graph_tools,
)
from session_buddy.mcp.tools.collaboration.team_tools import register_team_tools

# Infrastructure tools
from session_buddy.mcp.tools.infrastructure.access_log_tools import (
    register_access_log_tools,
)
from session_buddy.mcp.tools.infrastructure.cache_tools import (
    register_cache_tools,
)
from session_buddy.mcp.tools.infrastructure.feature_flags_tools import (
    register_feature_flags_tools,
)
from session_buddy.mcp.tools.infrastructure.pools import register_pool_tools
from session_buddy.mcp.tools.infrastructure.serverless_tools import (
    register_serverless_tools,
)

# Intelligence tools
from session_buddy.mcp.tools.intelligence.agent_analyzer import (
    AgentAnalyzer,
    AgentType,
)
from session_buddy.mcp.tools.intelligence.llm_tools import register_llm_tools

# Memory tools
from session_buddy.mcp.tools.memory.category_tools import register_category_tools
from session_buddy.mcp.tools.memory.memory_tools import register_memory_tools
from session_buddy.mcp.tools.memory.search_tools import register_search_tools
from session_buddy.mcp.tools.memory.validated_memory_tools import (
    register_validated_memory_tools,
)

# Monitoring tools
from session_buddy.mcp.tools.monitoring.bottleneck_tools import (
    register_bottleneck_tools,
)
from session_buddy.mcp.tools.monitoring.memory_health_tools import (
    register_memory_health_tools,
)
from session_buddy.mcp.tools.monitoring.monitoring_tools import (
    register_monitoring_tools,
)
from session_buddy.mcp.tools.monitoring.session_analytics_tools import (
    register_session_analytics_tools,
)
from session_buddy.mcp.tools.monitoring.workflow_metrics_tools import (
    register_workflow_metrics_tools,
)

# Oneiric integration tools
from session_buddy.mcp.tools.oneiric.oneiric_discovery_tools import (
    register_oneiric_discovery_tools,
)

# Session tools
from session_buddy.mcp.tools.session.crackerjack_tools import (
    register_crackerjack_tools,
)
from session_buddy.mcp.tools.session.hooks_tools import register_hooks_tools
from session_buddy.mcp.tools.session.migration_tools import register_migration_tools
from session_buddy.mcp.tools.session.prompt_tools import register_prompt_tools
from session_buddy.mcp.tools.session.session_tools import register_session_tools

# Subscribers (cross-system integration)
from session_buddy.subscribers.code_graph_subscriber import (
    register_code_graph_tools,
)

__all__ = [
    # Advanced
    "register_conscious_agent_tools",
    "register_extraction_tools",
    "register_fingerprint_tools",
    "register_intent_tools",
    # Collaboration
    "register_team_tools",
    "register_knowledge_graph_tools",
    # Infrastructure
    "register_access_log_tools",
    "register_cache_tools",
    "register_feature_flags_tools",
    "register_pool_tools",
    "register_serverless_tools",
    # Intelligence
    "AgentAnalyzer",
    "AgentType",
    "register_llm_tools",
    # Memory
    "register_memory_tools",
    "register_category_tools",
    "register_search_tools",
    "register_validated_memory_tools",
    # Monitoring
    "register_bottleneck_tools",
    "register_memory_health_tools",
    "register_monitoring_tools",
    "register_session_analytics_tools",
    "register_workflow_metrics_tools",
    # Oneiric
    "register_oneiric_discovery_tools",
    # Session
    "register_session_tools",
    "register_crackerjack_tools",
    "register_hooks_tools",
    "register_migration_tools",
    "register_prompt_tools",
    # Subscribers
    "register_code_graph_tools",
]
