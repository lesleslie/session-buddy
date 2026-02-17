# Memory Enhancement Integration Plan

> **Comprehensive integration strategy for 5 complementary memory features**
> **Created**: January 20, 2026
> **Status**: Planning Phase
> **Estimated Duration**: ~35-45 days total

## Purpose

This document focuses on **how the 5 memory enhancement features work together**, including:
- Integration points between features
- Conflict resolution strategies
- Data flow and coordination
- Implementation dependencies
- Rollout considerations

For individual feature details, see:
- `ENGRAM_FEATURE_1_QUERY_CACHE.md`
- `ENGRAM_FEATURE_2_NGRAM_FINGERPRINT.md`
- `MEMU_INSPIRED_FEATURES_PLAN.md`

## Feature Overview

| # | Feature | Inspiration | Layer | Est. Days | Priority |
|---|---------|-------------|-------|-----------|----------|
| 1 | Query Cache | Engram | Retrieval | 6-8 | **High** |
| 2 | N-gram Fingerprinting | Engram | Storage | 8-10 | Medium |
| 3 | Query Rewriting | MemU | Understanding | 7-9 | **High** |
| 4 | Progressive Search | MemU | Strategy | 6-8 | Medium |
| 5 | Category Evolution | MemU | Organization | 8-10 | Medium |

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
│  │               │                                  │                          │         │
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
│  │                                                            ▼             │ │
│  │                                                    Search Results    │ │
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

`★ Insight ─────────────────────────────────────`
**Key Integration Principle**: Each feature enhances the others through well-defined interfaces:
- **Cache shortcuts** expensive operations from later phases
- **Rewriting** improves cache hit rates by normalizing queries
- **Progressive Search** leverages cache for tier-specific results
- **Fingerprinting** provides clean data for clustering
- **Evolution** benefits from deduplicated content

The features form a **positive feedback loop** where each improvement amplifies the others.
`─────────────────────────────────────────────────`

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

**Configuration**:
```python
@dataclass
class QueryRewriteSettings:
    enabled: bool = True
    llm_provider: str = "haiku"
    cache_rewrites: bool = True  # Cache rewritten queries
    cache_context_sensitive: bool = True  # Different cache keys per context
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

        # Fallback to embedding-based assignment
        embedding = memory.get("embedding")
        if not embedding:
            return CategoryAssignment(
                memory_id=memory.get("id"),
                category=category,
                subcategory=None,
                confidence=1.0,
            )

        # Standard embedding similarity
        best_subcat = None
        best_similarity = 0.0
        embedding_arr = np.array(embedding)

        for subcat in subcategories:
            if subcat.centroid:
                similarity = self._cosine_similarity(
                    embedding_arr,
                    np.array(subcat.centroid)
                )
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_subcat = subcat

        return CategoryAssignment(
            memory_id=memory.get("id"),
            category=category,
            subcategory=best_subcat.name if best_subcat else None,
            confidence=best_similarity,
            method="embedding",
        )
```

**Performance Benefit**:
- Fingerprint pre-filtering: ~60-80% reduction in embedding similarity computations
- Typical assignment time: ~5ms → ~1-2ms

**Data Model Extension**:
```python
@dataclass
class Subcategory:
    id: str
    parent_category: TopLevelCategory
    name: str
    keywords: list[str]
    centroid: list[float] | None = None  # Embedding centroid
    centroid_fingerprint: bytes | None = None  # NEW: Fingerprint centroid
    memory_count: int = 0
```

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

**Cache Statistics**:
```python
def get_cache_stats(self) -> dict[str, Any]:
    """Return cache statistics with tier breakdown."""
    return {
        "overall_hit_rate": self._calc_hit_rate(),
        "tier_breakdown": {
            "categories": self._tier_cache_hits["categories"] / self._tier_cache_lookups["categories"],
            "insights": self._tier_cache_hits["insights"] / self._tier_cache_lookups["insights"],
            "reflections": self._tier_cache_hits["reflections"] / self._tier_cache_lookups["reflections"],
            "conversations": self._tier_cache_hits["conversations"] / self._tier_cache_lookups["conversations"],
        }
    }
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

**Performance Impact**: Minimal - cache invalidation is rare (only on deduplication)

## Conflict Resolution Matrix

| Conflict Pair | Severity | Resolution Strategy | Status |
|---------------|----------|---------------------|----------|
| Query Cache + N-gram Dedup | Low | Invalidate cache entries on merge | ✅ Documented |
| Query Rewriting + Progressive Search | Low | Tier-specific query application | ✅ Documented |
| Category Evolution + Fingerprint | None | No conflict - fingerprints are category-agnostic | ✅ Verified |
| Query Cache + Query Rewriting | None | Context-aware cache keys | ✅ Documented |
| Progressive Search + Query Cache | None | Tier-specific cache entries | ✅ Documented |

## Implementation Timeline

### Phase 1: Foundation (Days 1-8)

**Focus**: Query Cache (Engram Feature 1)

**Deliverables**:
- ✅ Two-level cache (L1 memory + L2 DuckDB)
- ✅ Cache invalidation hooks
- ✅ Cache statistics and metrics
- ✅ Integration points for future phases

**Integration Preparation**:
- Add `content_id` field to cache entries for future dedup invalidation
- Add `tier` field to cache entries for future progressive search
- Add `context_hash` field for future query rewriting

**Milestone**: Cache operational with 30%+ hit rate

### Phase 2: Intelligence Layer (Days 9-17)

**Focus**: Query Rewriting (MemU Feature 1)

**Deliverables**:
- ✅ LLM-powered query expansion
- ✅ Context-aware caching
- ✅ Rewrite metadata in results

**Integration Actions**:
- Modify cache key generation to include context hash
- Add rewrite metadata to cached results
- Implement cache invalidation on context changes

**Dependencies**:
- Requires: Phase 1 (cache infrastructure)
- Blocks: Phase 3 (progressive search benefits from rewritten queries)

**Milestone**: Conversational queries working with 80%+ resolution rate

### Phase 3: Search Optimization (Days 18-25)

**Focus**: Progressive Search (MemU Feature 2)

**Deliverables**:
- ✅ Multi-tier search with early stopping
- ✅ Tier-specific caching
- ✅ Sufficiency evaluation

**Integration Actions**:
- Implement tier-aware cache keys
- Add tier breakdown to cache statistics
- Support tier-specific query application (original vs rewritten)

**Dependencies**:
- Requires: Phase 1 (cache), Phase 2 (rewriting - optional)
- Blocks: None

**Milestone**: 30%+ search time reduction with maintained quality

### Phase 4: Data Quality (Days 26-35)

**Focus**: N-gram Fingerprinting (Engram Feature 2)

**Deliverables**:
- ✅ MinHash-based deduplication
- ✅ Duplicate detection and merging
- ✅ Fingerprint storage

**Integration Actions**:
- Implement cache invalidation on duplicate merges
- Add fingerprint pre-filtering hooks for Phase 5
- Store fingerprints in new BLOB columns

**Dependencies**:
- Requires: Phase 1 (cache invalidation)
- Blocks: Phase 5 (category evolution benefits from clean data)

**Milestone**: 15-30% database size reduction, <5% duplicate slip-through

### Phase 5: Organization (Days 36-45)

**Focus**: Category Evolution (MemU Feature 3)

**Deliverables**:
- ✅ Dynamic subcategory creation
- ✅ Background clustering job
- ✅ Subcategory assignment

**Integration Actions**:
- Use fingerprint pre-filtering for fast assignment
- Add fingerprint centroids to subcategories
- Benefit from deduplicated data (cleaner clusters)

**Dependencies**:
- Requires: Phase 4 (fingerprints)
- Blocks: None

**Milestone**: 3-10 subcategories per category with >75% accuracy

## Integration Testing Strategy

### Cross-Feature Integration Tests

```python
# tests/integration/test_full_pipeline_integration.py

import pytest

class TestFullPipelineIntegration:
    """Test all 5 features working together."""

    @pytest.mark.asyncio
    async def test_conversational_query_with_full_pipeline(self):
        """Test complete flow: rewrite → cache → progressive → dedup → evolve."""

        # 1. User asks conversational question
        query = "What did he say about that?"
        context = [
            {"role": "user", "content": "Ask John about the database migration"},
            {"role": "assistant", "content": "John mentioned the migration needs testing..."}
        ]

        # 2. Query is rewritten (Phase 2)
        # 3. Checked in cache (Phase 1)
        # 4. Progressive search executed (Phase 3)
        result = await self.adapter.progressive_search(
            query=query,
            conversation_context=context,
            use_cache=True,
            enable_rewriting=True,
        )

        # Assertions
        assert result.stopped_early  # Progressive search worked
        assert len([t for t in result.tier_results if t.from_cache]) > 0  # Cache hit
        assert "John" in result.query  # Rewriting occurred

    @pytest.mark.asyncio
    async def test_deduplication_affects_cache(self):
        """Test that duplicate merging invalidates cache."""

        # Store duplicate content
        id1 = await self.adapter.store_conversation("How to implement OAuth2?")
        id2 = await self.adapter.store_conversation("How to implement OAuth2")  # Duplicate

        assert id2 == id1  # Should return same ID

        # Cache should have been invalidated
        cache_stats = await self.adapter.get_cache_stats()
        assert cache_stats["invalidations"] == 1

    @pytest.mark.asyncio
    async def test_fingerprint_speeds_category_assignment(self):
        """Test that fingerprint pre-filtering speeds up assignment."""

        # Create subcategories
        await self.evolver.evolve_category(TopLevelCategory.SKILLS)

        # Time assignment with fingerprints
        start = datetime.now()
        for i in range(100):
            await self.evolver.assign_subcategory(
                {"content": "Python async patterns", "embedding": test_embed}
            )
        with_fingerprint_time = (datetime.now() - start).total_seconds()

        # Time assignment without fingerprints
        self.evolver.use_fingerprint_pre_filter = False
        start = datetime.now()
        for i in range(100):
            await self.evolver.assign_subcategory(
                {"content": "Python async patterns", "embedding": test_embed}
            )
        without_fingerprint_time = (datetime.now() - start).total_seconds()

        # Fingerprinting should be faster
        assert with_fingerprint_time < without_fingerprint_time
```

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

## Rollback & Safety

### Per-Feature Rollback

Each feature can be independently disabled:

```python
# Disable specific features while keeping others active
settings.enable_query_rewriting = False  # Turn off rewriting
settings.enable_progressive_search = False  # Turn off progressive
# Query cache and fingerprinting remain active
```

### Graceful Degradation

```python
# Example: Query rewriting falls back gracefully
async def search_with_fallback(self, query: str) -> list[dict]:
    """Search with multiple fallback layers."""

    try:
        # Try full enhanced pipeline
        return await self.search_with_all_features(query)
    except LLMError:
        logger.warning("LLM unavailable, using cached rewrites")
        # Fallback to cached rewrites only
        return await self.search_with_cached_rewrites(query)
    except Exception as e:
        logger.error(f"Enhanced search failed: {e}, using baseline")
        # Final fallback to baseline search
        return await self.baseline_search(query)
```

### Migration Path

```sql
-- Schema migration script for all phases

-- Phase 1: Query cache table
CREATE TABLE IF NOT EXISTS query_cache (...);

-- Phase 4: Fingerprint columns
ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS fingerprint BLOB;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS fingerprint BLOB;
CREATE TABLE IF NOT EXISTS content_fingerprints (...);

-- Phase 5: Category evolution tables
CREATE TABLE IF NOT EXISTS memory_subcategories (...);
ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS subcategory TEXT;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS subcategory TEXT;
```

## Success Criteria

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

## Risk Register

| Risk | Probability | Impact | Mitigation | Owner |
|------|------------|--------|------------|-------|
| LLM dependency for rewriting | Medium | High | Graceful fallback, cached rewrites | Phase 2 |
| Cache invalidation bugs | Low | Medium | Comprehensive testing, manual clear tools | Phase 1 |
| Fingerprint false positives | Low | Medium | Conservative threshold, disable option | Phase 4 |
| Category instability | Low | Low | Minimum cluster size, centroid smoothing | Phase 5 |
| Integration complexity | Medium | Medium | Incremental rollout, feature flags | All |
| Performance degradation | Low | High | Per-feature benchmarks, rollback plan | All |

## Implementation Checklist

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

## References

- `ENGRAM_FEATURE_1_QUERY_CACHE.md` - Query cache details
- `ENGRAM_FEATURE_2_NGRAM_FINGERPRINT.md` - Fingerprinting details
- `MEMU_INSPIRED_FEATURES_PLAN.md` - MemU features details
- `UNIFIED_MEMORY_ENHANCEMENT_PLAN.md` - Unified feature plan

---

**Document Status**: 📝 Integration Planning - Ready for Implementation

**Next Steps**:
1. Review and approve integration architecture
2. Begin Phase 1 implementation
3. Set up integration testing infrastructure
4. Establish monitoring baseline metrics
