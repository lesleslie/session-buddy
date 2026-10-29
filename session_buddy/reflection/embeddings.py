"""Embedding generation for semantic search via HTTP providers.

Provides async embedding generation using llama-server with
graceful degradation when no providers are available.

Phase 5: ONNX path removed. llama-server is the sole local
HTTP provider.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from session_buddy.memory.embedding_dim import DEFAULT_EMBEDDING_DIM

logger = logging.getLogger(__name__)

# HTTP provider URL. Port 8081 is where the llama-server actually listens;
# 8080 was a stale default that answered nothing, which silently disabled
# every embedding in the reflection pipeline.
_LLAMA_SERVER_BASE = os.environ.get(
    "MAHAVISHNU__LLAMA_SERVER_URL", "http://localhost:8081/v1"
)


def _get_llama_server_url() -> str:
    """Compute full llama-server URL, stripping trailing /embeddings if present."""
    base = _LLAMA_SERVER_BASE.rstrip("/")
    if base.endswith(("/embeddings", "/v1/embeddings")):
        base = base.rsplit("/embeddings", 1)[0]
    return f"{base}/embeddings"


# The provider's vector width. This must track the canonical dimension: the
# DuckDB ``FLOAT[N]`` columns and the adapter's ``embedding_dim`` are bound
# to it, and binding a wrong-width vector corrupts the DuckDB instance
# fatally (see ``session_buddy.memory.embedding_dim``).
EMBEDDING_DIM = DEFAULT_EMBEDDING_DIM

# Read timeout for a single embedding request. With the request serialised by
# the semaphore below, the server serves it immediately, so this only has to
# cover one request's actual service time.
EMBEDDING_HTTP_TIMEOUT_S = 60.0

# The llama-server runs with a single slot (``n_parallel`` defaults to 1), so
# concurrent requests queue *server-side* and each one waits behind the
# previous. A client-side semaphore serialises them instead: every request is
# served promptly rather than queueing past the read timeout, which used to
# drop the vector silently.
#
# The semaphore is per event loop: the server entry point uses one
# ``asyncio.run`` for the whole process, but a few standalone call sites spin
# their own loop, and an ``asyncio.Semaphore`` is bound to the loop it was
# first awaited on.
_EMBEDDING_SEMAPHORES: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


def _embedding_semaphore() -> asyncio.Semaphore:
    """Return the semaphore that serialises embedding requests for this loop."""
    loop = asyncio.get_running_loop()
    semaphore = _EMBEDDING_SEMAPHORES.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(1)
        _EMBEDDING_SEMAPHORES[loop] = semaphore
    return semaphore


async def _try_llama_server(text: str) -> list[float] | None:
    """Try llama-server embedding, return embedding or None."""
    import httpx2 as httpx

    try:
        async with _embedding_semaphore(), httpx.AsyncClient(
            timeout=httpx.Timeout(EMBEDDING_HTTP_TIMEOUT_S, connect=5.0)
        ) as client:
            resp = await client.post(
                _get_llama_server_url(),
                json={"input": [text]},
            )
            if resp.status_code != 200:
                logger.warning(
                    "llama-server embedding returned HTTP %s (%d chars)",
                    resp.status_code,
                    len(text),
                )
                return None
            data = resp.json()
            if not isinstance(data, dict) or "data" not in data:
                logger.warning("llama-server embedding response had no 'data'")
                return None
            embedding_data = data["data"]
            if not isinstance(embedding_data, list) or not embedding_data:
                logger.warning("llama-server embedding response had empty 'data'")
                return None
            embedding = embedding_data[0].get("embedding")
            if (
                embedding
                and isinstance(embedding, list)
                and len(embedding) == EMBEDDING_DIM
                and all(isinstance(x, (int, float)) for x in embedding)
            ):
                return embedding
            logger.warning(
                "llama-server embedding had unexpected shape (expected %d dims)",
                EMBEDDING_DIM,
            )
            return None
    except Exception as e:  # noqa: BLE001 - embedding probe: any HTTP/JSON/network failure is logged and yields None so the next provider can be tried
        logger.warning(f"llama-server embedding failed: {e}")
    return None


async def _try_http_embedding_providers(text: str) -> list[float] | None:
    """Try llama-server, return embedding or None.

    llama-server: OpenAI-compatible /v1/embeddings endpoint.
    Returns pre-normalized vectors of the canonical width.
    """
    return await _try_llama_server(text)


# Thread-safe embedding cache (simple dict + lock)
_embedding_cache: dict[str, list[float]] = {}
_embedding_cache_lock = __import__("threading").RLock()


def _embedding_cache_get(text: str) -> list[float] | None:
    """Get embedding from cache.

    Args:
        text: Input text

    Returns:
        Cached embedding or None if not found
    """
    with _embedding_cache_lock:
        return _embedding_cache.get(text)


def _embedding_cache_put(text: str, embedding: list[float]) -> None:
    """Store embedding in cache."""
    with _embedding_cache_lock:
        _embedding_cache[text] = embedding
        # Simple eviction: if cache too large, remove oldest 10%
        if len(_embedding_cache) > 1024:
            oldest = list(_embedding_cache.keys())[: int(len(_embedding_cache) * 0.1)]
            for k in oldest:
                del _embedding_cache[k]


async def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding for text asynchronously via HTTP providers.

    Tries llama-server. Returns pre-normalized vectors of the canonical
    width. Results are cached.

    Args:
        text: Input text to embed

    Returns:
        Float vector of dimension ``EMBEDDING_DIM``, or None if all
        providers fail

    Example:
        >>> embedding = await generate_embedding("Hello world")
        >>> if embedding:
        ...     print(f"Generated {len(embedding)}-dimensional vector")
    """
    # Check cache first
    cached = _embedding_cache_get(text)
    if cached is not None:
        return cached

    # Try HTTP providers
    result = await _try_http_embedding_providers(text)
    if result is not None:
        _embedding_cache_put(text, result)
        return result

    return None


def clear_embedding_cache() -> None:
    """Clear the embedding cache."""
    with _embedding_cache_lock:
        _embedding_cache.clear()
    logger.info("Embedding cache cleared")


def get_embedding_system_info() -> dict[str, Any]:
    """Get information about the embedding system.

    Returns:
        Dict with keys:
        - available: Always True (HTTP providers handle failures gracefully)
        - initialized: Always True (HTTP is stateless)
        - model_dim: Embedding dimension (``EMBEDDING_DIM``)
        - cache_size: Current cache size
        - http_providers: Dict with llama_server URL
    """
    with _embedding_cache_lock:
        cache_size = len(_embedding_cache)
    return {
        "available": True,
        "initialized": True,
        "model_dim": EMBEDDING_DIM,
        "cache_size": cache_size,
        "http_providers": {
            "llama_server": _get_llama_server_url(),
        },
    }


# Backward-compatibility exports — ONNX is removed
# These were removed in Phase 5 but are kept as no-op stubs for any
# code that imports them. Remove them when you find usages.
def initialize_embedding_system(
    model_dir: str | None = None,
    allow_download: bool = False,
) -> None:
    """No-op. ONNX embedding removed in Phase 5.

    HTTP providers (llama-server) handle embeddings.
    Kept for backward compatibility — safe to ignore.
    """
    logger.debug("initialize_embedding_system: ONNX removed, HTTP providers used")


__all__ = [
    "clear_embedding_cache",
    "generate_embedding",
    "get_embedding_system_info",
    "initialize_embedding_system",  # backward compat
]
