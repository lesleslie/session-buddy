# Implementation Plan: N-gram Fingerprinting for Deduplication

**Inspired by**: DeepSeek Engram's n-gram hash mapping for pattern detection
**Priority**: Medium value, Low effort
**Status**: Proposed

## Overview

Implement n-gram fingerprinting to detect and prevent storage of near-duplicate conversations and reflections. This applies Engram's deterministic hashing approach to the content storage pipeline rather than retrieval.

## Problem Statement

Session Buddy currently has no deduplication:

```python
# Current: Every store operation creates a new record
await db.store_conversation(content, metadata)  # Always inserts
await db.store_reflection(content, tags)  # Always inserts
```

This leads to:

- Database bloat from repeated/similar content
- Search results polluted with near-duplicates
- Wasted embedding computation on duplicate content
- Degraded search relevance (duplicates dilute signal)

## Proposed Solution

### N-gram Fingerprinting Algorithm

Inspired by Engram's `NgramHashMapping`, but adapted for content deduplication:

```
┌─────────────────────────────────────────────────────────────┐
│              Content Storage Pipeline                        │
├─────────────────────────────────────────────────────────────┤
│  1. Normalize content (lowercase, whitespace, unicode)       │
│  2. Extract n-grams (configurable n, default 3)             │
│  3. Hash each n-gram with xxhash                            │
│  4. Create MinHash signature (k=128 hashes)                 │
│  5. Compute Jaccard similarity with existing fingerprints   │
│  6. If similarity > threshold: skip/merge, else: store      │
└─────────────────────────────────────────────────────────────┘
```

### Why MinHash over Simple Hash?

Simple content hashing (hash entire text) only catches **exact** duplicates.

MinHash catches **near-duplicates** with configurable similarity threshold:

- "How do I fix this bug?" vs "How do I fix this bug" (trailing punctuation)
- Same content with different whitespace
- Minor typo corrections
- Content with timestamps or IDs that change

### Components

#### 1. N-gram Extractor

```python
def extract_ngrams(text: str, n: int = 3) -> set[str]:
    """Extract character n-grams from normalized text.

    Character n-grams are more robust than word n-grams for:
    - Typo detection
    - Languages without clear word boundaries
    - Technical content with unusual tokenization

    Args:
        text: Input text (will be normalized internally)
        n: N-gram size (default 3, trigrams)

    Returns:
        Set of unique n-grams
    """
    # Normalize first
    normalized = normalize_for_fingerprint(text)

    if len(normalized) < n:
        return {normalized} if normalized else set()

    return {normalized[i:i+n] for i in range(len(normalized) - n + 1)}
```

#### 2. MinHash Signature Generator

```python
from dataclasses import dataclass
import xxhash

@dataclass
class MinHashSignature:
    """MinHash signature for approximate set similarity."""
    values: tuple[int, ...]  # k hash values
    num_hashes: int = 128

    @classmethod
    def from_ngrams(cls, ngrams: set[str], num_hashes: int = 128) -> "MinHashSignature":
        """Generate MinHash signature from n-gram set.

        Uses different seeds for each hash function (Engram-style XOR variation).
        """
        if not ngrams:
            return cls(values=tuple([0] * num_hashes), num_hashes=num_hashes)

        # Generate k minimum hashes
        min_hashes = []
        for seed in range(num_hashes):
            min_hash = min(
                xxhash.xxh64(gram.encode(), seed=seed).intdigest()
                for gram in ngrams
            )
            min_hashes.append(min_hash)

        return cls(values=tuple(min_hashes), num_hashes=num_hashes)

    def jaccard_similarity(self, other: "MinHashSignature") -> float:
        """Estimate Jaccard similarity from MinHash signatures.

        Jaccard(A, B) ≈ |matching_hashes| / |total_hashes|
        """
        if self.num_hashes != other.num_hashes:
            raise ValueError("Signatures must have same num_hashes")

        matches = sum(a == b for a, b in zip(self.values, other.values))
        return matches / self.num_hashes

    def to_bytes(self) -> bytes:
        """Serialize for storage."""
        import struct
        return struct.pack(f">{self.num_hashes}Q", *self.values)

    @classmethod
    def from_bytes(cls, data: bytes, num_hashes: int = 128) -> "MinHashSignature":
        """Deserialize from storage."""
        import struct
        values = struct.unpack(f">{num_hashes}Q", data)
        return cls(values=values, num_hashes=num_hashes)
```

#### 3. Fingerprint Storage Schema

```sql
-- Add to existing tables
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS
    fingerprint BLOB;  -- MinHash signature bytes

ALTER TABLE reflections ADD COLUMN IF NOT EXISTS
    fingerprint BLOB;

-- Dedicated fingerprint index for fast lookup
CREATE TABLE IF NOT EXISTS content_fingerprints (
    id TEXT PRIMARY KEY,
    content_type TEXT NOT NULL,  -- 'conversation' or 'reflection'
    content_id TEXT NOT NULL,
    fingerprint BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(content_type, content_id)
);

-- Index for efficient similarity search
-- Note: DuckDB doesn't support custom index types, so we'll scan
CREATE INDEX idx_fingerprints_type ON content_fingerprints(content_type);
```

#### 4. Deduplication Logic

```python
class DeduplicationResult:
    """Result of deduplication check."""
    is_duplicate: bool
    similar_id: str | None = None
    similarity: float = 0.0
    action: Literal["store", "skip", "merge"] = "store"


async def check_duplicate(
    self,
    content: str,
    content_type: Literal["conversation", "reflection"],
    threshold: float = 0.85,
) -> DeduplicationResult:
    """Check if content is a near-duplicate of existing content.

    Args:
        content: Content to check
        content_type: Type of content
        threshold: Jaccard similarity threshold (default 0.85 = 85% similar)

    Returns:
        DeduplicationResult with duplicate status and action
    """
    # Generate fingerprint for new content
    ngrams = extract_ngrams(content, n=self.settings.fingerprint_ngram_size)
    new_sig = MinHashSignature.from_ngrams(ngrams, self.settings.fingerprint_num_hashes)

    # Query existing fingerprints
    rows = self.conn.execute("""
        SELECT content_id, fingerprint
        FROM content_fingerprints
        WHERE content_type = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, [content_type, self.settings.fingerprint_check_limit]).fetchall()

    # Check similarity against recent content
    for row in rows:
        existing_sig = MinHashSignature.from_bytes(
            row[1],
            num_hashes=self.settings.fingerprint_num_hashes
        )
        similarity = new_sig.jaccard_similarity(existing_sig)

        if similarity >= threshold:
            return DeduplicationResult(
                is_duplicate=True,
                similar_id=row[0],
                similarity=similarity,
                action="skip" if similarity > 0.95 else "merge",
            )

    return DeduplicationResult(is_duplicate=False, action="store")
```

### Integration Points

#### File: `session_buddy/adapters/reflection_adapter_oneiric.py`

```python
async def store_conversation(
    self,
    content: str,
    metadata: dict[str, Any] | None = None,
    deduplicate: bool = True,  # NEW parameter
) -> str:
    """Store conversation with optional deduplication."""

    if deduplicate and self.settings.deduplication_enabled:
        dedup_result = await self.check_duplicate(content, "conversation")

        if dedup_result.action == "skip":
            logger.debug(
                f"Skipping duplicate conversation (similarity={dedup_result.similarity:.2%})"
            )
            return dedup_result.similar_id  # Return existing ID

        if dedup_result.action == "merge":
            # Could merge metadata or update timestamp
            logger.debug(
                f"Near-duplicate detected (similarity={dedup_result.similarity:.2%}), storing anyway"
            )

    # Generate fingerprint for new content
    ngrams = extract_ngrams(content, n=self.settings.fingerprint_ngram_size)
    fingerprint = MinHashSignature.from_ngrams(ngrams).to_bytes()

    # Store with fingerprint
    conv_id = str(uuid.uuid4())
    # ... existing INSERT logic with fingerprint column ...

    # Also store in fingerprint index
    await self._store_fingerprint(conv_id, "conversation", fingerprint)

    return conv_id
```

### Configuration

Add to `session_buddy/adapters/settings.py`:

```python
class ReflectionAdapterSettings(BaseSettings):
    # Existing settings...

    # Deduplication settings
    deduplication_enabled: bool = True
    fingerprint_ngram_size: int = 3  # Character trigrams
    fingerprint_num_hashes: int = 128  # MinHash signature size
    fingerprint_similarity_threshold: float = 0.85  # 85% similar = duplicate
    fingerprint_check_limit: int = 1000  # Check against last N items
    fingerprint_skip_threshold: float = 0.95  # >95% = skip entirely
```

### Merge Strategy for Near-Duplicates

When `action == "merge"` (similarity between 85-95%):

```python
async def merge_conversation(
    self,
    existing_id: str,
    new_content: str,
    new_metadata: dict[str, Any] | None,
) -> str:
    """Merge new content with existing near-duplicate.

    Strategy:
    1. Keep the longer content (more information)
    2. Merge metadata (union of keys, newer values win)
    3. Update timestamp to most recent
    4. Increment a 'version' counter
    """
    existing = await self.get_conversation(existing_id)

    # Keep longer content
    final_content = (
        new_content if len(new_content) > len(existing["content"])
        else existing["content"]
    )

    # Merge metadata
    final_metadata = {**existing.get("metadata", {}), **(new_metadata or {})}

    # Update record
    self.conn.execute("""
        UPDATE conversations
        SET content = ?,
            metadata = ?,
            updated_at = CURRENT_TIMESTAMP,
            version = COALESCE(version, 1) + 1
        WHERE id = ?
    """, [final_content, json.dumps(final_metadata), existing_id])

    return existing_id
```

### Metrics & Observability

```python
def get_deduplication_stats(self) -> dict[str, Any]:
    """Return deduplication metrics."""
    return {
        "total_checked": self._dedup_checks,
        "duplicates_found": self._dedup_found,
        "duplicates_skipped": self._dedup_skipped,
        "duplicates_merged": self._dedup_merged,
        "dedup_rate": self._dedup_found / self._dedup_checks if self._dedup_checks > 0 else 0,
        "fingerprints_stored": self._get_fingerprint_count(),
    }
```

## Implementation Steps

### Phase 1: Core Fingerprinting Module (2-3 hours)

1. [ ] Create `session_buddy/utils/fingerprint.py` with:
   - `normalize_for_fingerprint()` function
   - `extract_ngrams()` function
   - `MinHashSignature` dataclass
1. [ ] Add fingerprint settings to `ReflectionAdapterSettings`
1. [ ] Add unit tests for fingerprinting functions

### Phase 2: Database Schema (1 hour)

1. [ ] Add `fingerprint` column to `conversations` table
1. [ ] Add `fingerprint` column to `reflections` table
1. [ ] Create `content_fingerprints` index table
1. [ ] Add migration script for existing databases

### Phase 3: Integration (2-3 hours)

1. [ ] Add `check_duplicate()` method to adapter
1. [ ] Modify `store_conversation()` to use deduplication
1. [ ] Modify `store_reflection()` to use deduplication
1. [ ] Implement `merge_conversation()` for near-duplicates
1. [ ] Add `_store_fingerprint()` helper method

### Phase 4: Testing (2-3 hours)

1. [ ] Unit tests for MinHash accuracy (known Jaccard values)
1. [ ] Integration tests for duplicate detection
1. [ ] Edge case tests (empty content, very short content, unicode)
1. [ ] Performance benchmarks for fingerprint generation

### Phase 5: MCP Tool Exposure (1 hour)

1. [ ] Add `deduplication_stats` tool to expose metrics
1. [ ] Add `find_duplicates` tool to scan for existing duplicates
1. [ ] Update `reflection_stats` to include dedup stats

## Dependencies

**Optional dependency** (same as Feature 1):

```toml
[project.optional-dependencies]
performance = ["xxhash>=3.0"]
```

**Fallback**: Use `hashlib.blake2b` with different seeds.

## Expected Impact

| Metric | Before | After (Estimated) |
|--------|--------|-------------------|
| Database size growth | Unbounded | 15-30% reduction |
| Duplicate entries | Common | \<5% slip-through |
| Search result quality | Diluted by duplicates | Cleaner results |
| Embedding compute | Every store | Skip for duplicates |
| Store latency | ~10ms | ~12-15ms (fingerprint overhead) |

## Similarity Threshold Tuning

| Threshold | Effect |
|-----------|--------|
| 0.70 | Aggressive dedup, may merge distinct content |
| 0.80 | Balanced, catches most duplicates |
| **0.85** | **Recommended default** |
| 0.90 | Conservative, only clear duplicates |
| 0.95 | Very conservative, near-exact only |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| False positives (distinct content marked duplicate) | Conservative threshold (0.85), option to disable |
| Fingerprint computation overhead | O(n) where n=content length, negligible for typical content |
| Storage overhead for fingerprints | 1KB per item (128 × 8-byte hashes), minimal |
| Index scan performance | Limit check to recent N items, can add LSH for larger scale |

## Future Enhancements (Not in Scope)

1. **Locality-Sensitive Hashing (LSH)**: For O(1) approximate nearest neighbor lookup instead of scanning
1. **Hierarchical fingerprints**: Different n-gram sizes for coarse-to-fine matching
1. **Semantic deduplication**: Combine fingerprints with embedding similarity
1. **Cross-project deduplication**: Dedupe across all projects (currently per-project)

## Success Criteria

- [ ] >90% of exact duplicates detected
- [ ] >70% of near-duplicates (>85% similar) detected
- [ ] \<1% false positive rate (distinct content incorrectly merged)
- [ ] Store latency increase \<50% (target \<15ms)
- [ ] All existing tests pass
- [ ] New dedup tests achieve >90% coverage

## References

- MinHash algorithm: https://en.wikipedia.org/wiki/MinHash
- Jaccard similarity: https://en.wikipedia.org/wiki/Jaccard_index
- DeepSeek Engram: https://github.com/deepseek-ai/Engram
- xxhash Python: https://github.com/ifduyue/python-xxhash
- DuckDB BLOB handling: https://duckdb.org/docs/sql/data_types/blob
