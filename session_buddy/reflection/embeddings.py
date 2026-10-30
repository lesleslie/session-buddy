"""Embedding generation for semantic search via HTTP providers.

The provider is selected from a **width-aware chain**. Every leg of the
chain declares the width of the vectors it produces, and only a leg whose
width matches the canonical dimension is eligible. The chain tries the
eligible legs in order and returns the first vector that comes back.

Width matters because the DuckDB embedding columns are fixed-size ARRAY
columns (``FLOAT[1536]``). A vector of the wrong width cannot be bound
into one, and the width cannot be negotiated at runtime -- DuckDB
refuses to widen an existing column ("Cannot cast array of size 4096 to
array of size 1536").

The legs, in order:

1. ``openai_gateway`` -- the local Bifrost gateway, an OpenAI-compatible
   endpoint on loopback, serving ``text-embedding-3-small`` shortened to
   the canonical width via its ``dimensions`` parameter.
2. ``openai_direct``  -- api.openai.com, same model, when a key exists.
3. ``llama_embed``    -- a dedicated local llama.cpp server running
   EmbeddingGemma-300M, whose native width *is* the canonical width.
4. ``llama_server``   -- the chat llama.cpp server (4096 dims for the
   Qwen3-8B model this host runs), skipped because its width differs.

The last leg is **not deleted**; it is skipped because its width does not
match. Change the canonical width and it becomes eligible again with no
code change.

Two independent guards keep the chain honest. *Eligibility* skips a leg
whose declared width differs from the canonical dimension, without a
network call. *Validation* length-checks every vector that comes back,
which is the authoritative gate: a leg that lies about its width is
caught here rather than at the DuckDB bind.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from session_buddy.memory.embedding_dim import DEFAULT_EMBEDDING_DIM

logger = logging.getLogger(__name__)

# The provider's vector width. This must track the canonical dimension: the
# DuckDB ``FLOAT[N]`` columns and the adapter's ``embedding_dim`` are bound
# to it, and binding a wrong-width vector cannot be bound into a
# fixed-size ARRAY at all (see ``session_buddy.memory.embedding_dim``).
EMBEDDING_DIM = DEFAULT_EMBEDDING_DIM

# Read timeout for a single embedding request. With the request serialised by
# the semaphore below, the server serves it immediately, so this only has to
# cover one request's actual service time.
EMBEDDING_HTTP_TIMEOUT_S = 60.0

#: Width of the vectors served by the dedicated local embedding server
#: (EmbeddingGemma-300M). Its native width *is* the canonical width, so
#: this leg is eligible.
LLAMA_EMBED_DIM = int(os.environ.get("LLAMA_EMBED_DIM", "768") or "768")

#: Width of the vectors served by the chat llama-server. The model this
#: host runs (Qwen3-8B) produces 4096-dim embeddings, which is *not* the
#: canonical width -- so this leg is skipped rather than silently
#: producing vectors the DuckDB columns would reject. Override with
#: ``LLAMA_SERVER_EMBEDDING_DIM`` when a differently-sized local model is
#: installed.
LLAMA_SERVER_EMBEDDING_DIM = int(
    os.environ.get("LLAMA_SERVER_EMBEDDING_DIM", "4096") or "4096"
)

#: Width of the vectors served by OpenAI's ``text-embedding-3-small``.
#: The model is Matryoshka-trained, so its ``dimensions`` parameter
#: shortens it to any width -- which is what lets the cloud leg match the
#: column whatever width the column happens to use.
OPENAI_EMBEDDING_DIM = 768

# HTTP provider URLs.
#
# llama-server: the fleet convention is the ``LLAMA_SERVER_URL`` env var.
# ``MAHAVISHNU__LLAMA_SERVER_URL`` is honoured first because it is what
# this module has always read, and a change of precedence would silently
# move an operator's endpoint.
_LLAMA_SERVER_BASE = os.environ.get(
    "MAHAVISHNU__LLAMA_SERVER_URL",
    os.environ.get("LLAMA_SERVER_URL", "http://localhost:8081/v1"),
)

#: A dedicated llama.cpp server running an *embedding* model. The chat
#: server on :8081 serves Qwen3-8B, whose embeddings are 4096-dim; a
#: separate instance runs EmbeddingGemma-300M, whose native width is the
#: canonical one. One server cannot serve both models.
_LLAMA_EMBED_BASE = os.environ.get("LLAMA_EMBED_SERVER_URL", "http://localhost:8082/v1")

#: The local Bifrost gateway. It is an OpenAI-compatible endpoint and it
#: already serves ``text-embedding-3-small`` -- its own semantic-cache
#: plugin is configured for that model at that dimension -- so no new
#: credential is needed to reach a cloud embedding provider through it.
_BIFROST_BASE = os.environ.get("BIFROST_BASE_URL", "http://127.0.0.1:8471/v1")

#: The model the gateway is asked for.
_BIFROST_EMBEDDING_MODEL = os.environ.get(
    "BIFROST_EMBEDDING_MODEL", "text-embedding-3-small"
)

#: The direct OpenAI endpoint, used when a key is present.
_OPENAI_BASE = "https://api.openai.com/v1"
_OPENAI_EMBEDDING_MODEL = os.environ.get(
    "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
)

#: An assignment in the operator credential store.
#:
#: The ``export`` keyword is optional. The store's convention includes it
#: -- shell rc files source the file, so its assignments are exported
#: -- and a parser that requires a bare ``KEY=value`` matches nothing
#: in it.
_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _get_llama_server_url() -> str:
    """Compute full llama-server URL, stripping trailing /embeddings if present."""
    base = _LLAMA_SERVER_BASE.rstrip("/")
    if base.endswith(("/embeddings", "/v1/embeddings")):
        base = base.rsplit("/embeddings", 1)[0]
    return f"{base}/embeddings"


def _get_llama_embed_url() -> str:
    """Compute the dedicated embedding server's URL."""
    base = _LLAMA_EMBED_BASE.rstrip("/")
    if base.endswith(("/embeddings", "/v1/embeddings")):
        base = base.rsplit("/embeddings", 1)[0]
    return f"{base}/embeddings"


def _get_bifrost_url() -> str:
    """Compute the gateway's embeddings URL."""
    return f"{_BIFROST_BASE.rstrip('/')}/embeddings"


def _get_openai_url() -> str:
    """Compute the direct OpenAI embeddings URL."""
    return f"{_OPENAI_BASE}/embeddings"


def _secret_from_store(name: str) -> str | None:
    """Read one key from the operator credential store.

    A launchd-spawned process inherits no interactive environment, so the
    credential has to come from ``~/.config/secrets.env`` when it is not
    already in the environment. Only the named key is read.

    The store's convention is ``export KEY=value`` -- shell rc files
    source it, so the assignments carry the ``export`` keyword. A parser
    that compares the raw left-hand side therefore never matches any
    key, and a launchd-spawned process silently finds nothing. The
    keyword is optional here so both spellings are accepted, the same
    way the rest of the fleet's store readers accept them.

    Args:
        name: The environment-variable name to look up.

    Returns:
        The value, or ``None`` when the store is unreadable or has no
        such key.
    """
    path = Path.home() / ".config" / "secrets.env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGNMENT.match(stripped)
        if match is None or match.group(1) != name:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value or None
    return None


def _resolve_secret(*names: str) -> str | None:
    """Return the first of ``names`` that resolves to a non-empty value.

    The environment wins over the credential store: an operator who exports
    a value for this process means it.

    Args:
        *names: Candidate environment-variable names, in priority order.

    Returns:
        The value, or ``None`` when none of the names resolve.
    """
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    for name in names:
        value = _secret_from_store(name)
        if value:
            return value
    return None


def _resolve_bifrost_key() -> str | None:
    """Return the gateway credential, if one is configured."""
    return _resolve_secret("BIFROST_VIRTUAL_KEY", "ONEIRIC_BIFROST_AUTH_TOKEN")


def _resolve_openai_key() -> str | None:
    """Return the direct OpenAI credential, if one is configured."""
    return _resolve_secret("OPENAI_API_KEY")


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


def _extract_embedding(payload: Any) -> list[float] | None:
    """Pull the vector out of an OpenAI-compatible embeddings response.

    Args:
        payload: The decoded JSON body.

    Returns:
        The vector, or ``None`` when the body has no usable one.
    """
    if not isinstance(payload, dict) or "data" not in payload:
        return None
    data = payload["data"]
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    vector = first.get("embedding")
    if (
        vector
        and isinstance(vector, list)
        and all(isinstance(x, (int, float)) for x in vector)
    ):
        return vector
    return None


async def _post_embeddings(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
) -> list[float] | None:
    """POST an OpenAI-compatible embeddings request and decode the vector.

    Args:
        url: The embeddings endpoint.
        body: The request body.
        headers: Extra headers (credentials).

    Returns:
        The vector, or ``None`` when the request failed or the body carried
        no usable vector.
    """
    import httpx2 as httpx

    try:
        async with (
            _embedding_semaphore(),
            httpx.AsyncClient(
                timeout=httpx.Timeout(EMBEDDING_HTTP_TIMEOUT_S, connect=5.0)
            ) as client,
        ):
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "embedding request to %s returned HTTP %s", url, resp.status_code
                )
                return None
            return _extract_embedding(resp.json())
    except Exception as e:  # noqa: BLE001 - embedding probe: any HTTP/JSON/network failure is logged and yields None so the next provider can be tried
        logger.warning(f"embedding request to {url} failed: {e}")
        return None


async def _try_openai_gateway(text: str) -> list[float] | None:
    """Try the local Bifrost gateway, which serves OpenAI's embedding model."""
    headers: dict[str, str] = {}
    key = _resolve_bifrost_key()
    if key:
        headers["x-bf-vk"] = key
    return await _post_embeddings(
        _get_bifrost_url(),
        {
            "model": _BIFROST_EMBEDDING_MODEL,
            "input": [text],
            "dimensions": OPENAI_EMBEDDING_DIM,
        },
        headers,
    )


async def _try_openai_direct(text: str) -> list[float] | None:
    """Try OpenAI directly, when a key is configured."""
    key = _resolve_openai_key()
    if not key:
        return None
    return await _post_embeddings(
        _get_openai_url(),
        {
            "model": _OPENAI_EMBEDDING_MODEL,
            "input": [text],
            "dimensions": OPENAI_EMBEDDING_DIM,
        },
        {"Authorization": f"Bearer {key}"},
    )


async def _try_llama_embed_server(text: str) -> list[float] | None:
    """Try the dedicated local embedding server (EmbeddingGemma-300M)."""
    return await _post_embeddings(
        _get_llama_embed_url(),
        {"input": [text]},
        {},
    )


async def _try_llama_server(text: str) -> list[float] | None:
    """Try the chat llama-server embedding endpoint."""
    return await _post_embeddings(
        _get_llama_server_url(),
        {"input": [text]},
        {},
    )


@dataclass(frozen=True)
class ProviderLeg:
    """One provider in the chain.

    Attributes:
        name: Identifier used in logs and in the system-info report.
        width: The width of the vectors this leg produces.
        fetch: Coroutine that requests a vector, or ``None`` on failure.
    """

    name: str
    width: int
    fetch: Callable[[str], Awaitable[list[float] | None]]


#: The chain, in priority order.
_PROVIDER_LEGS: tuple[ProviderLeg, ...] = (
    ProviderLeg("openai_gateway", OPENAI_EMBEDDING_DIM, _try_openai_gateway),
    ProviderLeg("openai_direct", OPENAI_EMBEDDING_DIM, _try_openai_direct),
    ProviderLeg("llama_embed", LLAMA_EMBED_DIM, _try_llama_embed_server),
    ProviderLeg("llama_server", LLAMA_SERVER_EMBEDDING_DIM, _try_llama_server),
)

#: The leg that served the last vector. Reported by
#: :func:`get_embedding_system_info` so an operator can see which provider
#: is actually answering.
_ACTIVE_LEG: str | None = None


def _eligible_legs(width: int | None = None) -> list[ProviderLeg]:
    """The legs whose declared width matches the requested dimension.

    A leg whose width differs cannot produce a vector the DuckDB columns
    would accept, so it is skipped without a network call.

    Args:
        width: The width wanted. Defaults to the canonical dimension.

    Returns:
        The eligible legs, in chain order.
    """
    target = EMBEDDING_DIM if width is None else width
    return [leg for leg in _PROVIDER_LEGS if leg.width == target]


async def _try_http_embedding_providers(
    text: str, *, width: int | None = None
) -> list[float] | None:
    """Try the eligible providers in order, return an embedding or None.

    Each leg's vector is validated against the requested width before it
    is accepted. That check is authoritative: a leg that declares the
    wrong width is caught here rather than at the DuckDB bind.

    Args:
        text: The text to embed.
        width: The width wanted. Defaults to the canonical dimension.

    Returns:
        A vector of the requested width, or ``None`` when no leg produced
        one.
    """
    global _ACTIVE_LEG

    target = EMBEDDING_DIM if width is None else width
    for leg in _eligible_legs(target):
        vector = await leg.fetch(text)
        if vector is None:
            continue
        if len(vector) != target:
            logger.warning(
                "provider %s returned %d dims, expected %d -- rejecting it",
                leg.name,
                len(vector),
                target,
            )
            continue
        _ACTIVE_LEG = leg.name
        return vector
    return None


# Thread-safe embedding cache (simple dict + lock).
#
# The key includes the width: the chain can serve more than one width
# (a caller may ask for the width of a column that is being migrated),
# and a vector of the wrong width is not interchangeable with one of
# the right width.
_embedding_cache: dict[tuple[str, int], list[float]] = {}
_embedding_cache_lock = __import__("threading").RLock()


def _embedding_cache_get(text: str, width: int | None = None) -> list[float] | None:
    """Get embedding from cache.

    Args:
        text: Input text
        width: The width the caller wants. Defaults to the canonical
            dimension.

    Returns:
        Cached embedding or None if not found
    """
    target = EMBEDDING_DIM if width is None else width
    with _embedding_cache_lock:
        return _embedding_cache.get((text, target))


def _embedding_cache_put(
    text: str, embedding: list[float], width: int | None = None
) -> None:
    """Store embedding in cache."""
    target = EMBEDDING_DIM if width is None else width
    with _embedding_cache_lock:
        _embedding_cache[(text, target)] = embedding
        # Simple eviction: if cache too large, remove oldest 10%
        if len(_embedding_cache) > 1024:
            oldest = list(_embedding_cache.keys())[: int(len(_embedding_cache) * 0.1)]
            for k in oldest:
                del _embedding_cache[k]


async def generate_embedding(text: str, width: int | None = None) -> list[float] | None:
    """Generate embedding for text asynchronously via HTTP providers.

    Tries the width-eligible legs of the provider chain in order and
    returns the first vector of the requested width. Results are cached.

    Args:
        text: Input text to embed
        width: The width wanted. Defaults to the canonical dimension.
            Callers that write into a DuckDB column should pass the
            width of that column -- the schema is the authority on what
            fits, and it may differ from the constant while a database
            is being migrated.

    Returns:
        Float vector of the requested width, or None if all eligible
        providers fail

    Example:
        >>> embedding = await generate_embedding("Hello world")
        >>> if embedding:
        ...     print(f"Generated {len(embedding)}-dimensional vector")
    """
    # Check cache first
    target = EMBEDDING_DIM if width is None else width
    cached = _embedding_cache_get(text, target)
    if cached is not None:
        return cached

    # Try the provider chain.
    #
    # The canonical width is the overwhelmingly common case, and it is
    # called with the single-argument form on purpose: that is the
    # signature the provider stubs in the test suite replace, and
    # changing the arity would silently bypass them.
    if target == EMBEDDING_DIM:
        result = await _try_http_embedding_providers(text)
    else:
        result = await _try_http_embedding_providers(text, width=target)
    if result is not None:
        _embedding_cache_put(text, result, target)
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
        - active_provider: The leg that served the last vector, if any
        - eligible_providers: The legs whose width matches the canonical
          dimension, in chain order
        - skipped_providers: The legs that were skipped, with the reason
        - http_providers: The URLs the chain may call
    """
    with _embedding_cache_lock:
        cache_size = len(_embedding_cache)
    eligible = _eligible_legs()
    eligible_names = {leg.name for leg in eligible}
    return {
        "available": True,
        "initialized": True,
        "model_dim": EMBEDDING_DIM,
        "cache_size": cache_size,
        "active_provider": _ACTIVE_LEG,
        "eligible_providers": [leg.name for leg in eligible],
        "skipped_providers": [
            {"name": leg.name, "width": leg.width, "reason": "width mismatch"}
            for leg in _PROVIDER_LEGS
            if leg.name not in eligible_names
        ],
        "http_providers": {
            "openai_gateway": _get_bifrost_url(),
            "openai_direct": _get_openai_url(),
            "llama_embed": _get_llama_embed_url(),
            "llama_server": _get_llama_server_url(),
        },
    }


# Backward-compatibility exports -- ONNX is removed
# These were removed in Phase 5 but are kept as no-op stubs for any
# code that imports them. Remove them when you find usages.
def initialize_embedding_system(
    model_dir: str | None = None,
    allow_download: bool = False,
) -> None:
    """No-op. ONNX embedding removed in Phase 5.

    HTTP providers handle embeddings.
    Kept for backward compatibility -- safe to ignore.
    """
    logger.debug("initialize_embedding_system: ONNX removed, HTTP providers used")


__all__ = [
    "EMBEDDING_DIM",
    "ProviderLeg",
    "clear_embedding_cache",
    "generate_embedding",
    "get_embedding_system_info",
    "initialize_embedding_system",  # backward compat
]
