"""Reflection database adapter using native DuckDB vector operations.

Replaces ACB vector adapter with direct DuckDB vector operations while maintaining
the same API for backward compatibility.

Phase 5: Oneiric Adapter Conversion - Native DuckDB implementation
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import typing as t
from contextlib import suppress
from datetime import UTC, datetime
from operator import itemgetter
from pathlib import Path

from ulid import ULID

if t.TYPE_CHECKING:
    from types import TracebackType

    import duckdb
    import numpy as np

# Runtime imports (available at runtime but optional for type checking)
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# HTTP-based embedding — no local ONNX model needed.
# Providers (llama-server/Ollama) return pre-normalized 384d vectors.
ONNX_AVAILABLE = False  # Always False — using HTTP providers
ort = None
AutoTokenizer: type | None = None  # Not needed for HTTP

from session_buddy.adapters.settings import ReflectionAdapterSettings
from session_buddy.cache.query_cache import QueryCacheManager
from session_buddy.ingesters.redaction import (
    ALLOWED_METADATA_KEYS,
    RedactionSizeError,
    redact,
    redact_metadata,
)
from session_buddy.insights.models import validate_collection_name
from session_buddy.memory.category_evolution import CategoryEvolutionEngine
from session_buddy.memory.causal import (
    infer_causal_links_for as _infer_causal_links_for,
)
from session_buddy.memory.causal import (
    prune_causal_links_older_than as _prune_causal_links_older_than,
)
from session_buddy.memory.causal import (
    record_observed_link as _record_observed_link,
)
from session_buddy.memory.causal import (
    walk_causal_chain as _walk_causal_chain,
)
from session_buddy.memory.peer_modeling import (
    build_peer_context,
    get_peer_model,
    upsert_peer_model,
)
from session_buddy.memory.schema_v2 import SCHEMA_V2_SQL
from session_buddy.skills.distiller import (
    DEFAULT_EVIDENCE_THRESHOLD as _DEFAULT_EVIDENCE_THRESHOLD,
)
from session_buddy.skills.distiller import (
    HEURISTIC_MODEL as _HEURISTIC_MODEL,
)
from session_buddy.skills.distiller import (
    distill_skills as _distill_skills,
)
from session_buddy.skills.distiller import (
    reinforce_skill as _reinforce_skill,
)
from session_buddy.skills.distiller import (
    search_distilled_skills as _search_distilled_skills,
)
from session_buddy.utils.fingerprint import MinHashSignature

logger = logging.getLogger(__name__)

# Module-level connection cache: maps resolved database path -> shared DuckDB connection.
# This ensures that multiple adapter instances pointing to the same database file
# share a single connection, making HNSW indexes visible across all of them.
_connection_cache: dict[str, t.Any] = {}


class _CachedConnection:
    """Wrapper for cached connections with reference counting.

    Tracks how many adapter instances share a connection and only closes
    when the last one calls close().
    """

    def __init__(self, conn: t.Any, cache_key: str) -> None:
        self.conn = conn
        self.cache_key = cache_key
        self.ref_count = 1

    def release(self) -> None:
        """Decrement reference count; close connection if no more references."""
        self.ref_count -= 1
        if self.ref_count <= 0:
            with suppress(Exception):
                self.conn.close()
            _connection_cache.pop(self.cache_key, None)


_typed_connection_cache: dict[str, _CachedConnection] = {}


# DuckDB will be imported at runtime
DUCKDB_AVAILABLE = True
try:
    import duckdb
except ImportError:
    DUCKDB_AVAILABLE = False
    if t.TYPE_CHECKING:
        # Type stub for type checking when duckdb is not installed
        import types as _duckdb_types

        _duckdb_stub: t.Any = _duckdb_types.SimpleNamespace()


class ReflectionDatabaseAdapterOneiric:
    """Manages conversation memory and reflection using native DuckDB vector operations.

    This adapter replaces ACB's Vector adapter with direct DuckDB operations while maintaining
    the original ReflectionDatabase API for backward compatibility. It handles:
    - HTTP-based embedding generation (llama-server/Ollama, 384 dimensions)
    - Vector storage and retrieval via native DuckDB
    - Graceful fallback to text search when embeddings unavailable
    - Async/await patterns consistent with existing code

    The adapter uses Oneiric settings and lifecycle management, providing:
    - Native DuckDB vector operations (no ACB dependency)
    - Oneiric settings integration
    - Same API as the ACB-based adapter

    Example:
        >>> async with ReflectionDatabaseAdapterOneiric() as db:
        >>>     conv_id = await db.store_conversation("content", {"project": "foo"})
        >>>     results = await db.search_conversations("query")

    """

    def __init__(
        self,
        collection_name: str = "default",
        settings: ReflectionAdapterSettings | None = None,
        db_path: str | None = None,  # Backward compat for legacy callers
    ) -> None:
        """Initialize adapter with optional collection name.

        Args:
            collection_name: Name of the vector collection to use.
                           Default "default" collection will be created automatically.
            settings: Reflection adapter settings. If None, uses defaults.
            db_path: Override the database path. Takes precedence over
                     ``settings.database_path``. Useful for tests that
                     want to isolate each instance into a tempdir
                     (otherwise multiple processes / xdist workers
                     collide on the shared default path).

        """
        self.settings = settings or ReflectionAdapterSettings.from_settings()
        if collection_name == "default":
            # Validate collection name to prevent SQL injection
            self.collection_name = validate_collection_name(
                self.settings.collection_name
            )
        else:
            # Validate collection name to prevent SQL injection
            self.collection_name = validate_collection_name(collection_name)
        # Resolve the database path. ``db_path`` (when provided) takes
        # precedence so tests can isolate each adapter into a tempdir.
        # Preserve :memory: paths as-is to avoid converting to file paths.
        if db_path is not None:
            self.db_path = ":memory:" if str(db_path) == ":memory:" else str(db_path)
        else:
            settings_db_path = self.settings.database_path
            if str(settings_db_path) == ":memory:":
                self.db_path = ":memory:"
            else:
                self.db_path = str(settings_db_path)
        self.conn: t.Any = None  # DuckDB connection (sync)
        self.embedding_dim = self.settings.embedding_dim  # all-MiniLM-L6-v2 dimension
        self._initialized = False

        # Category evolution engine (Phase 5)
        self._category_engine: CategoryEvolutionEngine | None = None
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._hnsw_available: bool = False

        # Query cache for performance optimization (Phase 1: Query Cache)
        self._query_cache: QueryCacheManager | None = None

    def __enter__(self) -> t.Self:
        """Sync context manager entry (not recommended - use async)."""
        msg = "Use 'async with' instead of 'with' for ReflectionDatabaseAdapterOneiric"
        raise RuntimeError(msg)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Sync context manager exit."""
        self.close()

    async def __aenter__(self) -> t.Self:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Async context manager exit with cleanup."""
        await self.aclose()

    # -------------------------------------------------------------------------
    # Identifier construction helpers — validates ONCE at construction time,
    # then all internal queries use these helpers instead of raw interpolation.
    # This eliminates the class of SQL injection that cannot be caught by
    # parameterized queries (identifier vs value injection).
    # -------------------------------------------------------------------------

    def _table(self, suffix: str) -> str:
        """Return a validated table name for this collection.

        All internal table references MUST use this helper to guarantee
        that the collection name was validated at __init__ time.

        v2 rewire (Phase 0): the conversations and reflections suffixes now
        resolve to the global ``conversations_v2`` / ``reflections_v2``
        tables instead of the legacy ``{collection}_conversations`` /
        ``{collection}_reflections`` collection-scoped tables. This keeps
        all write/read paths pointing at the v2 schema after the rewire.
        """
        if suffix == "conversations":
            return "conversations_v2"
        if suffix == "reflections":
            return "reflections_v2"
        return f"{self.collection_name}_{suffix}"

    def _index(self, suffix: str) -> str:
        """Return a validated index name for this collection."""
        return f"idx_{self.collection_name}_{suffix}"

    def _validate_hnsw_ef(self, value: int) -> int:
        """Validate HNSW ef_search/ef_construction parameter (must be >= 1)."""
        if not isinstance(value, int) or value < 1:
            return 100  # Safe default
        return value

    def _get_conn(self) -> t.Any:
        """Return the active DuckDB connection.

        Backward-compat shim: the legacy ReflectionDatabase had this method,
        and ``code_graph_subscriber`` / ``reflection/storage`` call it
        defensively via :func:`hasattr` before falling back to ``self.conn``.
        The Oneiric adapter migration preserved the legacy API on most
        methods but accidentally dropped this one. Keep the API alive so
        the 12 call sites that depend on it (verified via exploration) keep
        working without modification.
        """
        if not self._initialized:
            msg = (
                "ReflectionDatabaseAdapterOneiric._get_conn() called before "
                "initialize(); the adapter is not connected."
            )
            raise RuntimeError(msg)
        return self.conn

    def _log_access(
        self,
        *,
        memory_id: str | None,
        access_type: str,
        query_text: str | None = None,
    ) -> None:
        """Unconditionally write a row to ``memory_access_log``.

        The Conscious Agent analysis loop reads from ``memory_access_log``
        to decide which memories to promote. Per the rollout plan, the
        read path MUST write to this table from day one — before the
        background analysis loop is enabled — so the log is populated
        the day the loop turns on.

        This method is deliberately permissive:

        * It never raises. An instrumentation failure must never break
          the read path that called it.
        * It does not consult any feature flag. The flag gates the
          background analysis loop, not the write path.
        * It tolerates ``memory_id=None`` (a search that hits nothing).

        Args:
            memory_id: ID of the memory being accessed, or None for
                access events not tied to a specific memory (e.g. a
                search that returned no hits).
            access_type: Category of access (``search``, ``retrieve``,
                ``promote``, ``demote``).
            query_text: Original search string, when applicable.

        """
        try:
            if not self._initialized:
                # No connection yet — we cannot log. Silently drop.
                return
            self.conn.execute(
                """
                INSERT INTO memory_access_log (
                    id, memory_id, access_type, query_text, timestamp
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [str(ULID()), memory_id, access_type, query_text],
            )
        except Exception:
            # Instrumentation must NEVER break the read path.
            logger.debug("memory_access_log write failed", exc_info=True)

    def close(self) -> None:
        """Close adapter connections (sync version for compatibility)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            task = loop.create_task(self.aclose())

            def _consume_result(future: asyncio.Future[t.Any]) -> None:
                try:
                    future.result()
                except asyncio.CancelledError:
                    # Task was cancelled during shutdown, which is expected
                    pass
                except Exception:
                    # Log other exceptions if needed
                    logger.debug(
                        "Exception in ReflectionDatabaseAdapterOneiric close task",
                        exc_info=True,
                    )

            task.add_done_callback(_consume_result)
        else:
            asyncio.run(self.aclose())

    async def aclose(self) -> None:
        """Close adapter connections (async)."""
        # Close query cache properly BEFORE closing connection (Phase 1: Query Cache - Phase 6 fix)
        # This prevents race conditions by clearing cache while connection is still alive
        if self._query_cache:
            with suppress(Exception):
                self._query_cache.invalidate()  # Clear cache
                await asyncio.sleep(0.1)  # Phase 6: Wait for pending operations
            self._query_cache = None

        # Now close the connection
        if self.conn:
            # Release from shared connection cache with reference counting
            if self.db_path != ":memory:":
                cache_key = str(Path(self.db_path).resolve())
                cached = _typed_connection_cache.get(cache_key)
                if cached is not None:
                    cached.release()  # Decrements ref_count, closes if last reference
            with suppress(Exception):
                self.conn.close()
            self.conn = None

        self._cache_hits = 0
        self._cache_misses = 0

        self._initialized = False

    async def initialize(self) -> None:  # noqa: C901
        """Initialize DuckDB connection and create tables if needed."""
        if self._initialized:
            return

        if not DUCKDB_AVAILABLE:
            msg = "DuckDB not available. Install with: uv add duckdb"
            raise ImportError(msg)

        # Create database directory if it doesn't exist (skip for :memory:)
        if self.db_path == ":memory:":
            return
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Remove stale/empty database file that DuckDB cannot open.
        # NamedTemporaryFile (and similar) may create a zero-byte file at the
        # target path; DuckDB treats an existing but empty file as an invalid
        # database.  Deleting it lets DuckDB create a fresh one.
        db_file = Path(self.db_path)
        if db_file.exists() and db_file.stat().st_size == 0:
            db_file.unlink()

        # Connect to DuckDB database
        # Use consistent config to avoid "different configuration" errors when
        # other parts of the codebase (e.g., legacy ReflectionDatabase) have
        # already opened the same database file with allow_unsigned_extensions.
        # Reuse an existing connection if one is already open for this database
        # path so that session-local objects (like HNSW indexes) are visible to
        # all adapter instances sharing the file. :memory: databases are never
        # cached because each duckdb.connect() creates a unique in-memory
        # database that must not be shared.
        self.conn = self._open_duckdb_connection()

        # Enable vector extension if available
        with suppress(Exception):
            self.conn.execute("INSTALL 'httpfs';")
            self.conn.execute("LOAD 'httpfs';")

        # Enable vector extension if available
        with suppress(Exception):
            self.conn.execute("INSTALL 'httpfs';")
            self.conn.execute("LOAD 'httpfs';")

        # Create tables if they don't exist
        self._create_tables()

        # Initialize query cache (Phase 1: Query Cache)
        self._query_cache = QueryCacheManager(
            l1_max_size=1000,
            l2_ttl_days=7,
        )
        await self._query_cache.initialize(conn=self.conn)

        # Initialize category evolution engine (Phase 5)
        self._category_engine = CategoryEvolutionEngine(
            db_adapter=self,
            enable_fingerprint_prefilter=True,
        )
        await self._category_engine.initialize()

        self._initialized = True

    def _open_duckdb_connection(self) -> t.Any:
        """Return a live DuckDB connection, reusing a cache entry when possible.

        For file-based paths, the module-level ``_typed_connection_cache`` may
        already hold a live connection (e.g. another adapter instance opened
        the same file). Reusing it keeps session-local objects like HNSW
        indexes visible across adapters. :memory: databases are never cached
        because each ``duckdb.connect()`` produces a unique in-memory instance.

        If a fresh connect fails because of a stale ``.wal`` sidecar, the
        sidecar is purged and the connect is retried once. Any uncommitted
        writes are already lost in that case; a successful retry yields a
        consistent database.
        """
        if self.db_path != ":memory:":
            cache_key = str(Path(self.db_path).resolve())
            cached = _typed_connection_cache.get(cache_key)
            if cached is not None:
                try:
                    # Verify the connection is still alive
                    cached.conn.execute("SELECT 1")
                    cached.ref_count += 1
                    return cached.conn
                except Exception:
                    # Stale connection; remove and create a fresh one
                    cached.release()
                    _typed_connection_cache.pop(cache_key, None)

        try:
            conn = duckdb.connect(
                database=self.db_path,
                read_only=False,
                config={"allow_unsigned_extensions": True},
            )
        except Exception as e:
            msg = str(e)
            if self.db_path != ":memory:" and (
                "replaying WAL" in msg or "GetDefaultDatabase" in msg
            ):
                wal_file = Path(self.db_path + ".wal")
                if wal_file.exists():
                    with suppress(Exception):
                        wal_file.unlink()
                conn = duckdb.connect(
                    database=self.db_path,
                    read_only=False,
                    config={"allow_unsigned_extensions": True},
                )
            else:
                raise

        # Only cache file-based connections, not :memory:
        if self.db_path != ":memory:":
            cache_key = str(Path(self.db_path).resolve())
            _typed_connection_cache[cache_key] = _CachedConnection(conn, cache_key)

        return conn

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        # ========================================================================
        # v2 SCHEMA (Phase 0 v2 rewire) — Memori-inspired global tables.
        # Runs the SCHEMA_V2_SQL constant first so the conversations_v2 /
        # reflections_v2 tables exist with the v2 column set. The legacy
        # CREATE TABLE IF NOT EXISTS below is then a no-op for conversations_v2.
        # ========================================================================
        self._create_v2_schema()

        # Create conversations table
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("conversations")} (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                metadata JSON,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                embedding FLOAT[{self.embedding_dim}]
            )
            """
        )

        # Create reflections table with insight support
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("reflections")} (
                id VARCHAR PRIMARY KEY,
                conversation_id VARCHAR,
                content TEXT NOT NULL,
                tags VARCHAR[],
                metadata JSON,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                embedding FLOAT[{self.embedding_dim}],

                -- Insight-specific fields
                insight_type VARCHAR DEFAULT 'general',
                usage_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP,
                confidence_score REAL DEFAULT 0.5,

                FOREIGN KEY (conversation_id) REFERENCES {self._table("conversations")}(id)
            )
            """
        )

        # Create indices for faster search.
        # v2 rewire: ``conversations_v2`` uses ``timestamp`` not
        # ``created_at``, so we pick the column that actually exists.
        conv_idx_col = (
            "timestamp"
            if self._table("conversations") == "conversations_v2"
            else "created_at"
        )
        refl_idx_col = (
            "timestamp"
            if self._table("reflections") == "reflections_v2"
            else "created_at"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS {self._index('conv_created')} ON {self._table('conversations')}({conv_idx_col})"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS {self._index('refl_created')} ON {self._table('reflections')}({refl_idx_col})"
        )

        # ========================================================================
        # MIGRATION: Add insight columns to existing reflections tables
        # ========================================================================
        # This migration ensures existing databases get the new insight columns
        # We use ALTER TABLE IF NOT EXISTS pattern (DuckDB-safe)

        # Add insight_type column if it doesn't exist
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self._table('reflections')} ADD COLUMN IF NOT EXISTS insight_type VARCHAR DEFAULT 'general'"
            )

        # Add usage_count column if it doesn't exist
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self._table('reflections')} ADD COLUMN IF NOT EXISTS usage_count INTEGER DEFAULT 0"
            )

        # Add last_used_at column if it doesn't exist
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self._table('reflections')} ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP"
            )

        # Add confidence_score column if it doesn't exist
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self._table('reflections')} ADD COLUMN IF NOT EXISTS confidence_score REAL DEFAULT 0.5"
            )

        # Create insight-specific indexes for performance
        # Note: DuckDB doesn't support partial indexes (WHERE clauses), so we create full indexes
        # and filter at query time instead. Also can't index array types (VARCHAR[])
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS {self._index('refl_insight_type')} ON {self._table('reflections')}(insight_type)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS {self._index('refl_usage_count')} ON {self._table('reflections')}(usage_count)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS {self._index('refl_last_used')} ON {self._table('reflections')}(last_used_at)"
        )

        # ========================================================================
        # QUERY CACHE L2 TABLE (Phase 1: Query Cache)
        # ========================================================================
        # Creates a persistent cache for query results to eliminate redundant vector searches

        # Create query cache L2 table
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS query_cache_l2 (
                cache_key TEXT PRIMARY KEY,
                normalized_query TEXT NOT NULL,
                project TEXT,
                result_ids TEXT[],
                hit_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ttl_seconds INTEGER DEFAULT 604800
            )
            """
        )

        # Create indexes for query cache
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_query_cache_l2_accessed ON query_cache_l2(last_accessed)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_query_cache_l2_project ON query_cache_l2(project)"
        )

        # REWRITTEN QUERIES TABLE (Phase 2: Query Rewriting)
        # ========================================================================
        # Tracks query rewrites for performance analysis and cache optimization

        # Create rewritten queries table
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rewritten_queries (
                id TEXT PRIMARY KEY,
                original_query TEXT NOT NULL,
                rewritten_query TEXT NOT NULL,
                llm_provider TEXT,
                confidence_score FLOAT,
                context_snapshot TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used_count INTEGER DEFAULT 1,
                effective BOOLEAN DEFAULT TRUE
            )
            """
        )

        # Create indexes for rewritten queries
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rewritten_queries_created ON rewritten_queries(created_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rewritten_queries_original ON rewritten_queries(original_query)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rewritten_queries_effective ON rewritten_queries(effective)"
        )

        # ========================================================================
        # N-GRAM FINGERPRINTING (Phase 4: Duplicate Detection)
        # ========================================================================
        # Adds MinHash fingerprint columns to enable duplicate and near-duplicate detection

        # Add fingerprint column to conversations table
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self._table('conversations')} ADD COLUMN IF NOT EXISTS fingerprint BLOB"
            )

        # Add fingerprint column to reflections table
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self._table('reflections')} ADD COLUMN IF NOT EXISTS fingerprint BLOB"
            )

        # Create fingerprint index table for efficient duplicate detection
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS content_fingerprints (
                id TEXT PRIMARY KEY,
                content_type TEXT NOT NULL,
                fingerprint BLOB NOT NULL,
                content_id TEXT NOT NULL,
                collection_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(content_type, content_id, collection_name)
            )
            """
        )

        # Create indexes for fingerprint operations
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fingerprints_type ON content_fingerprints(content_type)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fingerprints_collection ON content_fingerprints(collection_name)"
        )

        # ========================================================================
        # CATEGORY EVOLUTION (Phase 5: Intelligent Subcategory Organization)
        # ========================================================================
        # Persistent storage for evolved subcategories with clustering metadata

        # Create subcategories table
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_subcategories (
                id TEXT PRIMARY KEY,
                parent_category TEXT NOT NULL,
                name TEXT NOT NULL,
                keywords TEXT[],
                centroid FLOAT[384],
                centroid_fingerprint BLOB,
                memory_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(parent_category, name)
            )
            """
        )

        # Add subcategory column to existing tables (if not exists)
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self._table('conversations')} ADD COLUMN IF NOT EXISTS subcategory TEXT"
            )

        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self._table('reflections')} ADD COLUMN IF NOT EXISTS subcategory TEXT"
            )

        # Create indexes for category operations
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subcategories_parent ON memory_subcategories(parent_category)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subcategories_count ON memory_subcategories(memory_count)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_conversations_subcategory ON {self._table('conversations')}(subcategory)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_reflections_subcategory ON {self._table('reflections')}(subcategory)"
        )

        # Add temporal tracking fields to memory_subcategories (for decay)
        with suppress(Exception):
            self.conn.execute(
                "ALTER TABLE memory_subcategories ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )
        with suppress(Exception):
            self.conn.execute(
                "ALTER TABLE memory_subcategories ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0"
            )

        # ========================================================================
        # CATEGORY EVOLUTION SNAPSHOTS (Phase 5: Temporal Decay)
        # ========================================================================
        # Tracks evolution history and quality metrics over time

        # Create evolution snapshots table
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS category_evolution_snapshots (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                before_subcategory_count INTEGER NOT NULL,
                before_silhouette REAL,
                before_total_memories INTEGER NOT NULL,
                after_subcategory_count INTEGER NOT NULL,
                after_silhouette REAL,
                after_total_memories INTEGER NOT NULL,
                decayed_count INTEGER DEFAULT 0,
                archived_count INTEGER DEFAULT 0,
                bytes_freed INTEGER DEFAULT 0,
                evolution_duration_ms REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create archived subcategories table (for decayed subcategories)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS archived_subcategories (
                id TEXT PRIMARY KEY,
                parent_category TEXT NOT NULL,
                name TEXT NOT NULL,
                keywords TEXT[],
                centroid FLOAT[384],
                centroid_fingerprint BLOB,
                memory_count INTEGER DEFAULT 0,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                last_accessed_at TIMESTAMP NOT NULL,
                access_count INTEGER DEFAULT 0,
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                archive_reason TEXT NOT NULL
            )
            """
        )

        # Create indexes for evolution tracking
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_evolution_snapshots_category ON category_evolution_snapshots(category)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_evolution_snapshots_timestamp ON category_evolution_snapshots(timestamp)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_archived_subcategories_parent ON archived_subcategories(parent_category)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_archived_subcategories_archived_at ON archived_subcategories(archived_at)"
        )

        # ========================================================================
        # USAGE ANALYTICS (Phase 5: Adaptive Results)
        # ========================================================================
        # Tracks user interactions for personalized ranking and adaptive thresholds

        # Create result interactions table
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS result_interactions (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                result_id TEXT NOT NULL,
                result_type TEXT NOT NULL,
                position INTEGER NOT NULL,
                similarity_score REAL NOT NULL,
                clicked BOOLEAN NOT NULL,
                dwell_time_ms INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT
            )
            """
        )

        # Create indexes for analytics queries
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_interactions_query ON result_interactions(query)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_interactions_result_id ON result_interactions(result_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON result_interactions(timestamp)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_interactions_clicked ON result_interactions(clicked)"
        )

        # Create aggregated usage metrics table (materialized view cache)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_metrics_summary (
                id TEXT PRIMARY KEY,
                total_interactions INTEGER DEFAULT 0,
                click_through_rate REAL DEFAULT 0.0,
                avg_dwell_time_ms REAL DEFAULT 0.0,
                avg_position_clicked REAL DEFAULT 0.0,
                type_preference JSON,
                success_threshold REAL DEFAULT 0.7,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create HNSW indexes for fast vector similarity search (requires VSS extension)
        self._create_hnsw_indexes()

    def _create_v2_schema(self) -> None:
        """Run the v2 DDL (SCHEMA_V2_SQL) against the current connection.

        Executes the multi-statement v2 SQL string. DuckDB's ``execute()`` is
        statement-atomic but accepts multi-statement strings separated by
        semicolons; we iterate to keep error messages readable and to
        continue past benign ``IF NOT EXISTS``-style no-ops.

        The v2 schema is global (not collection-scoped), so it is created
        once per database file and shared by every adapter instance.
        """
        statements = [stmt.strip() for stmt in SCHEMA_V2_SQL.split(";") if stmt.strip()]
        for stmt in statements:
            try:
                self.conn.execute(stmt)
            except Exception as e:  # noqa: BLE001 — best-effort bootstrap
                logger.debug("v2 schema statement skipped: %s", e)

    def _create_hnsw_indexes(self) -> None:
        """Create HNSW indexes for fast vector similarity search.

        HNSW (Hierarchical Navigable Small World) indexes provide O(log n) search
        performance compared to O(n) for linear scan with array_cosine_similarity.
        Requires DuckDB VSS extension to be installed and loaded.

        Falls back gracefully if VSS extension is not available.
        """
        if not self.settings.enable_hnsw_index:
            logger.debug("HNSW indexing disabled in settings")
            self._hnsw_available = False
            return

        try:
            # Try to install and load VSS extension
            self.conn.execute("INSTALL 'vss';")
            self.conn.execute("LOAD 'vss';")
            logger.info("VSS extension loaded successfully")
        except Exception as e:
            logger.warning(
                f"VSS extension not available, HNSW indexing disabled: {e}. "
                "Vector search will use array_cosine_similarity (slower)."
            )
            self._hnsw_available = False
            return

        try:
            # Enable experimental persistence for HNSW indexes on disk databases
            # HNSW indexes require this flag to work with persistent (disk-based) databases
            self.conn.execute("SET hnsw_enable_experimental_persistence=true")
            logger.debug(
                "Enabled HNSW experimental persistence for disk-based database"
            )

            # Create HNSW index for conversations table
            self.conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {self._index("conv_embeddings_hnsw")}
                ON {self._table("conversations")}
                USING HNSW (embedding)
                WITH (
                    metric = '{self.settings.distance_metric}',
                    M = {self.settings.hnsw_m},
                    ef_construction = {self.settings.hnsw_ef_construction}
                )
                """
            )
            logger.info(
                f"Created HNSW index for {self._table('conversations')} embeddings "
                f"(M={self.settings.hnsw_m}, ef_construction={self.settings.hnsw_ef_construction})"
            )

            # Create HNSW index for reflections table
            self.conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {self._index("refl_embeddings_hnsw")}
                ON {self._table("reflections")}
                USING HNSW (embedding)
                WITH (
                    metric = '{self.settings.distance_metric}',
                    M = {self.settings.hnsw_m},
                    ef_construction = {self.settings.hnsw_ef_construction}
                )
                """
            )
            logger.info(
                f"Created HNSW index for {self._table('reflections')} embeddings "
                f"(M={self.settings.hnsw_m}, ef_construction={self.settings.hnsw_ef_construction})"
            )
            self._hnsw_available = True

            # Force checkpoint so that HNSW indexes are persisted and visible
            # to other connections sharing the same database file.
            try:
                self.conn.execute("CHECKPOINT")
                logger.debug("Database checkpointed after HNSW index creation")
            except Exception as ckpt_err:
                logger.debug(f"Checkpoint after HNSW creation skipped: {ckpt_err}")

        except Exception as e:
            self._hnsw_available = False
            logger.warning(
                f"Failed to create HNSW indexes: {e}. Falling back to array_cosine_similarity."
            )

    async def _init_embedding_model(self) -> None:
        """Initialize embedding model.

        After migration to HTTP: no local model loading needed.
        HTTP providers (llama-server/Ollama) are called directly.
        Kept as no-op for backward compatibility.
        """
        pass  # HTTP embedding is stateless — no initialization needed

    async def _generate_embedding(self, text: str) -> list[float] | None:
        """Generate embedding for text via HTTP provider chain.

        Delegates to generate_embedding() from embeddings.py which calls
        llama-server → Ollama → None. HTTP providers return pre-normalized
        384d vectors, so no mean-pooling or normalization needed.

        Cache is handled by generate_embedding()'s thread-safe dict cache.
        """
        # Import here to avoid circular imports
        from session_buddy.reflection.embeddings import (
            generate_embedding as http_generate_embedding,
        )

        try:
            return await http_generate_embedding(text)
        except Exception as e:
            logger.warning(f"HTTP embedding failed: {e}")
            return None

    def _quantize_embedding(self, embedding: list[float]) -> list[int] | None:
        """Quantize embedding from float32 to uint8 for 4x memory compression.

        Uses global calibration data (min/max across all embeddings)
        to ensure consistent quantization across the dataset.

        Args:
            embedding: Float32 embedding vector (384 dimensions)

        Returns:
            Quantized embedding as uint8 values [0-255], or None if quantization disabled
        """
        if not self.settings.enable_quantization:
            return None

        # Get global calibration data
        calibration_data = self._get_calibration_data()
        if not calibration_data:
            logger.warning("Quantization enabled but no calibration data available")
            return None

        min_vals, max_vals = calibration_data

        # Convert to numpy array for efficient computation
        arr = np.array(embedding, dtype=np.float32)

        # Avoid division by zero
        range_vals = max_vals - min_vals
        range_vals = np.where(range_vals == 0, 1.0, range_vals)  # Prevent div/0

        # Scale to [0, 255] and convert to uint8
        quantized = np.clip(((arr - min_vals) / range_vals) * 255, 0, 255).astype(
            np.uint8
        )

        result: list[int] = quantized.tolist()
        return result  # [384] uint8 values

    def _dequantize_embedding(self, quantized: list[int]) -> list[float] | None:
        """Dequantize embedding from uint8 back to float32.

        Args:
            quantized: Quantized uint8 embedding vector

        Returns:
            Dequantized float32 embedding vector, or None if quantization disabled
        """
        if not self.settings.enable_quantization or not quantized:
            return None

        # Get global calibration data
        calibration_data = self._get_calibration_data()
        if not calibration_data:
            return None

        min_vals, max_vals = calibration_data

        # Convert to numpy arrays
        quantized_arr = np.array(quantized, dtype=np.uint8)
        min_vals_arr = np.array(min_vals, dtype=np.float32)
        max_vals_arr = np.array(max_vals, dtype=np.float32)

        # Calculate range
        range_vals = max_vals_arr - min_vals_arr

        # Dequantize: scale back from [0, 255] to original range
        dequantized = (
            quantized_arr.astype(np.float32) / 255.0 * range_vals + min_vals_arr
        )

        result: list[float] = dequantized.tolist()
        return result

    def _get_calibration_data(
        self,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Get global calibration data (min/max across all embeddings).

        Returns:
            Tuple of (min_values, max_values) as numpy arrays, or None if unavailable

        Note:
            This implementation uses fixed calibration data for simplicity.
            In production, you would compute this from all embeddings in the database.
        """
        if not hasattr(self, "_calibration_min"):
            # Use fixed calibration data for all-MiniLM-L6-v2 model
            # These values represent typical min/max across the embedding space
            self._calibration_min: np.ndarray = np.full((384,), -0.15, dtype=np.float32)
            self._calibration_max: np.ndarray = np.full((384,), 0.15, dtype=np.float32)

        return self._calibration_min, self._calibration_max

    def _update_calibration_data(self, all_embeddings: list[list[float]]) -> None:
        """Update calibration data from all embeddings in the database.

        Args:
            all_embeddings: List of all embedding vectors in the database
        """
        if not all_embeddings:
            return

        # Stack all embeddings and compute min/max per dimension
        stacked = np.array(all_embeddings, dtype=np.float32)  # Shape: [N, 384]

        # Compute min/max across all embeddings for each dimension
        self._calibration_min = np.min(stacked, axis=0)  # Shape: [384]
        self._calibration_max = np.max(stacked, axis=0)  # Shape: [384]

        logger.debug(f"Updated calibration data from {len(all_embeddings)} embeddings")

    def _generate_id(self, content: str) -> str:
        """Generate deterministic ID from content."""
        content_bytes = content.encode("utf-8")
        hash_obj = hashlib.sha256(content_bytes)
        return hash_obj.hexdigest()[:16]

    def _check_for_duplicates(
        self,
        fingerprint: MinHashSignature,
        content_type: t.Literal["conversation", "reflection"],
        threshold: float = 0.85,
    ) -> list[dict[str, t.Any]]:
        """Check for duplicate or near-duplicate content using MinHash similarity.

        Args:
            fingerprint: MinHash signature to compare against
            content_type: Either "conversation" or "reflection"
            threshold: Minimum Jaccard similarity to consider a duplicate (default 0.85)

        Returns:
            List of duplicate records with similarity scores

        """
        table_name = self._table(f"{content_type}s")

        # Get all fingerprints from the table
        result = self.conn.execute(
            f"""
            SELECT id, content, fingerprint FROM {table_name}
            WHERE fingerprint IS NOT NULL
            """
        ).fetchall()

        duplicates = []

        for row in result:
            existing_id = row[0]
            existing_content = row[1]
            existing_fingerprint_bytes = row[2]

            if not existing_fingerprint_bytes:
                continue

            try:
                # Reconstruct MinHash signature from bytes
                existing_fingerprint = MinHashSignature.from_bytes(
                    existing_fingerprint_bytes
                )

                # Estimate Jaccard similarity
                similarity = fingerprint.estimate_jaccard_similarity(
                    existing_fingerprint
                )

                if similarity >= threshold:
                    duplicates.append(
                        {
                            "id": existing_id,
                            "content": existing_content,
                            "similarity": similarity,
                            "content_type": content_type,
                        }
                    )
            except Exception as e:
                logger.warning(f"Error comparing fingerprints: {e}")
                continue

        # Sort by similarity (highest first)
        duplicates.sort(key=itemgetter("similarity"), reverse=True)
        return duplicates

    async def store_conversation(
        self,
        content: str,
        metadata: dict[str, t.Any] | None = None,
        deduplicate: bool = False,
        dedup_threshold: float = 0.85,
        *,
        source_type: str | None = None,
        turn_parent_id: str | None = None,
        causal_parent_id: str | None = None,
        category: str | None = None,
        memory_tier: str | None = None,
    ) -> str:
        """Store a conversation in the database.

        v2 rewire (Phase 0): writes go to ``conversations_v2`` (the global
        Memori-style table) instead of the legacy
        ``{collection}_conversations`` collection table. Content and
        metadata are redacted via :mod:`session_buddy.ingesters.redaction`
        before insertion. Provenance/lineage kwargs (``source_type``,
        ``turn_parent_id``, ``causal_parent_id``) are persisted as their
        own columns so transcript ingesters and Conscious-Agent write
        paths can reconstruct the chain.

        Args:
            content: Conversation content
            metadata: Optional metadata (allowlist-filtered on write)
            deduplicate: If True, check for duplicates before storing (Phase 4).
                Note: the duplicate check is over the v2 table — pre-v2
                duplicates are invisible.
            dedup_threshold: Minimum Jaccard similarity (0.0 to 1.0)
            source_type: Provenance tag (``claude_code`` | ``crackerjack``
                | ``mahavishnu_workflow`` | ``manual`` | ``migration``).
                Subject to the ``source_type_check`` CHECK constraint.
            turn_parent_id: ID of the parent turn in a transcript chain.
            causal_parent_id: ID of the parent that caused this memory.
            category: Memori-inspired category (``facts`` | ``preferences``
                | ``skills`` | ``rules`` | ``context`` | ``claude_turn``).
                Defaults to ``context`` for backward compatibility.
            memory_tier: Storage tier (``working`` | ``short_term`` |
                ``long_term``). Defaults to ``long_term``.

        Returns:
            Conversation ID (existing ID if duplicate found and deduplicate=True)

        """
        if not self._initialized:
            await self.initialize()

        # Redact content + metadata BEFORE any duplicate check or write so
        # secrets never reach the on-disk store. The redaction module is
        # idempotent and dependency-free.
        try:
            redacted_content = redact(content)
            redacted_metadata = redact_metadata(
                dict(metadata or {}), set(ALLOWED_METADATA_KEYS)
            )
        except RedactionSizeError:
            # Re-raise with a clearer error — 64KB+ conversation content is
            # a configuration error, not a transient one.
            msg = (
                "store_conversation rejected oversized payload "
                f"(> {65536} bytes); split the content or raise MAX_REDACTION_BYTES."
            )
            raise ValueError(msg) from None

        # Generate MinHash fingerprint for duplicate detection (Phase 4)
        fingerprint = MinHashSignature.from_text(redacted_content)

        # Check for duplicates if deduplication is enabled
        if deduplicate:
            duplicates = self._check_for_duplicates(
                fingerprint, "conversation", threshold=dedup_threshold
            )
            if duplicates:
                logger.info(
                    f"Found {len(duplicates)} duplicate(s) with similarity >= {dedup_threshold:.2f}. "
                    f"Returning existing ID: {duplicates[0]['id']}"
                )
                existing_id: str = duplicates[0]["id"]
                return existing_id  # Return ID of most similar duplicate

        conv_id = self._generate_id(redacted_content)
        if not deduplicate:
            existing_row = self.conn.execute(
                f"""
                SELECT 1
                FROM {self._table("conversations")}
                WHERE id = ?
                LIMIT 1
                """,
                [conv_id],
            ).fetchone()
            if existing_row:
                conv_id = str(ULID())
        now = datetime.now(UTC)
        metadata_json = json.dumps(redacted_metadata)
        # Extract the project from the (redacted) metadata dict; v2 has a
        # dedicated ``project`` column that callers expect to be filterable.
        project_value = (
            str(redacted_metadata["project"])
            if isinstance(redacted_metadata.get("project"), (str, int, float))
            else None
        )

        # Generate embedding if enabled
        embedding = None
        if self.settings.enable_embeddings:
            embedding = await self._generate_embedding(redacted_content)

        # Convert MinHash fingerprint to bytes for storage
        fingerprint_bytes = fingerprint.to_bytes()

        # v2 rewire: write to conversations_v2 with the new column set.
        # We keep ``fingerprint`` (DuckDB stores BLOB as BLOB) for backward
        # compatibility with the duplicate-detection path.
        self.conn.execute(
            f"""
            INSERT INTO {self._table("conversations")}
            (
                id, content, embedding, category, subcategory, importance_score,
                memory_tier, project, namespace, session_id, user_id,
                searchable_content, reasoning, metadata, source_type,
                turn_parent_id, causal_parent_id, timestamp, fingerprint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content = excluded.content,
                embedding = excluded.embedding,
                category = excluded.category,
                subcategory = excluded.subcategory,
                importance_score = excluded.importance_score,
                memory_tier = excluded.memory_tier,
                project = excluded.project,
                namespace = excluded.namespace,
                session_id = excluded.session_id,
                user_id = excluded.user_id,
                searchable_content = excluded.searchable_content,
                reasoning = excluded.reasoning,
                metadata = excluded.metadata,
                source_type = excluded.source_type,
                turn_parent_id = excluded.turn_parent_id,
                causal_parent_id = excluded.causal_parent_id,
                timestamp = excluded.timestamp,
                fingerprint = excluded.fingerprint
            """,
            [
                conv_id,
                redacted_content,
                embedding,
                category or "context",  # default category for the rewire path
                None,  # subcategory (None preserves current behavior)
                0.5,  # importance_score default
                memory_tier or "long_term",  # memory_tier default
                project_value,
                "default",  # namespace
                None,  # session_id (not threaded through in this rewire)
                "default",  # user_id
                redacted_content,  # searchable_content: keep parity with v1
                None,  # reasoning
                metadata_json,
                source_type,
                turn_parent_id,
                causal_parent_id,
                now,
                fingerprint_bytes,
            ],
        )

        # Phase 1 Feature #4: lineage / provenance. Only track writes
        # that declare a source_type — sourceless writes (tests,
        # legacy code, manual) intentionally have no provenance row.
        self._write_provenance(
            memory_id=conv_id,
            source_type=source_type,
            metadata=redacted_metadata,
        )

        return conv_id

    def _write_provenance(
        self,
        *,
        memory_id: str,
        source_type: str | None,
        metadata: dict[str, t.Any] | None,
    ) -> None:
        """Insert a ``memory_provenance`` row for a freshly written memory.

        Phase 1 Feature #4. Silently no-ops when ``source_type`` is None:
        sourceless writes (legacy callers, tests) intentionally leave
        the provenance table untouched. ``source_ref`` is taken from
        ``metadata['source_session']`` (the transcript-ingester field);
        ``model`` is taken from ``metadata['model']``. Both are
        nullable; missing keys become NULL rows.
        """
        if source_type is None:
            return
        meta = metadata or {}
        source_ref = meta.get("source_session")
        model = meta.get("model")
        self.conn.execute(
            """
            INSERT INTO memory_provenance
                (id, memory_id, source_type, source_ref, model)
            VALUES (?, ?, ?, ?, ?)
            """,
            [str(ULID()), memory_id, source_type, source_ref, model],
        )

    async def memory_lineage(self, memory_id: str) -> list[dict[str, t.Any]]:
        """Return the provenance chain for a memory, oldest-first.

        Phase 1 Feature #4. Each row in ``memory_provenance`` describes
        one extraction event (source_type + source_ref + model +
        extracted_at) for the given memory id. Most memories have a
        single row; transcripts and Conscious-Agent writes can produce
        more.
        """
        result = self.conn.execute(
            """
            SELECT id, source_type, source_ref, extracted_at, model
            FROM memory_provenance
            WHERE memory_id = ?
            ORDER BY extracted_at ASC
            """,
            [memory_id],
        )
        columns = [c[0] for c in (result.description or [])]
        return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]

    async def prune_provenance_older_than(self, *, days: int = 90) -> int:
        """Delete provenance rows older than ``days``. Returns count.

        Phase 1 Feature #4. Default 90-day retention window keeps the
        table small while preserving long-enough history to answer
        lineage questions. Pruned rows are unrecoverable; the FK
        CASCADE trigger keeps the parent table unaffected.
        """
        before_row = self.conn.execute(
            "SELECT COUNT(*) FROM memory_provenance"
        ).fetchone()
        before = int(before_row[0]) if before_row else 0
        self.conn.execute(
            """
            DELETE FROM memory_provenance
            WHERE extracted_at < CURRENT_TIMESTAMP - INTERVAL (? || ' days')
            """,
            [days],
        )
        after_row = self.conn.execute(
            "SELECT COUNT(*) FROM memory_provenance"
        ).fetchone()
        after = int(after_row[0]) if after_row else 0
        return max(0, before - after)

    async def search_conversations(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        project: str | None = None,
        min_score: float | None = None,
        use_cache: bool = True,
    ) -> list[dict[str, t.Any]]:
        """Search conversations using vector similarity.

        Args:
            query: Search query
            limit: Maximum number of results
            threshold: Minimum similarity score (0.0 to 1.0)
            project: Optional project filter (not yet implemented)
            min_score: Alias for threshold (for backward compatibility)
            use_cache: Whether to use query cache (Phase 1: Query Cache)

        Returns:
            List of matching conversations with scores

        """
        # Use min_score as threshold if provided (backward compatibility)
        if min_score is not None:
            threshold = min_score

        if not self._initialized:
            await self.initialize()

        # Phase 0c: Unconditional instrumentation. The Conscious Agent
        # analysis loop reads from ``memory_access_log`` to decide which
        # memories to promote; the write path must be active from day
        # one of the rollout so the log is populated the day the loop
        # turns on. The ``_log_access`` helper is fail-safe (never
        # raises) and does not consult any feature flag.
        self._log_access(
            memory_id=None,
            access_type="search",
            query_text=query,
        )

        # Check cache first (Phase 1: Query Cache)
        cached_results = self._get_cached_conversations(
            query=query,
            project=project,
            limit=limit,
            use_cache=use_cache,
        )
        if cached_results is not None:
            return cached_results

        # Perform search (vector or text fallback)
        results = await self._search_conversations_db(
            query=query,
            limit=limit,
            threshold=threshold,
        )

        # Populate cache for future searches (Phase 1: Query Cache)
        self._cache_conversation_results(
            query=query,
            project=project,
            limit=limit,
            results=results,
            use_cache=use_cache,
        )

        return results

    # Allowed values for ``source_type`` on ``conversations_v2``. Mirrors
    # the CHECK constraint in ``schema_v2.py``. Used by ``search_by_source``
    # to validate user input before it reaches DuckDB.
    _VALID_SOURCE_TYPES: t.Final[frozenset[str]] = frozenset(
        {
            "claude_code",
            "crackerjack",
            "mahavishnu_workflow",
            "manual",
            "migration",
        },
    )

    async def search_by_source(
        self,
        query: str,
        source_type: str | None = None,
        project: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, t.Any]]:
        """Cross-tool query: filter ``conversations_v2`` by source_type and/or project.

        Phase 1 Feature #5. The ``idx_v2_source_type_project`` covering index
        on ``(source_type, project, timestamp DESC)`` makes this an O(log n)
        range scan rather than a full table scan.

        Args:
            query: Text fragment to match in ``content`` (LIKE %query%).
            source_type: Optional provenance tag. Must be one of
                ``claude_code``, ``crackerjack``, ``mahavishnu_workflow``,
                ``manual``, ``migration`` — matching the v2 CHECK constraint.
            project: Optional project name filter.
            limit: Maximum number of rows to return.

        Returns:
            List of matching rows, most recent first. Each row contains
            ``id``, ``content``, ``metadata``, ``source_type``, ``project``,
            ``category``, ``timestamp``.

        Raises:
            ValueError: If ``source_type`` is not in the allowed set.

        """
        if source_type is not None and source_type not in self._VALID_SOURCE_TYPES:
            valid = ", ".join(sorted(self._VALID_SOURCE_TYPES))
            msg = f"Invalid source_type {source_type!r}; must be one of: {valid}"
            raise ValueError(msg)

        if not self._initialized:
            await self.initialize()

        sql = """
            SELECT id, content, metadata, source_type, project, category, timestamp
            FROM conversations_v2
            WHERE content LIKE ?
        """
        params: list[t.Any] = [f"%{query}%"]
        if source_type is not None:
            sql += " AND source_type = ?"
            params.append(source_type)
        if project is not None:
            sql += " AND project = ?"
            params.append(project)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "id": row[0],
                "content": row[1],
                "metadata": json.loads(row[2]) if row[2] else {},
                "source_type": row[3],
                "project": row[4],
                "category": row[5],
                "timestamp": row[6],
            }
            for row in rows
        ]

    def _get_cached_conversations(
        self,
        query: str,
        project: str | None,
        limit: int,
        use_cache: bool,
    ) -> list[dict[str, t.Any]] | None:
        """Retrieve cached conversation search results if available.

        Args:
            query: Search query
            project: Optional project filter
            limit: Maximum number of results
            use_cache: Whether to check cache

        Returns:
            Cached results or None if cache miss

        """
        if not (use_cache and self._query_cache):
            return None

        cache_key = QueryCacheManager.compute_cache_key(
            query=query,
            project=project,
            limit=limit,
        )
        cached_result_ids = self._query_cache.get(cache_key)

        if cached_result_ids is None:
            return None

        # Cache hit - fetch full results by IDs
        if not cached_result_ids:
            return []

        # Fetch cached results by IDs
        id_list = "', '".join(cached_result_ids)
        result = self.conn.execute(
            f"""
            SELECT id, content, metadata, created_at, updated_at
            FROM {self._table("conversations")}
            WHERE id IN ('{id_list}')
            ORDER BY updated_at DESC
            """
        ).fetchall()

        # Reconstruct cached results
        return [
            {
                "id": row[0],
                "content": row[1],
                "metadata": json.loads(row[2]) if row[2] else {},
                "created_at": row[3],
                "updated_at": row[4],
                "score": 1.0,  # Cached results don't have original scores
                "_cached": True,  # Mark as cached result
            }
            for row in result
        ]

    async def _search_conversations_db(
        self,
        query: str,
        limit: int,
        threshold: float,
    ) -> list[dict[str, t.Any]]:
        """Search conversations using vector similarity or text fallback.

        Args:
            query: Search query
            limit: Maximum number of results
            threshold: Minimum similarity score for vector search

        Returns:
            List of matching conversations with scores

        """
        # Generate query embedding
        query_embedding = None
        if self.settings.enable_embeddings:
            query_embedding = await self._generate_embedding(query)

        if query_embedding and self.settings.enable_vss:
            return self._vector_search_conversations(
                query_embedding=query_embedding,
                limit=limit,
                threshold=threshold,
            )
        return self._text_search_conversations(
            query=query,
            limit=limit,
        )

    def _vector_search_conversations(
        self,
        query_embedding: list[float],
        limit: int,
        threshold: float,
    ) -> list[dict[str, t.Any]]:
        """Perform vector similarity search on conversations.

        Args:
            query_embedding: Query vector embedding
            limit: Maximum number of results
            threshold: Minimum similarity score

        Returns:
            List of matching conversations with scores

        """
        # Set HNSW ef_search parameter if indexes exist
        if self._hnsw_available:
            self.conn.execute(f"SET hnsw_ef_search = {self.settings.hnsw_ef_search}")

        vector_query = f"[{', '.join(map(str, query_embedding))}]"
        # v2 rewire: the v2 schema has ``timestamp`` rather than
        # ``created_at``/``updated_at``. We detect the table name to choose
        # the right columns without breaking the v1 collection path.
        table = self._table("conversations")
        if table == "conversations_v2":
            result = self.conn.execute(
                f"""
                SELECT
                    id, content, metadata, timestamp,
                    array_cosine_similarity(embedding, '{vector_query}'::FLOAT[{self.embedding_dim}]) as score
                FROM {table}
                WHERE embedding IS NOT NULL
                ORDER BY score DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
            return [
                {
                    "id": row[0],
                    "content": row[1],
                    "metadata": json.loads(row[2]) if row[2] else {},
                    "created_at": row[3],
                    "updated_at": row[3],
                    "score": float(row[4]),
                }
                for row in result
                if row[4] >= threshold
            ]
        result = self.conn.execute(
            f"""
            SELECT
                id, content, metadata, created_at, updated_at,
                array_cosine_similarity(embedding, '{vector_query}'::FLOAT[{self.embedding_dim}]) as score
            FROM {table}
            WHERE embedding IS NOT NULL
            ORDER BY score DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()

        # Filter by threshold and build results
        return [
            {
                "id": row[0],
                "content": row[1],
                "metadata": json.loads(row[2]) if row[2] else {},
                "created_at": row[3],
                "updated_at": row[4],
                "score": float(row[5]),
            }
            for row in result
            if row[5] >= threshold
        ]

    def _text_search_conversations(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, t.Any]]:
        """Perform text-based search on conversations.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching conversations with scores

        """
        # v2 rewire: the v2 schema has ``timestamp`` rather than
        # ``created_at``/``updated_at``. Pick the columns that exist.
        table = self._table("conversations")
        if table == "conversations_v2":
            result = self.conn.execute(
                f"""
                SELECT id, content, metadata, timestamp
                FROM {table}
                WHERE content LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                [f"%{query}%", limit],
            ).fetchall()
            return [
                {
                    "id": row[0],
                    "content": row[1],
                    "metadata": json.loads(row[2]) if row[2] else {},
                    "created_at": row[3],
                    "updated_at": row[3],
                    "score": 1.0,  # Text search gets maximum score
                }
                for row in result
            ]
        result = self.conn.execute(
            f"""
            SELECT id, content, metadata, created_at, updated_at
            FROM {table}
            WHERE content LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            [f"%{query}%", limit],
        ).fetchall()

        return [
            {
                "id": row[0],
                "content": row[1],
                "metadata": json.loads(row[2]) if row[2] else {},
                "created_at": row[3],
                "updated_at": row[4],
                "score": 1.0,  # Text search gets maximum score
            }
            for row in result
        ]

    def _cache_conversation_results(
        self,
        query: str,
        project: str | None,
        limit: int,
        results: list[dict[str, t.Any]],
        use_cache: bool,
    ) -> None:
        """Cache conversation search results for future queries.

        Args:
            query: Search query
            project: Optional project filter
            limit: Maximum number of results
            results: Search results to cache
            use_cache: Whether to populate cache

        """
        if not (use_cache and self._query_cache and results):
            return

        cache_key = QueryCacheManager.compute_cache_key(
            query=query,
            project=project,
            limit=limit,
        )
        result_ids = [r["id"] for r in results]
        normalized_query = QueryCacheManager.normalize_query(query)

        self._query_cache.put(
            cache_key=cache_key,
            result_ids=result_ids,
            normalized_query=normalized_query,
            project=project,
        )

    async def get_stats(self) -> dict[str, t.Any]:
        """Get database statistics.

        Returns:
            Dictionary with statistics

        """
        if not self._initialized:
            await self.initialize()

        # Get conversation count
        conv_count = self.conn.execute(
            f"SELECT COUNT(*) FROM {self._table('conversations')}"
        ).fetchone()[0]

        # Get reflection count
        refl_count = self.conn.execute(
            f"SELECT COUNT(*) FROM {self._table('reflections')}"
        ).fetchone()[0]

        # Get embedding stats
        embedding_count = self.conn.execute(
            f"SELECT COUNT(*) FROM {self._table('conversations')} WHERE embedding IS NOT NULL"
        ).fetchone()[0]

        return {
            "total_conversations": conv_count,
            "total_reflections": refl_count,
            "conversations_with_embeddings": embedding_count,
            "database_path": self.db_path,
            "collection_name": self.collection_name,
        }

    async def store_reflection(
        self,
        content: str,
        tags: list[str] | None = None,
        deduplicate: bool = False,
        dedup_threshold: float = 0.85,
    ) -> str:
        """Store a reflection with optional tags.

        Args:
            content: Reflection text content
            tags: Optional list of tags for categorization
            deduplicate: If True, check for duplicates before storing (Phase 4)
            dedup_threshold: Minimum Jaccard similarity to consider a duplicate (0.0 to 1.0)

        Returns:
            Unique reflection ID (existing ID if duplicate found and deduplicate=True)

        """
        if not self._initialized:
            await self.initialize()

        if content is None:
            msg = "content cannot be None"
            raise TypeError(msg)

        if not content.strip():
            raise ValueError("content cannot be empty")

        # Generate MinHash fingerprint for duplicate detection (Phase 4)
        fingerprint = MinHashSignature.from_text(content)

        # Check for duplicates if deduplication is enabled
        if deduplicate:
            duplicates = self._check_for_duplicates(
                fingerprint, "reflection", threshold=dedup_threshold
            )
            if duplicates:
                logger.info(
                    f"Found {len(duplicates)} duplicate(s) with similarity >= {dedup_threshold:.2f}. "
                    f"Returning existing ID: {duplicates[0]['id']}"
                )
                existing_id: str = duplicates[0]["id"]
                return existing_id  # Return ID of most similar duplicate

        reflection_id = str(ULID())
        now = datetime.now(tz=UTC)

        # Generate embedding if available
        embedding: list[float] | None = None
        if self.settings.enable_embeddings:
            try:
                embedding = await self._generate_embedding(content)
            except Exception:
                embedding = None

        # Convert MinHash fingerprint to bytes for storage
        fingerprint_bytes = fingerprint.to_bytes()

        # Store reflection (explicitly set insight_type to NULL to distinguish from insights)
        # v2 rewire (Phase 0): write to ``reflections_v2`` (the global
        # Memori-style table). The INSERT now lists the v2 column set so the
        # table stores both v2 fields (category, importance_score, memory_tier,
        # tags, related_entities, project, namespace, timestamp) and the
        # legacy compatibility columns (created_at, updated_at, insight_type,
        # usage_count, last_used_at, confidence_score, fingerprint).
        if embedding:
            self.conn.execute(
                f"""
                INSERT INTO {self._table("reflections")}
                (
                    id, content, embedding, category, importance_score,
                    memory_tier, tags, related_entities, project, namespace,
                    timestamp, created_at, updated_at, insight_type,
                    usage_count, last_used_at, confidence_score, fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reflection_id,
                    content,
                    embedding,
                    "context",  # category default
                    0.5,  # importance_score default
                    "long_term",  # memory_tier default
                    tags or [],
                    None,  # related_entities (not threaded through here)
                    None,  # project (not threaded through here)
                    "default",  # namespace
                    now,  # timestamp (v2)
                    now,  # created_at (legacy)
                    now,  # updated_at (legacy)
                    None,  # insight_type (NULL to distinguish from insights)
                    0,  # usage_count
                    None,  # last_used_at
                    0.5,  # confidence_score
                    fingerprint_bytes,
                ),
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO {self._table("reflections")}
                (
                    id, content, embedding, category, importance_score,
                    memory_tier, tags, related_entities, project, namespace,
                    timestamp, created_at, updated_at, insight_type,
                    usage_count, last_used_at, confidence_score, fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reflection_id,
                    content,
                    None,  # embedding
                    "context",  # category default
                    0.5,  # importance_score default
                    "long_term",  # memory_tier default
                    tags or [],
                    None,  # related_entities
                    None,  # project
                    "default",  # namespace
                    now,  # timestamp
                    now,  # created_at
                    now,  # updated_at
                    None,  # insight_type
                    0,  # usage_count
                    None,  # last_used_at
                    0.5,  # confidence_score
                    fingerprint_bytes,
                ),
            )

        # Auto-assign subcategory if category evolution engine is available (Phase 5)
        subcategory: str | None = None
        if self._category_engine and embedding:
            memory_dict = {
                "id": reflection_id,
                "content": content,
                "embedding": embedding,
                "fingerprint": fingerprint_bytes,
            }
            assignment = await self._category_engine.assign_subcategory(memory_dict)
            if assignment.subcategory:
                subcategory = assignment.subcategory
                # Store subcategory with reflection
                self.conn.execute(
                    f"""
                    UPDATE {self._table("reflections")}
                    SET subcategory = ?
                    WHERE id = ?
                    """,
                    [subcategory, reflection_id],
                )
                logger.info(
                    f"Assigned subcategory: {subcategory} (confidence: {assignment.confidence:.2f})"
                )

        return reflection_id

    async def search_reflections(
        self,
        query: str,
        limit: int = 10,
        use_embeddings: bool = True,
        use_cache: bool = True,
    ) -> list[dict[str, t.Any]]:
        """Search reflections by content or tags.

        Args:
            query: Search query
            limit: Maximum number of results
            use_embeddings: Whether to use semantic search if embeddings available
            use_cache: Whether to use query cache (Phase 1: Query Cache)

        Returns:
            List of matching reflections

        """
        if not self._initialized:
            await self.initialize()

        # Check cache first (Phase 1: Query Cache)
        cached_results = self._get_cached_reflections(
            query=query,
            limit=limit,
            use_cache=use_cache,
        )
        if cached_results is not None:
            return cached_results

        # Perform search (cache miss or cache disabled)
        results = await self._search_reflections_db(
            query=query,
            limit=limit,
            use_embeddings=use_embeddings,
        )

        # Populate cache for future searches (Phase 1: Query Cache)
        self._cache_reflection_results(
            query=query,
            limit=limit,
            results=results,
            use_cache=use_cache,
        )

        return results

    def _get_cached_reflections(
        self,
        query: str,
        limit: int,
        use_cache: bool,
    ) -> list[dict[str, t.Any]] | None:
        """Retrieve cached reflection search results if available.

        Args:
            query: Search query
            limit: Maximum number of results
            use_cache: Whether to check cache

        Returns:
            Cached results or None if cache miss

        """
        if not (use_cache and self._query_cache):
            return None

        cache_key = QueryCacheManager.compute_cache_key(
            query=query,
            project=None,  # reflections don't have project filter
            limit=limit,
        )
        cached_result_ids = self._query_cache.get(cache_key)

        if cached_result_ids is None:
            return None

        # Cache hit - fetch full results by IDs
        if not cached_result_ids:
            return []

        # Fetch cached results by IDs
        id_list = "', '".join(cached_result_ids)
        result = self.conn.execute(
            f"""
            SELECT id, content, tags, created_at, updated_at
            FROM {self._table("reflections")}
            WHERE id IN ('{id_list}')
                AND insight_type IS NULL
            ORDER BY created_at DESC
            """
        ).fetchall()

        # Reconstruct cached results
        return [
            {
                "id": row[0],
                "content": row[1],
                "tags": list(row[2]) if row[2] else [],
                "created_at": row[3].isoformat() if row[3] else None,
                "updated_at": row[4].isoformat() if row[4] else None,
                "similarity": 1.0,  # Cached results don't have original scores
                "_cached": True,  # Mark as cached result
            }
            for row in result
        ]

    async def _search_reflections_db(
        self,
        query: str,
        limit: int,
        use_embeddings: bool,
    ) -> list[dict[str, t.Any]]:
        """Search reflections using semantic or text search.

        Args:
            query: Search query
            limit: Maximum number of results
            use_embeddings: Whether to use semantic search if available

        Returns:
            List of matching reflections

        """
        if use_embeddings and self.settings.enable_embeddings:
            return await self._semantic_search_reflections(query, limit)
        return await self._text_search_reflections(query, limit)

    def _cache_reflection_results(
        self,
        query: str,
        limit: int,
        results: list[dict[str, t.Any]],
        use_cache: bool,
    ) -> None:
        """Cache reflection search results for future queries.

        Args:
            query: Search query
            limit: Maximum number of results
            results: Search results to cache
            use_cache: Whether to populate cache

        """
        if not (use_cache and self._query_cache and results):
            return

        cache_key = QueryCacheManager.compute_cache_key(
            query=query,
            project=None,
            limit=limit,
        )
        result_ids = [r["id"] for r in results]
        normalized_query = QueryCacheManager.normalize_query(query)

        self._query_cache.put(
            cache_key=cache_key,
            result_ids=result_ids,
            normalized_query=normalized_query,
            project=None,
        )

    async def _semantic_search_reflections(
        self, query: str, limit: int = 10
    ) -> list[dict[str, t.Any]]:
        """Perform semantic search on reflections using embeddings.

        Filters for insight_type IS NULL to only return reflections, not insights.
        """
        if not self._initialized:
            await self.initialize()

        # Generate query embedding
        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return await self._text_search_reflections(query, limit)

        # Perform vector similarity search
        results = self.conn.execute(
            f"""
            SELECT id, content, tags, created_at, updated_at,
                   array_cosine_similarity(embedding::FLOAT[384], ?::FLOAT[384]) as similarity
            FROM {self._table("reflections")}
            WHERE embedding IS NOT NULL
                AND insight_type IS NULL
            ORDER BY similarity DESC
            LIMIT ?
            """,
            (query_embedding, limit),
        ).fetchall()

        return [
            {
                "id": row[0],
                "content": row[1],
                "tags": list(row[2]) if row[2] else [],
                "created_at": row[3].isoformat() if row[3] else None,
                "updated_at": row[4].isoformat() if row[4] else None,
                "similarity": row[5] or 0.0,
            }
            for row in results
        ]

    async def _text_search_reflections(
        self, query: str, limit: int = 10
    ) -> list[dict[str, t.Any]]:
        """Perform text search on reflections.

        Filters for insight_type IS NULL to only return reflections, not insights.
        """
        if not self._initialized:
            await self.initialize()

        results = self.conn.execute(
            f"""
            SELECT id, content, tags, created_at, updated_at
            FROM {self._table("reflections")}
            WHERE insight_type IS NULL
                AND (content LIKE ? OR list_contains(tags, ?))
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (f"%{query}%", query, limit),
        ).fetchall()

        return [
            {
                "id": row[0],
                "content": row[1],
                "tags": list(row[2]) if row[2] else [],
                "created_at": row[3].isoformat() if row[3] else None,
                "updated_at": row[4].isoformat() if row[4] else None,
            }
            for row in results
        ]

    async def get_reflection_by_id(self, reflection_id: str) -> dict[str, t.Any] | None:
        """Get a reflection by its ID.

        Args:
            reflection_id: Reflection ID

        Returns:
            Reflection dictionary or None if not found

        """
        if not self._initialized:
            await self.initialize()

        result = self.conn.execute(
            f"""
            SELECT id, content, tags, created_at, updated_at
            FROM {self._table("reflections")}
            WHERE id = ?
            """,
            (reflection_id,),
        ).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "content": result[1],
            "tags": list(result[2]) if result[2] else [],
            "created_at": result[3].isoformat() if result[3] else None,
            "updated_at": result[4].isoformat() if result[4] else None,
        }

    async def similarity_search(
        self, query: str, limit: int = 10
    ) -> list[dict[str, t.Any]]:
        """Perform similarity search across both conversations and reflections.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching items with type information

        """
        if not self._initialized:
            await self.initialize()

        # Search conversations
        conv_results = await self.search_conversations(query, limit)

        # Search reflections
        refl_results = await self.search_reflections(query, limit)

        # Combine and limit results
        combined = [{"type": "conversation"} | result for result in conv_results] + [
            {"type": "reflection"} | result for result in refl_results
        ]

        return combined[:limit]

    async def delete_conversation(self, memory_id: str) -> int:
        """Delete a conversation and all its child rows (app-level cascade).

        DuckDB does NOT support ``ON DELETE CASCADE`` on FOREIGN KEY
        constraints (Parser Error: FOREIGN KEY constraints cannot use
        CASCADE, SET NULL or SET DEFAULT). The v2 schema has five child
        tables that reference ``conversations_v2.id`` (directly or
        transitively); this method removes them in the right order:

        1. ``memory_access_log`` — write-heavy, free first.
        2. ``memory_provenance`` — direct FK, one row per source write.
        3. ``memory_relationships`` — 2nd-level FK to
           ``memory_entities``; must be removed BEFORE the entity rows
           it points at.
        4. ``memory_entities`` — direct FK, holds the ids that
           relationships reference.
        5. ``memory_promotions`` — direct FK.
        6. ``conversations_v2`` — the parent row.

        The cascade is conservative: instrumentation rows in
        ``memory_access_log`` are removed too. An access-log row whose
        parent memory has been deleted is a dead pointer that would
        otherwise confuse the Conscious Agent analysis loop.

        Args:
            memory_id: ULID of the conversation to delete.

        Returns:
            Number of ``conversations_v2`` rows removed (0 or 1).
            The method is idempotent: deleting a non-existent id
            returns 0 and does not raise.

        """
        if not self._initialized:
            await self.initialize()

        # DuckDB auto-commits each statement unless explicitly bracketed
        # with ``BEGIN``/``COMMIT``. We rely on per-statement commit so
        # the cascade is incremental — if any single DELETE fails the
        # earlier ones stay applied. That is acceptable for a cascade
        # because the next call to ``delete_conversation`` for the same
        # id is idempotent and re-runs the rest of the cascade.
        # 1. Free write-heavy instrumentation rows first.
        self.conn.execute(
            "DELETE FROM memory_access_log WHERE memory_id = ?",
            [memory_id],
        )

        # 2. Direct child: provenance (Phase 1 Feature #4).
        self.conn.execute(
            "DELETE FROM memory_provenance WHERE memory_id = ?",
            [memory_id],
        )

        # 3. 2nd-level: relationships reference entities. Look up
        #    the entity ids first, then remove any relationship
        #    that points at them. This must happen BEFORE the
        #    entities are deleted, otherwise we'd orphan rows.
        entity_rows = self.conn.execute(
            "SELECT id FROM memory_entities WHERE memory_id = ?",
            [memory_id],
        ).fetchall()
        entity_ids = [row[0] for row in entity_rows]
        if entity_ids:
            placeholders = ",".join("?" * len(entity_ids))
            params = entity_ids + entity_ids
            self.conn.execute(
                f"DELETE FROM memory_relationships "
                f"WHERE from_entity_id IN ({placeholders}) "
                f"OR to_entity_id IN ({placeholders})",
                params,
            )

        # 4. Direct child: entities.
        self.conn.execute(
            "DELETE FROM memory_entities WHERE memory_id = ?",
            [memory_id],
        )

        # 5. Direct child: promotions.
        self.conn.execute(
            "DELETE FROM memory_promotions WHERE memory_id = ?",
            [memory_id],
        )

        # 6. Parent row. Use before/after COUNT to compute the
        #    return value — DuckDB's Python ``execute()`` does
        #    not expose a stable ``rowcount`` attribute.
        before = self.conn.execute(
            "SELECT COUNT(*) FROM conversations_v2 WHERE id = ?",
            [memory_id],
        ).fetchone()[0]
        self.conn.execute(
            "DELETE FROM conversations_v2 WHERE id = ?",
            [memory_id],
        )
        after = self.conn.execute(
            "SELECT COUNT(*) FROM conversations_v2 WHERE id = ?",
            [memory_id],
        ).fetchone()[0]
        return int(before) - int(after)

    async def reset_database(self) -> None:
        """Reset the database by dropping and recreating tables."""
        if not self._initialized:
            await self.initialize()

        # Drop foreign key constraints first, then tables
        try:
            # Drop reflections table first (has foreign key to conversations)
            self.conn.execute(f"DROP TABLE IF EXISTS {self._table('reflections')}")
            # Then drop conversations table
            self.conn.execute(f"DROP TABLE IF EXISTS {self._table('conversations')}")
        except Exception:
            # If there are issues, try dropping with CASCADE
            self.conn.execute(
                f"DROP TABLE IF EXISTS {self._table('reflections')} CASCADE"
            )
            self.conn.execute(
                f"DROP TABLE IF EXISTS {self._table('conversations')} CASCADE"
            )

        # Recreate tables
        self._create_tables()

    async def health_check(self) -> bool:
        """Check if database is healthy.

        Returns:
            True if database is healthy, False otherwise

        """
        try:
            if not self._initialized:
                await self.initialize()
            # Simple query to test connection
            self.conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    # ========================================================================
    # INSIGHT-SPECIFIC METHODS
    # ========================================================================

    async def store_insight(
        self,
        content: str,
        insight_type: str = "general",
        topics: list[str] | None = None,
        projects: list[str] | None = None,
        source_conversation_id: str | None = None,
        source_reflection_id: str | None = None,
        confidence_score: float = 0.5,
        quality_score: float = 0.5,
    ) -> str:
        """Store an insight with embedding for semantic search.

        Args:
            content: Insight content text
            insight_type: Type of insight (general, pattern, architecture, etc.)
            topics: Optional topic tags for categorization
            projects: Optional list of project names this insight relates to
            source_conversation_id: Optional ID of conversation that generated this insight
            source_reflection_id: Optional ID of reflection that generated this insight
            confidence_score: Confidence in extraction accuracy (0.0 to 1.0)
            quality_score: Quality score of the insight (0.0 to 1.0)

        Returns:
            Unique insight ID

        """
        if not self._initialized:
            await self.initialize()

        insight_id = str(ULID())
        now = datetime.now(tz=UTC)

        # Validate insight_type
        from session_buddy.insights.models import validate_collection_name

        try:
            validate_collection_name(insight_type)
        except ValueError:
            # Default to 'general' if validation fails
            insight_type = "general"

        # Sanitize project names
        from session_buddy.insights.models import sanitize_project_name

        if projects:
            projects = [sanitize_project_name(p) for p in projects]

        # Generate embedding if available
        embedding: list[float] | None = None
        if self.settings.enable_embeddings:
            try:
                embedding = await self._generate_embedding(content)
            except Exception:
                embedding = None

        # Build metadata
        metadata = {
            "quality_score": quality_score,
            "source_conversation_id": source_conversation_id,
            "source_reflection_id": source_reflection_id,
        }

        # Store insight with or without embedding
        if embedding:
            self.conn.execute(
                f"""
                INSERT INTO {self._table("reflections")}
                (id, content, tags, metadata, embedding, created_at, updated_at,
                 insight_type, usage_count, confidence_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    insight_id,
                    content,
                    topics or [],
                    json.dumps(metadata),
                    embedding,
                    now,
                    now,
                    insight_type,
                    0,  # usage_count starts at 0
                    confidence_score,
                ),
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO {self._table("reflections")}
                (id, content, tags, metadata, created_at, updated_at,
                 insight_type, usage_count, confidence_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    insight_id,
                    content,
                    topics or [],
                    json.dumps(metadata),
                    now,
                    now,
                    insight_type,
                    0,  # usage_count starts at 0
                    confidence_score,
                ),
            )

        return insight_id

    async def search_insights(
        self,
        query: str,
        limit: int = 10,
        min_quality_score: float = 0.0,
        min_similarity: float = 0.0,
        use_embeddings: bool = True,
    ) -> list[dict[str, t.Any]]:
        """Search insights with pre-filtering by quality and similarity.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            min_quality_score: Minimum quality score threshold (0.0 to 1.0)
            min_similarity: Minimum semantic similarity threshold (0.0 to 1.0)
            use_embeddings: Whether to use semantic search if available

        Returns:
            List of matching insights with metadata

        """
        if not self._initialized:
            await self.initialize()

        # Use semantic search if embeddings available
        if use_embeddings and self.settings.enable_embeddings:
            return await self._semantic_search_insights(
                query, limit, min_quality_score, min_similarity
            )

        # Fall back to text search
        return await self._text_search_insights(query, limit, min_quality_score)

    async def _semantic_search_insights(
        self,
        query: str,
        limit: int,
        min_quality_score: float,
        min_similarity: float,
    ) -> list[dict[str, t.Any]]:
        """Perform semantic search on insights using embeddings.

        Filters for insight_type IS NOT NULL to only return insights, not reflections.
        Special handling: '*' and '' fall back to text search to return all insights.
        """
        if not self._initialized:
            await self.initialize()

        # Wildcard search - fall back to text search which handles '*' properly
        if query in {"*", ""}:
            return await self._text_search_insights(query, limit, min_quality_score)

        # Generate query embedding
        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return await self._text_search_insights(query, limit, min_quality_score)

        # Perform vector similarity search with quality filter
        # Cast embedding to match query_embedding type for array_cosine_similarity
        results = self.conn.execute(
            f"""
            SELECT
                id, content, tags, metadata, created_at, updated_at,
                insight_type, usage_count, last_used_at, confidence_score,
                array_cosine_similarity(embedding::FLOAT[384], ?::FLOAT[384]) as similarity
            FROM {self._table("reflections")}
            WHERE
                embedding IS NOT NULL
                AND insight_type IS NOT NULL
                AND json_extract(metadata, '$.quality_score') >= ?
            ORDER BY similarity DESC, created_at DESC
            LIMIT ?
            """,
            (query_embedding, min_quality_score, limit * 2),  # Get extra for filtering
        ).fetchall()

        # Filter by similarity and format results
        formatted_results = []
        for row in results:
            similarity = row[10] or 0.0
            if similarity < min_similarity:
                continue

            # Parse metadata
            metadata = {}
            with suppress(Exception):
                if row[3]:
                    metadata = json.loads(row[3])

            formatted_results.append(
                {
                    "id": row[0],
                    "content": row[1],
                    "tags": list(row[2]) if row[2] else [],
                    "metadata": metadata,
                    "created_at": row[4].isoformat() if row[4] else None,
                    "updated_at": row[5].isoformat() if row[5] else None,
                    "insight_type": row[6],
                    "usage_count": row[7] or 0,
                    "last_used_at": row[8].isoformat() if row[8] else None,
                    "confidence_score": row[9] or 0.5,
                    "similarity": similarity,
                }
            )

        # Limit results after filtering
        return formatted_results[:limit]

    async def _text_search_insights(
        self,
        query: str,
        limit: int,
        min_quality_score: float,
    ) -> list[dict[str, t.Any]]:
        """Perform text search on insights (fallback when embeddings unavailable).

        Filters for insight_type IS NOT NULL to only return insights, not reflections.
        Special handling: '*' matches all insights (wildcard search).
        """
        if not self._initialized:
            await self.initialize()

        # Special handling for wildcard - return all insights
        if query in {"*", ""}:
            results = self.conn.execute(
                f"""
                SELECT
                    id, content, tags, metadata, created_at, updated_at,
                    insight_type, usage_count, last_used_at, confidence_score
                FROM {self._table("reflections")}
                WHERE
                    insight_type IS NOT NULL
                    AND json_extract(metadata, '$.quality_score') >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (min_quality_score, limit),
            ).fetchall()
        else:
            results = self.conn.execute(
                f"""
                SELECT
                    id, content, tags, metadata, created_at, updated_at,
                    insight_type, usage_count, last_used_at, confidence_score
                FROM {self._table("reflections")}
                WHERE
                    insight_type IS NOT NULL
                    AND (content LIKE ? OR list_contains(tags, ?))
                    AND json_extract(metadata, '$.quality_score') >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (f"%{query}%", query, min_quality_score, limit),
            ).fetchall()

        formatted_results = []
        for row in results:
            # Parse metadata
            metadata = {}
            with suppress(Exception):
                if row[3]:
                    metadata = json.loads(row[3])

            formatted_results.append(
                {
                    "id": row[0],
                    "content": row[1],
                    "tags": list(row[2]) if row[2] else [],
                    "metadata": metadata,
                    "created_at": row[4].isoformat() if row[4] else None,
                    "updated_at": row[5].isoformat() if row[5] else None,
                    "insight_type": row[6],
                    "usage_count": row[7] or 0,
                    "last_used_at": row[8].isoformat() if row[8] else None,
                    "confidence_score": row[9] or 0.5,
                    "similarity": None,  # No similarity score in text search
                }
            )

        return formatted_results

    async def update_insight_usage(self, insight_id: str) -> bool:
        """Atomically increment the usage count for an insight.

        This fixes the race condition vulnerability identified in security review.
        Uses atomic UPDATE to prevent concurrent updates from losing data.

        Args:
            insight_id: ID of the insight to update

        Returns:
            True if update succeeded, False otherwise

        """
        if not self._initialized:
            await self.initialize()

        try:
            # Check if insight exists first
            check_result = self.conn.execute(
                f"""
                SELECT COUNT(*) FROM {self._table("reflections")}
                WHERE id = ? AND insight_type IS NOT NULL
                """,
                (insight_id,),
            ).fetchone()

            if not check_result or check_result[0] == 0:
                return False

            # Atomic increment prevents race condition
            self.conn.execute(
                f"""
                UPDATE {self._table("reflections")}
                SET
                    usage_count = usage_count + 1,
                    last_used_at = ?,
                    updated_at = ?
                WHERE id = ? AND insight_type IS NOT NULL
                """,
                (datetime.now(tz=UTC), datetime.now(tz=UTC), insight_id),
            )
            return True
        except Exception:
            return False

    async def get_insights_statistics(self) -> dict[str, t.Any]:
        """Get aggregate statistics about stored insights.

        Returns:
            Dictionary with insight statistics:
            - total: Total number of insights
            - avg_quality: Average quality score
            - avg_usage: Average usage count
            - by_type: Count of insights by type
            - top_projects: Most common project associations

        """
        if not self._initialized:
            await self.initialize()

        # Total insights count
        total_result = self.conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {self._table("reflections")}
            WHERE insight_type IS NOT NULL
            """
        ).fetchone()
        total = total_result[0] if total_result else 0

        # Average quality score
        quality_result = self.conn.execute(
            f"""
            SELECT AVG(CAST(json_extract(metadata, '$.quality_score') AS REAL))
            FROM {self._table("reflections")}
            WHERE
                insight_type IS NOT NULL
                AND json_extract(metadata, '$.quality_score') IS NOT NULL
            """
        ).fetchone()
        avg_quality = quality_result[0] if quality_result and quality_result[0] else 0.0

        # Average usage count
        usage_result = self.conn.execute(
            f"""
            SELECT AVG(usage_count)
            FROM {self._table("reflections")}
            WHERE insight_type IS NOT NULL
            """
        ).fetchone()
        avg_usage = usage_result[0] if usage_result and usage_result[0] else 0.0

        # Count by insight type
        type_results = self.conn.execute(
            f"""
            SELECT insight_type, COUNT(*) as count
            FROM {self._table("reflections")}
            WHERE insight_type IS NOT NULL
            GROUP BY insight_type
            ORDER BY count DESC
            """
        ).fetchall()
        by_type = {row[0]: row[1] for row in type_results}

        return {
            "total": total,
            "avg_quality": round(avg_quality, 3),
            "avg_usage": round(avg_usage, 2),
            "by_type": by_type,
        }

    async def generate_session_differential(
        self,
        session_id: str,
        window_hours: int = 24,
    ) -> dict[str, t.Any]:
        """Generate a 'session learning report' for the given session_id.

        Pure read over v2 tables; no new writes. The differential summarizes
        what memories were created, reinforced, contradicted, or had new
        causal links attributed to this session within the time window.

        Args:
            session_id: Session identifier to scope the report.
            window_hours: How far back to look (default 24 hours).

        Returns:
            Dictionary with keys:
            - session_id: Echo of the input.
            - window_hours: Echo of the input.
            - new_memory_count: Count of new memories in the window.
            - new_memories: Row dicts for those memories.
            - reinforced_memories: ``[{memory_id, access_count}, ...]``
              for memories accessed more than once in the window.
            - contradictions: ``[]`` (placeholder; NLP detection is out of
              scope for v1).
            - new_causal_links: ``[]`` (placeholder; will be wired up in
              Phase 2 Feature #3).
            - generated_at: ISO-8601 UTC timestamp of report generation.
        """
        if not self._initialized:
            await self.initialize()

        # New memories: rows in conversations_v2 with matching session_id
        # and timestamp inside the window.
        new_memories_result = self.conn.execute(
            """
            SELECT id, content, category, subcategory, project, namespace,
                   timestamp, session_id, importance_score
            FROM conversations_v2
            WHERE session_id = ?
              AND timestamp > now() - INTERVAL '1 hour' * ?
            ORDER BY timestamp DESC
            """,
            [session_id, window_hours],
        )
        new_memories_columns = [c[0] for c in (new_memories_result.description or [])]
        new_memories_rows = new_memories_result.fetchall()
        new_memories: list[dict[str, t.Any]] = [
            dict(zip(new_memories_columns, row, strict=False))
            for row in new_memories_rows
        ]
        new_memory_ids = [row["id"] for row in new_memories]

        # Reinforced: memories in this session whose id appears in
        # memory_access_log more than once during the window. We build
        # a comma-separated IN-list to avoid DuckDB's bind semantics
        # for ``ANY(?)`` lists.
        reinforced: list[dict[str, t.Any]] = []
        if new_memory_ids:
            placeholders = ",".join(["?"] * len(new_memory_ids))
            reinforced_rows = self.conn.execute(
                f"""
                SELECT memory_id, COUNT(*) AS access_count
                FROM memory_access_log
                WHERE memory_id IN ({placeholders})
                  AND timestamp > now() - INTERVAL '1 hour' * ?
                GROUP BY memory_id
                HAVING COUNT(*) > 1
                """,
                [*new_memory_ids, window_hours],
            ).fetchall()
            reinforced = [
                {"memory_id": row[0], "access_count": int(row[1])}
                for row in reinforced_rows
            ]

        # Contradictions: NLP-based detection is out of scope for v1.
        contradictions: list[dict[str, t.Any]] = []
        # New causal links: wired up in Phase 2 Feature #3.
        new_causal_links: list[dict[str, t.Any]] = []

        return {
            "session_id": session_id,
            "window_hours": window_hours,
            "new_memory_count": len(new_memory_ids),
            "new_memories": new_memories,
            "reinforced_memories": reinforced,
            "contradictions": contradictions,
            "new_causal_links": new_causal_links,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    # ========================================================================
    # Per-project peer modeling (Phase 1.5 Feature #2: Honcho)
    # ========================================================================
    # ACL: the adapter exposes data-layer methods without permission
    # checks. Tool/agent callers MUST verify ``peer_models:read`` before
    # calling ``get_peer_model`` / ``peer_context`` and ``peer_models:write``
    # before calling ``update_peer_model``. A global user model would
    # leak preferences across projects — the composite
    # ``PRIMARY KEY (peer_id, project_id)`` in ``user_models`` enforces
    # per-project scoping at the schema level. See
    # ``session_buddy.memory.peer_modeling`` for the full ACL contract.

    async def get_peer_model(
        self, peer_id: str, project_id: str
    ) -> dict[str, t.Any] | None:
        """Return the row for ``(peer_id, project_id)`` or None.

        Phase 1.5 #2. Read miss returns None; the row is NOT created
        on read. Use :meth:`update_peer_model` to create a row.
        """
        if not self._initialized:
            await self.initialize()
        return get_peer_model(self.conn, peer_id=peer_id, project_id=project_id)

    async def update_peer_model(
        self,
        peer_id: str,
        project_id: str,
        *,
        representation_text: str | None = None,
        model: str = "heuristic",
    ) -> str:
        """Insert or update the peer model for ``(peer_id, project_id)``.

        Phase 1.5 #2. On the first call for a peer, this synthesizes a
        representation from the peer's recent memories in this project
        (heuristic; no LLM cost). On subsequent calls, the
        ``evidence_count`` is incremented and the ``representation_text``
        is refreshed (heuristically, or from the caller's
        ``representation_text`` arg when the Conscious Agent runs an
        LLM-driven synthesis).

        The composite ``PRIMARY KEY (peer_id, project_id)`` makes the
        upsert race-safe via DuckDB's ``ON CONFLICT`` clause — two
        workers updating the same peer is last-writer-wins on the row,
        which is acceptable because both writers produce equivalent
        representations from the same evidence.

        Returns:
            The ``representation_text`` that was stored.
        """
        if not self._initialized:
            await self.initialize()
        return upsert_peer_model(
            self.conn,
            peer_id=peer_id,
            project_id=project_id,
            representation_text=representation_text,
            model=model,
        )

    async def peer_context(
        self,
        peer_id: str,
        project_id: str,
        *,
        recent_limit: int = 5,
        target_peer_id: str | None = None,
    ) -> dict[str, t.Any]:
        """Bundle a peer's representation + recent memories into one dict.

        Phase 1.5 #2. When ``target_peer_id`` is set, the response also
        includes a ``target_peer`` field with that peer's model
        (useful for agent-vs-user theory of mind).

        Returns a dict with keys: ``peer_id``, ``project_id``,
        ``representation_text``, ``last_updated``, ``evidence_count``,
        ``model``, ``recent_memories``, ``target_peer``.
        """
        if not self._initialized:
            await self.initialize()
        return build_peer_context(
            self.conn,
            peer_id=peer_id,
            project_id=project_id,
            recent_limit=recent_limit,
            target_peer_id=target_peer_id,
        )

    # ========================================================================
    # Causal Memory Chains (Phase 1.5 Feature #3)
    # ========================================================================
    # The causal graph is a directed, weighted, ``link_origin``-tagged
    # network of "A caused B" relationships between memory rows. Two
    # flavors: ``observed`` (ground truth from a transcript
    # ``parentUuid`` chain, manual note, or a tool that asserts
    # "A caused B") and ``inferred`` (heuristic guess from same-
    # project co-occurrence + category overlap + time decay). Per
    # the plan, inference is LLM-free — pure DuckDB queries.
    #
    # See ``session_buddy.memory.causal`` for the heuristic and
    # the evidence-weight formula.

    async def record_observed_link(
        self,
        from_id: str,
        to_id: str,
        link_type: str,
        evidence: float,
    ) -> str:
        """Record an observed causal link from ``from_id`` to ``to_id``.

        Phase 1.5 #3. Self-links (``from_id == to_id``) are rejected
        with ``ValueError``. Calling with the same ``(from_id, to_id)``
        pair upserts (same ULID), bumping ``last_evidence_at`` and
        updating ``evidence``.

        Returns the link's id (a fresh ULID on insert; same id on
        upsert).
        """
        if not self._initialized:
            await self.initialize()
        return _record_observed_link(
            self.conn,
            from_id=from_id,
            to_id=to_id,
            link_type=link_type,
            evidence=evidence,
        )

    async def infer_causal_links_for(
        self,
        memory_id: str,
        *,
        lookback_limit: int = 20,
    ) -> list[dict[str, t.Any]]:
        """Infer causal links FROM prior memories TO ``memory_id``.

        Phase 1.5 #3. LLM-free heuristic: looks at the last
        ``lookback_limit`` same-project memories with
        ``timestamp < memory_id.timestamp``, computes an evidence
        weight from category overlap and time decay, and persists
        any link with ``evidence > 0.5`` as ``link_origin='inferred'``.

        Returns the list of newly inferred links.
        """
        if not self._initialized:
            await self.initialize()
        return _infer_causal_links_for(
            self.conn,
            memory_id=memory_id,
            lookback_limit=lookback_limit,
        )

    async def causal_chain(
        self,
        start_id: str,
        *,
        max_depth: int = 3,
    ) -> list[dict[str, t.Any]]:
        """BFS-walk the causal graph from ``start_id`` up to ``max_depth``.

        Phase 1.5 #3. Cycle-safe via a visited set keyed on the
        destination ``to_id``. Returns a list of walked edges, each
        with ``from_id``, ``to_id``, ``link_type``, ``evidence``,
        ``link_origin``, ``depth`` (hop count from ``start_id``).
        An isolated start returns ``[]``.
        """
        if not self._initialized:
            await self.initialize()
        return _walk_causal_chain(self.conn, start_id=start_id, max_depth=max_depth)

    async def prune_causal_links_older_than(self, *, days: int = 90) -> int:
        """Delete causal links stale for ``days``. Returns count.

        Phase 1.5 #3. The Conscious Agent calls this as a periodic
        cleanup. ``record_observed_link`` bumps ``last_evidence_at``
        so reused links survive another full window.
        """
        if not self._initialized:
            await self.initialize()
        return _prune_causal_links_older_than(self.conn, days=days)

    # ========================================================================
    # Skill Distillation (Phase 1.5 Feature #6)
    # ========================================================================
    # A "skill" is a learnable pattern extracted from observed session
    # activity: "for problems like X, try Y because Z worked in N prior
    # cases." The data layer is LLM-optional; the LLM path (Conscious
    # Agent) is an enhancement, not a dependency. Per the plan's LLM
    # Cost Ceiling: 100 calls/week cap, $Y/week (TBD with ops).
    #
    # See ``session_buddy.skills.distiller`` for the heuristic.

    async def distill_skills_now(
        self,
        *,
        evidence_threshold: int = _DEFAULT_EVIDENCE_THRESHOLD,
        model: str = _HEURISTIC_MODEL,
    ) -> list[dict[str, t.Any]]:
        """Distill skills from current session activity.

        Phase 1.5 #6. The first 10 distilled skills are sampled for
        human review (per the plan's quality gate). The function
        is idempotent on the same data — a re-run produces
        duplicate rows. The Conscious Agent is responsible for
        scheduling cadence and dedup.

        The importance floor (>= 0.7) is enforced by the CHECK
        constraint; the application filter is the first line of
        defense, the constraint is the second.
        """
        if not self._initialized:
            await self.initialize()
        return _distill_skills(
            self.conn,
            evidence_threshold=evidence_threshold,
            model=model,
        )

    async def search_distilled_skills(
        self,
        *,
        query: str = "",
        limit: int = 5,
    ) -> list[dict[str, t.Any]]:
        """Search distilled skills by problem_pattern / approach / because.

        Phase 1.5 #6. An empty ``query`` returns the top ``limit``
        skills by ``importance_score DESC, last_reinforced_at DESC``.
        A non-empty ``query`` does a case-insensitive substring
        match across the three text fields.

        LLM-based semantic search is a future Conscious Agent
        enhancement; the data layer is a thin LIKE wrapper.
        """
        if not self._initialized:
            await self.initialize()
        return _search_distilled_skills(self.conn, query=query, limit=limit)

    async def reinforce_skill(self, *, skill_id: str) -> bool:
        """Bump ``evidence_count`` + ``last_reinforced_at`` for a skill.

        Phase 1.5 #6. Returns ``True`` if the row existed and was
        updated, ``False`` if no row matched (idempotent no-op
        for unknown ids).
        """
        if not self._initialized:
            await self.initialize()
        return _reinforce_skill(self.conn, skill_id=skill_id)


# Alias for backward compatibility
ReflectionDatabase = ReflectionDatabaseAdapterOneiric


__all__ = [
    "ReflectionDatabase",
    "ReflectionDatabaseAdapterOneiric",
]
