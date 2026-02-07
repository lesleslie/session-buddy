#!/usr/bin/env python3
"""MCP tools to inspect feature flags and rollout guidance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from session_buddy.config.feature_flags import get_feature_flags

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_feature_flags_tools(mcp: FastMCP) -> None:
    @mcp.tool()  # type: ignore[no-untyped-call]
    async def feature_flags_status() -> dict[str, Any]:
        """Return current feature flag values."""
        flags = get_feature_flags()
        return {
            "use_schema_v2": flags.use_schema_v2,
            "enable_llm_entity_extraction": flags.enable_llm_entity_extraction,
            "enable_anthropic": flags.enable_anthropic,
            "enable_ollama": flags.enable_ollama,
            "enable_conscious_agent": flags.enable_conscious_agent,
            "enable_filesystem_extraction": flags.enable_filesystem_extraction,
        }

    @mcp.tool()  # type: ignore[no-untyped-call]
    async def rollout_plan() -> dict[str, Any]:
        """Return a staged enablement plan for features (read-only guidance)."""
        return {
            "day_1_2": [
                "Enable SESSION_MGMT_USE_SCHEMA_V2=true (parallel with v1)",
                "Verify migration: use migration_status tool",
            ],
            "day_3_4": [
                "Enable SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION=true",
                "Optionally set ANTHROPIC_API_KEY/OPENAI_API_KEY/GEMINI_API_KEY",
                "Check provider distribution via access_log_stats (by_provider)",
            ],
            "day_5_6": [
                "Enable SESSION_MGMT_ENABLE_CONSCIOUS_AGENT=true",
                "Start agent with start_conscious_agent",
                "Monitor promotions/demotions using access_log_stats",
            ],
            "day_7": [
                "Enable SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION=true",
                "Tune filesystem settings (TTL, size, ignore dirs)",
            ],
            "rollback": [
                "Use trigger_migration(dry_run=true) to preview",
                "Create backup via trigger_migration(create_backup_first=true)",
                "If needed, restore with rollback_migration(backup_path)",
            ],
            "notes": "All flags default to false; enable progressively. Monitor via access_log_stats.",
        }
