#!/usr/bin/env python3
"""Reflection Tools for Claude Session Management.

Provides memory and conversation search capabilities using DuckDB and local embeddings.

DEPRECATION NOTICE (Phase 2.7 - January 2025):
    The ReflectionDatabase class in this module is deprecated and will be removed
    in a future release. Please use ReflectionDatabaseAdapter from
    session_buddy.adapters.reflection_adapter instead.

    Migration Guide:
        # Old (deprecated):
        from session_buddy.reflection_tools import ReflectionDatabase

        # New (recommended):
        from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

    The adapter provides the same API while using ACB (Asynchronous Component Base)
    for improved connection pooling, lifecycle management, and integration with
    the dependency injection system.
"""

import asyncio
import base64
import hashlib
import json
import os
import threading
import time
import warnings
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    import duckdb
    import onnxruntime as ort
    from transformers import AutoTokenizer

# Database and embedding imports
try:
    import duckdb

    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False


try:
    import onnxruntime as ort
    from transformers import AutoTokenizer

    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False

import operator

import numpy as np

# Import the new adapter for replacement
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

_DB_PATH_UNSET = object()


_SURROGATE_PREFIX = "__SB64__"


def _encode_text_for_db(text: str) -> str:
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        data = text.encode("utf-8", "surrogatepass")
        return _SURROGATE_PREFIX + base64.b64encode(data).decode("ascii")


def _decode_text_from_db(text: str) -> str:
    if text.startswith(_SURROGATE_PREFIX):
        data = base64.b64decode(text[len(_SURROGATE_PREFIX) :])
        return data.decode("utf-8", "surrogatepass")
    return text


class ReflectionDatabase:
    """Manages DuckDB database for conversation memory and reflection.

    DEPRECATED: This class is deprecated as of Phase 2.7 (January 2025).
    Use ReflectionDatabaseAdapter from session_buddy.adapters.reflection_adapter instead.

    The adapter provides the same API with improved ACB integration:
    - Connection pooling and lifecycle management
    - Dependency injection support
    - Better async/await patterns

    This class will be removed in a future release.
    """

    def __init__(self, db_path: str | None | object = _DB_PATH_UNSET) -> None:
        # Issue deprecation warning
        warnings.warn(
            "ReflectionDatabase is deprecated and will be removed in a future release. "
            "Use ReflectionDatabaseAdapter from session_buddy.adapters.reflection_adapter instead.",
            DeprecationWarning,
            stacklevel=2,
        )

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
        self.onnx_session: ort.InferenceSession | None = None
        self.tokenizer = None
        self.embedding_dim = 384  # all-MiniLM-L6-v2 dimension
        self._initialized = False  # Track initialization state

    @property
    def conn(self) -> "duckdb.DuckDBPyConnection | None":
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
        """Context manager exit with cleanup."""
        self.close()

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit with cleanup."""
        self.close()

    def close(self) -> None:
        """Close database connections for all threads."""
        if hasattr(self.local, "conn") and self.local.conn:
            try:
                self.local.conn.close()
            except Exception:
                # nosec B110 - intentionally suppressing exceptions during cleanup
                pass  # Ignore errors during cleanup
            finally:
                self.local.conn = None

    def __del__(self) -> None:
        """Destructor to ensure cleanup."""
        self.close()

    async def initialize(self) -> None:
        """Initialize database and embedding models."""
        if not DUCKDB_AVAILABLE:
            msg = "DuckDB not available. Install with: pip install duckdb"
            raise ImportError(msg)

        # Initialize ONNX embedding model
        if ONNX_AVAILABLE and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                model_path = os.path.expanduser(
                    "~/.claude/all-MiniLM-L6-v2/onnx/model.onnx",
                )
                if Path(model_path).exists():
                    # Load tokenizer with revision pinning for security
                    self.tokenizer = AutoTokenizer.from_pretrained(
                        "sentence-transformers/all-MiniLM-L6-v2",
                        revision="7dbbc90392e2f80f3d3c277d6e90027e55de9125",  # Pin to specific commit
                    )
                    self.onnx_session = ort.InferenceSession(model_path)
                    self.embedding_dim = 384
                else:
                    self.onnx_session = None
                    self.tokenizer = None
            except Exception:
                self.onnx_session = None
                self.tokenizer = None
        else:
            self.onnx_session = None
            self.tokenizer = None

        if not self.is_temp_db:
            with suppress(Exception):
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create tables if they don't exist (this will initialize a connection in the main thread)
        # During initialization, we need to create a direct connection without going through _get_conn
        # since _get_conn checks for initialization state
        try:
            temp_conn = duckdb.connect(
                self.db_path, config={"allow_unsigned_extensions": True}
            )
        except Exception as e:
            msg = f"Database connection error (directory/permission): {e}"
            raise RuntimeError(msg) from e
        try:
            # Create conversations table
            temp_conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id VARCHAR PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding FLOAT[384],
                    project VARCHAR,
                    timestamp TIMESTAMP,
                    metadata JSON
                )
            """)

            # Create reflections table
            temp_conn.execute("""
                CREATE TABLE IF NOT EXISTS reflections (
                    id VARCHAR PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding FLOAT[384],
                    project VARCHAR,
                    tags VARCHAR[],
                    timestamp TIMESTAMP,
                    metadata JSON
                )
            """)

            # Create reflection_tags table for tag-based search
            temp_conn.execute("""
                CREATE TABLE IF NOT EXISTS reflection_tags (
                    reflection_id VARCHAR,
                    tag VARCHAR,
                    PRIMARY KEY (reflection_id, tag)
                )
            """)

            # Create indexes for performance
            temp_conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project)"
            )
            temp_conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp)"
            )
            temp_conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reflections_project ON reflections(project)"
            )
            temp_conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reflections_timestamp ON reflections(timestamp)"
            )
            temp_conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reflection_tags_tag ON reflection_tags(tag)"
            )
        finally:
            temp_conn.close()

        # Now mark as initialized
        self._initialized = True

        # Create the connection for the current thread so that the conn property works
        if self.is_temp_db:
            # For temp DBs, create the shared connection
            with self.lock:
                self._shared_conn = duckdb.connect(
                    self.db_path, config={"allow_unsigned_extensions": True}
                )
                # Create tables in the shared connection for in-memory DB
                self._initialize_shared_tables()
                # Backward-compat: expose connection via thread-local conn property
                self.local.conn = self._shared_conn
        else:
            # For non-temporary DBs, create a connection in the local storage
            self.local.conn = duckdb.connect(
                self.db_path, config={"allow_unsigned_extensions": True}
            )

    def _get_conn(self) -> "duckdb.DuckDBPyConnection":
        """Get database connection for the current thread, initializing if needed."""
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
                    # Create tables in the shared connection for in-memory DB
                    self._initialize_shared_tables()
                self.local.conn = self._shared_conn
            return self._shared_conn  # type: ignore[return-value]

        # For normal environments, use thread-local storage
        if not hasattr(self.local, "conn") or self.local.conn is None:
            self.local.conn = duckdb.connect(
                self.db_path, config={"allow_unsigned_extensions": True}
            )
        return self.local.conn  # type: ignore[return-value]

    def _initialize_shared_tables(self) -> None:
        """Initialize tables in the shared connection for in-memory databases."""
        # Access the shared connection through the instance variable
        conn = getattr(self, "_shared_conn", None)
        if not conn:
            return  # Defensive check

        # Create conversations table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                embedding FLOAT[384],
                project VARCHAR,
                timestamp TIMESTAMP,
                metadata JSON
            )
        """)

        # Create reflections table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reflections (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                embedding FLOAT[384],
                project VARCHAR,
                tags VARCHAR[],
                timestamp TIMESTAMP,
                metadata JSON
            )
        """)

        # Create reflection_tags table for tag-based search (no FK: DuckDB has limitations on updates)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reflection_tags (
                reflection_id VARCHAR,
                tag VARCHAR,
                PRIMARY KEY (reflection_id, tag)
            )
        """)

        # Create project_groups table for multi-project coordination
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_groups (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                description TEXT,
                projects VARCHAR[] NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                metadata JSON
            )
        """)

        # Create project_dependencies table for project relationships
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_dependencies (
                id VARCHAR PRIMARY KEY,
                source_project VARCHAR NOT NULL,
                target_project VARCHAR NOT NULL,
                dependency_type VARCHAR NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                metadata JSON,
                UNIQUE(source_project, target_project, dependency_type)
            )
        """)

        # Create session_links table for cross-project session coordination
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_links (
                id VARCHAR PRIMARY KEY,
                source_session_id VARCHAR NOT NULL,
                target_session_id VARCHAR NOT NULL,
                link_type VARCHAR NOT NULL,
                context TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                metadata JSON,
                UNIQUE(source_session_id, target_session_id, link_type)
            )
        """)

        # Create search_index table for advanced search capabilities
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_index (
                id VARCHAR PRIMARY KEY,
                content_type VARCHAR NOT NULL,  -- 'conversation', 'reflection', 'file', 'project'
                content_id VARCHAR NOT NULL,
                indexed_content TEXT NOT NULL,
                search_metadata JSON,
                last_indexed TIMESTAMP DEFAULT NOW(),
                UNIQUE(content_type, content_id)
            )
        """)

        # Create search_facets table for faceted search
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_facets (
                id VARCHAR PRIMARY KEY,
                content_type VARCHAR NOT NULL,
                content_id VARCHAR NOT NULL,
                facet_name VARCHAR NOT NULL,
                facet_value VARCHAR NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

    async def _ensure_tables(self) -> None:
        """Ensure required tables exist."""
        # Create conversations table
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                embedding FLOAT[384],
                project VARCHAR,
                timestamp TIMESTAMP,
                metadata JSON
            )
        """)

        # Create reflections table
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS reflections (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                embedding FLOAT[384],
                tags VARCHAR[],
                timestamp TIMESTAMP,
                metadata JSON
            )
        """)

        # Create project_groups table for multi-project coordination
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS project_groups (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                description TEXT,
                projects VARCHAR[] NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                metadata JSON
            )
        """)

        # Create project_dependencies table for project relationships
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS project_dependencies (
                id VARCHAR PRIMARY KEY,
                source_project VARCHAR NOT NULL,
                target_project VARCHAR NOT NULL,
                dependency_type VARCHAR NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                metadata JSON,
                UNIQUE(source_project, target_project, dependency_type)
            )
        """)

        # Create session_links table for cross-project session coordination
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS session_links (
                id VARCHAR PRIMARY KEY,
                source_session_id VARCHAR NOT NULL,
                target_session_id VARCHAR NOT NULL,
                link_type VARCHAR NOT NULL,
                context TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                metadata JSON,
                UNIQUE(source_session_id, target_session_id, link_type)
            )
        """)

        # Create search_index table for advanced search capabilities
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS search_index (
                id VARCHAR PRIMARY KEY,
                content_type VARCHAR NOT NULL,  -- 'conversation', 'reflection', 'file', 'project'
                content_id VARCHAR NOT NULL,
                indexed_content TEXT NOT NULL,
                search_metadata JSON,
                last_indexed TIMESTAMP DEFAULT NOW(),
                UNIQUE(content_type, content_id)
            )
        """)

        # Create search_facets table for faceted search
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS search_facets (
                id VARCHAR PRIMARY KEY,
                content_type VARCHAR NOT NULL,
                content_id VARCHAR NOT NULL,
                facet_name VARCHAR NOT NULL,
                facet_value VARCHAR NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Create indices for better performance
        await self._ensure_indices()

    async def _ensure_indices(self) -> None:
        """Create indices for better query performance."""
        indices = [
            # Existing table indices
            "CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project)",
            "CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_reflections_timestamp ON reflections(timestamp)",
            # New multi-project indices
            "CREATE INDEX IF NOT EXISTS idx_project_deps_source ON project_dependencies(source_project)",
            "CREATE INDEX IF NOT EXISTS idx_project_deps_target ON project_dependencies(target_project)",
            "CREATE INDEX IF NOT EXISTS idx_session_links_source ON session_links(source_session_id)",
            "CREATE INDEX IF NOT EXISTS idx_session_links_target ON session_links(target_session_id)",
            # Search indices
            "CREATE INDEX IF NOT EXISTS idx_search_index_type ON search_index(content_type)",
            "CREATE INDEX IF NOT EXISTS idx_search_index_last_indexed ON search_index(last_indexed)",
            "CREATE INDEX IF NOT EXISTS idx_search_facets_name_value ON search_facets(facet_name, facet_value)",
            "CREATE INDEX IF NOT EXISTS idx_search_facets_content ON search_facets(content_type, content_id)",
        ]

        for index_sql in indices:
            with suppress(Exception):
                # Some indices might not be supported in all DuckDB versions, continue
                self._get_conn().execute(index_sql)

    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding for text using ONNX model."""
        if self.onnx_session and self.tokenizer:

            def _get_embedding() -> list[float]:
                # Tokenize text
                assert self.tokenizer is not None  # For type checker
                encoded = self.tokenizer(
                    text,
                    truncation=True,
                    padding=True,
                    return_tensors="np",
                )

                # Run inference
                assert self.onnx_session is not None  # For type checker
                outputs = self.onnx_session.run(
                    None,
                    {
                        "input_ids": encoded["input_ids"],
                        "attention_mask": encoded["attention_mask"],
                        "token_type_ids": encoded.get(
                            "token_type_ids",
                            np.zeros_like(encoded["input_ids"]),
                        ),
                    },
                )

                # Mean pooling
                embeddings = outputs[0]
                attention_mask = encoded["attention_mask"]
                masked_embeddings = embeddings * np.expand_dims(attention_mask, axis=-1)
                summed = np.sum(masked_embeddings, axis=1)
                counts = np.sum(attention_mask, axis=1, keepdims=True)
                mean_pooled = summed / counts

                # Normalize
                norms = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
                normalized = mean_pooled / norms

                # Convert to float32 to match DuckDB FLOAT type
                return normalized[0].astype(np.float32).tolist()

            return await asyncio.get_event_loop().run_in_executor(None, _get_embedding)

        msg = "No embedding model available"
        raise RuntimeError(msg)

    async def store_conversation(self, content: str, metadata: dict[str, Any]) -> str:
        """Store conversation with optional embedding."""
        conversation_id = hashlib.md5(
            f"{content}_{time.time()}".encode("utf-8", "surrogatepass"),
            usedforsecurity=False,
        ).hexdigest()

        db_content = _encode_text_for_db(content)

        embedding: list[float] | None = None

        if ONNX_AVAILABLE and self.onnx_session:
            try:
                embedding = await self.get_embedding(content)
            except Exception:
                embedding = None  # Fallback to no embedding
        else:
            embedding = None  # Store without embedding

        # For synchronized database access in test environments using in-memory DB
        if self.is_temp_db:
            # Use lock to protect database operations for in-memory DB
            with self.lock:
                self._get_conn().execute(
                    """
                    INSERT INTO conversations (id, content, embedding, project, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        conversation_id,
                        db_content,
                        embedding,
                        metadata.get("project"),
                        datetime.now(UTC),
                        json.dumps(metadata),
                    ],
                )
        else:
            # For normal file-based DB, run in executor for thread safety
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_conn().execute(
                    """
                    INSERT INTO conversations (id, content, embedding, project, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        conversation_id,
                        db_content,
                        embedding,
                        metadata.get("project"),
                        datetime.now(UTC),
                        json.dumps(metadata),
                    ],
                ),
            )

        # DuckDB is ACID-compliant by default, explicit commit is not required for individual operations
        # However, if needed, we can call commit on the thread-local connection
        # self._get_conn().commit()
        return conversation_id

    async def store_reflection(
        self,
        content: str,
        tags: list[str] | None = None,
        project: str | None = None,
    ) -> str:
        """Store reflection/insight with optional embedding."""
        if content is None:
            msg = "content cannot be None"
            raise TypeError(msg)

        reflection_id = hashlib.md5(
            f"reflection_{content}_{time.time()}".encode("utf-8", "surrogatepass"),
            usedforsecurity=False,
        ).hexdigest()

        db_content = _encode_text_for_db(content)

        tags_list = tags or []

        embedding: list[float] | None = None

        if ONNX_AVAILABLE and self.onnx_session:
            try:
                embedding = await self.get_embedding(content)
            except Exception:
                embedding = None  # Fallback to no embedding
        else:
            embedding = None  # Store without embedding

        def _store() -> None:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO reflections (id, content, embedding, project, tags, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    reflection_id,
                    db_content,
                    embedding,
                    project,
                    tags_list,
                    datetime.now(UTC),
                    json.dumps({"type": "reflection", "project": project}),
                ],
            )
            conn.execute(
                "DELETE FROM reflection_tags WHERE reflection_id = ?",
                [reflection_id],
            )
            tags_unique = list(dict.fromkeys(tags_list))
            for tag in tags_unique:
                conn.execute(
                    "INSERT INTO reflection_tags (reflection_id, tag) VALUES (?, ?)",
                    [reflection_id, tag],
                )

        # For synchronized database access in test environments using in-memory DB
        if self.is_temp_db:
            with self.lock:
                _store()
        else:
            await asyncio.get_event_loop().run_in_executor(None, _store)

        # DuckDB is ACID-compliant by default, explicit commit is not required for individual operations
        # However, if needed, we can call commit on the thread-local connection
        # self._get_conn().commit()
        return reflection_id

    async def get_reflection(self, reflection_id: str | None) -> dict[str, Any] | None:
        """Get a reflection by ID."""
        if not reflection_id or not isinstance(reflection_id, str):
            return None
        if len(reflection_id) < 5 or len(reflection_id) > 128:
            return None

        rows = await self._execute_query(
            "SELECT id, content, project, tags, timestamp, metadata FROM reflections WHERE id = ?",
            [reflection_id],
        )
        if not rows:
            return None

        row = rows[0]
        return {
            "id": row[0],
            "content": _decode_text_from_db(row[1]),
            "project": row[2],
            "tags": list(row[3]) if row[3] else [],
            "timestamp": row[4],
            "metadata": json.loads(row[5]) if row[5] else {},
        }

    async def update_reflection(
        self,
        reflection_id: str | None,
        content: str | None,
        tags: list[str] | None = None,
        project: str | None = None,
    ) -> None:
        """Update an existing reflection.

        This is best-effort: updating a non-existent reflection is a no-op.
        """
        if (
            reflection_id is None
            or not isinstance(reflection_id, str)
            or not reflection_id
        ):
            return
        if content is None:
            msg = "content cannot be None"
            raise TypeError(msg)

        tags_list = tags or []

        db_content = _encode_text_for_db(content)

        embedding: list[float] | None = None
        if ONNX_AVAILABLE and self.onnx_session:
            with suppress(Exception):
                embedding = await self.get_embedding(content)

        def _update() -> None:
            conn = self._get_conn()

            result = conn.execute(
                "SELECT COUNT(*) FROM reflections WHERE id = ?",
                [reflection_id],
            ).fetchone()
            exists = result[0] if result else 0
            if exists <= 0:
                return

            conn.execute(
                """
                UPDATE reflections
                SET content = ?,
                    embedding = ?,
                    tags = ?,
                    project = COALESCE(?, project),
                    timestamp = ?,
                    metadata = ?
                WHERE id = ?
                """,
                [
                    db_content,
                    embedding,
                    tags_list,
                    project,
                    datetime.now(UTC),
                    json.dumps({"type": "reflection", "project": project}),
                    reflection_id,
                ],
            )
            conn.execute(
                "DELETE FROM reflection_tags WHERE reflection_id = ?",
                [reflection_id],
            )
            tags_unique = list(dict.fromkeys(tags_list))
            for tag in tags_unique:
                conn.execute(
                    "INSERT INTO reflection_tags (reflection_id, tag) VALUES (?, ?)",
                    [reflection_id, tag],
                )

        if self.is_temp_db:
            with self.lock:
                _update()
        else:
            await asyncio.get_event_loop().run_in_executor(None, _update)

    async def delete_reflection(self, reflection_id: str | None) -> None:
        """Delete a reflection by ID.

        Deleting a non-existent reflection is a no-op.
        """
        if reflection_id is None:
            msg = "reflection_id cannot be None"
            raise TypeError(msg)
        if not isinstance(reflection_id, str) or not reflection_id:
            msg = "reflection_id must be a non-empty string"
            raise ValueError(msg)

        def _delete() -> None:
            conn = self._get_conn()
            conn.execute(
                "DELETE FROM reflection_tags WHERE reflection_id = ?",
                [reflection_id],
            )
            conn.execute(
                "DELETE FROM reflections WHERE id = ?",
                [reflection_id],
            )

        if self.is_temp_db:
            with self.lock:
                _delete()
        else:
            await asyncio.get_event_loop().run_in_executor(None, _delete)

    async def search_conversations(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.7,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search conversations by text similarity (fallback to text search if no embeddings)."""
        if ONNX_AVAILABLE and self.onnx_session:
            return await self._semantic_search_conversations(
                query, limit, min_score, project
            )
        return await self._text_search_conversations(query, limit, project)

    async def _semantic_search_conversations(
        self, query: str, limit: int, min_score: float, project: str | None
    ) -> list[dict[str, Any]]:
        """Semantic search implementation with embeddings."""
        with suppress(Exception):
            query_embedding = await self.get_embedding(query)

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

            # For synchronized database access in test environments using in-memory DB
            if self.is_temp_db:
                # Use lock to protect database operations for in-memory DB
                with self.lock:
                    results = self._get_conn().execute(sql, params).fetchall()
            else:
                # For normal file-based DB, run in executor for thread safety
                results = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._get_conn().execute(sql, params).fetchall(),
                )

            # Build results and log accesses into v2 access log (best-effort)
            filtered = [row for row in results if float(row[6]) >= min_score]
            self._log_accesses([str(row[0]) for row in filtered])

            return [
                {
                    "content": _decode_text_from_db(row[1]),
                    "score": float(row[6]),
                    "timestamp": row[4],
                    "project": row[3],
                    "metadata": json.loads(row[5]) if row[5] else {},
                }
                for row in filtered
            ]

        # If semantic search fails or is not available, fallback to text search
        return await self._text_search_conversations(query, limit, project)

    async def _text_search_conversations(
        self, query: str, limit: int, project: str | None
    ) -> list[dict[str, Any]]:
        """Fallback text search implementation."""
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

        # For synchronized database access in test environments using in-memory DB
        if self.is_temp_db:
            # Use lock to protect database operations for in-memory DB
            with self.lock:
                results = self._get_conn().execute(sql, params).fetchall()
        else:
            # For normal file-based DB, run in executor for thread safety
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_conn().execute(sql, params).fetchall(),
            )

        # Simple text matching score
        matches = []
        matched_ids: list[str] = []
        for row in results:
            content = _decode_text_from_db(row[1])
            content_lower = content.lower()
            score = sum(1 for term in search_terms if term in content_lower) / len(
                search_terms,
            )

            if score > 0:  # At least one term matches
                matches.append(
                    {
                        "content": content,
                        "score": score,
                        "timestamp": row[3],
                        "project": row[2],
                        "metadata": json.loads(row[4]) if row[4] else {},
                    },
                )
                with suppress(Exception):
                    matched_ids.append(str(row[0]))

        # Sort by score and return top matches, then log accesses
        matches.sort(key=operator.itemgetter("score"), reverse=True)
        top = matches[:limit]
        self._log_accesses(matched_ids[:limit])
        return top

    def _log_accesses(self, conv_ids: list[str]) -> None:
        """Helper to log memory accesses."""
        from contextlib import suppress

        with suppress(Exception):
            from session_buddy.memory.persistence import (
                log_memory_access as _log_access,
            )

            for conv_id in conv_ids:
                _log_access(conv_id, access_type="search")

    async def search_reflections(
        self,
        query: str,
        limit: int = 5,
        project: str | None = None,
        *,
        tags: list[str] | None = None,
        min_score: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Search stored reflections by semantic similarity with text fallback."""
        if query is None:
            msg = "query cannot be None"
            raise TypeError(msg)
        if limit <= 0:
            return []

        results = await self._semantic_reflection_search(
            query,
            limit,
            min_score,
            project,
            tags,
        )
        if results is not None:
            return results

        return await self._text_reflection_search(query, limit, project, tags)

    async def _semantic_reflection_search(
        self,
        query: str,
        limit: int,
        min_score: float,
        project: str | None,
        tags: list[str] | None,
    ) -> list[dict[str, Any]] | None:
        """Run semantic reflection search if ONNX embeddings available."""
        if not (ONNX_AVAILABLE and self.onnx_session):
            return None

        with suppress(Exception):
            query_embedding = await self.get_embedding(query)
            sql = """
                SELECT
                    id, content, project, tags, timestamp, metadata,
                    array_cosine_similarity(embedding, CAST(? AS FLOAT[384])) as score
                FROM reflections
                WHERE embedding IS NOT NULL
            """

            params: list[Any] = [query_embedding]
            if project is not None:
                sql += " AND project = ?"
                params.append(project)

            if tags:
                tag_clauses = " OR ".join(["list_contains(tags, ?)"] * len(tags))
                sql += f" AND ({tag_clauses})"
                params.extend(tags)

            sql += """
                ORDER BY score DESC
                LIMIT ?
            """

            params.append(limit)
            results = await self._execute_query(sql, params)
            semantic_results = [
                {
                    "id": row[0],
                    "content": _decode_text_from_db(row[1]),
                    "score": float(row[6]),
                    "project": row[2],
                    "tags": list(row[3]) if row[3] else [],
                    "timestamp": row[4],
                    "metadata": json.loads(row[5]) if row[5] else {},
                }
                for row in results
                if float(row[6]) >= min_score
            ]

            if semantic_results:
                return semantic_results
        return None

    async def _text_reflection_search(
        self,
        query: str,
        limit: int,
        project: str | None,
        tags: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Fallback text search for reflections."""
        sql = "SELECT id, content, project, tags, timestamp, metadata FROM reflections"
        params: list[Any] = []

        where_clauses = []
        if project is not None:
            where_clauses.append("project = ?")
            params.append(project)

        if tags:
            tag_clauses = " OR ".join(["list_contains(tags, ?)"] * len(tags))
            where_clauses.append(f"({tag_clauses})")
            params.extend(tags)

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        sql += " ORDER BY timestamp DESC"
        results = await self._execute_query(sql, params or None)

        search_terms = query.lower().split()
        matches = []
        for row in results:
            content = _decode_text_from_db(row[1])
            combined_text = f"{content.lower()} {' '.join(list(row[3] or [])).lower()}"
            score = (
                sum(1 for term in search_terms if term in combined_text)
                / len(search_terms)
                if search_terms
                else 1.0
            )

            if score > 0:
                matches.append(
                    {
                        "id": row[0],
                        "content": content,
                        "score": score,
                        "project": row[2],
                        "tags": list(row[3]) if row[3] else [],
                        "timestamp": row[4],
                        "metadata": json.loads(row[5]) if row[5] else {},
                    },
                )

        matches.sort(key=operator.itemgetter("score"), reverse=True)
        return matches[:limit]

    async def _execute_query(
        self,
        sql: str,
        params: list[Any] | None = None,
    ) -> list[Any]:
        """Execute a query with locking or async executor based on DB type."""
        params = params or []
        if self.is_temp_db:
            with self.lock:
                return self._get_conn().execute(sql, params).fetchall()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._get_conn().execute(sql, params).fetchall(),
        )

    async def search_by_file(
        self,
        file_path: str,
        limit: int = 10,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search conversations that mention a specific file."""
        sql = """
            SELECT id, content, project, timestamp, metadata
            FROM conversations
            WHERE content LIKE ?
        """
        params: list[Any] = [f"%{file_path}%"]

        if project:
            sql += " AND project = ?"
            params.append(project)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        # For synchronized database access in test environments using in-memory DB
        if self.is_temp_db:
            # Use lock to protect database operations for in-memory DB
            with self.lock:
                results = self._get_conn().execute(sql, params).fetchall()
        else:
            # For normal file-based DB, run in executor for thread safety
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_conn().execute(sql, params).fetchall(),
            )

        # Build results and log access for each conversation id
        output = []
        for row in results:
            output.append(
                {
                    "content": _decode_text_from_db(row[1]),
                    "project": row[2],
                    "timestamp": row[3],
                    "metadata": json.loads(row[4]) if row[4] else {},
                }
            )
            from contextlib import suppress

            with suppress(Exception):
                from session_buddy.memory.persistence import (
                    log_memory_access as _log_access,
                )

                _log_access(str(row[0]), access_type="search")
        return output

    async def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
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
        """Get the count of conversations from the database."""
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
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: (
                    (
                        result := self._get_conn()
                        .execute(
                            "SELECT COUNT(*) FROM conversations",
                        )
                        .fetchone()
                    )
                    and result[0]
                )
                or 0,
            )

    async def _get_reflection_count(self) -> int:
        """Get the count of reflections from the database."""
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
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: (
                    (
                        result := self._get_conn()
                        .execute(
                            "SELECT COUNT(*) FROM reflections",
                        )
                        .fetchone()
                    )
                    and result[0]
                )
                or 0,
            )


# Global database adapter instance
_reflection_db: ReflectionDatabaseAdapter | None = None


async def get_reflection_database() -> ReflectionDatabaseAdapter:
    """Get or create reflection database adapter instance.

    DEPRECATED: This function is deprecated and will be removed in a future release.
    Use the ReflectionDatabaseAdapter directly with dependency injection instead.
    """
    global _reflection_db
    if _reflection_db is None:
        from session_buddy.di import configure

        configure()
        _reflection_db = ReflectionDatabaseAdapter()
        await _reflection_db.initialize()
    return _reflection_db


def get_initialized_reflection_database() -> ReflectionDatabaseAdapter | None:
    """Return the initialized reflection database if available."""
    return _reflection_db


def cleanup_reflection_database() -> None:
    """Clean up global reflection database instance."""
    global _reflection_db
    if _reflection_db:
        _reflection_db.close()
        _reflection_db = None


def get_current_project() -> str | None:
    """Get current project name from working directory."""
    try:
        cwd = Path.cwd()
        # Try to detect project from common indicators
        if (cwd / "pyproject.toml").exists() or (cwd / "package.json").exists():
            return cwd.name
        # Fallback to directory name
        return cwd.name if cwd.name != "." else None
    except Exception:
        return None
