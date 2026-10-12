-- =====================================================================
-- 001_down.sql — reverse of 001_consolidate_conversations.sql
--
-- Reverses the 3-way merge of conversations_v2, conversations (v0),
-- and default_conversations into the canonical `conversations` table.
--
-- Scope of reversal:
--   * Step 1: drop the dependent memory_* tables (memory_entities,
--     memory_relationships, memory_promotions) and memory_access_log.
--     These were either (a) emptied + recreated in 001 step F with
--     FKs pointing at `conversations(id)`, or (b) in the case of
--     memory_access_log, fully rebuilt in step G. The down-script
--     drops them so the subsequent `conversations` -> `conversations_v2`
--     rename can proceed (DuckDB strictly enforces FK dependents).
--   * Step 2: drop the indexes that 001 step E re-created on the
--     renamed `conversations` table (they target v2 column expressions
--     and must not survive the rename to conversations_v2).
--   * Step 3: rename `conversations` back to `conversations_v2`.
--   * Step 4: re-create `conversations_legacy` (v0 schema) and
--     `default_conversations` (v0 schema) as empty tables. Document
--     the data fidelity loss: the 3-way merge in the up-script mixed
--     the v0-unique rows and the 5 default_conversations rows into
--     `conversations`; the down-script cannot reconstruct which row
--     originated from which source. The original v0 conversations
--     table was dropped by 004, the original default_conversations
--     table was dropped by 005; both row sets now live in
--     `conversations_v2` (post-step 3) and are indistinguishable from
--     the original v2 rows.
--   * Step 5: re-create the v2 indexes on `conversations_v2` (matching
--     the schema_v2.py CREATE INDEX IF NOT EXISTS block).
--   * Step 6: re-create the memory_* dependents with the v2 schema
--     (FKs pointing at `conversations_v2(id)` per the v2 contract).
--
-- Data loss (per-step 4 above): the 265 v0-unique rows and the 5
-- default_conversations rows are no longer separable from the 935
-- original v2 rows. The down-script's `conversations_legacy` and
-- `default_conversations` are recreated EMPTY.
--
-- Embedding note: vector embeddings (FLOAT[384]) are preserved
-- through the rename (column type is unchanged). The reversibility
-- concern is for ID mapping, not the embedding bytes themselves.
--
-- Idempotency: this script is NOT natively idempotent (the 001 up
-- script is not idempotent either, and the down mirrors that). The
-- memory_* DROP statements use IF EXISTS for the empty-table case.
-- Re-running on a partially-migrated or already-reversed DB will
-- fail loudly; restore the Phase 1 archive to retry.
--
-- Atomicity: the rename in step 3 is a single DDL statement; the
-- dependent CREATE TABLE statements in steps 4 and 6 are independent.
-- Wrapped in BEGIN; ... COMMIT; to keep the rename and the dependent
-- table drops atomic.
-- =====================================================================

BEGIN;

-- Step 1: drop the dependents so the conversations -> conversations_v2
-- rename can proceed. memory_relationships must be dropped before
-- memory_entities (FK chain).
DROP TABLE IF EXISTS memory_relationships;
DROP TABLE IF EXISTS memory_entities;
DROP TABLE IF EXISTS memory_promotions;
DROP TABLE IF EXISTS memory_access_log;

-- Step 2: drop the v2 indexes (they target v2 column expressions and
-- must not survive the rename; they get re-created on conversations_v2
-- in step 5).
DROP INDEX IF EXISTS idx_conversations_category;
DROP INDEX IF EXISTS idx_conversations_tier;
DROP INDEX IF EXISTS idx_conversations_namespace;
DROP INDEX IF EXISTS idx_conversations_timestamp;
DROP INDEX IF EXISTS idx_conversations_access;
DROP INDEX IF EXISTS idx_conversations_fts;
DROP INDEX IF EXISTS idx_v2_source_type_project;

-- Step 3: rename the canonical `conversations` back to `conversations_v2`.
-- This restores the v2 table to its pre-001 name. All rows currently in
-- `conversations` (1205 = 935 original v2 + 265 v0-unique + 5 default)
-- move with the rename. The down-script does not split them out
-- (see step 4 data-loss note).
ALTER TABLE conversations RENAME TO conversations_v2;

-- Step 4: re-create the v0 conversations_legacy table and the v0
-- default_conversations table, both empty. The v0 schema for
-- conversations_legacy mirrors the columns referenced in 001 step 3
-- (id, content, embedding, project, timestamp, metadata). The v0
-- schema for default_conversations mirrors the columns referenced
-- in 001 step 4 + the CREATE TABLE IF NOT EXISTS sentinel in 001
-- (id, content, embedding, subcategory, fingerprint, metadata,
-- created_at). `metadata` is JSON on the v0 source (DuckDB implicit
-- JSON -> VARCHAR cast in the up-script confirms this).
CREATE TABLE IF NOT EXISTS conversations_legacy (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],
    project TEXT,
    timestamp TIMESTAMP,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS default_conversations (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],
    subcategory TEXT,
    fingerprint TEXT,
    metadata VARCHAR,
    created_at TIMESTAMP
);

-- Step 5: re-create the v2 indexes on `conversations_v2`. Same column
-- expressions as the schema_v2.py CREATE INDEX IF NOT EXISTS block.
CREATE INDEX IF NOT EXISTS idx_conversations_category
    ON conversations_v2(category, namespace);
CREATE INDEX IF NOT EXISTS idx_conversations_tier
    ON conversations_v2(memory_tier, importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_namespace
    ON conversations_v2(namespace, project);
CREATE INDEX IF NOT EXISTS idx_conversations_timestamp
    ON conversations_v2(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_access
    ON conversations_v2(last_accessed DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_fts
    ON conversations_v2(searchable_content);
CREATE INDEX IF NOT EXISTS idx_v2_source_type_project
    ON conversations_v2(source_type, project, timestamp DESC);

-- Step 6: re-create the dependent memory_* tables with FKs pointing
-- at conversations_v2(id) per the v2 contract. All three are 0-row
-- (per the pre-001 verified state in the Phase 1 archive), so the
-- FK re-creation does not require any data movement.
CREATE TABLE IF NOT EXISTS memory_entities (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations_v2(id)
);
CREATE INDEX IF NOT EXISTS idx_entities_type
    ON memory_entities(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_entities_memory
    ON memory_entities(memory_id);

CREATE TABLE IF NOT EXISTS memory_relationships (
    id TEXT PRIMARY KEY,
    from_entity_id TEXT NOT NULL,
    to_entity_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    strength REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_entity_id) REFERENCES memory_entities(id),
    FOREIGN KEY (to_entity_id) REFERENCES memory_entities(id)
);
CREATE INDEX IF NOT EXISTS idx_relationships_from
    ON memory_relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_to
    ON memory_relationships(to_entity_id);

CREATE TABLE IF NOT EXISTS memory_promotions (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    from_tier TEXT NOT NULL,
    to_tier TEXT NOT NULL,
    reason TEXT,
    priority_score REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations_v2(id)
);

-- memory_access_log is recreated empty; 001 step G rebuilt it from
-- memory_access_log_backup which itself was created in 001 step C
-- (after the down, no memory_access_log_backup survives since 001's
-- step G dropped it; the original 3 rows are in the post-007
-- memory_access_log table, which is dropped in 001_down step 1).
-- The down-script leaves memory_access_log empty.
CREATE TABLE IF NOT EXISTS memory_access_log (
    id TEXT PRIMARY KEY,
    memory_id TEXT,
    access_type TEXT,
    query_text TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations_v2(id)
);
CREATE INDEX IF NOT EXISTS idx_access_log_memory
    ON memory_access_log(memory_id, timestamp DESC);

COMMIT;
