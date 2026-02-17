# Unified Memory Enhancement Plan

> **Comprehensive implementation plan for 5 complementary features**
> **Created**: January 20, 2026
> **Status**: Planning Phase
> **Estimated Duration**: ~35-40 days total

## Executive Summary

This plan unifies **5 complementary features** inspired by DeepSeek Engram and MemU to enhance session-buddy's memory system:

| Feature | Inspiration | Priority | Type | Est. Days |
|---------|-------------|----------|------|-----------|
| 1. Query Cache | Engram | High | Performance | 6-8 |
| 2. N-gram Fingerprinting | Engram | Medium | Data Quality | 8-10 |
| 3. Query Rewriting | MemU | High | Search Quality | 7-9 |
| 4. Progressive Hierarchical Search | MemU | Medium | Performance | 6-8 |
| 5. Self-Evolving Categories | MemU | Medium | Organization | 8-10 |

**Total Estimated Effort**: 35-45 days (with parallel work possible)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          MEMORY ENHANCEMENT PIPELINE                            │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                    │
│  User Query ──┬──► [1] Query Rewriting ──┬──► [2] Query Cache Lookup ──┬──► Cache Hit? │
│               │      (expand pronouns)    │      (hash-based O(1))      │       │     │
│               │                            │                            │       ├─Yes──► Return
│               │                            │       Cache Miss          │       │     │
│               │                            │                            │         │
│               │                            └────────────────────────────┘         │
│               │                                                                 │
│               └─────────────────────────────────────────────────────────────────┤
│                                                                                │
│  [3] Progressive Search ──► Tier 1: Categories  ──► Sufficient? ──► Return     │
│           │                Tier 2: Insights        │              │             │
│           │                Tier 3: Reflections     │              │             │
│           │                Tier 4: Conversations   │              │             │
│           │                       │              No                         │
│           │                       └───────────────────┐                     │
│           │                                           │                     │
│           └───────────────────────────────────────────┘                     │
│                             │                                                   │
│                             ▼                                                   │
│  Store Results ──┬──► [4] N-gram Fingerprint ──► Duplicate? ──► Skip/Merge  │
│                  │      (MinHash signature)         │                         │
│                  │                                  │                        No    │
│                  │                                  └─────────────────────────────┐│
│                  │                                                            ││
│                  └────────────────────────────────────────────────────────┘│
│                                                                         │   │
│                                                                         │   ▼
│  [5] Category Evolution ◄─────────────────────────────────────────────┘ │
│      (background clustering)                                                │
│                                                                                │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

`★ Insight ─────────────────────────────────────`
**Layer Separation Principle**: Each feature operates at a distinct layer:
- **Rewriting** operates on the query before processing
- **Caching** shortcuts expensive operations
- **Progressive Search** controls search scope
- **Fingerprinting** validates before storage
- **Evolution** organizes after storage

This separation enables independent development, testing, and gradual rollout.
`─────────────────────────────────────────────────`

## Feature Dependencies

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              DEPENDENCY GRAPH                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                    │
│    Query Cache ──────┬───────► Progressive Search (benefits from cache)       │
│          │           │                                                            │
│          │           │                                                            │
│          └──► Query Rewriting ◄──│                                              │
│                      │        │                                               │
│                      ▼        │                                               │
│                 [Rewritten Query]                                              │
│                      │        │                                               │
│                      └────────┘                                               │
│                                                                                │
│    N-gram Fingerprint ────────────► Category Evolution (cleaner data = better │
│                                         clustering)                           │
│                                                                                │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Foundation (Query Cache) - Days 1-8

**Deliverable**: Fast hash-based caching that bypasses expensive vector search

**Implementation Tasks**:

- [ ] **1.1** Create `session_buddy/utils/query_cache.py`
  - [ ] Add `normalize_query()` function (NFKC, lowercase, collapse whitespace)
  - [ ] Add `compute_cache_key()` function using xxhash
  - [ ] Add `QueryCacheEntry` dataclass
  - [ ] Unit tests for normalization and key generation

- [ ] **1.2** Create L2 cache table in `_ensure_tables()`
  ```sql
  CREATE TABLE IF NOT EXISTS query_cache (
      cache_key TEXT PRIMARY KEY,
      normalized_query TEXT NOT NULL,
      project TEXT,
      result_ids TEXT[],
      hit_count INTEGER DEFAULT 1,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      ttl_seconds INTEGER DEFAULT 604800
  );
  CREATE INDEX idx_query_cache_accessed ON query_cache(last_accessed);
  ```

- [ ] **1.3** Add L1 cache to `ReflectionDatabaseAdapterOneiric.__init__()`
  - [ ] Add `_query_cache: dict[str, QueryCacheEntry]`
  - [ ] Add `_query_cache_max_size`, `_query_cache_hits`, `_query_cache_misses`
  - [ ] Add cache settings to `ReflectionAdapterSettings`

- [ ] **1.4** Implement cache methods
  - [ ] `_check_query_cache()` - L1 → L2 lookup
  - [ ] `_populate_query_cache()` - store results
  - [ ] `_invalidate_project_cache()` - event-based invalidation
  - [ ] `clear_query_cache()` - manual cleanup

- [ ] **1.5** Modify search methods to use cache
  - [ ] Update `search_conversations()` with cache integration
  - [ ] Update `search_reflections()` with cache integration
  - [ ] Add `use_cache: bool = True` parameter

- [ ] **1.6** Add metrics and MCP tools
  - [ ] `get_cache_stats()` method
  - [ ] `query_cache_stats` MCP tool
  - [ ] `clear_query_cache` MCP tool

**Success Criteria**:
- [ ] Cache hit rate >30% for typical session workflows
- [ ] <1ms latency for cache hits
- [ ] Zero memory leaks (L1 cleared on close)
- [ ] All existing tests pass

---

### Phase 2: Query Enhancement (Query Rewriting) - Days 9-17

**Deliverable**: Context-aware query expansion for conversational memory search

**Implementation Tasks**:

- [ ] **2.1** Create `session_buddy/memory/query_rewriter.py`
  - [ ] Add `QueryRewriteResult` dataclass
  - [ ] Add `AmbiguityDetector` class (pronouns, demonstratives, temporal refs)
  - [ ] Add `QueryRewriter` class with LLM integration
  - [ ] Add rewrite prompt template

- [ ] **2.2** Implement core rewrite logic
  - [ ] `rewrite()` method with fast paths
  - [ ] `_format_context()` for conversation history
  - [ ] `_call_llm()` using configured provider
  - [ ] `_calculate_confidence()` for validation

- [ ] **2.3** Add rewrite settings
  ```python
  @dataclass
  class QueryRewriteSettings:
      enabled: bool = True
      llm_provider: str = "haiku"
      max_context_messages: int = 10
      confidence_threshold: float = 0.7
      cache_rewrites: bool = True
      cache_ttl_seconds: int = 300
  ```

- [ ] **2.4** Integrate with search methods
  - [ ] Add `enable_query_rewrite` parameter to search methods
  - [ ] Add `conversation_context` parameter for context
  - [ ] Include `_query_rewrite` metadata in results

- [ ] **2.5** Implement rewrite caching (synergy with Phase 1)
  - [ ] Cache rewritten queries separately from originals
  - [ ] Include rewrite signature in cache key
  - [ ] Invalidate on context changes

- [ ] **2.6** Add MCP tools
  - [ ] `rewrite_query` tool for testing/debugging
  - [ ] `query_rewrite_stats` tool for metrics

**Success Criteria**:
- [ ] >80% ambiguous query resolution rate
- [ ] <200ms average latency increase
- [ ] Graceful fallback when LLM unavailable
- [ ] Rewrite caching >50% hit rate for repeated contexts

---

### Phase 3: Progressive Search - Days 18-25

**Deliverable**: Multi-tier search with early stopping

**Implementation Tasks**:

- [ ] **3.1** Create `session_buddy/memory/progressive_search.py`
  - [ ] Add `SearchTier` enum (CATEGORIES, INSIGHTS, REFLECTIONS, CONVERSATIONS)
  - [ ] Add `TierSearchResult` dataclass
  - [ ] Add `ProgressiveSearchResult` dataclass
  - [ ] Add `SufficiencyConfig` dataclass

- [ ] **3.2** Implement sufficiency evaluation
  - [ ] `SufficiencyEvaluator` class
  - [ ] `is_sufficient()` method with multiple criteria
  - [ ] Configurable thresholds (min_results, min_avg_score, tier_coverage)

- [ ] **3.3** Implement progressive search engine
  - [ ] `ProgressiveSearchEngine` class
  - [ ] `search()` method with tier iteration
  - [ ] `_search_tier()` method per tier
  - [ ] `_search_categories()` proxy (high-quality insights)
  - [ ] `_deduplicate_results()` method

- [ ] **3.4** Integrate with existing adapter
  - [ ] Hook into `search_insights()` for Tier 2
  - [ ] Ensure `search_reflections()` works for Tier 3
  - [ ] Ensure `search_conversations()` works for Tier 4

- [ ] **3.5** Add MCP tool
  - [ ] `progressive_search` tool
  - [ ] Return results with tier metadata
  - [ ] Include `stopped_early` and `stop_reason` in response

- [ ] **3.6** Add synergy with Phase 1 (Query Cache)
  - [ ] Cache results per tier
  - [ ] Enable tier-aware cache hits
  - [ ] Update cache stats to show tier breakdown

**Success Criteria**:
- [ ] Average tiers searched <2.5 for typical queries
- [ ] >30% search time reduction vs full search
- [ ] Result quality maintained or improved
- [ ] Graceful degradation to single-tier if needed

---

### Phase 4: Data Quality (N-gram Fingerprinting) - Days 26-35

**Deliverable**: Near-duplicate detection and prevention

**Implementation Tasks**:

- [ ] **4.1** Create `session_buddy/utils/fingerprint.py`
  - [ ] Add `normalize_for_fingerprint()` function
  - [ ] Add `extract_ngrams()` function (character n-grams)
  - [ ] Add `MinHashSignature` dataclass
  - [ ] Implement `from_ngrams()` class method
  - [ ] Implement `jaccard_similarity()` method
  - [ ] Implement `to_bytes()` / `from_bytes()` serialization

- [ ] **4.2** Add fingerprint settings
  ```python
  # Add to ReflectionAdapterSettings
  deduplication_enabled: bool = True
  fingerprint_ngram_size: int = 3
  fingerprint_num_hashes: int = 128
  fingerprint_similarity_threshold: float = 0.85
  fingerprint_check_limit: int = 1000
  fingerprint_skip_threshold: float = 0.95
  ```

- [ ] **4.3** Create fingerprint schema
  - [ ] Add `fingerprint BLOB` column to `conversations` table
  - [ ] Add `fingerprint BLOB` column to `reflections` table
  - [ ] Create `content_fingerprints` index table
  - [ ] Create migration script for existing databases

- [ ] **4.4** Implement deduplication logic
  - [ ] `DeduplicationResult` dataclass
  - [ ] `check_duplicate()` method
  - [ ] `merge_conversation()` method for near-duplicates
  - [ ] `_store_fingerprint()` helper method

- [ ] **4.5** Integrate into storage methods
  - [ ] Modify `store_conversation()` with deduplication
  - [ ] Modify `store_reflection()` with deduplication
  - [ ] Add `deduplicate: bool = True` parameter

- [ ] **4.6** Add optional dependency
  ```toml
  [project.optional-dependencies]
  performance = ["xxhash>=3.0"]
  ```
  - [ ] Implement fallback using `hashlib.blake2b`

- [ ] **4.7** Add MCP tools
  - [ ] `deduplication_stats` tool
  - [ ] `find_duplicates` tool to scan existing data
  - [ ] Update `reflection_stats` to include dedup metrics

**Success Criteria**:
- [ ] >90% exact duplicate detection
- [ ] >70% near-duplicate (>85% similar) detection
- [ ] <1% false positive rate
- [ ] Store latency increase <50% (target <15ms)
- [ ] 15-30% database size reduction over time

---

### Phase 5: Organization (Category Evolution) - Days 36-45

**Deliverable**: Dynamic subcategory creation via clustering

**Implementation Tasks**:

- [ ] **5.1** Create `session_buddy/memory/category_evolution.py`
  - [ ] Add `TopLevelCategory` enum (FACTS, PREFERENCES, SKILLS, RULES, CONTEXT)
  - [ ] Add `Subcategory` dataclass
  - [ ] Add `CategoryAssignment` dataclass
  - [ ] Add `KeywordExtractor` class
  - [ ] Add `SubcategoryClusterer` class
  - [ ] Add `CategoryEvolutionEngine` class

- [ ] **5.2** Implement clustering logic
  - [ ] `KeywordExtractor.extract()` with stop words and tech terms
  - [ ] `SubcategoryClusterer.cluster_memories()` method
  - [ ] `_cosine_similarity()` for embedding comparison
  - [ ] `_update_centroid()` for incremental learning
  - [ ] `_create_new_subcategories()` for new clusters

- [ ] **5.3** Add category evolution schema
  ```sql
  CREATE TABLE IF NOT EXISTS memory_subcategories (
      id TEXT PRIMARY KEY,
      parent_category TEXT NOT NULL,
      name TEXT NOT NULL,
      keywords TEXT[],
      centroid FLOAT[384],
      memory_count INTEGER DEFAULT 0,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(parent_category, name)
  );

  ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS subcategory TEXT;
  ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS subcategory TEXT;
  ```

- [ ] **5.4** Implement evolution engine
  - [ ] `evolve_category()` method
  - [ ] `assign_subcategory()` for new memories
  - [ ] `get_subcategories()` query method
  - [ ] `_get_category_memories()` helper
  - [ ] `_persist_subcategories()` storage

- [ ] **5.5** Add background job
  - [ ] Periodic evolution task (every 6 hours configurable)
  - [ ] Merge small/similar clusters
  - [ ] Update subcategory assignments

- [ ] **5.6** Add MCP tools
  - [ ] `get_subcategories` tool
  - [ ] `evolve_categories` tool (manual trigger)
  - [ ] `assign_subcategory` tool (manual assignment)
  - [ ] `category_stats` tool

- [ ] **5.7** Leverage Phase 4 (Fingerprinting)
  - [ ] Deduplicate memories before clustering
  - [ ] Use fingerprints as additional clustering signal
  - [ ] Cleaner clusters from duplicate-free data

**Success Criteria**:
- [ ] 3-10 subcategories per top-level category
- [ ] >75% memory assignment accuracy
- [ ] Background job <5min runtime
- [ ] Subcategories remain stable between runs

---

## Unified Configuration

```python
# session_buddy/adapters/settings.py

@dataclass
class MemoryEnhancementSettings:
    """Unified settings for all memory enhancement features."""

    # Phase 1: Query Cache (Engram)
    enable_query_cache: bool = True
    query_cache_l1_max_size: int = 1000
    query_cache_l2_ttl_days: int = 7
    query_cache_normalize_accents: bool = False
    query_cache_normalize_punctuation: bool = False

    # Phase 2: Query Rewriting (MemU)
    enable_query_rewriting: bool = True
    query_rewrite_llm_provider: str = "haiku"
    query_rewrite_max_context: int = 10
    query_rewrite_confidence_threshold: float = 0.7
    query_rewrite_cache_enabled: bool = True
    query_rewrite_cache_ttl_seconds: int = 300

    # Phase 3: Progressive Search (MemU)
    enable_progressive_search: bool = True
    progressive_search_default: bool = False
    progressive_search_min_results: int = 3
    progressive_search_min_avg_score: float = 0.8
    progressive_search_max_tiers: int = 4

    # Phase 4: N-gram Fingerprinting (Engram)
    enable_deduplication: bool = True
    fingerprint_ngram_size: int = 3
    fingerprint_num_hashes: int = 128
    fingerprint_similarity_threshold: float = 0.85
    fingerprint_check_limit: int = 1000
    fingerprint_skip_threshold: float = 0.95

    # Phase 5: Category Evolution (MemU)
    enable_category_evolution: bool = True
    evolution_interval_hours: int = 6
    evolution_min_cluster_size: int = 5
    evolution_max_clusters_per_category: int = 10
    evolution_similarity_threshold: float = 0.7

    # Integrated mode
    integrated_mode: bool = True  # When True, features coordinate

    def validate(self) -> list[str]:
        """Validate settings and return any errors."""
        errors = []

        # Validate query cache settings
        if self.enable_query_cache and self.query_cache_l1_max_size < 100:
            errors.append("query_cache_l1_max_size must be at least 100")

        # Validate rewrite settings
        if self.enable_query_rewriting:
            if not (0.0 <= self.query_rewrite_confidence_threshold <= 1.0):
                errors.append("query_rewrite_confidence_threshold must be 0-1")

        # Validate fingerprint settings
        if self.enable_deduplication:
            if not (0.0 <= self.fingerprint_similarity_threshold <= 1.0):
                errors.append("fingerprint_similarity_threshold must be 0-1")
            if self.fingerprint_ngram_size < 2 or self.fingerprint_ngram_size > 5:
                errors.append("fingerprint_ngram_size must be 2-5")

        # Validate progressive search settings
        if self.enable_progressive_search:
            if self.progressive_search_min_results < 1:
                errors.append("progressive_search_min_results must be at least 1")

        return errors
```

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
    ttl_seconds INTEGER DEFAULT 604800
);
CREATE INDEX idx_query_cache_accessed ON query_cache(last_accessed);

-- ============================================================
-- PHASE 2: Query Rewriting (uses query_cache above)
-- ============================================================
-- No new schema - extends query_cache usage

-- ============================================================
-- PHASE 3: Progressive Search
-- ============================================================
-- No new schema - logic layer only

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

## Progress Tracking

### Overall Progress

- [ ] Phase 1: Query Cache (0/6 days)
- [ ] Phase 2: Query Rewriting (0/9 days)
- [ ] Phase 3: Progressive Search (0/8 days)
- [ ] Phase 4: N-gram Fingerprinting (0/10 days)
- [ ] Phase 5: Category Evolution (0/10 days)

### Milestones

- [ ] **M1**: Phase 1 complete - Basic caching operational
- [ ] **M2**: Phase 2 complete - Conversational queries working
- [ ] **M3**: Phase 3 complete - Progressive search faster than baseline
- [ ] **M4**: Phase 4 complete - Duplicate detection active
- [ ] **M5**: Phase 5 complete - Dynamic categories functional
- [ ] **M6**: All phases integrated - Full enhancement suite live

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM dependency for query rewriting | High | Graceful fallback to original query |
| Cache poisoning | Medium | TTL-based expiration, manual clear tool |
| Fingerprint false positives | Medium | Conservative threshold, disable option |
| Category instability | Low | Minimum cluster size, centroid smoothing |
| Performance degradation | Medium | Per-feature feature flags, benchmarking |

## Rollback Strategy

Each phase can be independently disabled via configuration:

```python
# To disable any feature, set in settings or environment
settings.enable_query_cache = False
settings.enable_query_rewriting = False
settings.enable_progressive_search = False
settings.enable_deduplication = False
settings.enable_category_evolution = False
```

All features are additive - disabling them returns system to baseline behavior.

## Success Metrics

### Overall Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Average search latency | ~50-100ms | <35ms | Benchmark suite |
| Cache hit rate | 0% | >40% | Cache stats tool |
| Duplicate rate | Unknown | <5% after dedup | Dedup stats |
| Subcategories per category | 0 | 3-10 | Category stats |
| Overall satisfaction | N/A | >80% perceive improvement | User feedback |

### Per-Feature Metrics

| Feature | Metric | Target |
|---------|--------|--------|
| Query Cache | Hit rate | >30% |
| Query Cache | Hit latency | <1ms |
| Query Rewriting | Ambiguous resolution | >80% |
| Query Rewriting | Latency increase | <200ms |
| Progressive Search | Avg tiers searched | <2.5 |
| Progressive Search | Time reduction | >30% |
| Fingerprinting | Exact duplicate detection | >90% |
| Fingerprinting | Near-duplicate detection | >70% |
| Fingerprinting | False positive rate | <1% |
| Category Evolution | Subcategories created | 3-10 per category |
| Category Evolution | Assignment accuracy | >75% |

## References

- **DeepSeek Engram**: https://github.com/deepseek-ai/Engram
- **MemU**: https://github.com/NevaMind-AI/memU
- **MinHash algorithm**: https://en.wikipedia.org/wiki/MinHash
- **Jaccard similarity**: https://en.wikipedia.org/wiki/Jaccard_index
- **xxhash Python**: https://github.com/ifduyue/python-xxhash

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-01-20 | Initial unified plan created | Claude |

---

**Document Status**: 📝 Planning - Ready for Implementation

**Next Steps**: Begin Phase 1 implementation starting with `query_cache.py` module creation.
