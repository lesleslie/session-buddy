"""CRUD operations for reflections and conversations.

Provides low-level database storage operations with proper
encoding/decoding and embedding support.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
import typing
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

# Text encoding constants for Unicode support
_SURROGATE_PREFIX = "__SB64__"


class SupportsGetConn(Protocol):
    """Protocol for objects that support _get_conn method."""

    def _get_conn(self) -> duckdb.DuckDBPyConnection: ...


def has_get_conn(obj: Any) -> bool:
    """Check if object has _get_conn method."""
    return hasattr(obj, "_get_conn")  # type: ignore[attr-defined]


def _encode_text_for_db(text: str) -> str:
    """Encode text for database storage, handling Unicode edge cases.

    Args:
        text: Input text to encode

    Returns:
        Encoded text safe for database storage

    Example:
        >>> encoded = _encode_text_for_db("Hello 𝕌𝕟𝕚𝕔𝕠𝕕𝕖")
        >>> assert "\\x00" not in encoded
    """
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        # Handle surrogate pairs for database compatibility
        data = text.encode("utf-8", "surrogatepass")
        return _SURROGATE_PREFIX + base64.b64encode(data).decode("ascii")


def _decode_text_from_db(text: str) -> str:
    """Decode text from database storage.

    Args:
        text: Text from database

    Returns:
        Decoded original text
    """
    if text.startswith(_SURROGATE_PREFIX):
        data = base64.b64decode(text[len(_SURROGATE_PREFIX) :])
        return data.decode("utf-8", "surrogatepass")
    return text


def _serialize_metadata(metadata: dict[str, Any] | None) -> str | None:
    """Serialize metadata to JSON string.

    Args:
        metadata: Metadata dictionary or None

    Returns:
        JSON string or None
    """
    if not metadata:
        return None

    try:
        return json.dumps(metadata)
    except Exception as e:
        logger.warning(f"Failed to serialize metadata: {e}")
        return None


def _parse_metadata(metadata_str: str | None) -> dict[str, Any]:
    """Parse metadata from JSON string.

    Args:
        metadata_str: JSON string or None

    Returns:
        Parsed metadata dictionary
    """
    if not metadata_str:
        return {}

    try:
        return json.loads(metadata_str)
    except Exception:  # type: ignore[no-any-return]
        logger.warning(f"Failed to parse metadata: {metadata_str[:100]}...")
        return {}


async def store_conversation(
    db: duckdb.DuckDBPyConnection | Any,
    content: str,
    metadata: dict[str, Any],
    embedding: list[float] | None,
    is_temp_db: bool = False,
    lock: Any = None,
) -> str:
    """Store a conversation in the database.

    Args:
        db: Database connection (or ReflectionDatabase instance)
        content: Conversation content
        metadata: Optional metadata dictionary
        embedding: Optional pre-generated embedding vector
        is_temp_db: Whether this is an in-memory temp DB
        lock: Optional lock for thread-safe temp DB access

    Returns:
        Conversation ID

    Example:
        >>> from session_buddy.reflection import ReflectionDatabase
        >>> db = ReflectionDatabase()
        >>> await db.initialize()
        >>> conv_id = await store_conversation(
        ...     db, "Hello world", {"project": "test"}, None
        ... )
    """
    # Generate conversation ID
    conversation_id = hashlib.md5(
        f"{content}_{time.time()}".encode("utf-8", "surrogatepass"),
        usedforsecurity=False,
    ).hexdigest()

    # Encode content for database
    db_content = _encode_text_for_db(content)

    # Get connection if db is ReflectionDatabase instance
    conn = db if hasattr(db, "execute") else typing.cast(Any, db)._get_conn()  # type: ignore[union-attr]

    # Insert into database
    def _store() -> None:
        conn.execute(
            """
            INSERT INTO conversations (id, content, embedding, project, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                conversation_id,
                db_content,
                embedding,
                metadata.get("project") if metadata else None,
                datetime.now(UTC),
                _serialize_metadata(metadata),
            ],
        )

    if is_temp_db and lock:
        # For temp DB, use lock to protect database operations
        with lock:
            _store()
    else:
        # For normal file-based DB, run in executor for thread safety
        await asyncio.get_event_loop().run_in_executor(None, _store)

    return conversation_id


async def store_reflection(
    db: duckdb.DuckDBPyConnection | Any,
    content: str,
    tags: list[str] | None,
    metadata: dict[str, Any],
    embedding: list[float] | None,
    is_temp_db: bool = False,
    lock: Any = None,
) -> str:
    """Store a reflection in the database.

    Args:
        db: Database connection (or ReflectionDatabase instance)
        content: Reflection content
        tags: Optional tags for categorization
        metadata: Optional metadata dictionary
        embedding: Optional pre-generated embedding vector
        is_temp_db: Whether this is an in-memory temp DB
        lock: Optional lock for thread-safe temp DB access

    Returns:
        Reflection ID

    Raises:
        TypeError: If content is None

    Example:
        >>> from session_buddy.reflection import ReflectionDatabase
        >>> db = ReflectionDatabase()
        >>> await db.initialize()
        >>> refl_id = await store_reflection(
        ...     db, "Important insight", ["ai", "ml"], {}, None
        ... )
    """
    if content is None:
        msg = "content cannot be None"
        raise TypeError(msg)

    # Generate reflection ID
    reflection_id = hashlib.md5(
        f"reflection_{content}_{time.time()}".encode("utf-8", "surrogatepass"),
        usedforsecurity=False,
    ).hexdigest()

    # Encode content for database
    db_content = _encode_text_for_db(content)

    tags_list = tags or []

    # Get connection if db is ReflectionDatabase instance
    conn = db if hasattr(db, "execute") else typing.cast(Any, db)._get_conn()  # type: ignore[union-attr]

    # Insert into database
    def _store() -> None:
        conn.execute(
            """
            INSERT INTO reflections (id, content, embedding, project, tags, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                reflection_id,
                db_content,
                embedding,
                metadata.get("project") if metadata else None,
                tags_list,
                datetime.now(UTC),
                _serialize_metadata(metadata),
            ],
        )

    if is_temp_db and lock:
        # For temp DB, use lock to protect database operations
        with lock:
            _store()
    else:
        # For normal file-based DB, run in executor for thread safety
        await asyncio.get_event_loop().run_in_executor(None, _store)

    return reflection_id


async def get_conversation(
    db: duckdb.DuckDBPyConnection | Any,
    conv_id: str,
    is_temp_db: bool = False,
    lock: Any = None,
) -> dict[str, Any] | None:
    """Get a conversation by ID.

    Args:
        db: Database connection (or ReflectionDatabase instance)
        conv_id: Conversation ID
        is_temp_db: Whether this is an in-memory temp DB
        lock: Optional lock for thread-safe temp DB access

    Returns:
        Conversation dict or None if not found

    Example:
        >>> conv = await get_conversation(db, "abc123")
        >>> if conv:
        ...     print(conv["content"])
    """
    # Get connection if db is ReflectionDatabase instance
    conn = db if hasattr(db, "execute") else typing.cast(Any, db)._get_conn()  # type: ignore[union-attr]

    def _get() -> dict[str, Any] | None:
        result = conn.execute(
            """
            SELECT id, content, embedding, project, timestamp, metadata
            FROM conversations
            WHERE id = ?
            """,
            [conv_id],
        ).fetchone()

        if not result:
            return None

        return {
            "id": result[0],  # type: ignore[misc]
            "content": _decode_text_from_db(result[1]),  # type: ignore[misc]
            "embedding": result[2],  # type: ignore[misc]
            "project": result[3],  # type: ignore[misc]
            "timestamp": result[4],  # type: ignore[misc]
            "metadata": _parse_metadata(result[5]),  # type: ignore[misc]
        }

    if is_temp_db and lock:
        with lock:
            return _get()
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get)


async def get_reflection(
    db: duckdb.DuckDBPyConnection | Any,
    refl_id: str,
    is_temp_db: bool = False,
    lock: Any = None,
) -> dict[str, Any] | None:
    """Get a reflection by ID.

    Args:
        db: Database connection (or ReflectionDatabase instance)
        refl_id: Reflection ID
        is_temp_db: Whether this is an in-memory temp DB
        lock: Optional lock for thread-safe temp DB access

    Returns:
        Reflection dict or None if not found

    Example:
        >>> refl = await get_reflection(db, "xyz789")
        >>> if refl:
        ...     print(refl["content"])
    """
    # Get connection if db is ReflectionDatabase instance
    conn = db if hasattr(db, "execute") else typing.cast(Any, db)._get_conn()  # type: ignore[union-attr]

    def _get() -> dict[str, Any] | None:
        result = conn.execute(
            """
            SELECT id, content, embedding, project, tags, timestamp, metadata
            FROM reflections
            WHERE id = ?
            """,
            [refl_id],
        ).fetchone()

        if not result:
            return None

        return {
            "id": result[0],  # type: ignore[misc]
            "content": _decode_text_from_db(result[1]),  # type: ignore[misc]
            "embedding": result[2],  # type: ignore[misc]
            "project": result[3],  # type: ignore[misc]
            "tags": result[4] or [],  # type: ignore[misc]
            "timestamp": result[5],  # type: ignore[misc]
            "metadata": _parse_metadata(result[6]),  # type: ignore[misc]
        }

    if is_temp_db and lock:
        with lock:
            return _get()
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get)


async def store_code_graph(
    db: duckdb.DuckDBPyConnection | Any,
    repo_path: str,
    commit_hash: str,
    indexed_at: str,
    nodes_count: int,
    graph_data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    lock: Any = None,
) -> str:
    """Store a code graph from Mahavishnu in the reflection database.

    Args:
        db: Database connection (or ReflectionDatabase instance)
        repo_path: Path to the repository
        commit_hash: Git commit hash
        indexed_at: When indexing was completed (ISO timestamp string)
        nodes_count: Number of nodes in the code graph
        graph_data: Code graph data (nodes, edges, etc.)
        metadata: Optional metadata dictionary
        lock: Optional lock for thread-safe temp DB access

    Returns:
        Code graph ID (repo_path + commit_hash)

    Example:
        >>> from session_buddy.reflection import ReflectionDatabase
        >>> db = ReflectionDatabase()
        >>> await db.initialize()
        >>> graph_id = await store_code_graph(
        ...     db,
        ...     "/path/to/repo",
        ...     "abc123",
        ...     "2025-02-03T12:00:00Z",
        ...     1234,
        ...     {"nodes": [...], "edges": [...]}
        ... )
    """
    # Generate unique ID (repo_path + commit_hash)
    code_graph_id = f"{repo_path}:{commit_hash}"

    # Serialize graph data to JSON
    graph_json = json.dumps(graph_data)

    # Serialize metadata
    metadata_json = _serialize_metadata(metadata or {})

    # Get connection if db is ReflectionDatabase instance
    conn = db if hasattr(db, "execute") else typing.cast(Any, db)._get_conn()  # type: ignore[union-attr]

    # Insert into database
    def _store() -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO code_graphs
            (id, repo_path, commit_hash, indexed_at, nodes_count, graph_data, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                code_graph_id,
                repo_path,
                commit_hash,
                indexed_at,
                nodes_count,
                graph_json,
                metadata_json,
            ],
        )

    if lock:
        with lock:
            _store()
    else:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _store)

    return code_graph_id


async def get_code_graph(
    db: duckdb.DuckDBPyConnection | Any,
    repo_path: str,
    commit_hash: str,
    is_temp_db: bool = False,
    lock: Any = None,
) -> dict[str, Any] | None:
    """Get a code graph by repo path and commit hash.

    Args:
        db: Database connection (or ReflectionDatabase instance)
        repo_path: Path to the repository
        commit_hash: Git commit hash
        is_temp_db: Whether this is an in-memory temp DB
        lock: Optional lock for thread-safe temp DB access

    Returns:
        Code graph dict or None if not found
    """
    import json

    # Get connection if db is ReflectionDatabase instance
    conn = db if hasattr(db, "execute") else typing.cast(Any, db)._get_conn()  # type: ignore[union-attr]

    def _get() -> dict[str, Any] | None:
        result = conn.execute(
            """
            SELECT repo_path, commit_hash, nodes_count, graph_data, metadata
            FROM code_graphs
            WHERE repo_path = ? AND commit_hash = ?
            """,
            [repo_path, commit_hash],
        ).fetchone()

        if not result:
            return None

        return {
            "repo_path": result[0],  # type: ignore[misc]
            "commit_hash": result[1],  # type: ignore[misc]
            "nodes_count": result[2],  # type: ignore[misc]
            "graph_data": json.loads(result[3]) if result[3] else {},  # type: ignore[misc]
            "metadata": json.loads(result[4]) if result[4] else {},  # type: ignore[misc]
        }

    if is_temp_db and lock:
        with lock:
            return _get()
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get)


async def list_code_graphs(
    db: duckdb.DuckDBPyConnection | Any,
    repo_path: str | None = None,
    limit: int = 100,
    is_temp_db: bool = False,
    lock: Any = None,
) -> dict[str, Any]:
    """List code graphs with optional filtering.

    Args:
        db: Database connection (or ReflectionDatabase instance)
        repo_path: Optional filter by repository path
        limit: Maximum number of results
        is_temp_db: Whether this is an in-memory temp DB
        lock: Optional lock for thread-safe temp DB access

    Returns:
        Dict with list of code graphs
    """
    # Get connection if db is ReflectionDatabase instance
    conn = db if hasattr(db, "execute") else typing.cast(Any, db)._get_conn()  # type: ignore[union-attr]

    def _query() -> list[dict[str, Any]]:
        if repo_path:
            result = conn.execute(
                """
                SELECT repo_path, commit_hash, nodes_count
                FROM code_graphs
                WHERE repo_path = ?
                ORDER BY indexed_at DESC
                LIMIT ?
                """,
                [repo_path, limit],
            ).fetchall()
        else:
            result = conn.execute(
                """
                SELECT repo_path, commit_hash, nodes_count
                FROM code_graphs
                ORDER BY indexed_at DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()

        return [
            {
                "repo_path": row[0],  # type: ignore[misc]
                "commit_hash": row[1],  # type: ignore[misc]
                "nodes_count": row[2],  # type: ignore[misc]
            }
            for row in result
        ]

    if is_temp_db and lock:
        with lock:
            graphs = _query()
    else:
        loop = asyncio.get_event_loop()
        graphs = await loop.run_in_executor(None, _query)

    return {
        "status": "success",
        "count": len(graphs),
        "code_graphs": graphs,
    }
