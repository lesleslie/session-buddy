"""MCP tools for fingerprint-based duplicate detection (Phase 4).

This module provides tools for:
- Finding duplicate and near-duplicate content using MinHash signatures
- Searching for similar content based on fingerprint similarity
- Computing deduplication statistics for quality monitoring
- Batch deduplication of existing content

These tools complement the semantic search capabilities by providing
content-level similarity detection independent of semantic meaning.
"""

from __future__ import annotations

import logging
import typing as t
from typing import Any

# Import the fingerprint utilities
from session_buddy.utils.fingerprint import MinHashSignature

logger = logging.getLogger(__name__)


def register_fingerprint_tools(mcp: Any) -> None:
    """Register all fingerprint tools with the MCP server.

    Args:
        mcp: FastMCP instance to register tools with
    """
    mcp.tool()(find_duplicates)
    mcp.tool()(fingerprint_search)
    mcp.tool()(deduplication_stats)
    mcp.tool()(deduplicate_content)


async def find_duplicates(
    content: str,
    content_type: t.Literal["conversation", "reflection"] = "reflection",
    threshold: float = 0.85,
    limit: int = 10,
    collection_name: str = "default",
) -> dict[str, t.Any]:
    """Find duplicate or near-duplicate content using MinHash fingerprinting.

    This tool uses character n-gram based MinHash signatures to efficiently
    detect duplicates and near-duplicates. Unlike semantic search, this detects
    content-level similarity regardless of meaning.

    Args:
        content: Content to check for duplicates
        content_type: Type of content ("conversation" or "reflection")
        threshold: Minimum Jaccard similarity (0.0 to 1.0)
                   - 0.95+: Near-identical content (perfect duplicate)
                   - 0.85-0.95: Near-duplicates with minor edits
                   - 0.70-0.85: Related content with significant differences
        limit: Maximum number of duplicates to return
        collection_name: Name of the collection to search

    Returns:
        Dictionary with:
        - success: True if duplicates found
        - duplicates: List of duplicate entries with:
            - id: Content ID
            - content: Existing content
            - similarity: Jaccard similarity score
        - count: Number of duplicates found
        - message: Human-readable summary

    Examples:
        >>> await find_duplicates("Python async patterns", threshold=0.90)
        {
            "success": True,
            "duplicates": [
                {"id": "abc123", "content": "Python async patterns", "similarity": 1.0}
            ],
            "count": 1,
            "message": "Found 1 duplicate(s) with similarity >= 0.90"
        }
    """
    try:
        # Import here to avoid circular imports
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        # Generate fingerprint for the content
        fingerprint = MinHashSignature.from_text(content)

        # Connect to database
        async with ReflectionDatabaseAdapterOneiric(
            collection_name=collection_name
        ) as db:
            # Check for duplicates using the adapter's method
            duplicates = db._check_for_duplicates(
                fingerprint, content_type, threshold=threshold
            )

            # Apply limit
            duplicates = duplicates[:limit]

            return {
                "success": True,
                "duplicates": duplicates,
                "count": len(duplicates),
                "message": f"Found {len(duplicates)} duplicate(s) with similarity >= {threshold:.2f}",
                "threshold_used": threshold,
                "content_type": content_type,
            }

    except Exception as e:
        logger.error(f"Error finding duplicates: {e}")
        return {
            "success": False,
            "duplicates": [],
            "count": 0,
            "message": f"Error finding duplicates: {e}",
        }


async def fingerprint_search(
    query: str,
    content_type: t.Literal["conversation", "reflection"] | None = None,
    threshold: float = 0.70,
    limit: int = 10,
    collection_name: str = "default",
) -> dict[str, t.Any]:
    """Search for similar content using fingerprint similarity.

    Unlike semantic search which finds conceptually related content,
    fingerprint search finds content that shares similar text patterns.
    This is useful for detecting content reuse, variations, and derivatives.

    Args:
        query: Search query text
        content_type: Filter by content type (None = search both)
        threshold: Minimum similarity threshold (default 0.70)
        limit: Maximum results per content type
        collection_name: Name of the collection to search

    Returns:
        Dictionary with:
        - success: True if search completed
        - results: Combined results from conversations and reflections
        - conversation_results: Results from conversations (if searched)
        - reflection_results: Results from reflections (if searched)
        - total_results: Total number of results

    Examples:
        >>> await fingerprint_search("async await patterns", threshold=0.75)
        {
            "success": True,
            "total_results": 3,
            "conversation_results": [...],
            "reflection_results": [...]
        }
    """
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        # Generate fingerprint for query
        fingerprint = MinHashSignature.from_text(query)

        all_results = []
        conversation_results = []
        reflection_results = []

        # Connect to database
        async with ReflectionDatabaseAdapterOneiric(
            collection_name=collection_name
        ) as db:
            # Search conversations if not filtered out
            if content_type is None or content_type == "conversation":
                conversation_duplicates = db._check_for_duplicates(
                    fingerprint, "conversation", threshold=threshold
                )
                conversation_results = conversation_duplicates[:limit]
                all_results.extend(conversation_results)

            # Search reflections if not filtered out
            if content_type is None or content_type == "reflection":
                reflection_duplicates = db._check_for_duplicates(
                    fingerprint, "reflection", threshold=threshold
                )
                reflection_results = reflection_duplicates[:limit]
                all_results.extend(reflection_results)

        return {
            "success": True,
            "results": all_results,
            "conversation_results": conversation_results
            if conversation_results
            else [],
            "reflection_results": reflection_results if reflection_results else [],
            "total_results": len(all_results),
            "message": f"Found {len(all_results)} similar items using fingerprint search",
            "threshold_used": threshold,
        }

    except Exception as e:
        logger.error(f"Error in fingerprint search: {e}")
        return {
            "success": False,
            "results": [],
            "conversation_results": [],
            "reflection_results": [],
            "total_results": 0,
            "message": f"Error in fingerprint search: {e}",
        }


async def deduplication_stats(
    collection_name: str = "default",
    threshold: float = 0.85,
) -> dict[str, t.Any]:
    """Compute deduplication statistics for the database.

    Analyzes all stored content to provide statistics on duplicate rates
    and storage efficiency. This helps assess the impact of deduplication
    and identify potential bloat.

    Args:
        collection_name: Name of the collection to analyze
        threshold: Similarity threshold for duplicate detection

    Returns:
        Dictionary with:
        - success: True if analysis completed
        - total_conversations: Total number of conversations
        - total_reflections: Total number of reflections
        - duplicate_conversations: Number of duplicate conversations
        - duplicate_reflections: Number of duplicate reflections
        - duplicate_rate: Percentage of content that is duplicated
        - storage_saved_bytes: Estimated storage saved by deduplication
        - message: Human-readable summary

    Examples:
        >>> await deduplication_stats(threshold=0.90)
        {
            "success": True,
            "total_conversations": 100,
            "total_reflections": 250,
            "duplicate_conversations": 15,
            "duplicate_reflections": 40,
            "duplicate_rate": 18.6,
            "message": "18.6% of content is duplicated at 0.90 threshold"
        }
    """
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        async with ReflectionDatabaseAdapterOneiric(
            collection_name=collection_name
        ) as db:
            # Get total counts
            conv_total_result = db.conn.execute(
                f"SELECT COUNT(*) FROM {collection_name}_conversations"
            ).fetchone()
            total_conversations = conv_total_result[0] if conv_total_result else 0

            refl_total_result = db.conn.execute(
                f"SELECT COUNT(*) FROM {collection_name}_reflections"
            ).fetchone()
            total_reflections = refl_total_result[0] if refl_total_result else 0

            # Check for duplicates in conversations
            # This is expensive for large databases, so we sample if needed
            duplicate_conversations = 0
            duplicate_reflections = 0

            # Get all conversations and check for duplicates
            conv_result = db.conn.execute(
                f"""
                SELECT id, content, fingerprint
                FROM {collection_name}_conversations
                WHERE fingerprint IS NOT NULL
                """
            ).fetchall()

            seen_fingerprints = set()
            for row in conv_result:
                _ = row[0]  # content_id (unused)
                _ = row[1]  # content (unused)
                fingerprint_bytes = row[2]

                if not fingerprint_bytes:
                    continue

                # Check if this fingerprint is similar to any seen fingerprint
                try:
                    fingerprint = MinHashSignature.from_bytes(fingerprint_bytes)
                    is_duplicate = False

                    for seen_fp_bytes in seen_fingerprints:
                        seen_fp = MinHashSignature.from_bytes(seen_fp_bytes)
                        similarity = fingerprint.estimate_jaccard_similarity(seen_fp)
                        if similarity >= threshold:
                            is_duplicate = True
                            break

                    if is_duplicate:
                        duplicate_conversations += 1
                    else:
                        seen_fingerprints.add(fingerprint_bytes)

                except Exception:
                    continue

            # Get all reflections and check for duplicates
            refl_result = db.conn.execute(
                f"""
                SELECT id, content, fingerprint
                FROM {collection_name}_reflections
                WHERE fingerprint IS NOT NULL
                """
            ).fetchall()

            seen_fingerprints = set()
            for row in refl_result:
                _ = row[0]  # content_id (unused)
                _ = row[1]  # content (unused)
                fingerprint_bytes = row[2]

                if not fingerprint_bytes:
                    continue

                try:
                    fingerprint = MinHashSignature.from_bytes(fingerprint_bytes)
                    is_duplicate = False

                    for seen_fp_bytes in seen_fingerprints:
                        seen_fp = MinHashSignature.from_bytes(seen_fp_bytes)
                        similarity = fingerprint.estimate_jaccard_similarity(seen_fp)
                        if similarity >= threshold:
                            is_duplicate = True
                            break

                    if is_duplicate:
                        duplicate_reflections += 1
                    else:
                        seen_fingerprints.add(fingerprint_bytes)

                except Exception:
                    continue

            total_items = total_conversations + total_reflections
            total_duplicates = duplicate_conversations + duplicate_reflections
            duplicate_rate = (
                (total_duplicates / total_items * 100) if total_items > 0 else 0
            )

            return {
                "success": True,
                "total_conversations": total_conversations,
                "total_reflections": total_reflections,
                "total_items": total_items,
                "duplicate_conversations": duplicate_conversations,
                "duplicate_reflections": duplicate_reflections,
                "total_duplicates": total_duplicates,
                "duplicate_rate": round(duplicate_rate, 2),
                "threshold_used": threshold,
                "message": f"{duplicate_rate:.1f}% of content ({total_duplicates}/{total_items} items) is duplicated at {threshold:.2f} threshold",
            }

    except Exception as e:
        logger.error(f"Error computing deduplication stats: {e}")
        return {
            "success": False,
            "total_conversations": 0,
            "total_reflections": 0,
            "total_items": 0,
            "duplicate_conversations": 0,
            "duplicate_reflections": 0,
            "total_duplicates": 0,
            "duplicate_rate": 0,
            "message": f"Error computing deduplication stats: {e}",
        }


async def deduplicate_content(  # noqa: C901
    content_type: t.Literal["conversation", "reflection", "both"] = "both",
    threshold: float = 0.85,
    dry_run: bool = True,
    collection_name: str = "default",
) -> dict[str, t.Any]:
    """Remove duplicate content from the database.

    This tool identifies and removes duplicate content to reduce database
    bloat and improve search quality. Use dry_run=True first to preview
    what would be deleted.

    Args:
        content_type: Type of content to deduplicate
        threshold: Similarity threshold for duplicate detection
        dry_run: If True, only report what would be deleted (recommended first)
        collection_name: Name of the collection

    Returns:
        Dictionary with:
        - success: True if operation completed
        - duplicates_removed: Number of duplicates removed (or would be removed)
        - ids_removed: List of IDs removed (or would be removed)
        - space_saved_bytes: Estimated storage saved
        - message: Human-readable summary

    Examples:
        >>> # Preview what would be deleted
        >>> await deduplicate_content(threshold=0.90, dry_run=True)
        {
            "success": True,
            "duplicates_removed": 5,
            "ids_removed": ["abc123", "def456", ...],
            "message": "Would remove 5 duplicates (dry run)"
        }

        >>> # Actually delete duplicates
        >>> await deduplicate_content(threshold=0.90, dry_run=False)
        {
            "success": True,
            "duplicates_removed": 5,
            "message": "Removed 5 duplicates"
        }
    """
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        async with ReflectionDatabaseAdapterOneiric(
            collection_name=collection_name
        ) as db:
            all_ids_to_remove = []

            # Deduplicate conversations
            if content_type in ["conversation", "both"]:
                conv_result = db.conn.execute(
                    f"""
                    SELECT id, content, fingerprint
                    FROM {collection_name}_conversations
                    WHERE fingerprint IS NOT NULL
                    ORDER BY created_at ASC
                    """
                ).fetchall()

                seen_fingerprints = set()
                for row in conv_result:
                    content_id = row[0]
                    _ = row[1]  # content (unused)
                    fingerprint_bytes = row[2]

                    if not fingerprint_bytes:
                        continue

                    try:
                        fingerprint = MinHashSignature.from_bytes(fingerprint_bytes)
                        is_duplicate = False

                        for seen_fp_bytes in seen_fingerprints:
                            seen_fp = MinHashSignature.from_bytes(seen_fp_bytes)
                            similarity = fingerprint.estimate_jaccard_similarity(
                                seen_fp
                            )
                            if similarity >= threshold:
                                is_duplicate = True
                                break

                        if is_duplicate:
                            all_ids_to_remove.append(
                                {"id": content_id, "type": "conversation"}
                            )
                        else:
                            seen_fingerprints.add(fingerprint_bytes)

                    except Exception:
                        continue

            # Deduplicate reflections
            if content_type in ["reflection", "both"]:
                refl_result = db.conn.execute(
                    f"""
                    SELECT id, content, fingerprint
                    FROM {collection_name}_reflections
                    WHERE fingerprint IS NOT NULL
                    ORDER BY created_at ASC
                    """
                ).fetchall()

                seen_fingerprints = set()
                for row in refl_result:
                    content_id = row[0]
                    _ = row[1]  # content (unused)
                    fingerprint_bytes = row[2]

                    if not fingerprint_bytes:
                        continue

                    try:
                        fingerprint = MinHashSignature.from_bytes(fingerprint_bytes)
                        is_duplicate = False

                        for seen_fp_bytes in seen_fingerprints:
                            seen_fp = MinHashSignature.from_bytes(seen_fp_bytes)
                            similarity = fingerprint.estimate_jaccard_similarity(
                                seen_fp
                            )
                            if similarity >= threshold:
                                is_duplicate = True
                                break

                        if is_duplicate:
                            all_ids_to_remove.append(
                                {"id": content_id, "type": "reflection"}
                            )
                        else:
                            seen_fingerprints.add(fingerprint_bytes)

                    except Exception:
                        continue

            total_duplicates = len(all_ids_to_remove)

            if dry_run:
                return {
                    "success": True,
                    "duplicates_removed": total_duplicates,
                    "ids_removed": [item["id"] for item in all_ids_to_remove],
                    "details": all_ids_to_remove,
                    "space_saved_bytes": total_duplicates * 512,  # Approximate
                    "message": f"[DRY RUN] Would remove {total_duplicates} duplicates at threshold {threshold:.2f}",
                }

            # Actually delete the duplicates
            duplicates_removed = 0
            ids_removed = []

            for item in all_ids_to_remove:
                item_id = item["id"]
                item_type = item["type"]

                try:
                    if item_type == "conversation":
                        db.conn.execute(
                            f"DELETE FROM {collection_name}_conversations WHERE id = ?",
                            [item_id],
                        )
                    else:  # reflection
                        db.conn.execute(
                            f"DELETE FROM {collection_name}_reflections WHERE id = ?",
                            [item_id],
                        )

                    duplicates_removed += 1
                    ids_removed.append(item_id)

                except Exception as e:
                    logger.warning(f"Failed to delete {item_type} {item_id}: {e}")
                    continue

            return {
                "success": True,
                "duplicates_removed": duplicates_removed,
                "ids_removed": ids_removed,
                "space_saved_bytes": duplicates_removed * 512,  # Approximate
                "message": f"Removed {duplicates_removed} duplicates at threshold {threshold:.2f}",
            }

    except Exception as e:
        logger.error(f"Error deduplicating content: {e}")
        return {
            "success": False,
            "duplicates_removed": 0,
            "ids_removed": [],
            "space_saved_bytes": 0,
            "message": f"Error deduplicating content: {e}",
        }
