"""Search operations for reflections and conversations.

Provides semantic search using vector embeddings and text-based
fallback search when embeddings are unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import typing
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

# Import encoding/decoding utilities
from session_buddy.reflection.storage import _decode_text_from_db


async def search_conversations(
    db: duckdb.DuckDBPyConnection | Any,
    query: str,
    query_embedding: list[float] | None,
    limit: int = 5,
    min_score: float = 0.7,
    project: str | None = None,
    is_temp_db: bool = False,
    lock: Any = None,
) -> list[dict[str, Any]]:
    """Search conversations by semantic similarity or text match.

    Args:
        db: Database connection (or ReflectionDatabase instance)
        query: Search query text
        query_embedding: Pre-generated query embedding (optional)
        limit: Maximum number of results
        min_score: Minimum similarity score (0-1)
        project: Filter by project (optional)
        is_temp_db: Whether this is an in-memory temp DB
        lock: Optional lock for thread-safe temp DB access

    Returns:
        List of search results with content, score, timestamp, etc.

    Example:
        >>> results = await search_conversations(
        ...     db, "machine learning", embedding, limit=10
        ... )
        >>> for r in results:
        ...     print(f"{r['score']:.2f}: {r['content'][:50]}...")
    """
    # Get connection if db is ReflectionDatabase instance
    conn = db if hasattr(db, "execute") else typing.cast(Any, db)._get_conn()  # type: ignore[union-attr]

    # Use semantic search if embedding available
    if query_embedding is not None:
        return await _semantic_search_conversations(
            conn, query, query_embedding, limit, min_score, project, is_temp_db, lock
        )

    # Fallback to text search
    return await _text_search_conversations(
        conn, query, limit, project, is_temp_db, lock
    )


async def _semantic_search_conversations(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    query_embedding: list[float],
    limit: int,
    min_score: float,
    project: str | None,
    is_temp_db: bool,
    lock: Any,
) -> list[dict[str, Any]]:
    """Semantic search using vector cosine similarity.

    Args:
        conn: Database connection
        query: Search query (for logging)
        query_embedding: Query vector
        limit: Max results
        min_score: Minimum similarity threshold
        project: Project filter
        is_temp_db: Temp DB flag
        lock: Thread safety lock

    Returns:
        Filtered list of search results above min_score threshold
    """
    try:
        sql = """
            SELECT
                id, content, embedding, project, timestamp, metadata,
                array_cosine_similarity(embedding, CAST(? AS FLOAT[384])) as score
            FROM conversations
            WHERE embedding IS NOT NULL
        """
        params: list[Any] = [query_embedding]

        if project:
            sql += " AND project = ?"
            params.append(project)

        sql += """
            ORDER BY score DESC
            LIMIT ?
        """
        params.append(limit)

        # Execute query
        if is_temp_db:
            with lock:
                results = conn.execute(sql, params).fetchall()
        else:
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: conn.execute(sql, params).fetchall(),
            )

        # Filter by minimum score
        filtered = [row for row in results if float(row[6]) >= min_score]

        return [
            {
                "id": str(row[0]),
                "content": _decode_text_from_db(row[1]),
                "score": float(row[6]),
                "timestamp": row[4],
                "project": row[3],
                "metadata": json.loads(row[5]) if row[5] else {},
            }
            for row in filtered
        ]

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        # Fallback to text search on error
        return await _text_search_conversations(
            conn, query, limit, project, is_temp_db, lock
        )


async def _text_search_conversations(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    limit: int,
    project: str | None,
    is_temp_db: bool,
    lock: Any,
) -> list[dict[str, Any]]:
    """Fallback text search using LIKE pattern matching.

    Args:
        conn: Database connection
        query: Search query
        limit: Max results
        project: Project filter
        is_temp_db: Temp DB flag
        lock: Thread safety lock

    Returns:
        List of search results with similarity=0 (no score available)
    """
    search_terms = query.lower().split()

    # Return empty list when query is empty
    if not search_terms:
        return []

    sql = "SELECT id, content, project, timestamp, metadata FROM conversations"
    params = []

    if project:
        sql += " WHERE project = ?"
        params.append(project)

    sql += " ORDER BY timestamp DESC"

    # Execute query
    if is_temp_db:
        with lock:
            results = conn.execute(sql, params).fetchall()
    else:
        results = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: conn.execute(sql, params).fetchall(),
        )

    # Filter results by search terms (search both content and tags for reflections)
    filtered = []
    for row in results:
        content = _decode_text_from_db(row[1]).lower()
        # Check if this is reflections (has tags column) or conversations (no tags)
        if len(row) >= 4 and isinstance(row[3], list):
            # Reflections - search both content and tags
            tags = [tag.lower() for tag in row[3]]
            if any(
                term in content or any(term in tag for tag in tags)
                for term in search_terms
            ):
                filtered.append(row)
        else:
            # Conversations - only search content
            if any(term in content for term in search_terms):
                filtered.append(row)

    # Return top results with no similarity score
    return [
        {
            "id": str(row[0]),
            "content": _decode_text_from_db(row[1]),
            "score": 0.0,  # No similarity score for text search
            "timestamp": row[3],  # type: ignore[misc]  # Tuple index
            "project": row[2],  # type: ignore[misc]  # Tuple index
            "metadata": json.loads(row[4]) if row[4] else {},  # type: ignore[misc]  # Tuple index
        }
        for row in filtered[:limit]
    ]


async def search_reflections(
    db: duckdb.DuckDBPyConnection | Any,
    query: str,
    query_embedding: list[float] | None,
    limit: int = 10,
    min_score: float = 0.7,
    project: str | None = None,
    is_temp_db: bool = False,
    lock: Any = None,
) -> list[dict[str, Any]]:
    """Search reflections by semantic similarity or text match.

    Args:
        db: Database connection (or ReflectionDatabase instance)
        query: Search query text
        query_embedding: Pre-generated query embedding (optional)
        limit: Maximum number of results
        min_score: Minimum similarity score (0-1)
        project: Filter by project (optional)
        is_temp_db: Whether this is an in-memory temp DB
        lock: Optional lock for thread-safe temp DB access

    Returns:
        List of search results with content, score, tags, etc.

    Example:
        >>> results = await search_reflections(
        ...     db, "database optimization", embedding, limit=5
        ... )
        >>> for r in results:
        ...     print(f"{r['score']:.2f}: {r['content'][:50]}...")
    """
    # Get connection if db is ReflectionDatabase instance
    conn = db if hasattr(db, "execute") else typing.cast(Any, db)._get_conn()  # type: ignore[union-attr]

    # Use semantic search if embedding available
    if query_embedding is not None:
        return await _semantic_search_reflections(
            conn, query, query_embedding, limit, min_score, project, is_temp_db, lock
        )

    # Fallback to text search
    return await _text_search_reflections(conn, query, limit, project, is_temp_db, lock)


async def _semantic_search_reflections(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    query_embedding: list[float],
    limit: int,
    min_score: float,
    project: str | None,
    is_temp_db: bool,
    lock: Any,
) -> list[dict[str, Any]]:
    """Semantic search for reflections using vector cosine similarity.

    Args:
        conn: Database connection
        query: Search query (for logging)
        query_embedding: Query vector
        limit: Max results
        min_score: Minimum similarity threshold
        project: Project filter
        is_temp_db: Temp DB flag
        lock: Thread safety lock

    Returns:
        Filtered list of search results above min_score threshold
    """
    try:
        sql = """
            SELECT
                id, content, embedding, project, tags, timestamp, metadata,
                array_cosine_similarity(embedding, CAST(? AS FLOAT[384])) as score
            FROM reflections
            WHERE embedding IS NOT NULL
        """
        params: list[Any] = [query_embedding]

        if project:
            sql += " AND project = ?"
            params.append(project)

        sql += """
            ORDER BY score DESC
            LIMIT ?
        """
        params.append(limit)

        # Execute query
        if is_temp_db:
            with lock:
                results = conn.execute(sql, params).fetchall()
        else:
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: conn.execute(sql, params).fetchall(),
            )

        # Filter by minimum score
        filtered = [row for row in results if float(row[7]) >= min_score]

        return [
            {
                "id": str(row[0]),
                "content": _decode_text_from_db(row[1]),
                "score": float(row[7]),
                "timestamp": row[5],
                "project": row[3],
                "tags": row[4] or [],
                "metadata": json.loads(row[6]) if row[6] else {},
            }
            for row in filtered
        ]

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        # Fallback to text search on error
        return await _text_search_reflections(
            conn, query, limit, project, is_temp_db, lock
        )


async def _text_search_reflections(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    limit: int,
    project: str | None,
    is_temp_db: bool,
    lock: Any,
) -> list[dict[str, Any]]:
    """Fallback text search for reflections using LIKE pattern matching.

    Args:
        conn: Database connection
        query: Search query
        limit: Max results
        project: Project filter
        is_temp_db: Temp DB flag
        lock: Thread safety lock

    Returns:
        List of search results with similarity=0 (no score available)
    """
    search_terms = query.lower().split()

    # Return empty list when query is empty
    if not search_terms:
        return []

    sql = "SELECT id, content, project, tags, timestamp, metadata FROM reflections"
    params = []

    if project:
        sql += " WHERE project = ?"
        params.append(project)

    sql += " ORDER BY timestamp DESC"

    # Execute query
    if is_temp_db:
        with lock:
            results = conn.execute(sql, params).fetchall()
    else:
        results = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: conn.execute(sql, params).fetchall(),
        )

    # Filter results by search terms (search both content and tags for reflections)
    filtered = []
    for row in results:
        content = _decode_text_from_db(row[1]).lower()
        # Check if this is reflections (has tags column) or conversations (no tags)
        if len(row) >= 4 and isinstance(row[3], list):
            # Reflections - search both content and tags
            tags = [tag.lower() for tag in row[3]]
            if any(
                term in content or any(term in tag for tag in tags)
                for term in search_terms
            ):
                filtered.append(row)
        else:
            # Conversations - only search content
            if any(term in content for term in search_terms):
                filtered.append(row)

    # Return top results with no similarity score
    return [
        {
            "id": str(row[0]),
            "content": _decode_text_from_db(row[1]),
            "score": 0.0,  # No similarity score for text search
            "timestamp": row[4],  # type: ignore[misc]  # Tuple index
            "project": row[2],  # type: ignore[misc]  # Tuple index
            "tags": row[3] or [],  # type: ignore[misc]  # Tuple index
            "metadata": json.loads(row[5]) if row[5] else {},  # type: ignore[misc]  # Tuple index
        }
        for row in filtered[:limit]
    ]
