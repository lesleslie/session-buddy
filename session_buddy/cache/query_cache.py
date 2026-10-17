"""Query cache utilities for Session Buddy.

The substrate (``oneiric.adapters.cache.memory.MemoryCacheAdapter``)
provides the cache primitive directly. This module re-exports it and
ships two module-level helpers (``normalize_query``,
``compute_cache_key``) that callers use to derive cache keys.

The legacy ``QueryCacheManager`` wrapper was deleted in the substrate-
adoption cleanup wave; per ``feedback-no-backwards-compat-pre-1.0.md``
pre-1.0 callers MUST switch to the substrate adapter directly.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from oneiric.adapters.cache.memory import (
    MemoryCacheAdapter,
    MemoryCacheSettings,
)

__all__ = [
    "MemoryCacheAdapter",
    "MemoryCacheSettings",
    "normalize_query",
    "compute_cache_key",
]


def normalize_query(query: str) -> str:
    """Normalize query string for consistent cache keys.

    Normalization steps:
        1. Convert to lowercase
        2. Collapse multiple whitespace to single space
        3. Strip leading/trailing whitespace
        4. Remove trailing punctuation (but keep internal operators)

    Args:
        query: Raw query string

    Returns:
        Normalized query string

    Examples:
        >>> normalize_query("What did I  learn about  async?")
        'what did i learn about async'
        >>> normalize_query("  Find insights on authentication  ")
        'find insights on authentication'
    """
    normalized = query.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[?!.;,]+$", "", normalized)
    return normalized


def compute_cache_key(
    query: str,
    project: str | None = None,
    limit: int = 10,
    **kwargs: Any,
) -> str:
    """Compute cache key from query parameters.

    Cache key components:
        1. Normalized query
        2. Project name (if provided)
        3. Result limit
        4. Additional kwargs (sorted for consistency)

    Args:
        query: Search query string
        project: Optional project filter
        limit: Result limit
        **kwargs: Additional search parameters

    Returns:
        SHA256 hash as hex string
    """
    normalized = normalize_query(query)

    components: dict[str, Any] = {
        "query": normalized,
        "project": project or "",
        "limit": limit,
    }

    if kwargs:
        sorted_kwargs = json.dumps(kwargs, sort_keys=True)
        components["kwargs"] = sorted_kwargs

    key_string = json.dumps(components, sort_keys=True)
    return hashlib.sha256(key_string.encode()).hexdigest()