# Session-Buddy ULID Migration Analysis

**Date:** 2026-02-12
**Status:** Ready for Migration Design
**Priority:** HIGH (Session tracking is core to ecosystem coordination)

---

## Current Identifier Format

### Conversations Table
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,  -- MD5 hash: {content}_{time.time()}
    content TEXT NOT NULL,
    embedding BLOB,           -- Pre-computed embedding vector
    project TEXT,
    timestamp TIMESTAMP NOT NULL,
    metadata TEXT                -- JSON serialized metadata
);
```

**Current ID Generation:**
```python
conversation_id = hashlib.md5(
    f"{content}_{time.time()}".encode("utf-8", "surrogatepass"),
    usedforsecurity=False,
).hexdigest()
```
- **Format:** 32-character hexadecimal MD5 hash
- **Example:** `a3f5e92ab1f8a4f9d4b1c8a7d9b3b6d123`
- **Properties:** Deterministic (same content = same ID), no time ordering, collision-resistant

### Reflections Table
```sql
CREATE TABLE reflections (
    id TEXT PRIMARY KEY,  -- MD5 hash: reflection_{content}_{time.time()}
    content TEXT NOT NULL,
    embedding BLOB,
    project TEXT,
    tags TEXT,                -- JSON array of tags
    timestamp TIMESTAMP NOT NULL,
    metadata TEXT
);
```

**Current ID Generation:**
```python
reflection_id = hashlib.md5(
    f"reflection_{content}_{time.time()}".encode("utf-8", "surrogatepass"),
    usedforsecurity=False,
).hexdigest()
```
- **Format:** 32-character hexadecimal MD5 hash
- **Example:** `c7b8e22a1f3d9e4f7a6b5c8d4e9f7a123456`

### Code Graphs Table
```sql
CREATE TABLE code_graphs (
    id TEXT PRIMARY KEY,  -- Composite: {repo_path}:{commit_hash}
    repo_path TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    indexed_at TIMESTAMP NOT NULL,
    nodes_count INTEGER,
    graph_data TEXT,            -- JSON: {nodes: [...], edges: [...]}
    metadata TEXT
);
```

**Current ID Generation:**
```python
code_graph_id = f"{repo_path}:{commit_hash}"
```
- **Format:** Composite string with colon delimiter
- **Example:** `/Users/les/Projects/mahavishnu:d924b55efac9b620`
- **Properties:** Hierarchical, globally unique within repo, but not time-sorted

---

## Migration Strategy

### Phase 1: Expand Schema (Zero Downtime)

**Step 1.1: Add ULID Columns**
```sql
-- Conversations table expansion
ALTER TABLE conversations ADD COLUMN conversation_ulid TEXT;
ALTER TABLE conversations ADD COLUMN conversation_ulid_generated_at TIMESTAMP;

-- Reflections table expansion
ALTER TABLE reflections ADD COLUMN reflection_ulid TEXT;
ALTER TABLE reflections ADD COLUMN reflection_ulid_generated_at TIMESTAMP;

-- Code graphs table expansion
ALTER TABLE code_graphs ADD COLUMN code_graph_ulid TEXT;
ALTER TABLE code_graphs ADD COLUMN code_graph_ulid_generated_at TIMESTAMP;
```

**Step 1.2: Backfill ULIDs for Existing Records**
```sql
-- Backfill conversations (batch-safe)
UPDATE conversations
SET conversation_ulid = generate_ulid(),
    conversation_ulid_generated_at = datetime('now')
WHERE conversation_ulid IS NULL;

UPDATE reflections
SET reflection_ulid = generate_ulid(),
    reflection_ulid_generated_at = datetime('now')
WHERE reflection_ulid IS NULL;

UPDATE code_graphs
SET code_graph_ulid = generate_ulid(),
    code_graph_ulid_generated_at = datetime('now')
WHERE code_graph_ulid IS NULL;
```

**Step 1.3: Create Indexes for Performance**
```sql
CREATE INDEX IF NOT EXISTS idx_conversations_ulid
ON conversations(conversation_ulid);

CREATE INDEX IF NOT EXISTS idx_reflections_ulid
ON reflections(reflection_ulid);

CREATE INDEX IF NOT EXISTS idx_code_graphs_ulid
ON code_graphs(code_graph_ulid);
```

---

## Application Code Changes Required

### File: `session_buddy/reflection/storage.py`

**Change 1: Update store_conversation()**
```python
# OLD:
conversation_id = hashlib.md5(...).hexdigest()

# NEW:
try:
    from dhruva import generate as generate_ulid
except ImportError:
    # Use timestamp-based fallback
    conversation_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{os.urandom(3).hex()}"
```

**Change 2: Update store_reflection()**
```python
# OLD:
reflection_id = hashlib.md5(...).hexdigest()

# NEW:
try:
    from dhruva import generate as generate_ulid
except ImportError:
    # Use timestamp-based fallback
    reflection_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{os.urandom(3).hex()}"
```

**Change 3: Update store_code_graph()**
```python
# OLD:
code_graph_id = f"{repo_path}:{commit_hash}"

# NEW:
try:
    from dhruva import generate as generate_ulid
except ImportError:
    # Use composite fallback
    code_graph_id = f"{repo_path}:{commit_hash}:{generate_ulid()}"
```

---

## Migration Timeline Estimate

- **Records to migrate:** ~10,000 conversations + reflections (estimated based on typical usage)
- **Batch size:** 1,000 records per batch (10 batches total)
- **Estimated time:** 2-5 minutes per batch (ULID generation is fast)
- **Total migration time:** 20-50 minutes for backfill
- **Verification period:** 7 days (keep both IDs active, monitor for issues)

---

## Rollback Strategy

If migration fails, rollback by:
```sql
-- Drop ULID columns
ALTER TABLE conversations DROP COLUMN conversation_ulid;
ALTER TABLE conversations DROP COLUMN conversation_ulid_generated_at;

-- Keep MD5 hash as active identifier
-- No application code changes needed (ULID fields just ignored)
```

---

## Testing Checklist

- [ ] Unit test: ULID generation in isolation
- [ ] Integration test: Store conversation with ULID
- [ ] Migration test: Backfill 1,000 records
- [ ] Verification test: Query by both old and new IDs
- [ ] Performance test: Ensure ULID indexes improve query performance
- [ ] Rollback test: Verify rollback path works cleanly

---

## Next Steps

1. **Design complete migration SQL script** with transaction safety
2. **Create ULID generation wrapper** in Session-Buddy utilities
3. **Implement dual-write period** where both MD5 and ULID are active
4. **Update MCP tools** to expose ULID fields in responses
5. **Execute migration** during maintenance window (user sessions are idle)
