"""Query cache implementation for Session Buddy.

Pure substitution: delegates to oneiric.adapters.cache.memory.MemoryCacheAdapter.

Pre-1.0 replace-not-extend (feedback-no-backwards-compat-pre-1.0.md): the
L2 DuckDB infrastructure (query_cache_l2 table) is dead per spec §10
risk #1 and is deleted in this commit alongside the substitution.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from oneiric.adapters.cache.memory import MemoryCacheAdapter, MemoryCacheSettings


class QueryCacheManager:
    """Two-tier cache substitute: now in-process via MemoryCacheAdapter.

    Sync API preserved for callers that reach the cache in non-async
    contexts. Per-call asyncio.run() bridge with a running-loop guard.
    """

    def __init__(
        self,
        l1_max_size: int = 1000,
        l2_ttl_days: int = 7,
    ) -> None:
        self.l1_max_size = l1_max_size
        self.l2_ttl_seconds = l2_ttl_days * 86400
        settings = MemoryCacheSettings(
            max_entries=l1_max_size,
            default_ttl=float(self.l2_ttl_seconds) if l2_ttl_days else None,
        )
        self._cache: MemoryCacheAdapter = MemoryCacheAdapter(settings)

    @staticmethod
    def normalize_query(query: str) -> str:
        """Normalize query string for consistent cache keys.

        Normalization steps:
            1. Convert to lowercase
            2. Collapse multiple whitespace to single space
            3. Strip leading/trailing whitespace
            4. Remove punctuation (except query operators)

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
        import re

        # Convert to lowercase
        normalized = query.lower().strip()

        # Collapse multiple whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        # Remove trailing punctuation (but keep internal operators like +, -, *)
        normalized = re.sub(r"[?!.;,]+$", "", normalized)

        return normalized

    @staticmethod
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

        Examples:
            >>> compute_cache_key("async patterns", project="myapp", limit=10)
            'a3f5c8d9e2b1...'
            >>> compute_cache_key("authentication", limit=20, min_score=0.8)
            '7d9e4a2f1c8b...'
        """
        # Normalize query first
        normalized = QueryCacheManager.normalize_query(query)

        # Build key components
        components: dict[str, Any] = {
            "query": normalized,
            "project": project or "",
            "limit": limit,
        }

        # Add sorted kwargs
        if kwargs:
            # Sort keys for consistent hashing
            sorted_kwargs = json.dumps(kwargs, sort_keys=True)
            components["kwargs"] = sorted_kwargs

        # Create hash
        key_string = json.dumps(components, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def _run_async(self, coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "QueryCacheManager sync API cannot be called from a running event loop. "
                "Use the underlying MemoryCacheAdapter async interface directly."
            )
        return asyncio.run(coro)

    def get(
        self,
        cache_key: str,
        check_l2: bool = True,  # req: REQ-OSUB-A-001 — preserved kwarg, no-op (L2 deleted)
    ) -> list[str] | None:
        raw = self._run_async(self._cache.get(cache_key))
        if raw is None:
            return None
        if not isinstance(raw, list):
            return None
        return raw

    def put(
        self,
        cache_key: str,
        result_ids: list[str],
        normalized_query: str,
        project: str | None = None,
    ) -> None:
        # req: REQ-OSUB-A-001 — store result_ids verbatim (the historical cache shape)
        self._run_async(self._cache.set(cache_key, list(result_ids)))

    def invalidate(
        self,
        cache_key: str | None = None,
    ) -> None:
        # req: REQ-OSUB-A-001
        if cache_key is None:
            self._run_async(self._cache.clear())
            return
        self._run_async(self._cache.delete(cache_key))

    def close(self) -> None:
        # req: REQ-OSUB-A-002 — was `async aclose`
        self._run_async(self._cache.cleanup())
