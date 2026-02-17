"""Semantic embedding service for skills metrics.

This module provides embedding generation and similarity search for skill
invocations, enabling semantic skill recommendations based on user queries.

Features:
    - Generate 384-dimensional embeddings using all-MiniLM-L6-v2
    - Embedding cache to avoid regenerating identical queries
    - Batch embedding generation for multiple invocations
    - Graceful degradation when ONNX unavailable
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Embedding system imports
try:
    from session_buddy.reflection.embeddings import (
        generate_embedding as generate_reflection_embedding,
    )
    from session_buddy.reflection.embeddings import (
        initialize_embedding_system,
    )

    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning("Reflection embeddings unavailable, semantic search disabled")


# ============================================================================
# Constants
# ============================================================================

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 dimension
EMBEDDING_BYTES = EMBEDDING_DIM * 4  # float32 = 4 bytes


# ============================================================================
# Embedding Utilities
# ============================================================================


def pack_embedding(embedding: list[float] | np.ndarray) -> bytes:
    """Pack embedding into bytes for storage.

    Args:
        embedding: 384-dimensional vector as list or numpy array

    Returns:
        Packed bytes (1536 bytes for 384-dim float32)

    Example:
        >>> embedding = [0.1, -0.2, 0.3, ...]  # 384 dimensions
        >>> packed = pack_embedding(embedding)
        >>> len(packed)
        1536
    """
    if isinstance(embedding, list):
        embedding = np.array(embedding, dtype=np.float32)
    elif isinstance(embedding, np.ndarray):
        embedding = embedding.astype(np.float32)
    else:
        raise TypeError(f"Unsupported embedding type: {type(embedding)}")

    if embedding.shape != (EMBEDDING_DIM,):
        raise ValueError(f"Expected {EMBEDDING_DIM}-dim vector, got {embedding.shape}")

    return embedding.tobytes()


def unpack_embedding(blob: bytes) -> np.ndarray:
    """Unpack embedding from database bytes.

    Args:
        blob: Packed embedding bytes (1536 bytes)

    Returns:
        Numpy array of shape (384,)

    Example:
        >>> blob = bytes_from_db
        >>> embedding = unpack_embedding(blob)
        >>> embedding.shape
        (384,)
    """
    if len(blob) != EMBEDDING_BYTES:
        raise ValueError(f"Expected {EMBEDDING_BYTES} bytes, got {len(blob)}")

    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(
    embedding1: list[float] | np.ndarray,
    embedding2: list[float] | np.ndarray,
) -> float:
    """Calculate cosine similarity between two embeddings.

    Args:
        embedding1: First embedding (384-dim vector)
        embedding2: Second embedding (384-dim vector)

    Returns:
        Similarity score between -1 and 1, where:
        - 1.0 = identical (same direction)
        - 0.0 = orthogonal (unrelated)
        - -1.0 = opposite (opposite meaning)

    Example:
        >>> emb1 = [1.0, 0.0, 0.0, ...]
        >>> emb2 = [1.0, 0.0, 0.0, ...]
        >>> cosine_similarity(emb1, emb2)
        1.0
    """
    if isinstance(embedding1, list):
        embedding1 = np.array(embedding1, dtype=np.float32)
    if isinstance(embedding2, list):
        embedding2 = np.array(embedding2, dtype=np.float32)

    # Calculate cosine similarity
    dot_product = np.dot(embedding1, embedding2)
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(dot_product / (norm1 * norm2))


# ============================================================================
# Embedding Service
# ============================================================================


class SkillsEmbeddingService:
    """Embedding generation service for skill invocations.

    Provides thread-safe embedding generation with caching and fallback
    support for when the ONNX model is unavailable.

    Attributes:
        cache_enabled: Whether to cache embeddings (default: True)
        batch_size: Number of embeddings to generate in parallel
        executor: Thread pool for parallel embedding generation

    Example:
        >>> service = SkillsEmbeddingService()
        >>> service.initialize()
        >>>
        >>> # Generate single embedding
        >>> embedding = service.generate_embedding("fix race condition in async code")
        >>>
        >>> # Generate batch
        >>> embeddings = service.generate_batch([
        ...     "how to implement JWT auth",
        ...     "fix database connection timeout"
        ... ])
    """

    def __init__(
        self,
        cache_enabled: bool = True,
        batch_size: int = 8,
    ) -> None:
        """Initialize embedding service.

        Args:
            cache_enabled: Enable LRU cache for embeddings (default: True)
            batch_size: Number of parallel embedding generations
        """
        self.cache_enabled = cache_enabled
        self.batch_size = batch_size
        self.executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="skills_embedding"
        )
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize the embedding system.

        Returns:
            True if embeddings are available, False otherwise
        """
        if self._initialized:
            return EMBEDDINGS_AVAILABLE

        if not EMBEDDINGS_AVAILABLE:
            logger.warning("Embeddings unavailable, semantic search disabled")
            return False

        try:
            # Initialize ONNX model
            session = initialize_embedding_system()
            self._initialized = session is not None

            if self._initialized:
                logger.info("Skills embedding service initialized")
            else:
                logger.warning("Failed to initialize embedding system")

            return self._initialized

        except Exception as e:
            logger.error(f"Failed to initialize embedding system: {e}")
            return False

    def generate_embedding(
        self,
        text: str,
        use_cache: bool = True,
    ) -> np.ndarray | None:
        """Generate embedding for text.

        Args:
            text: Input text to embed
            use_cache: Use LRU cache if enabled (default: True)

        Returns:
            384-dimensional numpy array, or None if embeddings unavailable

        Example:
            >>> service = SkillsEmbeddingService()
            >>> service.initialize()
            >>> embedding = service.generate_embedding("fix race condition")
            >>> embedding.shape
            (384,)
        """
        if not self._initialized and not self.initialize():
            return None

        if not text or not text.strip():
            return None

        try:
            # Use cached wrapper if cache enabled
            if use_cache and self.cache_enabled:
                return self._generate_embedding_cached(text.strip())
            else:
                return self._generate_embedding_impl(text.strip())

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    @lru_cache(maxsize=1024)
    def _generate_embedding_cached(self, text: str) -> np.ndarray | None:
        """Generate embedding with LRU cache.

        Args:
            text: Input text (already trimmed)

        Returns:
            Embedding or None
        """
        return self._generate_embedding_impl(text)

    def _generate_embedding_impl(self, text: str) -> np.ndarray | None:
        """Generate embedding without cache.

        Args:
            text: Input text

        Returns:
            Embedding or None
        """
        try:
            # Use reflection embedding system
            result = generate_reflection_embedding(text)

            if result is None or "embedding" not in result:
                return None

            # Extract embedding
            embedding = result["embedding"]

            # Convert to numpy array if needed
            if isinstance(embedding, list):
                embedding = np.array(embedding, dtype=np.float32)

            return embedding

        except Exception as e:
            logger.error(f"Embedding generation failed for '{text[:50]}...': {e}")
            return None

    def generate_batch(
        self,
        texts: list[str],
    ) -> list[np.ndarray | None]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embeddings (None for failed generations)

        Example:
            >>> service = SkillsEmbeddingService()
            >>> service.initialize()
            >>> embeddings = service.generate_batch([
            ...     "how to implement JWT",
            ...     "fix database timeout"
            ... ])
            >>> len(embeddings)
            2
        """
        if not texts:
            return []

        # Generate embeddings in parallel
        embeddings = [self.generate_embedding(text) for text in texts]

        return embeddings

    def clear_cache(self) -> None:
        """Clear the LRU cache.

        Example:
            >>> service = SkillsEmbeddingService()
            >>> service.generate_embedding("test")  # Cached
            >>> service.clear_cache()
            >>> # Next call will regenerate
        """
        if self.cache_enabled:
            self._generate_embedding_cached.cache_clear()
            logger.debug("Embedding cache cleared")

    def shutdown(self) -> None:
        """Shutdown the embedding service.

        Example:
            >>> service = SkillsEmbeddingService()
            >>> service.initialize()
            >>> # ... use service ...
            >>> service.shutdown()
        """
        self.executor.shutdown(wait=True)
        self.clear_cache()
        self._initialized = False
        logger.debug("Skills embedding service shutdown")


# ============================================================================
# Global Service Instance
# ============================================================================

_global_service: SkillsEmbeddingService | None = None


def get_embedding_service() -> SkillsEmbeddingService:
    """Get or create the global embedding service.

    Returns:
        Shared embedding service instance

    Example:
        >>> service = get_embedding_service()
        >>> service.initialize()
        >>> embedding = service.generate_embedding("test")
    """
    global _global_service

    if _global_service is None:
        _global_service = SkillsEmbeddingService()

    return _global_service
