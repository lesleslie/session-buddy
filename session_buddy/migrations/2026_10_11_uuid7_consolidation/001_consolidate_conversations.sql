-- =====================================================================
-- 001_consolidate_conversations.sql
--
-- Phase 0 / Step 1-4: Consolidate three conversation tables into a
-- single canonical `conversations` table.
--
-- Source tables (pre-migration):
--   conversations         (legacy v0) -- 1195 rows; 265 v0-unique
--   conversations_v2      (canonical v2) -- 935 rows; canonical
--   default_conversations (vestigial) -- 5 rows; previously dropped
--                                     silently by migration 005
--                                     (Phase 0.5 verification
--                                     2026-10-11 confirmed the
--                                     asymmetric treatment vs
--                                     default_reflections).
--
-- Target (post-migration):
--   conversations                  -- canonical name (renamed from
--                                    conversations_v2); 1205 rows
--                                    (935 + 265 + 5).
--   conversations_legacy           -- renamed from conversations;
--                                    preserved until DROP in 004.
--   default_conversations          -- preserved until DROP in 005.
--
-- Id pass-through: existing `id` values are kept verbatim in this
-- pass. They are 32-lowercase-hex in the live data. Script
-- 007_id_swap_load_bearing.sql is responsible for the formal
-- UUID7 conversion (rename id → legacy_id, add uuid7_id TEXT
-- NOT NULL, backfill via uuid7() UDF, drop legacy_id, rename
-- uuid7_id → id, rebuild PK constraints and indexes). 007
-- regenerates UUID7s from uuid.uuid7() rather than reusing
-- the existing IDs, so this pass preserves whatever form the
-- pre-migration IDs are in for traceability through 007.
--
-- Row-count invariants (verified in
-- tests/integration/test_uuid7_consolidation.py::
-- test_conversations_merged):
--   step 1+2: 935 rows in canonical `conversations`
--   step 3:   + 265 v0-unique rows (1195 v0 - 930 v0 ∩ v2)
--             = 1200 distinct rows
--   step 4:   + 5 default_conversations rows
--             = 1205 distinct rows in the merged table
--
-- Engine: DuckDB (reflections.duckdb). Schema uses DuckDB
-- types — FLOAT[384] arrays, TIMESTAMP, JSON columns.
-- DuckDB implicitly casts the cross-type `metadata` columns
-- (conversations_legacy.metadata is JSON;
-- default_conversations.metadata is JSON; target
-- conversations.metadata is VARCHAR) — confirmed via dry-run.
--
-- Transactional note (DuckDB-specific): per the DuckDB
-- documentation, "DDL is not transactional" — most DDL
-- statements auto-commit, so wrapping the whole script in
-- a single BEGIN; ... COMMIT; would not actually roll back
-- half-executed DDL on error (and in fact breaks the
-- `ALTER TABLE ... RENAME` operations mid-script because
-- re-evaluating a stale FK reference inside the open
-- transaction produces a binder error against the new
-- table name). Step 3 and step 4 (the only DML-heavy
-- phases) ARE wrapped in a single BEGIN; ... COMMIT; so a
-- mid-INSERT failure rolls back the row population;
-- recovery is then a re-run of the entire script.
--
-- FK-blocked index/table dance (steps A–D before the renames):
-- DuckDB does not support `ALTER TABLE ... DROP CONSTRAINT`
-- for FK declarations, and `ALTER TABLE x RENAME` errors with
-- "Cannot alter entry 'x' because there are entries that
-- depend on it" while FK dependents (or indexes) reference x.
-- The only FK-removal path is DROP+CREATE (or COPY+DROP+CREATE
-- for non-empty tables). Affected dependents:
--   memory_entities     (0 rows; FK → conversations_v2.id)
--   memory_promotions   (0 rows; FK → conversations_v2.id)
--   memory_access_log   (3 rows; FK → conversations_v2.id;
--                        rows preserved via memory_access_log_backup)
-- Plus the indexes on conversations (v0) and conversations_v2
-- (rename does not transfer indexes; they must be re-created
-- on the renamed table post-merge).
-- memory_relationships has FKs only to memory_entities, so it
-- is dropped first to break the dependency chain before
-- memory_entities itself is dropped.
--
-- Idempotency: this script assumes a fresh pre-migration DB.
-- To re-run, restore the Phase 1 archive (`~/.local/state/bodai/
-- db-archive/2026-10-11-uuid7-migration/<component>-<file>`)
-- first. DuckDB does not support `ALTER TABLE IF EXISTS ...
-- RENAME`; we accept that constraint.
-- =====================================================================

-- =================================================================
-- Step A: Drop indexes on conversations (v0). Two indexes —
-- idx_conversations_project and idx_conversations_timestamp —
-- block the v0 rename; conversations_legacy is being dropped in
-- 003, so the indexes do not need to be recreated. (Updated: 003 is now 004 after the v0 reflections pre-drop moved ahead in the script ordering.)
-- =================================================================
DROP INDEX IF EXISTS idx_conversations_project;
DROP INDEX IF EXISTS idx_conversations_timestamp;

-- =================================================================
-- Step B: Drop FK dependents in dependency order so the
-- conversations_v2 rename in step 2 can proceed.
--
-- memory_relationships has FKs to memory_entities, so drop it
-- first to break the chain. memory_entities and memory_promotions
-- each hold an FK to conversations_v2(id). Both are empty (0
-- rows), so DROP is safe.
-- =================================================================
DROP TABLE IF EXISTS memory_relationships;
DROP TABLE IF EXISTS memory_entities;
DROP TABLE IF EXISTS memory_promotions;

-- =================================================================
-- Step C: Preserve the 3 memory_access_log rows. Copy out,
-- drop the original (which holds the FK to conversations_v2),
-- recreate memory_access_log FK-less. After the merge in steps
-- 3 and 4 below, we re-attach the FK in step G.
--
-- Note on `query_text`: SCHEMA_V2_SQL declares
-- `query_text TEXT` on memory_access_log. The live
-- reflections.duckdb does NOT include that column on the
-- already-deployed table (verified 2026-10-11 via
-- `DESCRIBE memory_access_log`). The CREATE below includes
-- `query_text` as a nullable column so 007_id_swap_load_bearing.sql
-- can SELECT mal.query_text without an OperationalError, and
-- so the recreated table matches the canonical schema
-- declared in schema_v2.py:158-160. Rows copied from the
-- live table (which lacks the column) get NULL for
-- query_text; the loss of any pre-existing query_text values
-- is the documented cost of this pass (verified there are 0
-- in the archive copy).
-- =================================================================
CREATE TABLE memory_access_log_backup AS SELECT * FROM memory_access_log;
DROP TABLE memory_access_log;
CREATE TABLE memory_access_log (
    id TEXT PRIMARY KEY,
    memory_id TEXT,           -- nullable: search hits often have no memory_id
    access_type TEXT,
    query_text TEXT,          -- nullable; absent on the pre-migration table
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =================================================================
-- Step D: Drop indexes on conversations_v2 (rename does not
-- transfer indexes; they get recreated in step E).
-- =================================================================
DROP INDEX IF EXISTS idx_conversations_access;
DROP INDEX IF EXISTS idx_conversations_category;
DROP INDEX IF EXISTS idx_conversations_fts;
DROP INDEX IF EXISTS idx_conversations_namespace;
DROP INDEX IF EXISTS idx_conversations_tier;
DROP INDEX IF EXISTS idx_v2_source_type_project;

-- =================================================================
-- Step 1 (plan-aligned): rename v0 `conversations` to
-- `conversations_legacy`. After this, the canonical
-- `conversations` name is free for step 2 to claim.
-- =================================================================
ALTER TABLE conversations RENAME TO conversations_legacy;

-- =================================================================
-- Step 2 (plan-aligned): promote `conversations_v2` to the
-- canonical name. User-decided convention from the
-- 2026-10-11 plan: drop the `_v2` suffix post-migration; v2
-- is now the only "versioned" conversation table.
-- =================================================================
ALTER TABLE conversations_v2 RENAME TO conversations;

-- =================================================================
-- Steps 3 + 4 (plan-aligned): absorb the 265 v0-unique rows
-- (step 3) and the 5 `default_conversations` rows (step 4)
-- into the renamed `conversations` table. Wrapped in
-- BEGIN; ... COMMIT; to roll back the row inserts as a
-- single unit if either step errors.
--
-- Step 3 (265 rows): set difference between the v0 set and
-- the v0 ∩ v2 overlap. Schema backfill rules:
--   category         NOT NULL, no default  → legacy v0→v2 heuristic
--                                            from
--                                            memory/schema_v2.py::
--                                            MIGRATION_SQL.
--   subcategory       nullable             → NULL.
--   importance_score  DEFAULT 0.5           → omitted; inherits.
--   memory_tier       DEFAULT 'long_term'   → omitted; inherits.
--   access_count      DEFAULT 0             → omitted; inherits.
--   last_accessed     nullable             → omitted; inherited NULL.
--   namespace         DEFAULT 'default'     → 'default'.
--   user_id           DEFAULT 'default'     → 'default'.
--   searchable_content nullable             → content mirror.
--   fingerprint       nullable             → omitted; inherited NULL.
--   metadata          (target VARCHAR)     → legacy JSON → VARCHAR
--                                            via DuckDB implicit cast.
--   source_type       nullable             → 'migration' (per
--                                            CHECK constraint allowlist
--                                            `migration`).
--   turn_parent_id    nullable             → omitted; inherited NULL.
--   causal_parent_id  nullable             → omitted; inherited NULL.
--
-- Step 4 (5 rows): `default_conversations` set, no overlap
-- with v0 or v2. Schema backfill rules: every v2 column on
-- `conversations` either carries a schema DEFAULT or is
-- NULLABLE, so every column on `default_conversations` that
-- does not exist on v2 (none) is honored as-is. category
-- defaults to 'facts' because default_conversations did
-- not track category in its v0 schema; this is conservative
-- (vs the legacy v0 heuristic which does not apply to
-- non-checkpoint content). timestamp is mapped from
-- `created_at` because the v0 `conversations` table does not
-- have a separate created_at column; v2 semantics put
-- `timestamp` on the row.
--
-- Resulting merged table: 935 + 265 + 5 = 1205 distinct rows.
--
-- Guard: `default_conversations` may not exist on every
-- deployment (the only production-code reference is a
-- docstring in tests/integration/test_existing_callers_still_work.py:28;
-- no current code path creates it). The CREATE TABLE IF NOT
-- EXISTS below is a no-op when the real table exists, and
-- creates a 0-row sentinel with the columns the SELECT
-- references when it does not — so the subsequent INSERT
-- SELECT does not fail at parse time. The sentinel has the
-- same name as the real table, so 005's DROP TABLE IF EXISTS
-- still cleans it up at the end of Phase 0.
-- =================================================================
CREATE TABLE IF NOT EXISTS default_conversations (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],
    subcategory TEXT,
    metadata VARCHAR,
    created_at TIMESTAMP
);

BEGIN;

INSERT INTO conversations (
    id, content, embedding, category, subcategory,
    project, namespace, user_id, timestamp,
    searchable_content, metadata, source_type
)
SELECT
    legacy.id,
    legacy.content,
    legacy.embedding,
    CASE
        -- LOWER() makes the keyword match case-insensitive so 'Prefer', 'PREFER',
        -- 'prefer', and 'PreFer' all bucket into the same category. Without
        -- LOWER, mixed-case content silently lands in 'facts' and the downstream
        -- category-stats dashboards undercount 'preferences' / 'context'.
        WHEN LOWER(legacy.content) LIKE '%prefer%' THEN 'preferences'
        WHEN LOWER(legacy.content) LIKE '%error%' OR LOWER(legacy.content) LIKE '%bug%' THEN 'context'
        ELSE 'facts'
    END                                                    AS category,
    NULL                                                   AS subcategory,
    legacy.project,
    'default'                                              AS namespace,
    'default'                                              AS user_id,
    legacy.timestamp,
    legacy.content                                         AS searchable_content,
    legacy.metadata,
    'migration'                                            AS source_type
FROM conversations_legacy AS legacy
WHERE NOT EXISTS (
    SELECT 1 FROM conversations AS c WHERE c.id = legacy.id
);

INSERT INTO conversations (
    id, content, embedding, category, subcategory,
    namespace, user_id, timestamp,
    searchable_content, metadata, source_type
)
SELECT
    def.id,
    def.content,
    def.embedding,
    'facts'                                                AS category,
    def.subcategory,
    'default'                                              AS namespace,
    'default'                                              AS user_id,
    def.created_at                                         AS timestamp,
    def.content                                            AS searchable_content,
    def.metadata,
    'migration'                                            AS source_type
FROM default_conversations AS def
WHERE NOT EXISTS (
    SELECT 1 FROM conversations AS c WHERE c.id = def.id
);

COMMIT;

-- =================================================================
-- Step E: re-create the v2 conversation indexes on the
-- renamed canonical `conversations` table. Same column
-- expressions as the SCHEMA_V2_SQL block; the names are
-- unchanged so downstream code that references them by
-- name keeps working. `CREATE INDEX IF NOT EXISTS` is the
-- idempotency guard.
-- =================================================================
CREATE INDEX IF NOT EXISTS idx_conversations_category
    ON conversations(category, namespace);
CREATE INDEX IF NOT EXISTS idx_conversations_tier
    ON conversations(memory_tier, importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_namespace
    ON conversations(namespace, project);
CREATE INDEX IF NOT EXISTS idx_conversations_timestamp
    ON conversations(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_access
    ON conversations(last_accessed DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_fts
    ON conversations(searchable_content);
CREATE INDEX IF NOT EXISTS idx_v2_source_type_project
    ON conversations(source_type, project, timestamp DESC);

-- =================================================================
-- Step F: re-create the dependent memory_* tables with FKs
-- pointing at the canonical `conversations(id)`. The three
-- tables are recreated with the same column shape as
-- SCHEMA_V2_SQL; FKs now target `conversations` (no longer
-- `conversations_v2` by name; DuckDB does track FKs by
-- OID, but the rename changes the FK target table as
-- part of the rename propagation — verified empty since
-- the dependents were dropped before the rename). All
-- three tables are 0-row at this point, so the FK
-- re-creation does not require any data movement.
-- =================================================================
CREATE TABLE IF NOT EXISTS memory_entities (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
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
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
);

-- =================================================================
-- Step G: rebuild memory_access_log with its FK pointing at
-- `conversations(id)`, then INSERT the 3 preserved rows from
-- `memory_access_log_backup`, then DROP the backup. The
-- COPY-and-recreate path is required because DuckDB does
-- not support `ALTER TABLE ... ADD CONSTRAINT` for FKs;
-- only CREATE TABLE with the FK inlined or DROP+CREATE.
--
-- Order matters: DROP the FK-less memory_access_log (from
-- step C) before the FK-bearing CREATE; the FK-bearing
-- INSERT then validates against the canonical
-- `conversations` table; DROP backup last so the
-- row-preserving INSERT is observed end-to-end.
--
-- FK validation: the 3 preserved memory_id values all resolve
-- into the renamed `conversations` table (they previously
-- resolved into `conversations_v2`, which became `conversations`
-- in step 2 — verified via dry-run against a Phase 1 archive
-- copy).
-- =================================================================
DROP TABLE memory_access_log;
CREATE TABLE memory_access_log (
    id TEXT PRIMARY KEY,
    memory_id TEXT,
    access_type TEXT,
    query_text TEXT,          -- nullable; absent on the pre-migration table;
                              --           rows from backup get NULL
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
);
INSERT INTO memory_access_log (id, memory_id, access_type, query_text, timestamp)
SELECT id, memory_id, access_type, NULL, timestamp
FROM memory_access_log_backup;
CREATE INDEX IF NOT EXISTS idx_access_log_memory
    ON memory_access_log(memory_id, timestamp DESC);
DROP TABLE memory_access_log_backup;

-- ---------------------------------------------------------------------
-- Post-migration invariants (verified in
-- tests/integration/test_uuid7_consolidation.py::
-- test_conversations_merged):
--
--   rows_in(conversations)              == 1205  -- 935 + 265 + 5
--   distinct_count(id, conversations)   == 1205
--   conversations_v2                    not in (tables)
--   conversations                        in (tables)
--   conversations_legacy                 in (tables)   -- until 004
--   default_conversations                in (tables)   -- until 005
--   memory_access_log rows               == 3 (preserved)
--   memory_entities / promotions / relationships rows == 0 (preserved)
-- ---------------------------------------------------------------------
