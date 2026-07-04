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
    # onnxruntime removed — using HTTP embedding providers

try:
    import duckdb

    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

# HTTP embedding providers (llama-server/Ollama) handle embeddings
# No local ONNX runtime needed
ONNX_AVAILABLE = False  # Kept for compatibility but always False

logger = logging.getLogger(__name__)


class DatabaseLockedError(RuntimeError):
    """Raised when the DuckDB file is exclusively locked by another process.

    This is a normal condition when a long-running session-buddy instance
    already owns the lock. Callers (e.g. shutdown checkpoint) should catch
    this and skip storage rather than surfacing it as an error.
    """


# Import schema initialization
# Import embedding generation
from session_buddy.reflection.embeddings import (
    generate_embedding,
)
from session_buddy.reflection.schema import initialize_schema

# Import search operations
from session_buddy.reflection.search import (
    search_conversations,
    search_reflections,
)

# Import storage operations
from session_buddy.reflection.storage import (
    get_reflection as _get_reflection_storage,
)
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
            from session_buddy.settings import get_database_path

            resolved_path = str(get_database_path())
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

        # Embedding system — HTTP providers are stateless, no initialization needed
        self.embedding_dim = 384  # all-MiniLM-L6-v2 / nomic-embed-text dimension
        self._initialized = False

    @property
    def onnx_session(self) -> Any:
        """Backward-compat stub. HTTP embedding needs no session."""
        return None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection | None:
        """Get the connection for the current thread (for backward compatibility)."""
        return getattr(self.local, "conn", None)

    def __enter__(self) -> Self:
        """Synchronous context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Synchronous context manager exit - close connection."""
        self.close()

    async def __aenter__(self) -> Self:
        """Async context manager entry - initializes the database.

        This is the preferred way to use ReflectionDatabase:
            async with ReflectionDatabase() as db:
                ...
        """
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit - close connection."""
        await self.aclose()

    def __del__(self) -> None:
        """Cleanup connection on deletion."""
        self.close()

    def _raw_connect(self) -> duckdb.DuckDBPyConnection:
        """Open a DuckDB connection, converting lock conflicts to DatabaseLockedError."""
        try:
            return duckdb.connect(
                self.db_path, config={"allow_unsigned_extensions": True}
            )
        except Exception as e:
            err = str(e)
            if "Conflicting lock" in err or "Could not set lock" in err:
                msg = f"Database locked by another process: {e}"
                raise DatabaseLockedError(msg) from e
            raise

    def _connect_with_wal_retry(
        self, first_exc: Exception
    ) -> duckdb.DuckDBPyConnection:
        """Handle a WAL-related connect failure by deleting the stale WAL and retrying.

        Raises RuntimeError for non-WAL failures. Re-raises DatabaseLockedError
        unchanged. Uncommitted writes in the stale WAL are intentionally discarded.
        """
        err_msg = str(first_exc)
        is_wal_error = self.db_path != ":memory:" and (
            "replaying WAL" in err_msg or "GetDefaultDatabase" in err_msg
        )
        if not is_wal_error:
            msg = f"Database connection error (directory/permission): {first_exc}"
            raise RuntimeError(msg) from first_exc
        wal_file = Path(self.db_path + ".wal")
        if wal_file.exists():
            with suppress(Exception):
                wal_file.unlink()
        try:
            return self._raw_connect()
        except DatabaseLockedError:
            raise
        except Exception as retry_exc:
            msg = f"Database connection error (directory/permission): {retry_exc}"
            raise RuntimeError(msg) from retry_exc

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

        # Note: Embedding system is now lazy-loaded via HTTP providers
        # to avoid triggering external service calls during initialization

        # Create data directory if needed
        if not self.is_temp_db:
            with suppress(Exception):
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create tables if they don't exist
        try:
            temp_conn = self._raw_connect()
        except DatabaseLockedError:
            raise
        except Exception as e:
            temp_conn = self._connect_with_wal_retry(e)

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

    async def _ensure_tables(self) -> None:
        """Ensure the reflection schema exists.

        Compatibility hook for callers that still expect the legacy private
        table-initialization method from the older reflection database class.
        """
        if self._initialized and self.conn is not None:
            return

        if self.conn is None:
            await self.initialize()
            return

        initialize_schema(self.conn)
        self._initialized = True

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
            return self._shared_conn

        # For normal environments, use thread-local storage
        if not hasattr(self.local, "conn") or self.local.conn is None:
            self.local.conn = duckdb.connect(
                self.db_path, config={"allow_unsigned_extensions": True}
            )
        return self.local.conn

    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding for text using HTTP embedding provider.

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
        embedding = await generate_embedding(text)
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
        if project is not None:
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
        project: str | None = None,
        min_score: float = 0.7,
        tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search reflections by text similarity.

        Args:
            query: Search query text
            limit: Maximum number of results
            project: Optional project filter
            min_score: Minimum similarity score (0-1)
            tags: Optional tag filter (only return reflections with any of these tags)
            exclude_tags: Optional exclusion filter — reflections with ANY of these
                tags are removed from results. Use ``exclude_tags=["quarantine"]`` to
                hide quarantined reflections from general searches (M-NEW-31).

        Returns:
            List of search results with content, score, tags, etc.

        Example:
            >>> results = await db.search_reflections("architecture")
            >>> for r in results:
            ...     print(f"{r['score']:.2f}: {r['content'][:50]}...")
        """
        if query is None:
            msg = "query cannot be None"
            raise TypeError(msg)

        # Generate query embedding if available
        query_embedding = None
        if self.onnx_session:
            try:
                query_embedding = await self.get_embedding(query)
            except Exception:
                query_embedding = None

        # Search using search module
        results = await search_reflections(
            self,
            query,
            query_embedding,
            limit,
            min_score,
            project,
            self.is_temp_db,
            self.lock if self.is_temp_db else None,
        )

        # Apply inclusion tag filter
        if tags:
            results = [
                r for r in results if any(tag in r.get("tags", []) for tag in tags)
            ]

        # Apply exclusion tag filter (M-NEW-31 — quarantine isolation)
        if exclude_tags:
            exclude_set = set(exclude_tags)
            results = [
                r for r in results if not exclude_set.intersection(r.get("tags", []))
            ]

        return results

    async def get_reflection(self, reflection_id: str | None) -> dict[str, Any] | None:
        """Get a reflection by ID.

        Args:
            reflection_id: The reflection ID to look up

        Returns:
            Reflection dict or None if not found (or if ID is invalid/None)

        Example:
            >>> refl = await db.get_reflection("abc123")
            >>> if refl:
            ...     print(refl["content"])
        """
        if reflection_id is None:
            return None

        return await _get_reflection_storage(
            self,
            reflection_id,
            self.is_temp_db,
            self.lock if self.is_temp_db else None,
        )

    async def update_reflection(
        self,
        reflection_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Update a reflection's content and/or tags.

        Args:
            reflection_id: The reflection ID to update
            content: New content (raises TypeError if None)
            tags: New tags list

        Returns:
            True if updated, False if not found

        Raises:
            TypeError: If content is explicitly None
        """
        if content is None:
            msg = "content cannot be None"
            raise TypeError(msg)

        if not self._initialized:
            msg = "Database not initialized"
            raise RuntimeError(msg)

        conn = self._get_conn()

        def _update() -> bool:
            # Check if reflection exists
            result = conn.execute(
                "SELECT id FROM reflections WHERE id = ?",
                [reflection_id],
            ).fetchone()
            if not result:
                return False

            # Encode content for database
            from session_buddy.reflection.storage import _encode_text_for_db

            db_content = _encode_text_for_db(content)

            if tags is not None:
                conn.execute(
                    "UPDATE reflections SET content = ?, tags = ?, timestamp = NOW() WHERE id = ?",
                    [db_content, tags, reflection_id],
                )
            else:
                # tags=None means clear tags to empty list
                conn.execute(
                    "UPDATE reflections SET content = ?, tags = ?, timestamp = NOW() WHERE id = ?",
                    [db_content, [], reflection_id],
                )
            return True

        if self.is_temp_db:
            with self.lock:
                return _update()
        else:
            return await asyncio.get_event_loop().run_in_executor(None, _update)

    async def delete_reflection(self, reflection_id: str | None) -> bool:
        """Delete a reflection by ID.

        Args:
            reflection_id: The reflection ID to delete (raises TypeError if None)

        Returns:
            True if deleted, False if not found

        Raises:
            TypeError: If reflection_id is None
        """
        if reflection_id is None:
            msg = "reflection_id cannot be None"
            raise TypeError(msg)

        if not self._initialized:
            msg = "Database not initialized"
            raise RuntimeError(msg)

        conn = self._get_conn()

        def _delete() -> bool:
            # Check if reflection exists
            result = conn.execute(
                "SELECT id FROM reflections WHERE id = ?",
                [reflection_id],
            ).fetchone()
            if not result:
                return False

            conn.execute("DELETE FROM reflections WHERE id = ?", [reflection_id])

            # Also clean up reflection_tags
            with suppress(Exception):
                conn.execute(
                    "DELETE FROM reflection_tags WHERE reflection_id = ?",
                    [reflection_id],
                )

            return True

        if self.is_temp_db:
            with self.lock:
                return _delete()
        else:
            return await asyncio.get_event_loop().run_in_executor(None, _delete)

    async def search_by_file(
        self,
        file_path: str,
        limit: int = 5,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search conversations that mention a specific file path.

        Also logs memory access for each result via the persistence module.

        Args:
            file_path: File path to search for
            limit: Maximum number of results
            project: Optional project filter

        Returns:
            List of conversations mentioning the file path
        """
        # Use search_conversations with the file path as query
        results = await self.search_conversations(
            query=file_path,
            limit=limit,
            project=project,
        )

        # Log memory access for each result
        with suppress(Exception):
            from session_buddy.memory.persistence import log_memory_access

            for result in results:
                memory_id = result.get("id", "")
                if memory_id:
                    log_memory_access(memory_id, access_type="search")

        return results

    def close(self) -> None:
        """Close database connection (synchronous).

        Safe to call on a partially-initialized instance (e.g. when
        ``__init__`` raised before ``self.local`` was set, or before
        ``__aenter__``/``initialize`` opened a connection). Called by
        ``__del__`` during garbage collection, so it must not assume
        any specific state.

        Example:
            >>> db.close()
        """
        local = getattr(self, "local", None)
        if local is None:
            return
        if hasattr(local, "conn") and local.conn is not None:
            with suppress(Exception):
                local.conn.close()
            local.conn = None

    async def aclose(self) -> None:
        """Async close database connection.

        This is an async wrapper around close() for use in async contexts.

        Example:
            >>> await db.aclose()
        """
        # Run sync close in executor to avoid blocking event loop
        await asyncio.get_event_loop().run_in_executor(None, self.close)

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
                "http-embedding-providers" if self.onnx_session else "text-search-only"
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
                lambda: (
                    self._get_conn()
                    .execute("SELECT COUNT(*) FROM conversations")
                    .fetchone()
                ),
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
                lambda: (
                    self._get_conn()
                    .execute("SELECT COUNT(*) FROM reflections")
                    .fetchone()
                ),
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
