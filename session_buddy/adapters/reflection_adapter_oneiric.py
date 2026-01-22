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
from operator import itemgetter
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
from session_buddy.cache.query_cache import QueryCacheManager
from session_buddy.insights.models import validate_collection_name
from session_buddy.memory.category_evolution import CategoryEvolutionEngine
from session_buddy.utils.fingerprint import MinHashSignature

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
        # Use unique database file per collection to avoid DuckDB locking conflicts
        db_path = self.settings.database_path
        # Add collection name suffix if not already present (for test isolation)
        if self.collection_name != "default" and not str(db_path).endswith(
            f"{self.collection_name}.duckdb"
        ):
            db_path = db_path.parent / f"{db_path.stem}_{self.collection_name}.duckdb"
        self.db_path = str(db_path)
        self.conn: t.Any = None  # DuckDB connection (sync)
        self.onnx_session: InferenceSession | None = None
        self.tokenizer: t.Any = None
        self.embedding_dim = self.settings.embedding_dim  # all-MiniLM-L6-v2 dimension
        self._initialized = False

        # Embedding cache for performance optimization
        self._embedding_cache: dict[str, list[float]] = {}

        # Category evolution engine (Phase 5)
        self._category_engine: CategoryEvolutionEngine | None = None
        self._cache_hits: int = 0
        self._cache_misses: int = 0

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
            with suppress(Exception):
                self.conn.close()
            self.conn = None

        # Clear embedding cache to free memory
        self._embedding_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

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

        # Initialize query cache (Phase 1: Query Cache)
        self._query_cache = QueryCacheManager(
            l1_max_size=1000,
            l2_ttl_days=7,
        )
        await self._query_cache.initialize(conn=self.conn)

        # Initialize ONNX embedding model if embeddings are enabled
        if self.settings.enable_embeddings and ONNX_AVAILABLE:
            await self._init_embedding_model()

        # Initialize category evolution engine (Phase 5)
        self._category_engine = CategoryEvolutionEngine(
            db_adapter=self,
            enable_fingerprint_prefilter=True,
        )
        await self._category_engine.initialize()

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
                f"ALTER TABLE {self.collection_name}_conversations ADD COLUMN IF NOT EXISTS fingerprint BLOB"
            )

        # Add fingerprint column to reflections table
        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self.collection_name}_reflections ADD COLUMN IF NOT EXISTS fingerprint BLOB"
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
                f"ALTER TABLE {self.collection_name}_conversations ADD COLUMN subcategory TEXT"
            )

        with suppress(Exception):
            self.conn.execute(
                f"ALTER TABLE {self.collection_name}_reflections ADD COLUMN subcategory TEXT"
            )

        # Create indexes for category operations
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subcategories_parent ON memory_subcategories(parent_category)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subcategories_count ON memory_subcategories(memory_count)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_conversations_subcategory ON {self.collection_name}_conversations(subcategory)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_reflections_subcategory ON {self.collection_name}_reflections(subcategory)"
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

    def _create_hnsw_indexes(self) -> None:
        """Create HNSW indexes for fast vector similarity search.

        HNSW (Hierarchical Navigable Small World) indexes provide O(log n) search
        performance compared to O(n) for linear scan with array_cosine_similarity.
        Requires DuckDB VSS extension to be installed and loaded.

        Falls back gracefully if VSS extension is not available.
        """
        if not self.settings.enable_hnsw_index:
            logger.debug("HNSW indexing disabled in settings")
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
                CREATE INDEX IF NOT EXISTS idx_{self.collection_name}_conv_embeddings_hnsw
                ON {self.collection_name}_conversations
                USING HNSW (embedding)
                WITH (
                    metric = '{self.settings.distance_metric}',
                    M = {self.settings.hnsw_m},
                    ef_construction = {self.settings.hnsw_ef_construction}
                )
                """
            )
            logger.info(
                f"Created HNSW index for {self.collection_name}_conversations embeddings "
                f"(M={self.settings.hnsw_m}, ef_construction={self.settings.hnsw_ef_construction})"
            )

            # Create HNSW index for reflections table
            self.conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.collection_name}_refl_embeddings_hnsw
                ON {self.collection_name}_reflections
                USING HNSW (embedding)
                WITH (
                    metric = '{self.settings.distance_metric}',
                    M = {self.settings.hnsw_m},
                    ef_construction = {self.settings.hnsw_ef_construction}
                )
                """
            )
            logger.info(
                f"Created HNSW index for {self.collection_name}_reflections embeddings "
                f"(M={self.settings.hnsw_m}, ef_construction={self.settings.hnsw_ef_construction})"
            )

        except Exception as e:
            logger.warning(
                f"Failed to create HNSW indexes: {e}. Falling back to array_cosine_similarity."
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
        """Generate embedding for text using ONNX model.

        Uses embedding cache to avoid recomputation for repeated queries.
        Cache provides 5-10x performance improvement for common queries.
        """
        if not self.onnx_session or not self.tokenizer:
            return None

        # Check cache first (O(1) lookup)
        if text in self._embedding_cache:
            self._cache_hits += 1
            return self._embedding_cache[text]

        # Cache miss - generate embedding
        self._cache_misses += 1

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
            embedding_list = t.cast("list[float]", result)

            # Store in cache for future use
            self._embedding_cache[text] = embedding_list

            return embedding_list
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
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
            self._calibration_min = np.full((384,), -0.15, dtype=np.float32)
            self._calibration_max = np.full((384,), 0.15, dtype=np.float32)

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
        table_name = f"{self.collection_name}_{content_type}s"

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
    ) -> str:
        """Store a conversation in the database.

        Args:
            content: Conversation content
            metadata: Optional metadata
            deduplicate: If True, check for duplicates before storing (Phase 4)
            dedup_threshold: Minimum Jaccard similarity to consider a duplicate (0.0 to 1.0)

        Returns:
            Conversation ID (existing ID if duplicate found and deduplicate=True)

        """
        if not self._initialized:
            await self.initialize()

        # Generate MinHash fingerprint for duplicate detection (Phase 4)
        fingerprint = MinHashSignature.from_text(content)

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

        conv_id = self._generate_id(content)
        now = datetime.now(UTC)
        metadata_json = json.dumps(metadata or {})

        # Generate embedding if enabled
        embedding = None
        if self.settings.enable_embeddings:
            embedding = await self._generate_embedding(content)

        # Convert MinHash fingerprint to bytes for storage
        fingerprint_bytes = fingerprint.to_bytes()

        # Store conversation
        if embedding:
            self.conn.execute(
                f"""
                INSERT INTO {self.collection_name}_conversations
                (id, content, metadata, created_at, updated_at, embedding, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at,
                    embedding = excluded.embedding,
                    fingerprint = excluded.fingerprint
                """,
                [
                    conv_id,
                    content,
                    metadata_json,
                    now,
                    now,
                    embedding,
                    fingerprint_bytes,
                ],
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO {self.collection_name}_conversations
                (id, content, metadata, created_at, updated_at, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at,
                    fingerprint = excluded.fingerprint
                """,
                [conv_id, content, metadata_json, now, now, fingerprint_bytes],
            )

        return conv_id

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
            FROM {self.collection_name}_conversations
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
        if self.settings.enable_hnsw_index:
            self.conn.execute(f"SET hnsw_ef_search = {self.settings.hnsw_ef_search}")

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

        # Calculate cache statistics
        total_cache_requests = self._cache_hits + self._cache_misses
        cache_hit_rate = (
            self._cache_hits / total_cache_requests if total_cache_requests > 0 else 0.0
        )

        return {
            "total_conversations": conv_count,
            "total_reflections": refl_count,
            "conversations_with_embeddings": embedding_count,
            "database_path": self.db_path,
            "collection_name": self.collection_name,
            # Cache statistics
            "embedding_cache": {
                "size": len(self._embedding_cache),
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "hit_rate": cache_hit_rate,
            },
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

        reflection_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)

        # Generate embedding if available
        embedding: list[float] | None = None
        if ONNX_AVAILABLE and self.onnx_session:
            try:
                embedding = await self._generate_embedding(content)
            except Exception:
                embedding = None

        # Convert MinHash fingerprint to bytes for storage
        fingerprint_bytes = fingerprint.to_bytes()

        # Store reflection (explicitly set insight_type to NULL to distinguish from insights)
        if embedding:
            self.conn.execute(
                f"""
                INSERT INTO {self.collection_name}_reflections
                (id, content, tags, embedding, created_at, updated_at, insight_type, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    reflection_id,
                    content,
                    tags or [],
                    embedding,
                    now,
                    now,
                    fingerprint_bytes,
                ),
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO {self.collection_name}_reflections
                (id, content, tags, created_at, updated_at, insight_type, fingerprint)
                VALUES (?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    reflection_id,
                    content,
                    tags or [],
                    now,
                    now,
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
                    UPDATE {self.collection_name}_reflections
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
            FROM {self.collection_name}_reflections
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
        if use_embeddings and ONNX_AVAILABLE and self.onnx_session:
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
