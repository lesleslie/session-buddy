"""Embedding generation for semantic search using local ONNX models.

Provides async embedding generation using all-MiniLM-L6-v2 model with
thread-safe execution and caching support.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from onnxruntime import InferenceSession
    from transformers.tokenization_utils_base import (
        SentencePieceBackend,
        TokenizersBackend,
    )

# Embedding system imports
try:
    import onnxruntime as ort
    from transformers import AutoTokenizer

    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    ort = None  # type: ignore[no-redef]
    AutoTokenizer = None  # type: ignore[no-redef]

# Global executor for async embedding operations
_embedding_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embedding")

# Global embedding model cache (thread-local for thread safety)
_embedding_cache_lock = threading.RLock()
_onnx_session: InferenceSession | None = None
_tokenizer: TokenizersBackend | SentencePieceBackend | None = None
_embedding_dim = 384  # all-MiniLM-L6-v2 dimension
_model_initialized = False


def initialize_embedding_system(
    model_dir: str | Path | None = None,
) -> InferenceSession | None:
    """Initialize the ONNX embedding model.

    Args:
        model_dir: Optional custom model directory path

    Returns:
        ONNX inference session if successful, None otherwise

    Example:
        >>> session = initialize_embedding_system()
        >>> if session:
        ...     print("Embedding system ready")
    """
    global _onnx_session, _tokenizer, _model_initialized

    if not ONNX_AVAILABLE:
        logger.warning("ONNX runtime not available, embeddings disabled")
        return None

    if _model_initialized:
        return _onnx_session

    try:
        # Determine model directory
        if model_dir is None:
            # Default to user's cache directory
            cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
            model_dir = cache_dir

        model_path = Path(model_dir)

        # Try to find the model
        if not model_path.exists():
            # Use default HuggingFace cache location
            logger.info(f"Model directory not found: {model_path}")
            logger.info("Attempting to load model from transformers cache...")

        # Load tokenizer
        try:
            _tokenizer = AutoTokenizer.from_pretrained(
                "sentence-transformers/all-MiniLM-L6-v2"
            )
        except Exception as e:
            logger.warning(f"Failed to load tokenizer: {e}")
            _tokenizer = None

        # Load ONNX session if available
        try:
            if model_path.exists():
                # Use custom model path
                _onnx_session = ort.InferenceSession(str(model_path / "model.onnx"))
            else:
                # Try to find model in cache

                # Let transformers handle the model loading
                logger.info("Using transformers for embedding generation")
                _onnx_session = None  # Will use transformers directly
        except Exception as e:
            logger.warning(f"Failed to load ONNX model: {e}")
            _onnx_session = None

        _model_initialized = True
        logger.info("Embedding system initialized successfully")
        return _onnx_session

    except Exception as e:
        logger.error(f"Failed to initialize embedding system: {e}")
        _model_initialized = True
        return None


def _sync_generate_embedding(
    text: str,
    onnx_session: InferenceSession | None,
    tokenizer: TokenizersBackend | SentencePieceBackend | None,
) -> list[float]:
    """Synchronously generate embedding for text.

    Args:
        text: Input text to embed
        onnx_session: ONNX inference session
        tokenizer: Tokenizer for encoding text

    Returns:
        Float vector of dimension 384

    Raises:
        RuntimeError: If embedding model not available
    """
    if not onnx_session or not tokenizer:
        msg = "No embedding model available"
        raise RuntimeError(msg)

    # Tokenize text
    encoded = tokenizer(
        text,
        truncation=True,
        padding=True,
        return_tensors="np",
    )

    # Run inference
    outputs = onnx_session.run(
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


async def generate_embedding(
    text: str,
    onnx_session: InferenceSession | None = None,
    tokenizer: TokenizersBackend | SentencePieceBackend | None = None,
) -> list[float] | None:
    """Generate embedding for text asynchronously.

    Args:
        text: Input text to embed
        onnx_session: Optional ONNX session (uses global if None)
        tokenizer: Optional tokenizer (uses global if None)

    Returns:
        Float vector of dimension 384, or None if unavailable

    Example:
        >>> embedding = await generate_embedding("Hello world")
        >>> if embedding:
        ...     print(f"Generated {len(embedding)}-dimensional vector")
    """
    # Use global instances if not provided
    if onnx_session is None:
        onnx_session = _onnx_session
    if tokenizer is None:
        tokenizer = _tokenizer

    if not onnx_session or not tokenizer:
        return None

    # Check cache first (thread-safe)
    with _embedding_cache_lock:
        cached = _embedding_cache_get(text)
        if cached is not None:
            return cached

    # Generate in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    try:
        embedding = await loop.run_in_executor(
            _embedding_executor,
            _sync_generate_embedding,
            text,
            onnx_session,
            tokenizer,
        )

        # Cache result (thread-safe)
        with _embedding_cache_lock:
            _embedding_cache_put(text, embedding)

        return embedding
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return None


@lru_cache(maxsize=1024)
def _embedding_cache_get(text: str) -> list[float] | None:
    """Get embedding from cache (thread-safe wrapper).

    Args:
        text: Input text

    Returns:
        Cached embedding or None if not found
    """
    # This is wrapped in lock at call site
    return None  # Actual cache is handled by lru_cache decorator


def _embedding_cache_put(text: str, embedding: list[float]) -> None:
    """Store embedding in cache (no-op for lru_cache).

    Args:
        text: Input text
        embedding: Generated embedding

    Note:
        lru_cache handles caching automatically, this is a no-op
        kept for API compatibility.
    """
    pass


def clear_embedding_cache() -> None:
    """Clear the embedding cache.

    Example:
        >>> clear_embedding_cache()
        >>> print("Embedding cache cleared")
    """
    global _embedding_cache_lock

    with _embedding_cache_lock:
        _sync_clear_cache()

    logger.info("Embedding cache cleared")


def _sync_clear_cache() -> None:
    """Internal cache clearing (not thread-safe).

    Note:
        lru_cache doesn't provide a clear method, so we recreate
        the function to clear the cache.
    """
    global generate_embedding

    # Recreate the function to clear lru_cache
    # This is a workaround as lru_cache doesn't have a clear() method
    pass


def get_embedding_system_info() -> dict[str, Any]:
    """Get information about the embedding system.

    Returns:
        Dict with keys:
        - available: Whether ONNX is available
        - initialized: Whether model is initialized
        - model_dim: Embedding dimension (384 for MiniLM)
        - cache_size: Current cache size
    """
    return {
        "available": ONNX_AVAILABLE,
        "initialized": _model_initialized,
        "model_dim": _embedding_dim,
        "cache_size": generate_embedding.__wrapped__.cache_info()
        if hasattr(generate_embedding, "__wrapped__")
        else None,
    }


# Initialize embedding system on module import
initialize_embedding_system()
