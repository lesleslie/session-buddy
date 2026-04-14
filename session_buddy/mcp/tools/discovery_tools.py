"""Tool discovery meta-tool for session-buddy.

Provides a ``discover_tools(query)`` tool that lets Claude search
unloaded tool descriptions.  This registry is always available so
Claude can find tools that were not loaded by the active profile.

The ``ALL_TOOLS_REGISTRY`` dict is intentionally kept as a plain
in-memory mapping (not scraped from the live ``mcp`` instance) so
it stays constant regardless of which profile is active.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Comprehensive registry of every tool session-buddy *could* register,
# keyed by the public tool name with a one-line description.
#
# NOTE: Keep this in sync when adding or renaming tools.
# ---------------------------------------------------------------------------

ALL_TOOLS_REGISTRY: dict[str, str] = {
    # -- Health (MANDATORY) --
    "ping": "Liveness probe for infrastructure health checks.",
    "health_check": "Deep health check of all subsystems.",
    "get_health_status": "Detailed health status with per-component breakdown.",
    "server_info": "Server version and configuration info.",

    # -- Session lifecycle --
    "start": "Initialize Claude session with setup and automation.",
    "end": "End Claude session with cleanup and learning capture.",
    "status": "Get current session status and project context.",
    "checkpoint": "Mid-session quality checkpoint with analysis.",
    "session_welcome": "Display session connection info.",
    "preserve_current_context": "Preserve context before interruption.",
    "pre_compact_sync": "Sync state before context compaction.",
    "store_conversation_checkpoint": "Store a conversation checkpoint from session context.",
    "create_session_context": "Create a reusable session context snapshot.",
    "restore_session_context": "Restore a previously saved session context.",

    # -- Search --
    "quick_search": "Fast semantic search across reflections.",
    "quick_search_validated": "Validated semantic search with type checking.",
    "search_conversations": "Search conversations by semantic similarity.",
    "search_summary": "Search and summarize matching reflections.",
    "progressive_search": "Multi-tier progressive search with early stopping.",
    "search_by_concept": "Search reflections by concept.",
    "search_by_concept_validated": "Validated concept search.",
    "search_by_file": "Search reflections by file path.",
    "search_by_file_validated": "Validated file-based search.",
    "search_code": "Search code patterns in reflections.",
    "search_code_patterns": "Search for code patterns with regex support.",
    "search_errors": "Search for error patterns.",
    "search_temporal": "Search by time expression.",
    "get_more_results": "Get additional search results.",
    "search_regex": "Regex-based search across reflections.",

    # -- Hooks --
    "list_hooks": "List all registered hooks.",
    "enable_hook": "Enable a specific hook.",
    "disable_hook": "Disable a specific hook.",

    # -- Conversation --
    "store_conversation": "Store a conversation with embedding support.",
    "get_conversation_statistics": "Get statistics about stored conversations.",

    # -- Extraction --
    "extract_entities_from_context": "Extract named entities from text context.",
    "extract_and_store_memory": "Extract and store memories from text.",
    "extract_and_store_memory_tool": "Extract memories from text with auto-categorization.",

    # -- Knowledge graph --
    "create_entity": "Create a knowledge graph entity.",
    "create_relation": "Create a relation between entities.",
    "search_entities": "Search knowledge graph entities.",
    "get_entity_relationships": "Get relationships for an entity.",
    "get_knowledge_graph_stats": "Knowledge graph statistics.",
    "batch_create_entities": "Bulk create entities.",
    "discover_relationships": "Auto-discover relationships between entities.",
    "discover_transitive_relationships": "Find transitive connections.",
    "find_path": "Find shortest path between entities.",
    "find_usages": "Find all usages of an entity.",
    "add_observation": "Add an observation to an entity.",
    "analyze_graph_connectivity": "Analyze knowledge graph connectivity.",
    "get_relationship_confidence_stats": "Confidence score distribution for relations.",
    "extract_pattern_relationships": "Extract patterns from relationships.",

    # -- Phase 3 knowledge graph --
    "trigger_migration": "Trigger knowledge graph data migration.",
    "migration_status": "Check migration progress and status.",
    "rollback_migration": "Rollback a failed migration.",

    # -- Cache --
    "clear_query_cache": "Clear the search query cache.",
    "invalidate_cache": "Invalidate specific cache entries.",
    "query_cache_stats": "Get cache hit/miss statistics.",
    "optimize_cache": "Optimize cache for current usage patterns.",
    "reset_cache": "Reset cache to empty state.",
    "warm_cache": "Pre-populate cache with common queries.",
    "query_rewrite_stats": "Statistics on query rewrites.",

    # -- Intent detection --
    "detect_intent": "Detect user intent from natural language.",
    "list_supported_intents": "List all supported intent categories.",
    "get_intent_suggestions": "Suggest likely intents for a query.",
    "process_natural_language_input": "Route natural language to correct tool.",
    "initialize_intent_detector": "(Re)initialize the intent detection model.",

    # -- Crackerjack integration --
    "crackerjack_help": "Show Crackerjack help and available commands.",
    "crackerjack_run": "Run a Crackerjack quality check command.",
    "crackerjack_health_check": "Check Crackerjack server health.",
    "crackerjack_history": "View Crackerjack execution history.",
    "crackerjack_metrics": "Get Crackerjack quality metrics.",
    "crackerjack_patterns": "Analyze quality patterns with Crackerjack.",
    "crackerjack_quality_trends": "View quality trends over time.",
    "execute_crackerjack_command": "Execute an arbitrary Crackerjack command.",

    # -- Feature flags --
    "feature_flags_status": "Show all feature flags and their states.",

    # -- Monitoring --
    "get_prometheus_metrics": "Export metrics in Prometheus text format.",
    "list_session_metrics": "List available session metrics.",
    "get_metrics_summary": "Summary statistics of session metrics.",
    "get_real_time_metrics": "Real-time system metrics snapshot.",
    "quality_monitor": "Run quality monitoring checks.",
    "start_app_monitoring": "Start application performance monitoring.",
    "stop_app_monitoring": "Stop application monitoring.",
    "start_interruption_monitoring": "Monitor for workflow interruptions.",
    "stop_interruption_monitoring": "Stop interruption monitoring.",
    "get_interruption_history": "History of workflow interruptions.",
    "get_activity_summary": "Summary of recent activity.",
    "detect_anomalies": "Detect anomalies in session data.",
    "query_similar_errors": "Find similar errors across sessions.",
    "get_crackerjack_quality_metrics": "Quality metrics from Crackerjack.",
    "get_crackerjack_results_history": "History of Crackerjack quality results.",
    "pycharm_health": "PyCharm IDE health check.",
    "resolve_reflection_database": "Resolve reflection database state.",
    "configure_tiers": "Configure storage tiers for data.",
    "tier_stats": "Statistics for storage tiers.",

    # -- Access log --
    "access_log_stats": "Statistics from the access log.",

    # -- Bottleneck analysis --
    "detect_quality_bottlenecks": "Detect quality bottlenecks in workflow.",
    "detect_session_pattern_bottlenecks": "Find session pattern bottlenecks.",
    "detect_velocity_bottlenecks": "Identify development velocity bottlenecks.",
    "get_bottleneck_insights": "Get actionable bottleneck insights.",

    # -- Session analytics --
    "get_session_analytics": "Comprehensive session analytics.",
    "get_session_streaks": "Development streak statistics.",
    "get_session_length_distribution": "Session duration distribution.",
    "get_productivity_insights": "Productivity analysis and insights.",
    "get_temporal_patterns": "Temporal development patterns.",
    "get_activity_correlations": "Correlations between activities.",

    # -- Workflow metrics --
    "get_workflow_metrics": "Workflow execution metrics.",
    "get_causal_chain": "Causal chain analysis for failures.",
    "get_error_hotspots": "Identify error hotspots in code.",

    # -- Memory health --
    "get_reflection_health": "Health check for the reflection database.",
    "reflection_stats": "Reflection database statistics.",
    "store_reflection": "Store an insight or reflection.",
    "store_reflection_validated": "Store with type validation.",
    "vote_on_reflection": "Upvote/downvote a reflection for relevance.",
    "reset_reflection_database": "Reset the reflection database.",
    "deduplicate_content": "Find and remove duplicate reflections.",
    "deduplication_stats": "Statistics on duplicate content.",
    "find_duplicates": "Find duplicate entries in the database.",

    # -- Phase 4 skills analytics --
    "list_skills": "List all registered development skills.",
    "get_skill_details": "Detailed information about a specific skill.",
    "get_skill_dependencies": "Skill dependency graph.",
    "get_skill_trend": "Usage trend for a skill over time.",
    "invoke_skill": "Invoke a registered skill.",
    "rollout_plan": "Plan a skill rollout strategy.",

    # -- Conscious agent --
    "start_conscious_agent": "Start the conscious agent monitoring loop.",
    "stop_conscious_agent": "Stop the conscious agent.",
    "force_conscious_analysis": "Force an immediate conscious analysis pass.",

    # -- Migration --
    "track_session_start": "Record session start for migration tracking.",
    "track_session_end": "Record session end for migration tracking.",
    "trigger_learning": "Trigger a learning cycle from session data.",

    # -- Pools --
    "create_pool": "Create a new worker pool.",
    "delete_pool": "Delete a worker pool.",
    "execute_on_pool": "Execute a task on a specific pool.",
    "execute_batch_on_pool": "Execute batch tasks on a pool.",
    "route_to_pool": "Auto-route task to best available pool.",
    "list_pools": "List all worker pools.",
    "pool_list": "List pools (alias).",
    "pool_create": "Create pool (alias).",
    "pool_delete": "Delete pool (alias).",
    "pool_execute": "Execute on pool (alias).",
    "pool_execute_batch": "Batch execute on pool (alias).",
    "pool_health": "Check pool health (alias).",
    "pool_manager_status": "Pool manager status.",
    "pool_route_task": "Route task to pool (alias).",
    "pool_status": "Get pool status (alias).",
    "check_pool_health": "Health check for all pools.",
    "get_pool_status": "Status of a specific pool.",
    "get_pool_manager_status": "Overall pool manager status.",

    # -- Serverless sessions --
    "create_serverless_session": "Create a serverless execution session.",
    "delete_serverless_session": "Delete a serverless session.",
    "update_serverless_session": "Update serverless session state.",
    "get_serverless_session": "Get serverless session details.",
    "list_serverless_sessions": "List all serverless sessions.",
    "cleanup_serverless_sessions": "Clean up expired serverless sessions.",
    "configure_serverless_storage": "Configure storage backend for serverless.",

    # -- Team tools --
    "create_team": "Create a development team.",
    "get_team_statistics": "Team performance statistics.",
    "search_team_knowledge": "Search across team knowledge bases.",

    # -- LLM tools --
    "configure_llm_provider": "Configure an LLM provider connection.",
    "chat_with_llm": "Chat with a configured LLM.",
    "generate_with_llm": "Generate content using an LLM.",
    "list_llm_providers": "List configured LLM providers.",
    "generate_embeddings": "Generate embeddings for text.",
    "get_intelligence_stats": "LLM intelligence subsystem statistics.",

    # -- Prompt tools --
    "rewrite_query": "Rewrite a search query for better results.",
    "get_cleanup_recommendations": "Get cleanup recommendations for prompts.",
    "suggest_improvements": "Suggest prompt improvements.",
    "sync_claude_qwen_config": "Sync Claude/Qwen configuration.",

    # -- Code graph (subscribers) --
    "code_get_symbol_graph": "Get symbol graph for a codebase.",
    "code_search_symbols": "Search for symbols in code.",
    "code_list_projects": "List indexed code projects.",
    "code_ingest_file": "Ingest a file into the code graph.",
    "code_ingest_directory": "Ingest a directory into the code graph.",
    "get_symbol_info": "Get detailed info for a symbol.",
    "search_similar_patterns": "Search for similar code patterns.",

    # -- Code analysis (tree-sitter) --
    "get_file_problems": "Get problems/issues for a file.",
    "get_ide_diagnostics": "Get IDE diagnostic information.",
    "get_active_files": "List currently active files in session.",
    "get_context_insights": "Get insights from current context.",
    "get_collaborative_recommendations": "Get team collaborative recommendations.",
    "fingerprint_search": "Search by code fingerprint.",
    "capture_successful_pattern": "Capture a successful code pattern.",
    "rate_pattern_outcome": "Rate the outcome of an applied pattern.",
    "record_fix_success": "Record a successful fix for learning.",
    "get_community_baselines": "Get community baselines for quality.",
    "apply_pattern": "Apply a learned pattern to code.",
    "analyze_history": "Analyze development history for patterns.",

    # -- Oneiric discovery --
    "oneiric_discover_storage": "Discover Oneiric storage backends.",
    "oneiric_explain_storage": "Explain a Oneiric storage configuration.",
    "oneiric_resolve_storage": "Resolve Oneiric storage references.",
    "oneiric_storage_health": "Health check for Oneiric storage.",

    # -- Admin shell tracking --
    # (tools registered by register_admin_shell_tracking_tools)

    # -- Akosha integration --
    "sync_to_akosha": "Sync session data to Akosha for cross-system intelligence.",
    "akosha_sync_status": "Check Akosha sync status.",
    "get_evolution_engine": "Get category evolution engine status.",
    "evolve_categories": "Trigger category evolution cycle.",
    "assign_memory_subcategory": "Assign subcategory to a memory.",
    "get_subcategories": "List subcategories for a category.",
    "category_stats": "Statistics for memory categories.",

    # -- Collaboration --
    "store_execution_result": "Store a tool execution result for collaboration.",
}


def register_discovery_tools(mcp: Any) -> None:
    """Register the tool discovery meta-tool.

    This tool is always registered regardless of the active profile so
    that Claude can discover tools that were not loaded.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool()
    async def discover_tools(query: str) -> dict[str, Any]:
        """Search for available MCP tools by name or capability."""
        query_lower = query.lower().strip()
        if not query_lower:
            return {
                "found": 0,
                "tools": [],
                "hint": "Provide a search query to discover available tools.",
            }

        results: list[dict[str, str]] = []
        for tool_name, description in ALL_TOOLS_REGISTRY.items():
            if (
                query_lower in tool_name.lower()
                or query_lower in description.lower()
            ):
                results.append({"name": tool_name, "description": description})

        results.sort(key=lambda r: r["name"])

        logger.debug(
            "discover_tools query=%r matched=%d", query_lower, len(results)
        )

        return {
            "found": len(results),
            "tools": results[:25],
            "hint": (
                "Set SESSION_BUDDY_TOOL_PROFILE=full and restart "
                "to enable all tools."
            )
            if results
            else "No matching tools found. Try broader search terms.",
        }
