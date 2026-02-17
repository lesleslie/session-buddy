# Implementation Plan: Exact-Match Query Cache

**Inspired by**: DeepSeek Engram's O(1) deterministic addressing pattern
**Priority**: High value, Low effort
**Status**: Proposed

## Overview

Add a fast hash-based cache layer that bypasses expensive vector similarity search for repeated or near-identical queries. This implements Engram's core insight: **static patterns don't need neural/embedding computation**.

## Problem Statement

Currently, Session Buddy performs full vector similarity search for every query:

```python
# Current: Always compute embedding + vector search
embedding = await self._generate_embedding(query)
results = SELECT ... array_cosine_similarity(embedding, $1) ...
```

This is wasteful when:

- The same query is asked multiple times in a session
- Near-identical queries differ only in whitespace/punctuation
- Common patterns like "how do I..." or "what is the..." appear frequently

## Proposed Solution

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Query Pipeline                          │
├─────────────────────────────────────────────────────────────┤
│  1. Normalize query (lowercase, strip, collapse whitespace) │
│  2. Compute hash key                                        │
│  3. Check L1 cache (in-memory dict)                        │
│  4. Check L2 cache (DuckDB table)                          │
│  5. If miss: full vector search → populate caches          │
└─────────────────────────────────────────────────────────────┘
```

### Components

#### 1. Query Normalizer

```python
def normalize_query(query: str) -> str:
    """Normalize query for cache key generation.

    Applies same normalizations as Engram:
    - NFKC Unicode normalization
    - Lowercase
    - Strip accents (optional, configurable)
    - Collapse whitespace
    - Remove punctuation (optional, configurable)
    """
    import unicodedata

    # NFKC normalization (compatibility decomposition + canonical composition)
    text = unicodedata.normalize("NFKC", query)

    # Lowercase
    text = text.lower()

    # Collapse whitespace
    text = " ".join(text.split())

    return text.strip()
```

#### 2. Cache Key Generator

```python
def compute_cache_key(normalized_query: str, project: str | None = None) -> str:
    """Compute deterministic cache key using xxhash for speed.

    Uses xxhash (not cryptographic, but fast) like Engram's XOR hashing.
    """
    import xxhash

    # Include project in key for isolation
    key_input = f"{project or 'global'}:{normalized_query}"
    return xxhash.xxh64(key_input.encode()).hexdigest()
```

#### 3. Two-Level Cache Structure

**L1: In-Memory LRU Cache**

- Fast dict with LRU eviction
- Configurable max size (default: 1000 entries)
- Cleared on adapter close
- TTL: session duration

**L2: Persistent DuckDB Table**

- Survives restarts
- Configurable TTL (default: 7 days)
- Automatic cleanup of stale entries

```sql
CREATE TABLE IF NOT EXISTS query_cache (
    cache_key TEXT PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    project TEXT,
    result_ids TEXT[],  -- Array of conversation/reflection IDs
    hit_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ttl_seconds INTEGER DEFAULT 604800  -- 7 days
);

CREATE INDEX idx_query_cache_accessed ON query_cache(last_accessed);
```

### Integration Points

#### File: `session_buddy/adapters/reflection_adapter_oneiric.py`

```python
class ReflectionDatabaseAdapterOneiric:
    def __init__(self, ...):
        # Existing initialization
        ...

        # NEW: Query cache (L1 in-memory)
        self._query_cache: dict[str, QueryCacheEntry] = {}
        self._query_cache_max_size: int = 1000
        self._query_cache_hits: int = 0
        self._query_cache_misses: int = 0

    async def search_conversations(
        self,
        query: str,
        limit: int = 10,
        project: str | None = None,
        min_similarity: float = 0.7,
        use_cache: bool = True,  # NEW parameter
    ) -> list[dict[str, Any]]:
        """Search with optional cache bypass."""

        if use_cache:
            # Try cache first
            cached = await self._check_query_cache(query, project)
            if cached is not None:
                self._query_cache_hits += 1
                return cached[:limit]

        # Cache miss - full vector search
        self._query_cache_misses += 1
        results = await self._vector_search(query, limit, project, min_similarity)

        if use_cache and results:
            await self._populate_query_cache(query, project, results)

        return results
```

### Cache Entry Data Model

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class QueryCacheEntry:
    """Cached query result entry."""
    cache_key: str
    normalized_query: str
    project: str | None
    result_ids: list[str]
    hit_count: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### Configuration

Add to `session_buddy/adapters/settings.py`:

```python
class ReflectionAdapterSettings(BaseSettings):
    # Existing settings...

    # Query cache settings
    query_cache_enabled: bool = True
    query_cache_l1_max_size: int = 1000
    query_cache_l2_ttl_days: int = 7
    query_cache_normalize_accents: bool = False  # Strip accents?
    query_cache_normalize_punctuation: bool = False  # Strip punctuation?
```

### Cache Invalidation Strategy

1. **Time-based**: L2 entries expire after TTL
1. **Event-based**: Invalidate when new conversations are stored in same project
1. **Manual**: Expose `clear_query_cache()` method
1. **Size-based**: LRU eviction for L1 when max size exceeded

```python
async def _invalidate_project_cache(self, project: str | None) -> None:
    """Invalidate cache entries for a project when new data is added."""
    # L1: Remove matching entries
    keys_to_remove = [
        k for k, v in self._query_cache.items()
        if v.project == project
    ]
    for key in keys_to_remove:
        del self._query_cache[key]

    # L2: Mark as stale (will be refreshed on next hit)
    if self.conn:
        self.conn.execute("""
            DELETE FROM query_cache WHERE project = ?
        """, [project])
```

### Metrics & Observability

```python
def get_cache_stats(self) -> dict[str, Any]:
    """Return cache performance metrics."""
    total = self._query_cache_hits + self._query_cache_misses
    hit_rate = self._query_cache_hits / total if total > 0 else 0.0

    return {
        "l1_size": len(self._query_cache),
        "l1_max_size": self._query_cache_max_size,
        "hits": self._query_cache_hits,
        "misses": self._query_cache_misses,
        "hit_rate": hit_rate,
        "embedding_cache_hits": self._cache_hits,  # Existing
        "embedding_cache_misses": self._cache_misses,  # Existing
    }
```

## Implementation Steps

### Phase 1: Core Cache Infrastructure (2-3 hours)

1. [ ] Add `QueryCacheEntry` dataclass to `session_buddy/adapters/models.py`
1. [ ] Add `normalize_query()` and `compute_cache_key()` to new `session_buddy/utils/query_cache.py`
1. [ ] Add cache settings to `ReflectionAdapterSettings`
1. [ ] Create L2 cache table in `_ensure_tables()`

### Phase 2: Integration (2-3 hours)

1. [ ] Add L1 cache dict to `ReflectionDatabaseAdapterOneiric.__init__()`
1. [ ] Implement `_check_query_cache()` method (L1 → L2 lookup)
1. [ ] Implement `_populate_query_cache()` method
1. [ ] Modify `search_conversations()` to use cache
1. [ ] Add cache invalidation to `store_conversation()` and `store_reflection()`

### Phase 3: Cleanup & Metrics (1-2 hours)

1. [ ] Implement `clear_query_cache()` method
1. [ ] Add `get_cache_stats()` method
1. [ ] Add periodic L2 cleanup (delete expired entries)
1. [ ] Clear L1 cache in `aclose()`

### Phase 4: Testing (2-3 hours)

1. [ ] Unit tests for normalization functions
1. [ ] Unit tests for cache key generation
1. [ ] Integration tests for cache hit/miss scenarios
1. [ ] Performance benchmarks comparing cached vs uncached search

### Phase 5: MCP Tool Exposure (1 hour)

1. [ ] Add `query_cache_stats` tool to expose metrics
1. [ ] Add `clear_query_cache` tool for manual invalidation
1. [ ] Update `reflection_stats` to include cache stats

## Dependencies

**New dependency** (optional but recommended for speed):

```toml
[project.optional-dependencies]
performance = ["xxhash>=3.0"]  # Fast non-cryptographic hashing
```

**Fallback**: Use `hashlib.blake2b` if xxhash not available (still fast, stdlib).

## Expected Performance Impact

| Scenario | Current | With Cache |
|----------|---------|------------|
| Repeated exact query | ~50-100ms | \<1ms |
| Similar query (normalized match) | ~50-100ms | \<1ms |
| New unique query | ~50-100ms | ~50-100ms + cache write |
| Cache hit rate (estimated) | 0% | 30-50% for active sessions |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Stale results after new data | Invalidate on store operations |
| Memory bloat from L1 cache | LRU eviction at max size |
| Cache key collisions | Use 64-bit hash (collision probability ~1e-10 for 1M entries) |
| Complexity increase | Well-isolated module, can disable via config |

## Success Criteria

- [ ] Cache hit rate >30% for typical session workflows
- [ ] No regression in search result quality
- [ ] \<1ms latency for cache hits
- [ ] Zero memory leaks (L1 properly cleared on close)
- [ ] All existing tests pass
- [ ] New cache tests achieve >90% coverage

## References

- DeepSeek Engram: https://github.com/deepseek-ai/Engram
- xxhash Python: https://github.com/ifduyue/python-xxhash
- LRU Cache patterns: https://docs.python.org/3/library/functools.html#functools.lru_cache
