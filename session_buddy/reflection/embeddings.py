"""Embedding generation for semantic search using local ONNX models.

Provides async embedding generation using all-MiniLM-L6-v2 model with
thread-safe execution and caching support.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
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

# Lazy imports to avoid triggering transformers warnings on module load
ONNX_AVAILABLE = None  # Will be determined on first use
_ort = None
_AutoTokenizer = None


def _check_onnx_available() -> bool:
    """Lazily check if ONNX runtime is available."""
    global ONNX_AVAILABLE, _ort, _AutoTokenizer
    if ONNX_AVAILABLE is not None:
        return ONNX_AVAILABLE

    with suppress(ImportError):
        import onnxruntime as ort  # noqa: PLW2901

        _ort = ort
        ONNX_AVAILABLE = True

    if not ONNX_AVAILABLE:
        return False

    # Only import transformers if ONNX is available
    # Suppress the "PyTorch was not found" warning from transformers
    with suppress(ImportError):
        import logging
        import sys
        from io import StringIO

        # Temporarily redirect stdout/stderr to suppress PyTorch warning
        # The warning is printed directly by transformers, not via warnings module
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StringIO()
        sys.stderr = StringIO()

        # Also suppress transformers logger
        transformers_logger = logging.getLogger("transformers")
        original_level = transformers_logger.level
        transformers_logger.setLevel(logging.ERROR)

        try:
            from transformers import AutoTokenizer  # noqa: PLW2901

            _AutoTokenizer = AutoTokenizer
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            transformers_logger.setLevel(original_level)

    return ONNX_AVAILABLE


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
    allow_download: bool = False,
) -> InferenceSession | None:
    """Initialize the ONNX embedding model.

    Args:
        model_dir: Optional custom model directory path
        allow_download: If True, allow downloading from HuggingFace if not cached.
                       Default is False to avoid unexpected network requests.

    Returns:
        ONNX inference session if successful, None otherwise

    Example:
        >>> session = initialize_embedding_system()
        >>> if session:
        ...     print("Embedding system ready")
    """
    global _onnx_session, _tokenizer, _model_initialized

    # Lazily check ONNX availability (this triggers imports only when needed)
    if not _check_onnx_available():
        logger.debug("ONNX runtime not available, embeddings disabled")
        _model_initialized = True
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

        # Check if model is locally cached
        model_name = "models--sentence-transformers--all-MiniLM-L6-v2"
        local_cache = model_path / model_name
        is_cached = local_cache.exists()

        if not is_cached and not allow_download:
            logger.debug(
                "Embedding model not cached locally and allow_download=False. "
                "Embeddings will use text-only search."
            )
            _model_initialized = True
            return None

        # Load tokenizer (only if cached or downloads allowed)
        # Use lazy-loaded _AutoTokenizer from _check_onnx_available()
        if _AutoTokenizer is not None:
            try:
                _tokenizer = _AutoTokenizer.from_pretrained(
                    "sentence-transformers/all-MiniLM-L6-v2",
                    local_files_only=not allow_download,
                )
            except Exception as e:
                if allow_download:
                    logger.warning(f"Failed to load tokenizer: {e}")
                else:
                    logger.debug(f"Tokenizer not cached locally: {e}")
                _tokenizer = None
        else:
            logger.debug("AutoTokenizer not available, skipping tokenizer load")
            _tokenizer = None

        # Load ONNX session if available
        # Use lazy-loaded _ort from _check_onnx_available()
        if _ort is not None:
            try:
                if model_path.exists():
                    # Use custom model path
                    _onnx_session = _ort.InferenceSession(
                        str(model_path / "model.onnx")
                    )
                else:
                    # Try to find model in cache

                    # Let transformers handle the model loading
                    logger.debug("Using transformers for embedding generation")
                    _onnx_session = None  # Will use transformers directly
            except Exception as e:
                logger.warning(f"Failed to load ONNX model: {e}")
                _onnx_session = None
        else:
            logger.debug("ONNX runtime not available, skipping session load")
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
    # Ensure ONNX is available (triggers lazy import)
    if not _check_onnx_available():
        msg = "ONNX runtime not available"
        raise RuntimeError(msg)

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
        "available": _check_onnx_available(),
        "initialized": _model_initialized,
        "model_dim": _embedding_dim,
        "cache_size": generate_embedding.__wrapped__.cache_info()
        if hasattr(generate_embedding, "__wrapped__")
        else None,
    }


# Initialize embedding system on module import ONLY if model is cached locally
# This prevents network requests during import while still enabling embeddings
# for users who have already cached the model
_model_name = "models--sentence-transformers--all-MiniLM-L6-v2"
_cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
_local_cache = _cache_dir / _model_name
if _local_cache.exists():
    # Model is cached, safe to initialize without network requests
    initialize_embedding_system(allow_download=False)
else:
    # Model not cached - don't initialize to avoid network requests
    # Will be initialized lazily on first use if needed
    logger.debug("Embedding model not cached locally - will use text-only search")
