# Comprehensive Memory Enhancement Plan

> **Complete implementation guide for 5 complementary memory features with integration architecture**
>
> **Created**: January 20, 2026
>
> **Status**: Ready for Implementation
>
> **Estimated Duration**: 35-45 days total

## Table of Contents

- [Part 1: Architecture & Integration](#part-1-architecture--integration)
- [Part 2: Implementation Phases](#part-2-implementation-phases)
- [Part 3: Cross-Cutting Concerns](#part-3-cross-cutting-concerns)
- [Part 4: Reference Materials](#part-4-reference-materials)
- [Appendices](#appendices)

---

# Part 1: Architecture & Integration

## Feature Overview

| # | Feature | Inspiration | Layer | Est. Days | Priority |
|---|---------|-------------|-------|-----------|----------|
| 1 | Query Cache | Engram | Retrieval | 6-8 | **High** |
| 2 | N-gram Fingerprinting | Engram | Storage | 8-10 | Medium |
| 3 | Query Rewriting | MemU | Understanding | 7-9 | **High** |
| 4 | Progressive Search | MemU | Strategy | 6-8 | Medium |
| 5 | Category Evolution | MemU | Organization | 8-10 | Medium |

`★ Insight ─────────────────────────────────────`
**Layer Separation Principle**: Each feature operates at a distinct layer:
- **Rewriting** operates on the query before processing
- **Caching** shortcuts expensive operations
- **Progressive Search** controls search scope
- **Fingerprinting** validates before storage
- **Evolution** organizes after storage

This separation enables independent development, testing, and gradual rollout.
`─────────────────────────────────────────────────`

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           COMPLETE DATA FLOW                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                    │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ QUERY PROCESSING PIPELINE (Phases 1-3)                                    │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                            │ │
│  │  User Query ──┬──► [Phase 2] Query Rewriting ──┬──► Expanded Query       │ │
│  │               │      (LLM expands pronouns)     │                          │ │
│  │               └──────────────────────────────────┘                          │ │
│  │                                                     │                        │                 │
│  │                                                     ▼                        │                 │
│  │  [Phase 1] Query Cache Lookup (hash-based O(1))                        │ │
│  │                     │                                    │                 │
│  │                     ├─ Hit? ──────────────────────────► Return (<1ms)   │ │
│  │                     │                                                        │ │
│  │                     └─ Miss ────────────────────────────┐                  │ │
│  │                                                          │                  │ │
│  │                                                          ▼                  │ │
│  │                                         ┌──────────────────────────────────┐       │ │
│  │                                         │ [Phase 3] Progressive Search    │       │ │
│  │                                         │ ├─ Tier 1: Categories       │       │ │
│  │                                         │ ├─ Tier 2: Insights           │       │ │
│  │                                         │ ├─ Tier 3: Reflections       │       │ │
│  │                                         │ ├─ Tier 4: Conversations      │       │ │
│  │                                         │ │   (stop when sufficient)    │       │ │
│  │                                         │ └──────────────────────────────────┘       │ │
│  │                                                            │             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                    │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ STORAGE & ORGANIZATION PIPELINE (Phases 4-5)                                  │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                            │ │
│  │  New Content ──┬──► [Phase 4] N-gram Fingerprinting ──┬──► Duplicate?     │ │
│  │               │      (MinHash signature)              │                  │ │
│  │               │                                       │                  │ │
│  │               │                                       ├─ Yes ──► Skip/Merge │ │
│  │               │                                       │                  │ │
│  │               │                                       └─ No ────┐        │ │
│  │               │                                                 │        │ │
│  │               └─────────────────────────────────────────────────┘        │ │
│  │                                                                   │        │ │
│  │                                                                   ▼        │ │
│  │                                                      Store Content         │ │
│  │                                                                   │        │ │
│  │                                                                   ▼        │ │
│  │                                         ┌──────────────────────────────────┐       │ │
│  │                                         │ [Phase 5] Category Evolution    │       │ │
│  │                                         │ (background clustering job)    │       │ │
│  │                                         │ ├─ Assign to subcategory      │       │ │
│  │                                         │ ├─ Update cluster centroids   │       │ │
│  │                                         │ └─ Reorganize periodically    │       │ │
│  │                                         └──────────────────────────────────┘       │ │
│  │                                                                                    │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Critical Integration Points

### 1. Query Cache + Query Rewriting (🎯 CRITICAL)

**Synergy**: Cache rewritten queries for conversational memory

**Implementation**:

```python
# session_buddy/adapters/reflection_adapter_oneiric.py

async def search_conversations(
    self,
    query: str,
    *,
    enable_query_rewrite: bool = True,
    conversation_context: list[dict] | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """Search with integrated rewriting and caching."""

    rewrite_result = None
    effective_query = query

    # Phase 2: Rewrite query if enabled
    if enable_query_rewrite and self._query_rewriter:
        rewrite_result = await self._query_rewriter.rewrite(
            query=query,
            context=conversation_context,
        )
        effective_query = rewrite_result.expanded_query

        # INTEGRATION POINT: Include rewrite signature in cache key
        # to avoid cache collisions when same query refers to different
        # entities in different contexts
        context_hash = xxhash.xxh64(
            json.dumps(conversation_context[-5:], sort_keys=True).encode()
        ).hexdigest() if conversation_context else "none"
    else:
        context_hash = "none"

    # Phase 1: Check cache with context-aware key
    if use_cache:
        cache_key = f"{context_hash}:{compute_cache_key(effective_query, self.project)}"

        cached = await self._check_query_cache(cache_key)
        if cached is not None:
            # INTEGRATION POINT: Include rewrite metadata in cached results
            results = cached[:limit]
            if rewrite_result and rewrite_result.was_rewritten:
                for r in results:
                    r.setdefault("_metadata", {})["_query_rewrite"] = {
                        "original": rewrite_result.original_query,
                        "expanded": rewrite_result.expanded_query,
                        "confidence": rewrite_result.confidence,
                    }
            return results

    # Cache miss - proceed with search
    results = await self._vector_search(effective_query, limit, project, min_score)

    # Populate cache (with context-aware key)
    if use_cache and results:
        await self._populate_query_cache(cache_key, results, effective_query)

    return results
```

**Cache Key Strategy**:
```python
# Separate cache entries for different query variants
cache_keys = {
    "original": "abc123",                    # "what did he say"
    "rewritten_ctxA": "def456",              # "what did John say" (ctx A)
    "rewritten_ctxB": "ghi789",              # "what did Mike say" (ctx B)
}
```

### 2. N-gram Fingerprinting + Category Evolution (🎯 HIGH VALUE)

**Synergy**: Use fingerprints for fast subcategory pre-filtering

**Implementation**:

```python
# session_buddy/memory/category_evolution.py

class CategoryEvolutionEngine:
    async def assign_subcategory(
        self,
        memory: dict[str, Any],
        use_fingerprint_pre_filter: bool = True,  # NEW
    ) -> CategoryAssignment:
        """Assign memory to subcategory with fingerprint pre-filtering."""

        category = TopLevelCategory(memory.get("category", "context"))
        subcategories = self._subcategories.get(category, [])

        if not subcategories:
            return CategoryAssignment(
                memory_id=memory.get("id"),
                category=category,
                subcategory=None,
                confidence=1.0,
            )

        # INTEGRATION POINT: Fast fingerprint-based pre-filtering
        if use_fingerprint_pre_filter and memory.get("fingerprint"):
            fingerprint_sig = MinHashSignature.from_bytes(
                memory["fingerprint"],
                num_hashes=self.settings.fingerprint_num_hashes
            )

            # Find fingerprint-based matches
            fingerprint_matches = []
            for subcat in subcategories:
                if subcat.centroid_fingerprint:  # NEW: Store fingerprint in subcategory
                    similarity = fingerprint_sig.jaccard_similarity(
                        MinHashSignature.from_bytes(
                            subcat.centroid_fingerprint,
                            num_hashes=self.settings.fingerprint_num_hashes
                        )
                    )
                    if similarity >= 0.90:  # High confidence threshold
                        fingerprint_matches.append((subcat, similarity))

            if fingerprint_matches:
                # Use best fingerprint match
                best_subcat, best_sim = max(fingerprint_matches, key=lambda x: x[1])
                return CategoryAssignment(
                    memory_id=memory.get("id"),
                    category=category,
                    subcategory=best_subcat.name,
                    confidence=best_sim,
                    method="fingerprint",
                )

        # Fallback to embedding-based assignment (60-80% slower)
        # ... [embedding code here]

        return CategoryAssignment(
            memory_id=memory.get("id"),
            category=category,
            subcategory=best_subcat.name if best_subcat else None,
            confidence=best_similarity,
            method="embedding",
        )
```

**Performance Benefit**: Fingerprint pre-filtering achieves ~60-80% reduction in embedding similarity computations.

### 3. Query Cache + Progressive Search (🎯 MEDIUM VALUE)

**Synergy**: Tier-specific caching with early termination

**Implementation**:

```python
# session_buddy/memory/progressive_search.py

class ProgressiveSearchEngine:
    async def search(
        self,
        query: str,
        tiers: list[SearchTier] | None = None,
        use_cache: bool = True,  # NEW
        **kwargs
    ) -> ProgressiveSearchResult:
        """Progressive search with tier-aware caching."""

        tiers = tiers or self.DEFAULT_TIERS
        all_results: list[dict] = []
        tier_results: list[TierSearchResult] = []

        for tier in tiers:
            tier_start = datetime.now(UTC)

            # INTEGRATION POINT: Check cache for this specific tier
            if use_cache:
                cache_key = f"tier:{tier.value}:{compute_cache_key(query, self.project)}"
                cached = await self._check_tier_cache(cache_key)

                if cached is not None:
                    tier_time = (datetime.now(UTC) - tier_start).total_seconds() * 1000

                    tier_result = TierSearchResult(
                        tier=tier,
                        results=cached,
                        search_time_ms=tier_time,
                        total_in_tier=len(cached),
                        matched_count=len(cached),
                        from_cache=True,  # NEW: Track cache hits
                    )
                    tier_results.append(tier_result)
                    all_results.extend(cached)

                    # Check sufficiency with cached results
                    if self._is_sufficient(all_results, [tier]):
                        return ProgressiveSearchResult(
                            query=query,
                            results=all_results,
                            tiers_searched=[tier],
                            stopped_early=True,
                            stop_reason=f"Sufficient cached results from {tier.value}",
                            tier_results=tier_results,
                        )
                    continue  # Try next tier even with cached results

            # Cache miss - search this tier
            tier_matches = await self._search_tier(
                tier=tier,
                query=query,
                **kwargs
            )

            tier_time = (datetime.now(UTC) - tier_start).total_seconds() * 1000

            # INTEGRATION POINT: Cache tier results
            if use_cache and tier_matches:
                cache_key = f"tier:{tier.value}:{compute_cache_key(query, self.project)}"
                await self._populate_tier_cache(cache_key, tier_matches)

            # Record tier results
            tier_result = TierSearchResult(
                tier=tier,
                results=tier_matches,
                search_time_ms=tier_time,
                total_in_tier=len(tier_matches),
                matched_count=len(tier_matches),
                from_cache=False,
            )
            tier_results.append(tier_result)
            all_results.extend(tier_matches)

            # Check sufficiency
            if self._is_sufficient(all_results, [tier]):
                break

        # Deduplicate and return
        unique_results = self._deduplicate_results(all_results)
        return ProgressiveSearchResult(
            query=query,
            results=unique_results,
            tiers_searched=tiers,
            tier_results=tier_results,
        )
```

### 4. Query Rewriting + Progressive Search (🔧 REQUIRES DESIGN)

**Design Decision**: Should rewritten queries apply to all tiers or only detailed tiers?

**Recommended Strategy**:

```python
async def progressive_search_with_rewriting(
    self,
    query: str,
    conversation_context: list[dict] | None = None,
    **kwargs
) -> ProgressiveSearchResult:
    """Progressive search with tier-specific query application."""

    # Rewrite once upfront
    rewrite_result = await self._query_rewriter.rewrite(
        query=query,
        context=conversation_context
    )

    # Use ORIGINAL query for abstract tiers (categories, insights)
    # Use REWRITTEN query for concrete tiers (reflections, conversations)

    tier_queries = {
        SearchTier.CATEGORIES: query,  # Original
        SearchTier.INSIGHTS: query,      # Original
        SearchTier.REFLECTIONS: rewrite_result.expanded_query,  # Expanded
        SearchTier.CONVERSATIONS: rewrite_result.expanded_query,  # Expanded
    }

    all_results = []

    for tier in [SearchTier.CATEGORIES, SearchTier.INSIGHTS,
                 SearchTier.REFLECTIONS, SearchTier.CONVERSATIONS]:
        effective_query = tier_queries[tier]

        # Search with tier-specific query
        results = await self._search_tier(tier, effective_query, **kwargs)
        all_results.extend(results)

        if self._is_sufficient(all_results, [tier]):
            break

    return ProgressiveSearchResult(
        query=query,
        results=all_results,
        query_used=tier_queries,  # Track which query was used per tier
        rewrite_metadata=rewrite_result,
    )
```

**Rationale**:
- **Categories/Insights** are high-level summaries → original query captures intent
- **Reflections/Conversations** are detailed content → rewritten query resolves references

### 5. N-gram Fingerprinting + Query Cache (⚠️ CACHE INVALIDATION)

**Conflict**: Cached results might reference duplicate content that gets merged/deleted

**Resolution**:

```python
# session_buddy/adapters/reflection_adapter_oneiric.py

async def merge_duplicate(
    self,
    duplicate_id: str,
    canonical_id: str,
    content_type: Literal["conversation", "reflection"],
) -> str:
    """Merge duplicate content and invalidate affected cache entries."""

    # Merge the records
    await self._merge_records(duplicate_id, canonical_id, content_type)

    # INTEGRATION POINT: Invalidate cache entries referencing duplicate ID
    await self._invalidate_cache_for_content_id(duplicate_id)

    return canonical_id


async def _invalidate_cache_for_content_id(
    self,
    content_id: str,
) -> None:
    """Invalidate all cache entries that reference a specific content ID."""

    # L1: Remove from memory cache
    keys_to_remove = []
    for key, entry in self._query_cache.items():
        if content_id in entry.result_ids:
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del self._query_cache[key]

    # L2: Mark as stale in DuckDB
    if self.conn:
        self.conn.execute("""
            UPDATE query_cache
            SET last_accessed = NULL  -- Mark for cleanup
            WHERE ? = ANY(result_ids)
        """, [content_id])
```

## Conflict Resolution Matrix

| Conflict Pair | Severity | Resolution Strategy | Status |
|---------------|----------|---------------------|----------|
| Query Cache + N-gram Dedup | Low | Invalidate cache entries on merge | ✅ Documented |
| Query Rewriting + Progressive Search | Low | Tier-specific query application | ✅ Documented |
| Category Evolution + Fingerprint | None | No conflict - fingerprints are category-agnostic | ✅ Verified |
| Query Cache + Query Rewriting | None | Context-aware cache keys | ✅ Documented |
| Progressive Search + Query Cache | None | Tier-specific cache entries | ✅ Documented |

## Feature Flag Configuration

```python
# session_buddy/adapters/settings.py

@dataclass
class MemoryEnhancementSettings:
    """Unified settings with feature flags for gradual rollout."""

    # Phase 1: Query Cache
    enable_query_cache: bool = True
    query_cache_l1_max_size: int = 1000
    query_cache_l2_ttl_days: int = 7

    # Phase 2: Query Rewriting
    enable_query_rewriting: bool = True
    query_rewrite_cache_enabled: bool = True
    query_rewrite_context_sensitive: bool = True  # INTEGRATION: Context-aware keys

    # Phase 3: Progressive Search
    enable_progressive_search: bool = True
    progressive_search_default: bool = False  # Start opt-in
    progressive_search_cache_aware: bool = True  # INTEGRATION: Tier-specific caching

    # Phase 4: N-gram Fingerprinting
    enable_deduplication: bool = True
    dedup_cache_invalidation: bool = True  # INTEGRATION: Invalidate on merge

    # Phase 5: Category Evolution
    enable_category_evolution: bool = True
    evolution_fingerprint_prefilter: bool = True  # INTEGRATION: Fast assignment
    evolution_use_clean_data: bool = True  # INTEGRATION: Benefit from dedup

    # Integrated mode
    integrated_features: bool = True  # When True, features coordinate

    # Rollout controls
    rollout_percentage: float = 1.0  # 0.0 to 1.0 for gradual rollout

    def validate(self) -> list[str]:
        """Validate integration settings."""
        errors = []

        # Check integration dependencies
        if self.integrated_features:
            # If rewriting is context-sensitive, cache must be enabled
            if (self.enable_query_rewriting and
                self.query_rewrite_context_sensitive and
                not self.enable_query_cache):
                errors.append(
                    "Context-sensitive rewriting requires query cache to be enabled"
                )

            # If progressive search is cache-aware, cache must be enabled
            if (self.enable_progressive_search and
                self.progressive_search_cache_aware and
                not self.enable_query_cache):
                errors.append(
                    "Cache-aware progressive search requires query cache to be enabled"
                )

            # If category evolution uses fingerprints, dedup must be enabled
            if (self.enable_category_evolution and
                self.evolution_fingerprint_prefilter and
                not self.enable_deduplication):
                errors.append(
                    "Fingerprint pre-filtering requires deduplication to be enabled"
                )

        return errors
```

---

# Part 2: Implementation Phases

## Phase 1: Foundation (Query Cache) - Days 1-8

**Focus**: Query Cache (Engram Feature 1)

**Integration Context**: This phase establishes the cache infrastructure that will be used by Phases 2, 3, and 5. We must prepare integration hooks for future phases.

### Implementation Tasks

#### 1.1 Create Core Cache Module (2-3 hours)
- [ ] Create `session_buddy/utils/query_cache.py`
- [ ] Add `normalize_query()` function (NFKC, lowercase, collapse whitespace)
- [ ] Add `compute_cache_key()` function using xxhash
- [ ] Add `QueryCacheEntry` dataclass
- [ ] Unit tests for normalization and key generation

```python
# session_buddy/utils/query_cache.py

import unicodedata
import xxhash
from dataclasses import dataclass
from typing import Any

@dataclass
class QueryCacheEntry:
    """Cache entry with metadata."""
    cache_key: str
    normalized_query: str
    project: str | None
    result_ids: list[str]
    hit_count: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    ttl_seconds: int = 604800

    # INTEGRATION: Fields for future phases
    tier: str | None = None  # Phase 3: Progressive Search
    context_hash: str | None = None  # Phase 2: Query Rewriting


def normalize_query(query: str) -> str:
    """Normalize query for cache key generation."""
    text = unicodedata.normalize("NFKC", query)
    text = text.lower()
    text = " ".join(text.split())
    return text.strip()


def compute_cache_key(normalized_query: str, project: str | None = None) -> str:
    """Compute deterministic cache key using xxhash for speed."""
    key_input = f"{project or 'global'}:{normalized_query}"
    return xxhash.xxh64(key_input.encode()).hexdigest()
```

#### 1.2 Create Database Schema (1 hour)
- [ ] Add L2 cache table in `_ensure_tables()`
- [ ] Add indexes for performance
- [ ] Create migration script for existing databases

```sql
-- In session_buddy/adapters/reflection_adapter_oneiric.py _ensure_tables()

CREATE TABLE IF NOT EXISTS query_cache (
    cache_key TEXT PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    project TEXT,
    result_ids TEXT[],
    hit_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ttl_seconds INTEGER DEFAULT 604800,

    -- INTEGRATION: Fields for future phases
    tier TEXT,  -- Phase 3: 'categories', 'insights', 'reflections', 'conversations'
    context_hash TEXT,  -- Phase 2: Hash of conversation context for rewrites
    content_ids TEXT[]  -- Phase 4: Track actual content IDs for invalidation
);
CREATE INDEX idx_query_cache_accessed ON query_cache(last_accessed);
CREATE INDEX idx_query_cache_tier ON query_cache(tier);  -- Phase 3
```

#### 1.3 Add L1 Cache to Adapter (2 hours)
- [ ] Add `_query_cache: dict[str, QueryCacheEntry]` to `__init__()`
- [ ] Add `_query_cache_max_size`, `_query_cache_hits`, `_query_cache_misses` counters
- [ ] Add cache settings to `ReflectionAdapterSettings`

```python
# In session_buddy/adapters/settings.py

@dataclass
class ReflectionAdapterSettings(BaseSettings):
    # Existing settings...

    # Phase 1: Query Cache settings
    enable_query_cache: bool = True
    query_cache_l1_max_size: int = 1000
    query_cache_l2_ttl_days: int = 7
    query_cache_normalize_accents: bool = False
    query_cache_normalize_punctuation: bool = False

# In session_buddy/adapters/reflection_adapter_oneiric.py

class ReflectionDatabaseAdapterOneiric:
    def __init__(self, settings: ReflectionAdapterSettings):
        # Existing initialization...

        # Phase 1: L1 cache
        self._query_cache: dict[str, QueryCacheEntry] = {}
        self._query_cache_max_size = settings.query_cache_l1_max_size
        self._query_cache_hits = 0
        self._query_cache_misses = 0
```

#### 1.4 Implement Cache Methods (3-4 hours)
- [ ] `_check_query_cache()` - L1 → L2 lookup
- [ ] `_populate_query_cache()` - store results with LRU eviction
- [ ] `_invalidate_project_cache()` - event-based invalidation
- [ ] `_invalidate_cache_for_content_id()` - Phase 4 integration hook
- [ ] `clear_query_cache()` - manual cleanup

```python
async def _check_query_cache(self, cache_key: str) -> list[dict] | None:
    """Check cache (L1 then L2)."""

    # L1: Memory cache (fast)
    if cache_key in self._query_cache:
        entry = self._query_cache[cache_key]
        entry.last_accessed = datetime.now()
        entry.hit_count += 1
        self._query_cache_hits += 1

        # Retrieve full results from L2
        results = await self._get_cached_results(entry.result_ids)
        return results

    self._query_cache_misses += 1

    # L2: DuckDB persistent cache
    row = self.conn.execute("""
        SELECT result_ids
        FROM query_cache
        WHERE cache_key = ?
          AND (datetime('now') - created_at) < INTERVAL 1 SECOND * ttl_seconds
          AND last_accessed IS NOT NULL
    """, [cache_key]).fetchone()

    if row:
        # Promote to L1
        result_ids = row[0]
        results = await self._get_cached_results(result_ids)
        if results:
            await self._populate_l1_cache(cache_key, results)
        return results

    return None


async def _populate_query_cache(
    self,
    cache_key: str,
    results: list[dict],
    query: str,
    tier: str | None = None,  # Phase 3
    context_hash: str | None = None,  # Phase 2
) -> None:
    """Populate cache with results (L1 + L2)."""

    result_ids = [r.get("id") for r in results if r.get("id")]

    # L1: Memory cache with LRU eviction
    if len(self._query_cache) >= self._query_cache_max_size:
        # Evict least recently used
        lru_key = min(self._query_cache.items(),
                     key=lambda x: x[1].last_accessed)[0]
        del self._query_cache[lru_key]

    self._query_cache[cache_key] = QueryCacheEntry(
        cache_key=cache_key,
        normalized_query=query,
        project=self.project,
        result_ids=result_ids,
        tier=tier,  # Phase 3
        context_hash=context_hash,  # Phase 2
    )

    # L2: DuckDB persistent cache
    self.conn.execute("""
        INSERT OR REPLACE INTO query_cache
        (cache_key, normalized_query, project, result_ids, tier, context_hash)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [cache_key, query, self.project, result_ids, tier, context_hash])


async def _invalidate_cache_for_content_id(self, content_id: str) -> None:
    """Phase 4 INTEGRATION: Invalidate cache entries referencing content ID."""

    # L1: Remove from memory cache
    keys_to_remove = []
    for key, entry in self._query_cache.items():
        if content_id in entry.result_ids:
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del self._query_cache[key]

    # L2: Mark as stale in DuckDB
    self.conn.execute("""
        UPDATE query_cache
        SET last_accessed = NULL
        WHERE ? = ANY(result_ids)
    """, [content_id])
```

#### 1.5 Modify Search Methods to Use Cache (2 hours)
- [ ] Update `search_conversations()` with cache integration
- [ ] Update `search_reflections()` with cache integration
- [ ] Add `use_cache: bool = True` parameter

#### 1.6 Add Metrics and MCP Tools (2 hours)
- [ ] `get_cache_stats()` method
- [ ] `query_cache_stats` MCP tool
- [ ] `clear_query_cache` MCP tool

### Integration Preparation
- [ ] Add `content_id` field to cache entries for Phase 4 dedup invalidation
- [ ] Add `tier` field to cache entries for Phase 3 progressive search
- [ ] Add `context_hash` field for Phase 2 query rewriting

### Success Criteria
- [ ] Cache hit rate >30% for typical session workflows
- [ ] <1ms latency for cache hits
- [ ] Zero memory leaks (L1 cleared on close)
- [ ] All existing tests pass

---

## Phase 2: Query Enhancement (Query Rewriting) - Days 9-17

**Focus**: Query Rewriting (MemU Feature 1)

**Integration Context**: This phase enhances the cache from Phase 1 with context-aware caching. Must coordinate with Phase 3 for tier-specific query application.

### Implementation Tasks

#### 2.1 Create Query Rewriter Module (3-4 hours)
- [ ] Create `session_buddy/memory/query_rewriter.py`
- [ ] Add `QueryRewriteResult` dataclass
- [ ] Add `AmbiguityDetector` class (pronouns, demonstratives, temporal refs)
- [ ] Add `QueryRewriter` class with LLM integration
- [ ] Add rewrite prompt template

#### 2.2 Implement Core Rewrite Logic (3-4 hours)
- [ ] `rewrite()` method with fast paths
- [ ] `_format_context()` for conversation history
- [ ] `_call_llm()` using configured provider
- [ ] `_calculate_confidence()` for validation

#### 2.3 Add Rewrite Settings (1 hour)
- [ ] Add `QueryRewriteSettings` dataclass
- [ ] Integrate with `MemoryEnhancementSettings`

#### 2.4 Integrate with Search Methods (2 hours)
- [ ] Add `enable_query_rewrite` parameter to search methods
- [ ] Add `conversation_context` parameter for context
- [ ] Include `_query_rewrite` metadata in results

#### 2.5 Implement Rewrite Caching with Cache Integration (2-3 hours)
- [ ] Cache rewritten queries separately from originals
- [ ] Include rewrite signature in cache key
- [ ] Invalidate on context changes

```python
# Integration with Phase 1 cache
async def search_with_rewriting_and_cache(
    self,
    query: str,
    conversation_context: list[dict] | None = None,
    **kwargs
) -> list[dict]:
    """Search with rewriting and context-aware caching."""

    # Rewrite query
    rewrite_result = await self._query_rewriter.rewrite(
        query=query,
        context=conversation_context
    )

    effective_query = rewrite_result.expanded_query

    # INTEGRATION: Context-aware cache key
    context_hash = xxhash.xxh64(
        json.dumps(conversation_context[-5:], sort_keys=True).encode()
    ).hexdigest() if conversation_context else "none"

    # Check cache with context-aware key
    cache_key = f"{context_hash}:{compute_cache_key(effective_query, self.project)}"

    cached = await self._check_query_cache(cache_key)
    if cached is not None:
        # Add rewrite metadata
        for r in cached:
            r.setdefault("_metadata", {})["_query_rewrite"] = {
                "original": rewrite_result.original_query,
                "expanded": rewrite_result.expanded_query,
                "confidence": rewrite_result.confidence,
            }
        return cached

    # Cache miss - search and populate
    results = await self._vector_search(effective_query, **kwargs)

    if results:
        await self._populate_query_cache(
            cache_key=cache_key,
            results=results,
            query=effective_query,
            context_hash=context_hash
        )

    return results
```

#### 2.6 Add MCP Tools (1 hour)
- [ ] `rewrite_query` tool for testing/debugging
- [ ] `query_rewrite_stats` tool for metrics

### Success Criteria
- [ ] >80% ambiguous query resolution rate
- [ ] <200ms average latency increase
- [ ] Graceful fallback when LLM unavailable
- [ ] Rewrite caching >50% hit rate for repeated contexts

---

## Phase 3: Progressive Search - Days 18-25

**Focus**: Progressive Search (MemU Feature 2)

**Integration Context**: This phase leverages both Phase 1 (cache) and Phase 2 (rewriting) for tier-aware caching and query application.

### Implementation Tasks

#### 3.1 Create Progressive Search Module (3-4 hours)
- [ ] Create `session_buddy/memory/progressive_search.py`
- [ ] Add `SearchTier` enum (CATEGORIES, INSIGHTS, REFLECTIONS, CONVERSATIONS)
- [ ] Add `TierSearchResult` dataclass
- [ ] Add `ProgressiveSearchResult` dataclass
- [ ] Add `SufficiencyConfig` dataclass

#### 3.2 Implement Sufficiency Evaluation (2 hours)
- [ ] `SufficiencyEvaluator` class
- [ ] `is_sufficient()` method with multiple criteria
- [ ] Configurable thresholds (min_results, min_avg_score, tier_coverage)

#### 3.3 Implement Progressive Search Engine (3-4 hours)
- [ ] `ProgressiveSearchEngine` class
- [ ] `search()` method with tier iteration
- [ ] `_search_tier()` method per tier
- [ ] `_search_categories()` proxy (high-quality insights)
- [ ] `_deduplicate_results()` method

#### 3.4 Integrate with Existing Adapter (2 hours)
- [ ] Hook into `search_insights()` for Tier 2
- [ ] Ensure `search_reflections()` works for Tier 3
- [ ] Ensure `search_conversations()` works for Tier 4

#### 3.5 Add Tier-Specific Caching (3 hours)
- [ ] Check cache for each specific tier
- [ ] Cache results per tier
- [ ] Enable tier-aware cache hits
- [ ] Update cache stats to show tier breakdown

```python
# Integration with Phase 1 cache
async def search_with_tier_cache(
    self,
    query: str,
    **kwargs
) -> ProgressiveSearchResult:
    """Progressive search with tier-aware caching."""

    tiers = [SearchTier.CATEGORIES, SearchTier.INSIGHTS,
             SearchTier.REFLECTIONS, SearchTier.CONVERSATIONS]

    for tier in tiers:
        # INTEGRATION: Check cache for this specific tier
        cache_key = f"tier:{tier.value}:{compute_cache_key(query, self.project)}"
        cached = await self._check_tier_cache(cache_key)

        if cached is not None:
            # Add tier metadata
            tier_result = TierSearchResult(
                tier=tier,
                results=cached,
                from_cache=True,
            )
            # Check sufficiency with cached results
            if self._is_sufficient(all_results, [tier]):
                return ProgressiveSearchResult(
                    stopped_early=True,
                    stop_reason=f"Sufficient cached results from {tier.value}",
                    tier_results=[tier_result],
                )

        # Cache miss - search this tier
        tier_matches = await self._search_tier(tier, query, **kwargs)

        # INTEGRATION: Cache tier results
        cache_key = f"tier:{tier.value}:{compute_cache_key(query, self.project)}"
        await self._populate_tier_cache(cache_key, tier_matches)

        # Check sufficiency
        if self._is_sufficient(all_results, [tier]):
            break

    return ProgressiveSearchResult(...)
```

#### 3.6 Add Tier-Specific Query Application (2 hours)
- [ ] Apply original query to Categories/Insights tiers
- [ ] Apply rewritten query to Reflections/Conversations tiers
- [ ] Track which query was used per tier in results

#### 3.7 Add MCP Tool (1 hour)
- [ ] `progressive_search` tool
- [ ] Return results with tier metadata
- [ ] Include `stopped_early` and `stop_reason` in response

### Success Criteria
- [ ] Average tiers searched <2.5 for typical queries
- [ ] >30% search time reduction vs full search
- [ ] Result quality maintained or improved
- [ ] Graceful degradation to single-tier if needed

---

## Phase 4: Data Quality (N-gram Fingerprinting) - Days 26-35

**Focus**: N-gram Fingerprinting (Engram Feature 2)

**Integration Context**: This phase adds cache invalidation hooks (Phase 1) and provides fingerprints for Phase 5 category evolution.

### Implementation Tasks

#### 4.1 Create Fingerprint Module (3-4 hours)
- [ ] Create `session_buddy/utils/fingerprint.py`
- [ ] Add `normalize_for_fingerprint()` function
- [ ] Add `extract_ngrams()` function (character n-grams)
- [ ] Add `MinHashSignature` dataclass
- [ ] Implement `from_ngrams()` class method
- [ ] Implement `jaccard_similarity()` method
- [ ] Implement `to_bytes()` / `from_bytes()` serialization

#### 4.2 Add Fingerprint Settings (1 hour)
- [ ] Add deduplication settings to `ReflectionAdapterSettings`

#### 4.3 Create Fingerprint Schema (2 hours)
- [ ] Add `fingerprint BLOB` column to `conversations` table
- [ ] Add `fingerprint BLOB` column to `reflections` table
- [ ] Create `content_fingerprints` index table
- [ ] Create migration script for existing databases

#### 4.4 Implement Deduplication Logic (3-4 hours)
- [ ] `DeduplicationResult` dataclass
- [ ] `check_duplicate()` method
- [ ] `merge_conversation()` method for near-duplicates
- [ ] `_store_fingerprint()` helper method

#### 4.5 Integrate into Storage Methods (2-3 hours)
- [ ] Modify `store_conversation()` with deduplication
- [ ] Modify `store_reflection()` with deduplication
- [ ] Add `deduplicate: bool = True` parameter

#### 4.6 Implement Cache Invalidation Integration (2 hours)
- [ ] Call `_invalidate_cache_for_content_id()` on duplicate merge
- [ ] Test cache invalidation with deduplication

```python
# Integration with Phase 1 cache
async def store_with_deduplication(
    self,
    content: str,
    **kwargs
) -> str:
    """Store content with deduplication and cache invalidation."""

    # Check for duplicates
    dedup_result = await self.check_duplicate(content, "conversation")

    if dedup_result.action == "skip":
        # Return existing ID, no cache invalidation needed
        return dedup_result.similar_id

    if dedup_result.action == "merge":
        # Merge with existing content
        conv_id = await self.merge_conversation(
            duplicate_id=dedup_result.similar_id,
            new_content=content,
            ...
        )

        # INTEGRATION: Invalidate cache entries referencing merged content
        await self._invalidate_cache_for_content_id(dedup_result.similar_id)

        return conv_id

    # Generate fingerprint and store
    ngrams = extract_ngrams(content, n=self.settings.fingerprint_ngram_size)
    fingerprint = MinHashSignature.from_ngrams(ngrams).to_bytes()

    # Store with fingerprint
    conv_id = str(uuid.uuid4())
    # ... INSERT logic with fingerprint column ...

    return conv_id
```

#### 4.7 Add Optional Dependency (1 hour)
- [ ] Add xxhash to optional dependencies in pyproject.toml
- [ ] Implement fallback using `hashlib.blake2b`

#### 4.8 Add MCP Tools (1 hour)
- [ ] `deduplication_stats` tool
- [ ] `find_duplicates` tool to scan existing data
- [ ] Update `reflection_stats` to include dedup metrics

### Success Criteria
- [ ] >90% exact duplicate detection
- [ ] >70% near-duplicate (>85% similar) detection
- [ ] <1% false positive rate
- [ ] Store latency increase <50% (target <15ms)
- [ ] 15-30% database size reduction over time

---

## Phase 5: Organization (Category Evolution) - Days 36-45

**Focus**: Category Evolution (MemU Feature 3)

**Integration Context**: This phase leverages fingerprints from Phase 4 for fast assignment and benefits from deduplicated data.

### Implementation Tasks

#### 5.1 Create Category Evolution Module (4-5 hours)
- [ ] Create `session_buddy/memory/category_evolution.py`
- [ ] Add `TopLevelCategory` enum (FACTS, PREFERENCES, SKILLS, RULES, CONTEXT)
- [ ] Add `Subcategory` dataclass
- [ ] Add `CategoryAssignment` dataclass
- [ ] Add `KeywordExtractor` class
- [ ] Add `SubcategoryClusterer` class
- [ ] Add `CategoryEvolutionEngine` class

#### 5.2 Implement Clustering Logic (3-4 hours)
- [ ] `KeywordExtractor.extract()` with stop words and tech terms
- [ ] `SubcategoryClusterer.cluster_memories()` method
- [ ] `_cosine_similarity()` for embedding comparison
- [ ] `_update_centroid()` for incremental learning
- [ ] `_create_new_subcategories()` for new clusters

#### 5.3 Add Category Evolution Schema (2 hours)
- [ ] Create `memory_subcategories` table
- [ ] Add `subcategory` columns to conversations/reflections
- [ ] Add `centroid_fingerprint` BLOB column to subcategories

#### 5.4 Implement Evolution Engine (3-4 hours)
- [ ] `evolve_category()` method
- [ ] `assign_subcategory()` for new memories
- [ ] `get_subcategories()` query method
- [ ] `_get_category_memories()` helper
- [ ] `_persist_subcategories()` storage

#### 5.5 Implement Fingerprint Pre-Filtering (2-3 hours)
- [ ] Add fingerprint-based pre-filtering to `assign_subcategory()`
- [ ] Store fingerprint centroids in subcategories
- [ ] Fallback to embedding-based assignment

```python
# Integration with Phase 4 fingerprints
async def assign_with_fingerprint_pre_filter(
    self,
    memory: dict[str, Any],
    use_fingerprint_pre_filter: bool = True,
) -> CategoryAssignment:
    """Assign memory to subcategory with fingerprint pre-filtering."""

    if use_fingerprint_pre_filter and memory.get("fingerprint"):
        fingerprint_sig = MinHashSignature.from_bytes(
            memory["fingerprint"],
            num_hashes=self.settings.fingerprint_num_hashes
        )

        # Find fingerprint-based matches (60-80% faster)
        fingerprint_matches = []
        for subcat in subcategories:
            if subcat.centroid_fingerprint:
                similarity = fingerprint_sig.jaccard_similarity(
                    MinHashSignature.from_bytes(
                        subcat.centroid_fingerprint,
                        num_hashes=self.settings.fingerprint_num_hashes
                    )
                )
                if similarity >= 0.90:
                    fingerprint_matches.append((subcat, similarity))

        if fingerprint_matches:
            best_subcat, best_sim = max(fingerprint_matches, key=lambda x: x[1])
            return CategoryAssignment(
                memory_id=memory.get("id"),
                category=category,
                subcategory=best_subcat.name,
                confidence=best_sim,
                method="fingerprint",  # Track assignment method
            )

    # Fallback to embedding-based assignment
    # ... [embedding code]

    return CategoryAssignment(...)
```

#### 5.6 Add Background Job (2 hours)
- [ ] Periodic evolution task (every 6 hours configurable)
- [ ] Merge small/similar clusters
- [ ] Update subcategory assignments

#### 5.7 Benefit from Deduplication (1 hour)
- [ ] Verify deduplicated data improves clustering quality
- [ ] Track cluster quality metrics over time

#### 5.8 Add MCP Tools (2 hours)
- [ ] `get_subcategories` tool
- [ ] `evolve_categories` tool (manual trigger)
- [ ] `assign_subcategory` tool (manual assignment)
- [ ] `category_stats` tool

### Success Criteria
- [ ] 3-10 subcategories per top-level category
- [ ] >75% memory assignment accuracy
- [ ] Background job <5min runtime
- [ ] Subcategories remain stable between runs

---

# Part 3: Cross-Cutting Concerns

## Performance Optimization Strategies

### 1. Cache Warming

**Strategy**: Pre-populate cache for common queries during idle periods

```python
async def warm_cache_for_common_queries(self) -> None:
    """Warm cache with high-probability queries."""

    common_queries = [
        "how to implement",
        "what is the error",
        "fix the bug",
        "test failed",
    ]

    for query in common_queries:
        # Trigger cache population
        await self.search_conversations(query, use_cache=True)
```

### 2. Batch Fingerprint Computation

**Strategy**: Compute fingerprints during bulk operations

```python
async def batch_store_with_fingerprints(
    self,
    items: list[dict]
) -> list[str]:
    """Store multiple items with batch fingerprint computation."""

    # Compute all fingerprints in parallel
    fingerprints = await asyncio.gather(*[
        self._compute_fingerprint(item["content"])
        for item in items
    ])

    # Batch insert
    for item, fingerprint in zip(items, fingerprints):
        await self.store_conversation(
            content=item["content"],
            fingerprint=fingerprint,  # Pre-computed
        )
```

### 3. Lazy Evolution

**Strategy**: Only evolve categories that have received sufficient new content

```python
async def evolve_categories_selectively(self) -> None:
    """Only evolve categories that need it."""

    for category in TopLevelCategory:
        # Check if enough new content since last evolution
        new_content_count = await self._count_new_content_since_evolution(category)

        if new_content_count >= self.settings.evolution_min_new_content:
            await self.evolve_category(category)
```

## Monitoring & Observability

### Unified Metrics Dashboard

```python
@mcp.tool()
async def memory_enhancement_dashboard() -> dict[str, Any]:
    """Comprehensive dashboard for all enhancement features."""

    return {
        "query_cache": {
            "hit_rate": 0.42,
            "l1_size": 234,
            "l2_size": 1523,
            "avg_latency_ms": 0.8,
        },
        "query_rewriting": {
            "rewrite_rate": 0.28,
            "avg_confidence": 0.87,
            "resolution_rate": 0.83,
        },
        "progressive_search": {
            "avg_tiers_searched": 2.1,
            "early_stop_rate": 0.64,
            "time_reduction_vs_baseline": 0.35,
        },
        "fingerprinting": {
            "dedup_rate": 0.23,
            "exact_duplicate_detection": 0.94,
            "near_duplicate_detection": 0.76,
            "avg_fingerprint_time_ms": 2.3,
        },
        "category_evolution": {
            "total_subcategories": 42,
            "avg_per_category": 8.4,
            "assignment_accuracy": 0.81,
            "last_evolution": "2026-01-20T14:30:00Z",
        },
        "integration_metrics": {
            "cache_invalidations_from_dedup": 12,
            "fingerprint_prefilter_hit_rate": 0.67,
            "tier_specific_cache_hit_rate": {
                "categories": 0.38,
                "insights": 0.41,
                "reflections": 0.29,
                "conversations": 0.51,
            }
        }
    }
```

---

# Part 4: Reference Materials

## Database Schema Summary

```sql
-- ============================================================
-- PHASE 1: Query Cache
-- ============================================================
CREATE TABLE IF NOT EXISTS query_cache (
    cache_key TEXT PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    project TEXT,
    result_ids TEXT[],
    hit_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ttl_seconds INTEGER DEFAULT 604800,

    -- Integration fields for future phases
    tier TEXT,  -- Phase 3: 'categories', 'insights', 'reflections', 'conversations'
    context_hash TEXT,  -- Phase 2: Hash of conversation context
    content_ids TEXT[]  -- Phase 4: Track actual content IDs for invalidation
);
CREATE INDEX idx_query_cache_accessed ON query_cache(last_accessed);
CREATE INDEX idx_query_cache_tier ON query_cache(tier);

-- ============================================================
-- PHASE 2: Query Rewriting (uses query_cache above)
-- ============================================================
-- No new schema - extends query_cache usage with context_hash

-- ============================================================
-- PHASE 3: Progressive Search
-- ============================================================
-- No new schema - logic layer only, uses tier field from query_cache

-- ============================================================
-- PHASE 4: N-gram Fingerprinting
-- ============================================================
ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS fingerprint BLOB;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS fingerprint BLOB;

CREATE TABLE IF NOT EXISTS content_fingerprints (
    id TEXT PRIMARY KEY,
    content_type TEXT NOT NULL,  -- 'conversation' or 'reflection'
    content_id TEXT NOT NULL,
    fingerprint BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(content_type, content_id)
);
CREATE INDEX idx_fingerprints_type ON content_fingerprints(content_type);

-- ============================================================
-- PHASE 5: Category Evolution
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_subcategories (
    id TEXT PRIMARY KEY,
    parent_category TEXT NOT NULL,  -- facts, preferences, skills, rules, context
    name TEXT NOT NULL,
    keywords TEXT[],
    centroid FLOAT[384],
    centroid_fingerprint BLOB,  -- Integration: Phase 4 fingerprint centroid
    memory_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_category, name)
);

ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS subcategory TEXT;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS subcategory TEXT;

CREATE INDEX idx_conv_subcategory ON conversations_v2(category, subcategory);
CREATE INDEX idx_refl_subcategory ON reflections_v2(category, subcategory);
```

## MCP Tools Summary

| Phase | Tool | Description |
|-------|------|-------------|
| 1 | `query_cache_stats` | View cache performance metrics |
| 1 | `clear_query_cache` | Manual cache invalidation |
| 2 | `rewrite_query` | Test query rewriting |
| 2 | `query_rewrite_stats` | View rewrite metrics |
| 3 | `progressive_search` | Multi-tier search with early stopping |
| 4 | `deduplication_stats` | View dedup metrics |
| 4 | `find_duplicates` | Scan for existing duplicates |
| 5 | `get_subcategories` | View category structure |
| 5 | `evolve_categories` | Trigger category evolution |
| 5 | `assign_subcategory` | Manual subcategory assignment |
| 5 | `category_stats` | View category statistics |

## Testing Strategy

### Unit Tests

```python
tests/
├── unit/
│   ├── test_query_cache.py           # Phase 1
│   ├── test_query_rewriter.py        # Phase 2
│   ├── test_progressive_search.py    # Phase 3
│   ├── test_fingerprint.py           # Phase 4
│   └── test_category_evolution.py    # Phase 5
```

### Integration Tests

```python
tests/
├── integration/
│   ├── test_cache_integration.py              # Phase 1
│   ├── test_rewrite_cache_integration.py      # Phase 1+2
│   ├── test_progressive_cache_integration.py   # Phase 1+3
│   ├── test_dedup_integration.py              # Phase 4
│   ├── test_evolution_dedup_integration.py    # Phase 4+5
│   └── test_full_pipeline_integration.py       # All phases
```

### Performance Benchmarks

```python
tests/
├── performance/
│   ├── test_cache_performance.py         # Cache hit/miss latency
│   ├── test_rewrite_performance.py        # Rewrite overhead
│   ├── test_progressive_performance.py    # Search time reduction
│   ├── test_fingerprint_performance.py    # Fingerprint computation
│   └── test_evolution_performance.py     # Clustering performance
```

---

# Appendices

## Appendix A: Implementation Checklist

### Phase 1: Query Cache
- [ ] Core cache infrastructure
- [ ] L1/L2 cache implementation
- [ ] Cache invalidation hooks
- [ ] Cache statistics and metrics
- [ ] MCP tools for cache management
- [ ] Integration preparation for future phases

### Phase 2: Query Rewriting
- [ ] Ambiguity detection
- [ ] LLM integration
- [ ] Context-aware caching
- [ ] Rewrite metadata in results
- [ ] Graceful fallback implementation

### Phase 3: Progressive Search
- [ ] Multi-tier search logic
- [ ] Sufficiency evaluation
- [ ] Tier-specific caching
- [ ] Early stopping implementation
- [ ] Progressive search MCP tool

### Phase 4: N-gram Fingerprinting
- [ ] MinHash implementation
- [ ] Deduplication logic
- [ ] Cache invalidation integration
- [ ] Duplicate merge strategy
- [ ] Fingerprint storage schema

### Phase 5: Category Evolution
- [ ] Clustering engine
- [ ] Fingerprint pre-filtering
- [ ] Background job scheduler
- [ ] Subcategory assignment
- [ ] Evolution MCP tools

### Integration & Testing
- [ ] Cross-feature integration tests
- [ ] Performance benchmarking
- [ ] Cache consistency validation
- [ ] End-to-end pipeline testing
- [ ] Documentation updates

## Appendix B: Risk Register

| Risk | Probability | Impact | Mitigation | Owner |
|------|------------|--------|------------|-------|
| LLM dependency for rewriting | Medium | High | Graceful fallback, cached rewrites | Phase 2 |
| Cache invalidation bugs | Low | Medium | Comprehensive testing, manual clear tools | Phase 1 |
| Fingerprint false positives | Low | Medium | Conservative threshold, disable option | Phase 4 |
| Category instability | Low | Low | Minimum cluster size, centroid smoothing | Phase 5 |
| Integration complexity | Medium | Medium | Incremental rollout, feature flags | All |
| Performance degradation | Low | High | Per-feature benchmarks, rollback plan | All |

## Appendix C: Success Criteria Tracking

### Overall Metrics
- [ ] All 5 phases deployed and operational
- [ ] Zero critical integration bugs
- [ ] Performance regression <5% on any feature
- [ ] Combined features provide >40% search latency reduction
- [ ] User satisfaction >80% perceive improvement

### Per-Feature Integration Metrics

**Query Cache + Query Rewriting**:
- [ ] Context-aware cache hit rate >35%
- [ ] Rewrite cache hit rate >50%
- [ ] Zero cache poisoning incidents

**N-gram + Category Evolution**:
- [ ] Fingerprint pre-filtering >60% assignment speedup
- [ ] Cluster quality improved by deduplication
- [ ] No category instability from fingerprint noise

**Progressive Search + Query Cache**:
- [ ] Tier-specific cache hit rate >25%
- [ ] Early termination rate >60%
- [ ] No cache consistency issues

---

**Document Status**: ✅ Ready for Implementation

**Next Steps**:
1. Begin Phase 1 implementation starting with `query_cache.py` module creation
2. Set up integration testing infrastructure
3. Establish monitoring baseline metrics
4. Implement phases sequentially, validating integration points at each step
