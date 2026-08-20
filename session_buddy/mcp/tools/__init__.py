"""MCP tools registration module.

This module exports all tool registration functions from subdirectories.
"""

# Advanced tools
# Subscribers (cross-system integration)
# Health check tools
from mcp_common.baseline_tools import register_baseline_tools
from mcp_common.health import register_health_tools as register_health_tools_sb

from ...subscribers.code_graph_subscriber import register_code_graph_tools
from .advanced.conscious_agent_tools import register_conscious_agent_tools
from .advanced.entity_extraction_tools import register_extraction_tools
from .advanced.fingerprint_tools import (
    register_fingerprint_tools,
)
from .advanced.intent_detection_tools import register_intent_tools

# Code analysis tools (tree-sitter integration)
from .code_analysis.tools import register_code_analysis_tools

# Collaboration tools
from .collaboration.knowledge_graph_phase3_tools import (
    register_phase3_knowledge_graph_tools,
)
from .collaboration.knowledge_graph_tools import (
    register_knowledge_graph_tools,
)
from .collaboration.team_tools import register_team_tools

# Conversation tools
from .conversation.conversation_tools import (
    register_conversation_tools,
)

# Cross-repo work tools (Task 9 wiring)
from .cross_repo_work_register import register_cross_repo_work_tools

# Infrastructure tools
from .infrastructure.access_log_tools import (
    register_access_log_tools,
)
from .infrastructure.cache_tools import register_cache_tools
from .infrastructure.feature_flags_tools import (
    register_feature_flags_tools,
)
from .infrastructure.pools import register_pool_tools
from .infrastructure.serverless_tools import (
    register_serverless_tools,
)

# Intelligence tools
from .intelligence.llm_tools import register_llm_tools

# Memory tools
from .memory.akosha_tools import register_akosha_tools
from .memory.category_tools import register_category_tools
from .memory.export_tools import register_export_tools
from .memory.memory_tools import register_memory_tools
from .memory.otel_trace_tools import register_otel_trace_tools
from .memory.search_tools import register_search_tools
from .memory.validated_memory_tools import (
    register_validated_memory_tools,
)

# Monitoring tools
from .monitoring.bottleneck_tools import (
    register_bottleneck_tools,
)
from .monitoring.memory_health_tools import (
    register_memory_health_tools,
)
from .monitoring.monitoring_tools import (
    register_monitoring_tools,
)
from .monitoring.session_analytics_tools import (
    register_session_analytics_tools,
)
from .monitoring.workflow_metrics_tools import (
    register_workflow_metrics_tools,
)

# Session tools
from .session.admin_shell_tracking_tools import (
    register_admin_shell_tracking_tools,
)
from .session.channel_session_state_tools import (
    register_channel_session_state_tools,
)
from .session.channel_tracking_tools import register_channel_tracking_tools
from .session.crackerjack_tools import (
    register_crackerjack_tools,
)
from .session.hooks_tools import register_hooks_tools
from .session.migration_tools import register_migration_tools
from .session.prompt_tools import register_prompt_tools
from .session.session_tools import register_session_tools

# Skills tools (Phase 4 Analytics)
from .skills.phase4_tools import register_phase4_tools

# Git worktree tools (used by Mahavishnu SessionBuddyWorktreeProvider)
from .worktree_tools import register_worktree_tools

__all__ = [
    "register_access_log_tools",
    "register_admin_shell_tracking_tools",
    "register_akosha_tools",
    "register_bottleneck_tools",
    "register_cache_tools",
    "register_category_tools",
    "register_channel_session_state_tools",
    "register_channel_tracking_tools",
    "register_code_analysis_tools",
    "register_code_graph_tools",
    "register_conscious_agent_tools",
    "register_conversation_tools",
    "register_crackerjack_tools",
    "register_cross_repo_work_tools",
    "register_export_tools",
    "register_extraction_tools",
    "register_feature_flags_tools",
    "register_fingerprint_tools",
    "register_health_tools_sb",
    "register_hooks_tools",
    "register_intent_tools",
    "register_knowledge_graph_tools",
    "register_llm_tools",
    "register_memory_health_tools",
    "register_memory_tools",
    "register_migration_tools",
    "register_monitoring_tools",
    "register_otel_trace_tools",
    "register_phase3_knowledge_graph_tools",
    "register_phase4_tools",
    "register_pool_tools",
    "register_prompt_tools",
    "register_search_tools",
    "register_serverless_tools",
    "register_session_analytics_tools",
    "register_session_tools",
    "register_team_tools",
    "register_validated_memory_tools",
    "register_workflow_metrics_tools",
    "register_worktree_tools",
]
