"""Phase 3: Enhanced MCP Tools for Knowledge Graph.

This module adds Phase 3 MCP tools for:
1. Transitive relationship discovery
2. Pattern-based relationship extraction
3. Enhanced relationship statistics with confidence

These tools extend the base knowledge_graph_tools.py functionality.

"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from session_buddy.utils.error_management import _get_logger
from session_buddy.utils.messages import ToolMessages

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


# ============================================================================
# Phase 3 Tool Implementations
# ============================================================================


async def _discover_transitive_relationships_impl(
    max_depth: int = 3,
    min_confidence: str = "medium",
    limit: int = 100,
) -> str:
    """Discover transitive relationships (A→B→C implies A→C).

    Args:
        max_depth: Maximum chain length (default: 3)
        min_confidence: Minimum confidence level (low/medium/high)
        limit: Maximum relationships to create

    Returns:
        Summary of transitive relationships discovered
    """

    async def operation_wrapper(kg: Any) -> str:
        result = await kg.discover_transitive_relationships(
            max_depth=max_depth,
            min_confidence=min_confidence,
            limit=limit,
        )

        lines = [
            "🔗 Transitive Relationship Discovery Results",
            "",
            f"✅ Created: {result['created']}",
            f"⏭️ Skipped: {result['skipped']}",
            f"🔁 Duplicates Avoided: {result['duplicate']}",
            f"📊 Total Examined: {result['total_examined']}",
        ]

        _get_logger().info(
            "Transitive relationships discovered",
            created=result["created"],
            skipped=result["skipped"],
            duplicate=result["duplicate"],
        )

        return "\n".join(lines)

    return await _execute_kg_operation(
        "Discover transitive relationships",
        operation_wrapper,
    )


async def _extract_pattern_relationships_impl(
    entity_name: str,
    pattern_types: list[str] | None = None,
    auto_create: bool = False,
) -> str:
    """Extract relationships from entity observations using patterns.

    Args:
        entity_name: Name of entity to process
        pattern_types: Optional list of pattern types to extract (None = all)
        auto_create: Auto-create target entities if they don't exist

    Returns:
        Summary of pattern-based relationships extracted
    """

    async def operation_wrapper(kg: Any) -> str:
        # Find entity
        entity = await kg.find_entity_by_name(entity_name)
        if not entity:
            return f"❌ Entity '{entity_name}' not found"

        observations = entity.get("observations", [])
        if not observations:
            return f"ℹ️ Entity '{entity_name}' has no observations to process"

        # Extract patterns
        discovered = kg._extract_relationships_from_observations(
            entity_id=entity["id"],
            entity_name=entity_name,
            observations=observations,
        )

        # Filter by pattern types if specified
        if pattern_types:
            discovered = [d for d in discovered if d["relation_type"] in pattern_types]

        # Create relationships
        created = 0
        failed = 0

        for rel in discovered:
            try:
                # Try to find target entity
                target_entity = await kg.find_entity_by_name(rel["to_name"])

                if not target_entity and auto_create:
                    # Auto-create target entity
                    target_entity = await kg.create_entity(
                        name=rel["to_name"],
                        entity_type="unknown",  # Default type
                        observations=["Auto-created via pattern extraction"],
                    )

                if target_entity:
                    await kg.create_relation(
                        from_entity=entity["id"],
                        to_entity=target_entity["id"],
                        relation_type=rel["relation_type"],
                        properties={
                            "confidence": rel["confidence"],
                            "discovery_method": rel["discovery_method"],
                            "evidence": rel["evidence"],
                        },
                    )
                    created += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        lines = [
            f"🔍 Pattern Extraction Results for '{entity_name}'",
            "",
            f"📊 Patterns Found: {len(discovered)}",
            f"✅ Relationships Created: {created}",
            f"❌ Failed: {failed}",
        ]

        if discovered:
            lines.extend(["", "Discovered Patterns:"])
            for rel in discovered[:10]:  # Show first 10
                lines.append(
                    f"  • {rel['from_name']} --[{rel['relation_type']}]--> {rel['to_name']}"
                )
            if len(discovered) > 10:
                lines.append(f"  ... and {len(discovered) - 10} more")

        _get_logger().info(
            "Pattern relationships extracted",
            entity_name=entity_name,
            discovered=len(discovered),
            created=created,
        )

        return "\n".join(lines)

    return await _execute_kg_operation(
        "Extract pattern relationships",
        operation_wrapper,
    )


async def _get_relationship_confidence_stats_impl() -> str:
    """Get statistics about relationship confidence distribution.

    Returns:
        Confidence distribution statistics
    """

    async def operation_wrapper(kg: Any) -> str:
        # Get all relationships with confidence
        conn = kg._get_conn()
        result = conn.execute(
            """
            SELECT properties, relation_type
            FROM kg_relationships
        """
        ).fetchall()

        confidence_counts = {"low": 0, "medium": 0, "high": 0, "none": 0}
        type_by_confidence: dict[str, dict[str, int]] = {
            "low": {},
            "medium": {},
            "high": {},
        }

        for row in result:
            props_json = row[0]
            rel_type = row[1]

            try:
                # Use json.loads for safe parsing
                props_dict = json.loads(props_json) if props_json else {}
                confidence = props_dict.get("confidence", "none")
            except (json.JSONDecodeError, TypeError, ValueError):
                confidence = "none"

            confidence_counts[confidence] += 1

            if confidence in type_by_confidence:
                type_by_confidence[confidence][rel_type] = (
                    type_by_confidence[confidence].get(rel_type, 0) + 1
                )

        total = sum(confidence_counts.values())

        lines = [
            "📊 Relationship Confidence Statistics",
            "",
            f"📈 Total Relationships: {total}",
            "",
            "Confidence Distribution:",
            f"  🔴 Low: {confidence_counts['low']} ({confidence_counts['low'] / total * 100 if total > 0 else 0:.1f}%)",
            f"  🟡 Medium: {confidence_counts['medium']} ({confidence_counts['medium'] / total * 100 if total > 0 else 0:.1f}%)",
            f"  🟢 High: {confidence_counts['high']} ({confidence_counts['high'] / total * 100 if total > 0 else 0:.1f}%)",
            f"  ⚪ Not Scored: {confidence_counts['none']} ({confidence_counts['none'] / total * 100 if total > 0 else 0:.1f}%)",
        ]

        # Show type breakdown by confidence
        for conf in ["high", "medium", "low"]:
            if type_by_confidence[conf]:
                lines.extend(["", f"🔵 {conf.capitalize()} Confidence Types:"])
                sorted_types = sorted(
                    type_by_confidence[conf].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
                for rel_type, count in sorted_types[:5]:  # Top 5
                    lines.append(f"   • {rel_type}: {count}")

        return "\n".join(lines)

    return await _execute_kg_operation(
        "Get confidence stats",
        operation_wrapper,
    )


# Import helper from base module
async def _execute_kg_operation(
    operation_name: str, operation: Callable[[Any], Awaitable[str]]
) -> str:
    """Execute a knowledge graph operation with error handling."""
    try:
        from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
            KnowledgeGraphDatabaseAdapterOneiric,
        )
        from session_buddy.di import configure

        configure()
        async with KnowledgeGraphDatabaseAdapterOneiric() as kg:
            return await operation(kg)
    except RuntimeError as e:
        return f"❌ {e!s}. Install dependencies: uv sync"
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


def register_phase3_knowledge_graph_tools(mcp_server: Any) -> None:
    """Register Phase 3 knowledge graph MCP tools with the server."""

    @mcp_server.tool()  # type: ignore[misc]
    async def discover_transitive_relationships(
        max_depth: int = 3,
        min_confidence: str = "medium",
        limit: int = 100,
    ) -> str:
        """Discover transitive relationships (A→B→C implies A→C).

        Args:
            max_depth: Maximum chain length to search (default: 3)
            min_confidence: Minimum confidence level (low/medium/high)
            limit: Maximum relationships to create

        Returns:
            Summary of transitive relationships discovered

        Example:
            If we have:
                - session-buddy uses FastMCP
                - FastMCP extends MCP
            Then discover:
                - session-buddy uses MCP (transitive)
        """
        return await _discover_transitive_relationships_impl(
            max_depth, min_confidence, limit
        )

    @mcp_server.tool()  # type: ignore[misc]
    async def extract_pattern_relationships(
        entity_name: str,
        pattern_types: list[str] | None = None,
        auto_create: bool = False,
    ) -> str:
        """Extract relationships from entity observations using patterns.

        Scans entity observations for relationship patterns like:
            - "X uses Y" → X uses Y
            - "X extends Y" → X extends Y
            - "X depends on Y" → X depends_on Y

        Args:
            entity_name: Name of entity to process
            pattern_types: Optional filter by pattern types (e.g., ["uses", "extends"])
            auto_create: Auto-create target entities if they don't exist

        Returns:
            Summary of pattern-based relationships extracted

        Example:
            >>> extract_pattern_relationships(
            ...     entity_name="session-buddy",
            ...     auto_create=True
            ... )
            Extracts: session-buddy uses FastMCP
        """
        return await _extract_pattern_relationships_impl(
            entity_name, pattern_types, auto_create
        )

    @mcp_server.tool()  # type: ignore[misc]
    async def get_relationship_confidence_stats() -> str:
        """Get statistics about relationship confidence distribution.

        Shows how many relationships have high/medium/low confidence scores,
        broken down by relationship type.

        Returns:
            Confidence distribution statistics with type breakdown

        Example output:
            High Confidence:
              • uses: 45
              • extends: 23
              • very_similar_to: 18
        """
        return await _get_relationship_confidence_stats_impl()


__all__ = [
    "register_phase3_knowledge_graph_tools",
    "_discover_transitive_relationships_impl",
    "_extract_pattern_relationships_impl",
    "_get_relationship_confidence_stats_impl",
]
