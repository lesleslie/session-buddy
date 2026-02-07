#!/usr/bin/env python3
"""MCP tools for multi-provider entity extraction and persistence."""

from __future__ import annotations

import typing as t
from typing import TYPE_CHECKING

from session_buddy.config.feature_flags import get_feature_flags
from session_buddy.memory.entity_extractor import EntityExtractionEngine
from session_buddy.memory.persistence import insert_processed_memory

if TYPE_CHECKING:
    from fastmcp import FastMCP


async def extract_and_store_memory(
    user_input: str,
    ai_output: str,
    project: str | None = None,
    namespace: str = "default",
    activity_score: float | None = None,
) -> dict[str, t.Any]:
    """Extract entities using cascade and persist to v2 tables (when enabled).

    This is a module-level function that can be imported and called directly
    by both the MCP tool and internal modules like app_monitor.
    """
    flags = get_feature_flags()
    if not flags.enable_llm_entity_extraction or not flags.use_schema_v2:
        return {
            "status": "skipped",
            "reason": "feature_disabled",
        }

    engine = EntityExtractionEngine()
    result = await engine.extract_entities(user_input, ai_output)

    # Persist into v2 tables
    content = f"User: {user_input}\nAssistant: {ai_output}"

    # Try to compute embedding using ReflectionDatabaseAdapter (optional)
    embedding = None
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        async with ReflectionDatabaseAdapterOneiric() as db:
            embedding = await db._generate_embedding(content)
    except Exception:
        # Optional dependency or model not available; persist without embedding
        embedding = None

    # Activity-based importance scoring: blend LLM importance with activity
    pm = result.processed_memory
    if activity_score is not None:
        from contextlib import suppress

        with suppress(Exception):
            act = max(0.0, min(1.0, float(activity_score)))
            pm.importance_score = max(
                0.0, min(1.0, 0.7 * pm.importance_score + 0.3 * act)
            )

    persist = insert_processed_memory(
        pm,
        content=content,
        project=project,
        namespace=namespace,
        embedding=embedding,
    )

    # Log extraction provider usage in access log (for metrics)
    from contextlib import suppress

    with suppress(Exception):
        from session_buddy.memory.persistence import log_memory_access

        log_memory_access(
            persist.memory_id, access_type=f"extract:{result.llm_provider}"
        )

    return {
        "status": "ok",
        "llm_provider": result.llm_provider,
        "extraction_time_ms": result.extraction_time_ms,
        "memory_id": persist.memory_id,
        "entity_ids": persist.entity_ids,
        "relationship_ids": persist.relationship_ids,
    }


def register_extraction_tools(mcp: FastMCP) -> None:
    @mcp.tool()  # type: ignore[no-untyped-call]
    async def extract_and_store_memory_tool(
        user_input: str,
        ai_output: str,
        project: str | None = None,
        namespace: str = "default",
        activity_score: float | None = None,
    ) -> dict[str, t.Any]:
        """Extract entities using cascade and persist to v2 tables (when enabled)."""
        return await extract_and_store_memory(
            user_input, ai_output, project, namespace, activity_score
        )
