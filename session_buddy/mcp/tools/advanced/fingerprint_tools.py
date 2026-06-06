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
import re
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
    db_path: str | None = None,
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
            collection_name=collection_name,
            db_path=db_path,
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
    db_path: str | None = None,
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
            collection_name=collection_name,
            db_path=db_path,
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

            # Fallback for short queries when MinHash similarity is too strict.
            if not all_results:
                fallback_results = _search_by_token_overlap(
                    db,
                    query=query,
                    collection_name=collection_name,
                    content_type=content_type,
                    limit=limit,
                )
                all_results.extend(fallback_results)
                if content_type is None or content_type == "conversation":
                    conversation_results = [
                        result
                        for result in fallback_results
                        if result.get("content_type") == "conversation"
                    ]
                if content_type is None or content_type == "reflection":
                    reflection_results = [
                        result
                        for result in fallback_results
                        if result.get("content_type") == "reflection"
                    ]

        return {
            "success": True,
            "results": all_results,
            "conversation_results": conversation_results,
            "reflection_results": reflection_results,
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


def _search_by_token_overlap(
    db: Any,
    query: str,
    collection_name: str,
    content_type: t.Literal["conversation", "reflection"] | None,
    limit: int,
) -> list[dict[str, t.Any]]:
    """Fallback search using token overlap when fingerprint matching is too strict."""
    tokens = [
        token
        for token in re.findall(r"[A-Za-z0-9_]+", query.lower())
        if len(token) >= 3
    ]
    if not tokens:
        return []

    results: list[dict[str, t.Any]] = []
    table_specs: list[tuple[str, str]] = []
    if content_type is None or content_type == "conversation":
        table_specs.append((f"{collection_name}_conversations", "conversation"))
    if content_type is None or content_type == "reflection":
        table_specs.append((f"{collection_name}_reflections", "reflection"))

    for table_name, label in table_specs:
        where_clauses = " OR ".join(["lower(content) LIKE ?" for _ in tokens])
        params = [f"%{token}%" for token in tokens]
        if label == "conversation":
            rows = db.conn.execute(
                f"""
                SELECT id, content, metadata, created_at, updated_at
                FROM {table_name}
                WHERE {where_clauses}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()
        else:
            rows = db.conn.execute(
                f"""
                SELECT id, content, tags, created_at, updated_at
                FROM {table_name}
                WHERE {where_clauses}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()

        for row in rows:
            content = row[1] or ""
            content_lower = content.lower()
            overlap = sum(1 for token in tokens if token in content_lower)
            similarity = overlap / len(tokens)
            tags = []
            if label == "reflection":
                tags = list(row[2]) if row[2] else []
            results.append(
                {
                    "id": row[0],
                    "content": content,
                    "tags": tags,
                    "created_at": row[3].isoformat() if row[3] else None,
                    "updated_at": row[4].isoformat() if row[4] else None,
                    "similarity": similarity,
                    "content_type": label,
                }
            )

    results.sort(key=lambda item: item.get("similarity", 0.0), reverse=True)
    return results[:limit]


async def deduplication_stats(
    collection_name: str = "default",
    threshold: float = 0.85,
    db_path: str | None = None,
) -> dict[str, t.Any]:
    """Compute deduplication statistics for the database.

    Analyzes all stored content to provide statistics on duplicate rates
    and storage efficiency. This helps assess the impact of deduplication
    and identify potential bloat.

    Args:
        collection_name: Name of the collection to analyze
        threshold: Similarity threshold for duplicate detection

    Returns:
        Dictionary with deduplication statistics

    """
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        async with ReflectionDatabaseAdapterOneiric(
            collection_name=collection_name,
            db_path=db_path,
        ) as db:
            # Get total counts
            total_conversations = _get_table_count(db, collection_name, "conversations")
            total_reflections = _get_table_count(db, collection_name, "reflections")

            # Count duplicates in each table
            duplicate_conversations = await _count_duplicates_in_table(
                db, collection_name, "conversations", threshold
            )
            duplicate_reflections = await _count_duplicates_in_table(
                db, collection_name, "reflections", threshold
            )

            return _format_stats_result(
                total_conversations,
                total_reflections,
                duplicate_conversations,
                duplicate_reflections,
                threshold,
            )

    except Exception as e:
        logger.error(f"Error computing deduplication stats: {e}")
        return _format_stats_error(str(e))


def _get_table_count(
    db: Any,
    collection_name: str,
    table_name: str,
) -> int:
    """Get total count from a table.

    Args:
        db: Database adapter
        collection_name: Collection name
        table_name: Table name

    Returns:
        Total count

    """
    result = db.conn.execute(
        f"SELECT COUNT(*) FROM {collection_name}_{table_name}"
    ).fetchone()
    return result[0] if result else 0


async def _count_duplicates_in_table(
    db: Any,
    collection_name: str,
    table_name: str,
    threshold: float,
) -> int:
    """Count duplicates in a specific table.

    Args:
        db: Database adapter
        collection_name: Collection name
        table_name: Table name
        threshold: Similarity threshold

    Returns:
        Number of duplicates found

    """
    result = db.conn.execute(
        f"""
        SELECT fingerprint
        FROM {collection_name}_{table_name}
        WHERE fingerprint IS NOT NULL
        """
    ).fetchall()

    seen_fingerprints: set[bytes] = set()
    duplicate_count = 0

    for row in result:
        fingerprint_bytes = row[0]

        if not fingerprint_bytes:
            continue

        try:
            if _is_duplicate_fingerprint(
                fingerprint_bytes, seen_fingerprints, threshold
            ):
                duplicate_count += 1
            else:
                seen_fingerprints.add(fingerprint_bytes)
        except Exception:
            continue

    return duplicate_count


def _is_duplicate_fingerprint(
    fingerprint_bytes: bytes,
    seen_fingerprints: set[bytes],
    threshold: float,
) -> bool:
    """Check if a fingerprint is a duplicate.

    Args:
        fingerprint_bytes: Fingerprint bytes to check
        seen_fingerprints: Set of seen fingerprint bytes
        threshold: Similarity threshold

    Returns:
        True if duplicate, False otherwise

    """
    fingerprint = MinHashSignature.from_bytes(fingerprint_bytes)

    for seen_fp_bytes in seen_fingerprints:
        seen_fp = MinHashSignature.from_bytes(seen_fp_bytes)
        similarity = fingerprint.estimate_jaccard_similarity(seen_fp)
        if similarity >= threshold:
            return True

    return False


def _format_stats_result(
    total_conversations: int,
    total_reflections: int,
    duplicate_conversations: int,
    duplicate_reflections: int,
    threshold: float,
) -> dict[str, t.Any]:
    """Format deduplication statistics result.

    Args:
        total_conversations: Total conversation count
        total_reflections: Total reflection count
        duplicate_conversations: Duplicate conversation count
        duplicate_reflections: Duplicate reflection count
        threshold: Threshold used

    Returns:
        Formatted statistics dictionary

    """
    total_items = total_conversations + total_reflections
    total_duplicates = duplicate_conversations + duplicate_reflections
    duplicate_rate = (total_duplicates / total_items * 100) if total_items > 0 else 0

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


def _format_stats_error(error_message: str) -> dict[str, t.Any]:
    """Format deduplication stats error result.

    Args:
        error_message: The error message

    Returns:
        Formatted error dictionary

    """
    return {
        "success": False,
        "total_conversations": 0,
        "total_reflections": 0,
        "total_items": 0,
        "duplicate_conversations": 0,
        "duplicate_reflections": 0,
        "total_duplicates": 0,
        "duplicate_rate": 0,
        "message": f"Error computing deduplication stats: {error_message}",
    }


async def deduplicate_content(
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
        Dictionary with deduplication results

    """
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        async with ReflectionDatabaseAdapterOneiric(
            collection_name=collection_name,
            db_path=db_path,
        ) as db:
            all_ids_to_remove = await _find_duplicate_content(
                db, content_type, threshold, collection_name
            )

            if dry_run:
                return _format_dedup_dry_run_result(all_ids_to_remove, threshold)
            else:
                return await _delete_duplicate_content(
                    db, all_ids_to_remove, collection_name, threshold
                )

    except Exception as e:
        logger.error(f"Error deduplicating content: {e}")
        return _format_deduplication_error(str(e))


async def _find_duplicate_content(
    db: Any,
    content_type: str,
    threshold: float,
    collection_name: str,
) -> list[dict[str, t.Any]]:
    """Find duplicate content in database.

    Args:
        db: Database adapter
        content_type: Type of content to check
        threshold: Similarity threshold
        collection_name: Collection name

    Returns:
        List of duplicate items with id and type

    """
    all_ids_to_remove = []

    # Deduplicate conversations
    if content_type in ("conversation", "both"):
        conv_duplicates = await _find_duplicates_in_table(
            db, collection_name, "conversations", threshold
        )
        all_ids_to_remove.extend(conv_duplicates)

    # Deduplicate reflections
    if content_type in ("reflection", "both"):
        refl_duplicates = await _find_duplicates_in_table(
            db, collection_name, "reflections", threshold
        )
        all_ids_to_remove.extend(refl_duplicates)

    return all_ids_to_remove


async def _find_duplicates_in_table(
    db: Any,
    collection_name: str,
    table_name: str,
    threshold: float,
) -> list[dict[str, t.Any]]:
    """Find duplicates in a specific table.

    Args:
        db: Database adapter
        collection_name: Collection name
        table_name: "conversations" or "reflections"
        threshold: Similarity threshold

    Returns:
        List of duplicate items

    """
    result = db.conn.execute(
        f"""
        SELECT id, content, fingerprint
        FROM {collection_name}_{table_name}
        WHERE fingerprint IS NOT NULL
        ORDER BY created_at ASC
        """
    ).fetchall()

    seen_fingerprints: set[bytes] = set()
    duplicates = []

    for row in result:
        content_id = row[0]
        fingerprint_bytes = row[2]

        if not fingerprint_bytes:
            continue

        try:
            is_duplicate = _check_if_duplicate(
                fingerprint_bytes, seen_fingerprints, threshold
            )

            if is_duplicate:
                duplicates.append(
                    {"id": content_id, "type": table_name[:-1]}
                )  # Remove 's'
            else:
                seen_fingerprints.add(fingerprint_bytes)

        except Exception:
            continue

    return duplicates


def _check_if_duplicate(
    fingerprint_bytes: bytes,
    seen_fingerprints: set[bytes],
    threshold: float,
) -> bool:
    """Check if a fingerprint is a duplicate.

    Args:
        fingerprint_bytes: Fingerprint bytes to check
        seen_fingerprints: Set of seen fingerprint bytes
        threshold: Similarity threshold

    Returns:
        True if duplicate, False otherwise

    """
    fingerprint = MinHashSignature.from_bytes(fingerprint_bytes)

    for seen_fp_bytes in seen_fingerprints:
        seen_fp = MinHashSignature.from_bytes(seen_fp_bytes)
        similarity = fingerprint.estimate_jaccard_similarity(seen_fp)

        if similarity >= threshold:
            return True

    return False


def _format_dedup_dry_run_result(
    all_ids_to_remove: list[dict[str, t.Any]],
    threshold: float,
) -> dict[str, t.Any]:
    """Format dry run deduplication result.

    Args:
        all_ids_to_remove: List of items to remove
        threshold: Threshold used

    Returns:
        Formatted result dictionary

    """
    total_duplicates = len(all_ids_to_remove)
    return {
        "success": True,
        "duplicates_removed": total_duplicates,
        "ids_removed": [item["id"] for item in all_ids_to_remove],
        "details": all_ids_to_remove,
        "space_saved_bytes": total_duplicates * 512,  # Approximate
        "message": f"[DRY RUN] Would remove {total_duplicates} duplicates at threshold {threshold:.2f}",
    }


async def _delete_duplicate_content(
    db: Any,
    all_ids_to_remove: list[dict[str, t.Any]],
    collection_name: str,
    threshold: float,
) -> dict[str, t.Any]:
    """Delete duplicate content from database.

    Args:
        db: Database adapter
        all_ids_to_remove: List of items to delete
        collection_name: Collection name
        threshold: Threshold used

    Returns:
        Result dictionary with deletion statistics

    """
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


def _format_deduplication_error(error_message: str) -> dict[str, t.Any]:
    """Format deduplication error result.

    Args:
        error_message: The error message

    Returns:
        Formatted error dictionary

    """
    return {
        "success": False,
        "duplicates_removed": 0,
        "ids_removed": [],
        "space_saved_bytes": 0,
        "message": f"Error deduplicating content: {error_message}",
    }
