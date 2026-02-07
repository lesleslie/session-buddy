"""Core database management for reflection storage.

Provides the main ReflectionDatabase class with connection management,
thread-safe operations, and integration with embeddings/search/storage modules.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    import duckdb

try:
    import duckdb

    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

try:
    import onnxruntime as ort

    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    ort = None  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# Import schema initialization
# Import embedding generation
from session_buddy.reflection.embeddings import (
    generate_embedding,
    initialize_embedding_system,
)
from session_buddy.reflection.schema import initialize_schema

# Import search operations
from session_buddy.reflection.search import (
    search_conversations,
    search_reflections,
)

# Import storage operations
from session_buddy.reflection.storage import (
    store_conversation,
    store_reflection,
)

_DB_PATH_UNSET = object()


class ReflectionDatabase:
    """Manages DuckDB database for conversation memory and reflection.

    This is the NEW modular implementation that replaces the monolithic
    reflection_tools.py implementation. Use this class for all new code.

    Example:
        >>> from session_buddy.reflection import ReflectionDatabase
        >>>
        >>> async with ReflectionDatabase() as db:
        ...     # Store conversation
        ...     conv_id = await db.store_conversation(
        ...         "Hello world",
        ...         {"project": "test"}
        ...     )
        ...
        ...     # Search conversations
        ...     results = await db.search_conversations("hello")
    """

    def __init__(self, db_path: str | None | object = _DB_PATH_UNSET) -> None:
        """Initialize database instance.

        Args:
            db_path: Path to database file (uses default if None)
        """
        if db_path is None:
            msg = "db_path cannot be None"
            raise TypeError(msg)

        if db_path is _DB_PATH_UNSET:
            resolved_path: str = os.path.expanduser("~/.claude/data/reflection.duckdb")
        else:
            resolved_path = os.path.expanduser(str(db_path))

        # Special-case empty path: treat as in-memory to avoid filesystem issues
        if resolved_path in {"", ":memory:"}:
            self.db_path = ":memory:"
            self.is_temp_db = True
        else:
            self.db_path = resolved_path
            self.is_temp_db = False

        # Use thread-local storage for connections to avoid threading issues
        self.local = threading.local()
        self.lock = threading.RLock()  # Re-entrant for nested access in temp DB

        # Embedding system
        self.onnx_session = initialize_embedding_system()
        self.tokenizer = None  # Set by embedding system
        self.embedding_dim = 384  # all-MiniLM-L6-v2 dimension
        self._initialized = False

    @property
    def conn(self) -> duckdb.DuckDBPyConnection | None:
        """Get the connection for the current thread (for backward compatibility)."""
        return getattr(self.local, "conn", None)

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit - close connection."""
        self.close()

    def __del__(self) -> None:
        """Cleanup connection on deletion."""
        self.close()

    async def initialize(self) -> None:
        """Initialize database connection and create tables.

        This method must be called before using the database.

        Raises:
            RuntimeError: If database connection fails

        Example:
            >>> db = ReflectionDatabase()
            >>> await db.initialize()
            >>> # Database ready for use
        """
        if not DUCKDB_AVAILABLE:
            msg = "DuckDB is not available"
            raise RuntimeError(msg)

        # Initialize embedding system
        initialize_embedding_system()

        # Create data directory if needed
        if not self.is_temp_db:
            with suppress(Exception):
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create tables if they don't exist
        try:
            temp_conn = duckdb.connect(
                self.db_path, config={"allow_unsigned_extensions": True}
            )
        except Exception as e:
            msg = f"Database connection error (directory/permission): {e}"
            raise RuntimeError(msg) from e

        try:
            # Initialize schema using schema module
            initialize_schema(temp_conn)
        finally:
            temp_conn.close()

        # Mark as initialized
        self._initialized = True

        # Create the connection for the current thread
        if self.is_temp_db:
            # For temp DBs, create a shared connection
            with self.lock:
                self._shared_conn = duckdb.connect(
                    self.db_path, config={"allow_unsigned_extensions": True}
                )
                initialize_schema(self._shared_conn)
                self.local.conn = self._shared_conn
        else:
            # For non-temporary DBs, create a connection in the local storage
            self.local.conn = duckdb.connect(
                self.db_path, config={"allow_unsigned_extensions": True}
            )

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        """Get database connection for the current thread, initializing if needed.

        Raises:
            RuntimeError: If database not initialized
        """
        if not self._initialized:
            msg = "Database connection not initialized. Call initialize() first"
            raise RuntimeError(msg)

        # For test environments using in-memory DB, create a shared connection with locking
        if self.is_temp_db:
            with self.lock:
                if not hasattr(self, "_shared_conn"):
                    self._shared_conn = duckdb.connect(
                        self.db_path, config={"allow_unsigned_extensions": True}
                    )
                    initialize_schema(self._shared_conn)
                self.local.conn = self._shared_conn
            return self._shared_conn  # type: ignore[return-value]

        # For normal environments, use thread-local storage
        if not hasattr(self.local, "conn") or self.local.conn is None:
            self.local.conn = duckdb.connect(
                self.db_path, config={"allow_unsigned_extensions": True}
            )
        return self.local.conn  # type: ignore[return-value]

    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding for text using ONNX model.

        Args:
            text: Input text to embed

        Returns:
            Float vector of dimension 384

        Raises:
            RuntimeError: If embedding model not available

        Example:
            >>> embedding = await db.get_embedding("Hello world")
            >>> print(f"Generated {len(embedding)}-dimensional vector")
        """
        if self.onnx_session is None:
            msg = "No embedding model available"
            raise RuntimeError(msg)

        embedding = await generate_embedding(text, self.onnx_session, self.tokenizer)
        if embedding is None:
            msg = "Failed to generate embedding"
            raise RuntimeError(msg)

        return embedding

    async def store_conversation(self, content: str, metadata: dict[str, Any]) -> str:
        """Store conversation with optional embedding.

        Args:
            content: Conversation text content
            metadata: Optional metadata (project, source, etc.)

        Returns:
            Conversation ID

        Example:
            >>> conv_id = await db.store_conversation(
            ...     "Discussed database architecture",
            ...     {"project": "session-buddy", "topic": "architecture"}
            ... )
        """
        # Generate embedding if available
        embedding: list[float] | None = None
        if self.onnx_session:
            try:
                embedding = await self.get_embedding(content)
            except Exception:
                embedding = None  # Fallback to no embedding

        # Store using storage module
        return await store_conversation(
            self,
            content,
            metadata,
            embedding,
            self.is_temp_db,
            self.lock if self.is_temp_db else None,
        )

    async def store_reflection(
        self,
        content: str,
        tags: list[str] | None = None,
        project: str | None = None,
    ) -> str:
        """Store reflection/insight with optional embedding.

        Args:
            content: Reflection text content
            tags: Optional tags for categorization
            project: Optional project identifier

        Returns:
            Reflection ID

        Raises:
            TypeError: If content is None

        Example:
            >>> refl_id = await db.store_reflection(
            ...     "Important: Use dependency injection for testability",
            ...     tags=["architecture", "testing"],
            ...     project="session-buddy"
            ... )
        """
        if content is None:
            msg = "content cannot be None"
            raise TypeError(msg)

        # Generate embedding if available
        embedding: list[float] | None = None
        if self.onnx_session:
            try:
                embedding = await self.get_embedding(content)
            except Exception:
                embedding = None  # Fallback to no embedding

        # Build metadata
        metadata: dict[str, Any] = {}
        if project:
            metadata["project"] = project

        # Store using storage module
        return await store_reflection(
            self,
            content,
            tags,
            metadata,
            embedding,
            self.is_temp_db,
            self.lock if self.is_temp_db else None,
        )

    async def search_conversations(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.7,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search conversations by text similarity (fallback to text search if no embeddings).

        Args:
            query: Search query text
            limit: Maximum number of results
            min_score: Minimum similarity score (0-1)
            project: Optional project filter

        Returns:
            List of search results with content, score, timestamp, etc.

        Example:
            >>> results = await db.search_conversations("database design")
            >>> for r in results:
            ...     print(f"{r['score']:.2f}: {r['content'][:50]}...")
        """
        # Generate query embedding if available
        query_embedding = None
        if self.onnx_session:
            try:
                query_embedding = await self.get_embedding(query)
            except Exception:
                query_embedding = None

        # Search using search module
        return await search_conversations(
            self,
            query,
            query_embedding,
            limit,
            min_score,
            project,
            self.is_temp_db,
            self.lock if self.is_temp_db else None,
        )

    async def search_reflections(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.7,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search reflections by text similarity.

        Args:
            query: Search query text
            limit: Maximum number of results
            min_score: Minimum similarity score (0-1)
            project: Optional project filter

        Returns:
            List of search results with content, score, tags, etc.

        Example:
            >>> results = await db.search_reflections("architecture")
            >>> for r in results:
            ...     print(f"{r['score']:.2f}: {r['content'][:50]}...")
        """
        # Generate query embedding if available
        query_embedding = None
        if self.onnx_session:
            try:
                query_embedding = await self.get_embedding(query)
            except Exception:
                query_embedding = None

        # Search using search module
        return await search_reflections(
            self,
            query,
            query_embedding,
            limit,
            min_score,
            project,
            self.is_temp_db,
            self.lock if self.is_temp_db else None,
        )

    def close(self) -> None:
        """Close database connection.

        Example:
            >>> db.close()
        """
        if hasattr(self.local, "conn") and self.local.conn is not None:
            with suppress(Exception):
                self.local.conn.close()
            self.local.conn = None

    async def get_stats(self) -> dict[str, Any]:
        """Get database statistics.

        Returns:
            Dict with database statistics including counts, projects, provider info

        Example:
            >>> stats = await db.get_stats()
            >>> print(f"Conversations: {stats['conversations_count']}")
        """
        try:
            conv_count = await self._get_conversation_count()
            refl_count = await self._get_reflection_count()

            projects_rows = await self._execute_query(
                "SELECT DISTINCT project FROM reflections WHERE project IS NOT NULL",
            )
            projects = [row[0] for row in projects_rows if row and row[0] is not None]

            provider = (
                "onnx-runtime"
                if (self.onnx_session and ONNX_AVAILABLE)
                else "text-search-only"
            )
            return {
                "conversations_count": conv_count,
                "reflections_count": refl_count,
                "total_conversations": conv_count,
                "total_reflections": refl_count,
                "projects": projects,
                "total_projects": len(projects),
                "embedding_provider": provider,
                "embedding_dimension": self.embedding_dim,
                "database_path": self.db_path,
            }
        except Exception as e:
            return {"error": f"Failed to get stats: {e}"}

    async def _get_conversation_count(self) -> int:
        """Get the count of conversations from the database.

        Returns:
            Number of conversations stored
        """
        if self.is_temp_db:
            with self.lock:
                result = (
                    self._get_conn()
                    .execute(
                        "SELECT COUNT(*) FROM conversations",
                    )
                    .fetchone()
                )
                return result[0] if result and result[0] else 0
        else:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_conn()
                .execute("SELECT COUNT(*) FROM conversations")
                .fetchone(),
            )
            return result[0] if result and result[0] else 0

    async def _get_reflection_count(self) -> int:
        """Get the count of reflections from the database.

        Returns:
            Number of reflections stored
        """
        if self.is_temp_db:
            with self.lock:
                result = (
                    self._get_conn()
                    .execute(
                        "SELECT COUNT(*) FROM reflections",
                    )
                    .fetchone()
                )
                return result[0] if result and result[0] else 0
        else:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_conn()
                .execute("SELECT COUNT(*) FROM reflections")
                .fetchone(),
            )
            return result[0] if result and result[0] else 0

    async def _execute_query(
        self, sql: str, params: list[Any] | None = None
    ) -> list[Any]:
        """Execute a SQL query and return results.

        Args:
            sql: SQL query string
            params: Optional query parameters

        Returns:
            List of result rows
        """
        params = params or []

        if self.is_temp_db:
            with self.lock:
                return self._get_conn().execute(sql, params).fetchall()
        else:
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_conn().execute(sql, params).fetchall(),
            )


# Singleton instance for backward compatibility
_default_db: ReflectionDatabase | None = None
_db_lock = threading.Lock()


def get_reflection_database(
    db_path: str | None = None,
) -> ReflectionDatabase:
    """Get or create singleton reflection database instance.

    Args:
        db_path: Optional custom database path

    Returns:
        ReflectionDatabase singleton instance

    Example:
        >>> from session_buddy.reflection import get_reflection_database
        >>>
        >>> db = get_reflection_database()
        >>> # Use singleton instance
    """
    global _default_db

    with _db_lock:
        if _default_db is None:
            _default_db = ReflectionDatabase(db_path or _DB_PATH_UNSET)
        return _default_db
