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
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

if t.TYPE_CHECKING:
    from types import TracebackType

    import duckdb
    import numpy as np
    from onnxruntime import InferenceSession
    from transformers import AutoTokenizer

# Runtime imports (available at runtime but optional for type checking)
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# Embedding system imports
try:
    import onnxruntime as ort
    from transformers import AutoTokenizer

    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    ort = None  # type: ignore[no-redef]
    AutoTokenizer = None  # type: ignore[no-redef]

from session_buddy.adapters.settings import ReflectionAdapterSettings
from session_buddy.insights.models import validate_collection_name

logger = logging.getLogger(__name__)


# DuckDB will be imported at runtime
DUCKDB_AVAILABLE = True
try:
    import duckdb
except ImportError:
    DUCKDB_AVAILABLE = False
    if t.TYPE_CHECKING:
        # Type stub for type checking when duckdb is not installed
        import types

        duckdb = types.SimpleNamespace()  # type: ignore[misc,assignment]


class ReflectionDatabaseAdapterOneiric:
    """Manages conversation memory and reflection using native DuckDB vector operations.

    This adapter replaces ACB's Vector adapter with direct DuckDB operations while maintaining
    the original ReflectionDatabase API for backward compatibility. It handles:
    - Local ONNX embedding generation (all-MiniLM-L6-v2, 384 dimensions)
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
    ) -> None:
        """Initialize adapter with optional collection name.

        Args:
            collection_name: Name of the vector collection to use.
                           Default "default" collection will be created automatically.
            settings: Reflection adapter settings. If None, uses defaults.

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
        self.db_path = str(self.settings.database_path)
        self.conn: t.Any = None  # DuckDB connection (sync)
        self.onnx_session: InferenceSession | None = None
        self.tokenizer: t.Any = None
        self.embedding_dim = self.settings.embedding_dim  # all-MiniLM-L6-v2 dimension
        self._initialized = False

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
        if self.conn:
            with suppress(Exception):
                self.conn.close()
            self.conn = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize DuckDB connection and create tables if needed."""
        if self._initialized:
            return

        if not DUCKDB_AVAILABLE:
            msg = "DuckDB not available. Install with: uv add duckdb"
            raise ImportError(msg)

        # Create database directory if it doesn't exist
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Connect to DuckDB database
        self.conn = duckdb.connect(database=self.db_path, read_only=False)

        # Enable vector extension if available
        with suppress(Exception):
            self.conn.execute("INSTALL 'httpfs';")
            self.conn.execute("LOAD 'httpfs';")

        # Create tables if they don't exist
        self._create_tables()

        # Initialize ONNX embedding model if embeddings are enabled
        if self.settings.enable_embeddings and ONNX_AVAILABLE:
            await self._init_embedding_model()

        self._initialized = True

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        # Create conversations table
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.collection_name}_conversations (
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
            CREATE TABLE IF NOT EXISTS {self.collection_name}_reflections (
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

                FOREIGN KEY (conversation_id) REFERENCES {self.collection_name}_conversations(id)
            )
            """
        )

        # Create indices for faster search
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.collection_name}_conv_created ON {self.collection_name}_conversations(created_at)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.collection_name}_refl_created ON {self.collection_name}_reflections(created_at)"
        )

        # ========================================================================
        # MIGRATION: Add insight columns to existing reflections tables
        # ========================================================================
        # This migration ensures existing databases get the new insight columns
        # We use ALTER TABLE IF NOT EXISTS pattern (DuckDB-safe)

        # Add insight_type column if it doesn't exist
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self.collection_name}_reflections ADD COLUMN IF NOT EXISTS insight_type VARCHAR DEFAULT 'general'"
            )

        # Add usage_count column if it doesn't exist
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self.collection_name}_reflections ADD COLUMN IF NOT EXISTS usage_count INTEGER DEFAULT 0"
            )

        # Add last_used_at column if it doesn't exist
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self.collection_name}_reflections ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP"
            )

        # Add confidence_score column if it doesn't exist
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self.collection_name}_reflections ADD COLUMN IF NOT EXISTS confidence_score REAL DEFAULT 0.5"
            )

        # Create insight-specific indexes for performance
        # Note: DuckDB doesn't support partial indexes (WHERE clauses), so we create full indexes
        # and filter at query time instead. Also can't index array types (VARCHAR[])
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.collection_name}_refl_insight_type ON {self.collection_name}_reflections(insight_type)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.collection_name}_refl_usage_count ON {self.collection_name}_reflections(usage_count)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.collection_name}_refl_last_used ON {self.collection_name}_reflections(last_used_at)"
        )

    async def _init_embedding_model(self) -> None:
        """Initialize ONNX embedding model."""
        if not ONNX_AVAILABLE:
            return

        assert AutoTokenizer is not None
        assert ort is not None

        # Use Xenova's pre-converted ONNX model (no PyTorch required)
        model_name = "Xenova/all-MiniLM-L6-v2"

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

        # Load ONNX model from onnx/ subdirectory
        try:
            from huggingface_hub import snapshot_download

            # Get the actual cache directory for this model
            cache_dir = snapshot_download(
                repo_id=model_name, allow_patterns=["onnx/model.onnx"]
            )
            onnx_path = str(Path(cache_dir) / "onnx" / "model.onnx")

            self.onnx_session = ort.InferenceSession(
                onnx_path,
                providers=["CPUExecutionProvider"],
            )
            logger.info("✅ ONNX model loaded successfully (Xenova/all-MiniLM-L6-v2)")
        except Exception as e:
            logger.warning(f"Failed to load ONNX model from {model_name}: {e}")
            self.onnx_session = None

    async def _generate_embedding(self, text: str) -> list[float] | None:
        """Generate embedding for text using ONNX model."""
        if not self.onnx_session or not self.tokenizer:
            return None

        try:
            # Tokenize input (use NumPy to avoid PyTorch dependency)
            inputs = self.tokenizer(
                text,
                return_tensors="np",
                padding=True,
                truncation=True,
                max_length=256,
            )

            # Get numpy arrays directly (no conversion needed)
            input_ids = inputs["input_ids"]
            attention_mask = inputs["attention_mask"]
            token_type_ids = inputs.get("token_type_ids", None)

            # Run inference
            ort_inputs = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
            if token_type_ids is not None:
                ort_inputs["token_type_ids"] = token_type_ids

            # Get embeddings (shape: [batch, seq_len, 384])
            outputs = self.onnx_session.run(None, ort_inputs)
            last_hidden_state = outputs[0]  # Shape: [1, seq_len, 384]

            # Apply mean pooling to get sentence embedding
            # Expand attention_mask to match embedding dimensions
            input_mask_expanded = np.expand_dims(
                attention_mask, axis=-1
            )  # [1, seq_len, 1]
            input_mask_expanded = np.broadcast_to(
                input_mask_expanded, last_hidden_state.shape
            )

            # Weighted sum of embeddings (masked tokens have 0 weight)
            sum_embeddings = np.sum(
                last_hidden_state * input_mask_expanded, axis=1
            )  # [1, 384]

            # Sum of mask (number of real tokens, not padding)
            sum_mask = np.maximum(np.sum(input_mask_expanded, axis=1), 1e-9)  # [1, 384]

            # Mean pooling
            mean_pooled = sum_embeddings / sum_mask  # [1, 384]

            # Normalize to unit length
            embeddings = mean_pooled / np.linalg.norm(
                mean_pooled, axis=1, keepdims=True
            )

            # Return [384] as list
            result = embeddings[0].tolist()
            return t.cast("list[float]", result)
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
            return None

    def _generate_id(self, content: str) -> str:
        """Generate deterministic ID from content."""
        content_bytes = content.encode("utf-8")
        hash_obj = hashlib.sha256(content_bytes)
        return hash_obj.hexdigest()[:16]

    async def store_conversation(
        self, content: str, metadata: dict[str, t.Any] | None = None
    ) -> str:
        """Store a conversation in the database.

        Args:
            content: Conversation content
            metadata: Optional metadata

        Returns:
            Conversation ID

        """
        if not self._initialized:
            await self.initialize()

        conv_id = self._generate_id(content)
        now = datetime.now(UTC)
        metadata_json = json.dumps(metadata or {})

        # Generate embedding if enabled
        embedding = None
        if self.settings.enable_embeddings:
            embedding = await self._generate_embedding(content)

        # Store conversation
        if embedding:
            self.conn.execute(
                f"""
                INSERT INTO {self.collection_name}_conversations
                (id, content, metadata, created_at, updated_at, embedding)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at,
                    embedding = excluded.embedding
                """,
                [
                    conv_id,
                    content,
                    metadata_json,
                    now,
                    now,
                    embedding,
                ],
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO {self.collection_name}_conversations
                (id, content, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                [conv_id, content, metadata_json, now, now],
            )

        return conv_id

    async def search_conversations(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        project: str | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, t.Any]]:
        """Search conversations using vector similarity.

        Args:
            query: Search query
            limit: Maximum number of results
            threshold: Minimum similarity score (0.0 to 1.0)
            project: Optional project filter (not yet implemented)
            min_score: Alias for threshold (for backward compatibility)

        Returns:
            List of matching conversations with scores

        """
        # Use min_score as threshold if provided (backward compatibility)
        if min_score is not None:
            threshold = min_score
        if not self._initialized:
            await self.initialize()

        results = []

        # Generate query embedding
        query_embedding = None
        if self.settings.enable_embeddings:
            query_embedding = await self._generate_embedding(query)

        if query_embedding and self.settings.enable_vss:
            # Vector similarity search using DuckDB's array_cosine_similarity
            vector_query = f"[{', '.join(map(str, query_embedding))}]"
            result = self.conn.execute(
                f"""
                SELECT
                    id, content, metadata, created_at, updated_at,
                    array_cosine_similarity(embedding, '{vector_query}'::FLOAT[{self.embedding_dim}]) as score
                FROM {self.collection_name}_conversations
                WHERE embedding IS NOT NULL
                ORDER BY score DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()

            for row in result:
                if row[5] >= threshold:  # score column
                    results.append(
                        {
                            "id": row[0],
                            "content": row[1],
                            "metadata": json.loads(row[2]) if row[2] else {},
                            "created_at": row[3],
                            "updated_at": row[4],
                            "score": float(row[5]),
                        }
                    )
        else:
            # Fallback to text search
            result = self.conn.execute(
                f"""
                SELECT id, content, metadata, created_at, updated_at
                FROM {self.collection_name}_conversations
                WHERE content LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                [f"%{query}%", limit],
            ).fetchall()

            for row in result:
                results.append(
                    {
                        "id": row[0],
                        "content": row[1],
                        "metadata": json.loads(row[2]) if row[2] else {},
                        "created_at": row[3],
                        "updated_at": row[4],
                        "score": 1.0,  # Text search gets maximum score
                    }
                )

        return results

    async def get_stats(self) -> dict[str, t.Any]:
        """Get database statistics.

        Returns:
            Dictionary with statistics

        """
        if not self._initialized:
            await self.initialize()

        # Get conversation count
        conv_count = self.conn.execute(
            f"SELECT COUNT(*) FROM {self.collection_name}_conversations"
        ).fetchone()[0]

        # Get reflection count
        refl_count = self.conn.execute(
            f"SELECT COUNT(*) FROM {self.collection_name}_reflections"
        ).fetchone()[0]

        # Get embedding stats
        embedding_count = self.conn.execute(
            f"SELECT COUNT(*) FROM {self.collection_name}_conversations WHERE embedding IS NOT NULL"
        ).fetchone()[0]

        return {
            "total_conversations": conv_count,
            "total_reflections": refl_count,
            "conversations_with_embeddings": embedding_count,
            "database_path": self.db_path,
            "collection_name": self.collection_name,
        }

    async def store_reflection(
        self, content: str, tags: list[str] | None = None
    ) -> str:
        """Store a reflection with optional tags.

        Args:
            content: Reflection text content
            tags: Optional list of tags for categorization

        Returns:
            Unique reflection ID

        """
        if not self._initialized:
            await self.initialize()

        reflection_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)

        # Generate embedding if available
        embedding: list[float] | None = None
        if ONNX_AVAILABLE and self.onnx_session:
            try:
                embedding = await self._generate_embedding(content)
            except Exception:
                embedding = None

        # Store reflection (explicitly set insight_type to NULL to distinguish from insights)
        if embedding:
            self.conn.execute(
                f"""
                INSERT INTO {self.collection_name}_reflections
                (id, content, tags, embedding, created_at, updated_at, insight_type)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    reflection_id,
                    content,
                    tags or [],
                    embedding,
                    now,
                    now,
                ),
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO {self.collection_name}_reflections
                (id, content, tags, created_at, updated_at, insight_type)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    reflection_id,
                    content,
                    tags or [],
                    now,
                    now,
                ),
            )

        return reflection_id

    async def search_reflections(
        self, query: str, limit: int = 10, use_embeddings: bool = True
    ) -> list[dict[str, t.Any]]:
        """Search reflections by content or tags.

        Args:
            query: Search query
            limit: Maximum number of results
            use_embeddings: Whether to use semantic search if embeddings available

        Returns:
            List of matching reflections

        """
        if not self._initialized:
            await self.initialize()

        if use_embeddings and ONNX_AVAILABLE and self.onnx_session:
            return await self._semantic_search_reflections(query, limit)
        return await self._text_search_reflections(query, limit)

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
            FROM {self.collection_name}_reflections
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
            FROM {self.collection_name}_reflections
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
            FROM {self.collection_name}_reflections
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

    async def reset_database(self) -> None:
        """Reset the database by dropping and recreating tables."""
        if not self._initialized:
            await self.initialize()

        # Drop foreign key constraints first, then tables
        try:
            # Drop reflections table first (has foreign key to conversations)
            self.conn.execute(
                f"DROP TABLE IF EXISTS {self.collection_name}_reflections"
            )
            # Then drop conversations table
            self.conn.execute(
                f"DROP TABLE IF EXISTS {self.collection_name}_conversations"
            )
        except Exception:
            # If there are issues, try dropping with CASCADE
            self.conn.execute(
                f"DROP TABLE IF EXISTS {self.collection_name}_reflections CASCADE"
            )
            self.conn.execute(
                f"DROP TABLE IF EXISTS {self.collection_name}_conversations CASCADE"
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

        insight_id = str(uuid.uuid4())
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
        if ONNX_AVAILABLE and self.onnx_session:
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
                INSERT INTO {self.collection_name}_reflections
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
                INSERT INTO {self.collection_name}_reflections
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
        if use_embeddings and ONNX_AVAILABLE and self.onnx_session:
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
            FROM {self.collection_name}_reflections
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
                FROM {self.collection_name}_reflections
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
                FROM {self.collection_name}_reflections
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
                SELECT COUNT(*) FROM {self.collection_name}_reflections
                WHERE id = ? AND insight_type IS NOT NULL
                """,
                (insight_id,),
            ).fetchone()

            if not check_result or check_result[0] == 0:
                return False

            # Atomic increment prevents race condition
            self.conn.execute(
                f"""
                UPDATE {self.collection_name}_reflections
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
            FROM {self.collection_name}_reflections
            WHERE insight_type IS NOT NULL
            """
        ).fetchone()
        total = total_result[0] if total_result else 0

        # Average quality score
        quality_result = self.conn.execute(
            f"""
            SELECT AVG(CAST(json_extract(metadata, '$.quality_score') AS REAL))
            FROM {self.collection_name}_reflections
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
            FROM {self.collection_name}_reflections
            WHERE insight_type IS NOT NULL
            """
        ).fetchone()
        avg_usage = usage_result[0] if usage_result and usage_result[0] else 0.0

        # Count by insight type
        type_results = self.conn.execute(
            f"""
            SELECT insight_type, COUNT(*) as count
            FROM {self.collection_name}_reflections
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


# Alias for backward compatibility
ReflectionDatabase = ReflectionDatabaseAdapterOneiric


__all__ = [
    "ReflectionDatabase",
    "ReflectionDatabaseAdapterOneiric",
]
