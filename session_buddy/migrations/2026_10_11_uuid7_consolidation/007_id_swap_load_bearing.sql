-- =====================================================================
-- Migration 007: ID swap for load-bearing tables (DuckDB-native)
-- Plan: ~/Projects/mahavishnu/docs/plans/2026-10-11-uuid7-only-migration.md
--       (Phase 0, script 7 of 10)
--
-- Goal: Convert the primary key of every load-bearing table from the
--       pre-migration shape (whatever 001-006 produced) to a strict
--       UUID7 hex string (32 lowercase hex chars, no dashes), generated
--       fresh by the registered uuid7() UDF.
--
-- -------------------------------------------------------------------------
-- WHY CTAS (CREATE TABLE-AS + INSERT SELECT + DROP + RENAME), NOT ALTER
-- -------------------------------------------------------------------------
-- The previous version of this script used the SQLite-12-step rebuild
-- pattern (RENAME COLUMN id -> legacy_id, ADD COLUMN uuid7_id TEXT NOT
-- NULL DEFAULT '0...0', UPDATE ... SET uuid7_id = uuid7(),
-- CREATE TABLE new, INSERT, DROP, ALTER RENAME). DuckDB 1.5.6 rejects
-- `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT <literal>` at the
-- parser (DuckDB issue #16836 -- "Adding columns with constraints not
-- yet supported"). It also does not support `PRAGMA foreign_keys = OFF`
-- (DuckDB FK enforcement is connection-level, not PRAGMA-controllable,
-- and the CTAS rebuild preserves FKs naturally by translating dependent
-- columns BEFORE the FK is re-asserted on the new table). It also does
-- not support partial-index `WHERE` clauses on `CREATE INDEX`; those
-- predicates are stripped in this version. The CTAS pattern sidesteps
-- all three limitations in one go: the new schema is materialized in a
-- single CREATE TABLE statement, the data is copied with `uuid7()` in
-- the SELECT list, and the legacy table is dropped and renamed in two
-- statements that DuckDB supports natively. THIS IS THE CANONICAL
-- DUCKDB MIGRATION IDIOM -- DO NOT REGRESS TO ALTER TABLE.
--
-- -------------------------------------------------------------------------
-- CTAS pattern (per table)
-- -------------------------------------------------------------------------
--   1. CREATE TABLE <name>_new with the UUID7 target schema (id TEXT
--      PRIMARY KEY, no legacy_id column).
--   2. INSERT INTO <name>_new SELECT ... FROM <name>; the new id is
--      produced by uuid7() in the SELECT list (or by a JOIN onto
--      conv_id_map for the conversations table, so the mapping can be
--      reused by the memory_access_log rebuild).
--   3. DROP TABLE <name>.
--   4. ALTER TABLE <name>_new RENAME TO <name>.
--   5. Recreate the secondary indexes that reference `id` and other
--      columns (the rebuild drops the original indexes along with the
--      original table in step 3). Partial-index WHERE predicates are
--      dropped -- DuckDB does not support them.
--
-- -------------------------------------------------------------------------
-- Target tables (5 load-bearing)
-- -------------------------------------------------------------------------
--   1. conversations      -- Phase 0 script 001 renamed conversations_v2
--                            -> conversations (and absorbed the v0 +
--                            default_conversations rows). This script
--                            UUID7-izes the post-001 shape.
--   2. reflections        -- Phase 0 script 003 renamed reflections_v2
--                            -> reflections (and absorbed the
--                            default_reflections rows; the v0 reflections
--                            table was pre-dropped by 002). This script
--                            UUID7-izes the post-003 shape.
--   3. code_graphs        -- load-bearing per the plan; survives in
--                            session_buddy/mcp/tools/code_graph.py via
--                            the SQL fallback path. Schemas tracked in
--                            storage/migrations/V6__ulid_contract__up.sql.
--   4. session_windows    -- canonical session-identity table
--                            (schema_v2.py CROSS_REPO_CHECKPOINT_V2_1_DDL).
--   5. memory_access_log  -- access-tracking event log. NOT a vestige;
--                            schema_v2.py:161 declares 3 real rows. FK
--                            -> conversations(id); the conv_id_map pass
--                            below translates the legacy memory_id
--                            values to UUID7 before the new table asserts
--                            the FK.
--
-- -------------------------------------------------------------------------
-- Depends on (B-step ordering; the adversarial review 2026-10-11
-- caught the original a-step ordering where 003 ran before 002, which
-- is impossible because 002 drops the v0 `reflections` table that 003
-- needs to already be free of):
-- -------------------------------------------------------------------------
--   * 001_consolidate_conversations.sql -- v0+v2+default -> conversations
--   * 002_drop_legacy_reflections.sql   -- v0 reflections dropped (B-step
--                                          pre-drop required for 003)
--   * 003_consolidate_reflections.sql    -- v2 + default_reflections
--                                          -> reflections
--   * 004_drop_legacy_conversations.sql  -- v0 conversations (renamed
--                                          conversations_legacy by 001)
--                                          dropped
--   * 005_drop_legacy_default_conversations.sql -- default_conversations
--                                                  dropped
--   * 006_drop_vestigial.sql             -- access_log_v2 +
--                                          query_cache_l2 dropped;
--                                          __uuid7_migration_done
--                                          marker created
--
-- -------------------------------------------------------------------------
-- Pre-conditions (enforced by the migration runner, not this SQL file)
-- -------------------------------------------------------------------------
--   1. The migration runner MUST register a `uuid7()` SQL function (UDF)
--      that returns a 32-character lowercase hex string (no dashes).
--      DuckDB: `con.create_function("uuid7", 0, lambda: ...)`. Without
--      the UDF, every INSERT below will fail at parse / runtime.
--   2. All 5 load-bearing tables must exist in the target database
--      (they were left behind by 001-006 with their non-UUID7 ids).
--   3. `conversations` (NOT `conversations_v2`) must be the current
--      name; this script UUID7-izes the post-001 table.
--
-- -------------------------------------------------------------------------
-- Idempotency
-- -------------------------------------------------------------------------
--   * This script is NOT natively idempotent. DuckDB does not support
--     `CREATE TABLE IF NOT EXISTS` on a table name already in use
--     when the schema differs, and the per-table `_new` shadow names
--     are persistent (not TEMP) so a partial re-run will fail at
--     `CREATE TABLE <name>_new`. The migration runner MUST treat this
--     script as one-shot. Re-running on an already-migrated DB will
--     fail loudly on the first `CREATE TABLE`; that is the intended
--     contract. Operator must restore from the Phase 1 archive at
--     `~/.local/state/bodai/db-archive/2026-10-11-uuid7-migration/`
--     if a retry is needed.
--   * `DROP TABLE IF EXISTS conv_id_map` at the end is a no-op on the
--     second pass because the script never reached it; the table
--     would already be gone (it is a TEMP TABLE scoped to the
--     connection).
--
-- -------------------------------------------------------------------------
-- Atomicity
-- -------------------------------------------------------------------------
--   * The whole script is wrapped in a single `BEGIN; ... COMMIT;` so
--     either every table is rebuilt (with the new conv_id_map carrying
--     the conversation-id translation to memory_access_log) or none
--     are. DuckDB DDL inside an explicit transaction is transactional
--     (verified against the chain test on 2026-10-11), so a mid-script
--     error rolls the rebuild back to the pre-007 state.
--
-- -------------------------------------------------------------------------
-- UUID7 storage
-- -------------------------------------------------------------------------
--   TEXT (32 lowercase hex chars, no dashes). All new `id` columns are
--   TEXT PK, never VARCHAR or CHAR(26). The 32-char form is generated
--   by `uuid7()` and is the canonical UUID7 contract (no dashes;
--   matches the SQLite-era TEXT PK that the rest of the codebase
--   already queries against).
--
-- -------------------------------------------------------------------------
-- Type notes (DuckDB-native; this script is no longer portable to SQLite)
-- -------------------------------------------------------------------------
--   * Embeddings: DuckDB allows FLOAT[384] for the embedding column.
--     The post-001 conversations table and the post-003 reflections
--     table both have `embedding FLOAT[384]` (per schema_v2.py:45 and
--     schema_v2.py:83); copying FLOAT[384] to FLOAT[384] is a no-op
--     cast, no BLOB round-trip needed.
--   * Metadata: schema_v2.py:69 declares conversations.metadata
--     VARCHAR; schema_v2.py:111 declares reflections.metadata JSON.
--     The post-001 / post-003 tables already have those types, so the
--     new tables match.
--   * Tags / related_entities: schema_v2.py declares
--     `tags TEXT[]` and `related_entities TEXT[]` for the v2
--     reflection schema. The post-003 table's tags column is JSON
--     (per 003 step 1) but related_entities is the v2 TEXT[] (it is
--     not in the 003 step-1 columns, so it must already exist on the
--     pre-007 reflections table). The new table keeps TEXT[] for
--     related_entities and JSON for tags to preserve byte-equivalence
--     with the source data.
--   * TIMESTAMP: the existing tables use TIMESTAMP (no WITH TIME ZONE)
--     for everything except session_windows in the v2.1 DDL
--     (schema_v2.py:370). This script uses TIMESTAMP for consistency
--     with the data in the live reflection.duckdb (verified 2026-10-11
--     via DESCRIBE; the pre-007 table is TIMESTAMP, not TIMESTAMPTZ).
-- -------------------------------------------------------------------------

BEGIN;

-- ============================================================================
-- Pre-step A: drop FK dependents on conversations. DuckDB strictly
-- enforces FK references, so we cannot DROP conversations (line ~264
-- below) while memory_entities.memory_id or memory_promotions.
-- conversation_id still reference it. 008 rebuilds these tables with
-- their FKs pointing at the new UUID7 conversations. The pre-007
-- tables are empty in the production archive (verified 2026-10-11;
-- both had 0 rows in the Phase 1 archive copy), so this drop is
-- lossless.
-- ============================================================================
-- Drop leaves first, then roots (FK-aware order).
-- memory_access_log is NOT dropped here directly; instead we back it up
-- (lossless) and drop+rebuild it AFTER the conversations rebuild so the
-- FK from memory_access_log.memory_id to conversations can be re-attached
-- against the new UUID7 conversations table.
DROP TABLE IF EXISTS memory_relationships;  -- FK -> memory_entities
DROP TABLE IF EXISTS memory_entities;     -- FK -> conversations
DROP TABLE IF EXISTS memory_promotions;   -- FK -> conversations
CREATE TABLE memory_access_log_backup AS SELECT * FROM memory_access_log;
DROP TABLE memory_access_log;

-- ============================================================================
-- Pre-step B: build the conversations legacy_id -> uuid7_id mapping.
-- This must run BEFORE the conversations rebuild so the new conversations
-- rows can be assigned the same UUID7s the memory_access_log rebuild will
-- look up. The TEMP TABLE is connection-scoped in DuckDB (and session-
-- scoped in SQLite); the explicit DROP at the end of the script keeps
-- the connection tidy.
--
-- Why a TEMP TABLE: the data is short-lived (one-shot lookup) and
-- persisting it would pollute the schema with a runtime-only artifact.
-- DuckDB supports CREATE TEMP TABLE natively.
-- ============================================================================
CREATE TEMP TABLE IF NOT EXISTS conv_id_map (
    legacy_id TEXT PRIMARY KEY,
    uuid7_id  TEXT NOT NULL
);

INSERT INTO conv_id_map (legacy_id, uuid7_id)
SELECT id AS legacy_id, uuid7() AS uuid7_id FROM conversations;

-- ============================================================================
-- Table 1: conversations
-- Schema reference: schema_v2.py:42-77 (the post-001 column shape).
-- Columns: id TEXT PK (UUID7); content TEXT NOT NULL;
--   embedding FLOAT[384]; category TEXT NOT NULL; subcategory TEXT;
--   importance_score REAL DEFAULT 0.5; memory_tier TEXT DEFAULT
--   'long_term'; access_count INTEGER DEFAULT 0; last_accessed TIMESTAMP;
--   project TEXT; namespace TEXT DEFAULT 'default';
--   timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
--   session_id TEXT; user_id TEXT DEFAULT 'default';
--   searchable_content TEXT; reasoning TEXT;
--   metadata VARCHAR; source_type TEXT; turn_parent_id TEXT;
--   causal_parent_id TEXT.
-- ============================================================================

CREATE TABLE conversations_new (
    id                  TEXT PRIMARY KEY,
    content             TEXT NOT NULL,
    embedding           FLOAT[384],
    category            TEXT NOT NULL,
    subcategory         TEXT,
    importance_score    REAL DEFAULT 0.5,
    memory_tier         TEXT DEFAULT 'long_term',
    access_count        INTEGER DEFAULT 0,
    last_accessed       TIMESTAMP,
    project             TEXT,
    namespace           TEXT DEFAULT 'default',
    timestamp           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id          TEXT,
    user_id             TEXT DEFAULT 'default',
    searchable_content  TEXT,
    reasoning           TEXT,
    metadata            VARCHAR,
    source_type         TEXT,
    turn_parent_id      TEXT,
    causal_parent_id    TEXT
);

-- Join onto conv_id_map so the new id is the uuid7 the
-- memory_access_log rebuild will look up. The JOIN is inner
-- (1:1 by legacy_id PK), so the row count of the new table
-- equals the row count of the old table exactly.
INSERT INTO conversations_new (
    id, content, embedding, category, subcategory, importance_score,
    memory_tier, access_count, last_accessed, project, namespace,
    timestamp, session_id, user_id, searchable_content, reasoning,
    metadata, source_type, turn_parent_id, causal_parent_id
)
SELECT
    m.uuid7_id            AS id,
    c.content,
    c.embedding,
    c.category,
    c.subcategory,
    c.importance_score,
    c.memory_tier,
    c.access_count,
    c.last_accessed,
    c.project,
    c.namespace,
    c.timestamp,
    c.session_id,
    c.user_id,
    c.searchable_content,
    c.reasoning,
    c.metadata,
    c.source_type,
    c.turn_parent_id,
    c.causal_parent_id
FROM conversations c
JOIN conv_id_map m ON c.id = m.legacy_id;

DROP TABLE conversations;
ALTER TABLE conversations_new RENAME TO conversations;

-- Recreate indexes on the freshly built table. The original 007 had
-- partial-index `WHERE source_type IS NOT NULL` on
-- idx_v2_source_type_project -- DuckDB does not support partial
-- indexes, so the predicate is dropped (the index covers all rows,
-- which is slightly less efficient but still selective on the leading
-- source_type column).
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

-- ============================================================================
-- Table 2: reflections
-- Schema reference: schema_v2.py:80-120 (v2 columns) + the 5 columns
--   default_reflections contributed in 003 (usage_count, last_used_at,
--   confidence_score, conversation_id, insight_type). The post-003
--   `reflections` table has the union of those columns.
-- Columns: id TEXT PK (UUID7); content TEXT NOT NULL; embedding FLOAT[384];
--   category TEXT NOT NULL; importance_score REAL DEFAULT 0.5;
--   memory_tier TEXT DEFAULT 'long_term'; tags JSON; related_entities
--   TEXT[]; timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
--   project TEXT; namespace TEXT DEFAULT 'default';
--   access_count INTEGER DEFAULT 0; last_accessed TIMESTAMP;
--   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP; updated_at TIMESTAMP;
--   fingerprint BLOB; subcategory TEXT; metadata JSON;
--   source_session_id TEXT; source_artifact_uri TEXT;
--   usage_count INTEGER NOT NULL DEFAULT 0; last_used_at TIMESTAMP;
--   confidence_score REAL NOT NULL DEFAULT 0.5;
--   conversation_id TEXT; insight_type TEXT.
-- ============================================================================

CREATE TABLE reflections_new (
    id                   TEXT PRIMARY KEY,
    content              TEXT NOT NULL,
    embedding            FLOAT[384],
    category             TEXT NOT NULL,
    memory_tier          TEXT DEFAULT 'long_term',
    tags                 JSON,
    related_entities     TEXT[],
    timestamp            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    project              TEXT,
    namespace            TEXT DEFAULT 'default',
    access_count         INTEGER DEFAULT 0,
    last_accessed        TIMESTAMP,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP,
    fingerprint          BLOB,
    subcategory          TEXT,
    metadata             JSON,
    source_session_id    TEXT,
    source_artifact_uri  TEXT,
    usage_count          INTEGER NOT NULL DEFAULT 0,
    last_used_at         TIMESTAMP,
    confidence_score     REAL NOT NULL DEFAULT 0.5,
    conversation_id      TEXT,
    insight_type         TEXT
);

INSERT INTO reflections_new (
    id, content, embedding, category, memory_tier,
    tags, related_entities, timestamp, project, namespace,
    access_count, last_accessed, created_at, updated_at, fingerprint,
    subcategory, metadata, source_session_id, source_artifact_uri,
    usage_count, last_used_at, confidence_score, conversation_id,
    insight_type
)
SELECT
    uuid7()              AS id,
    content,
    embedding,
    category,
    memory_tier,
    tags,
    related_entities,
    timestamp,
    project,
    namespace,
    access_count,
    last_accessed,
    created_at,
    updated_at,
    fingerprint,
    subcategory,
    metadata,
    source_session_id,
    source_artifact_uri,
    usage_count,
    last_used_at,
    confidence_score,
    conversation_id,
    insight_type
FROM reflections;

DROP TABLE reflections;
ALTER TABLE reflections_new RENAME TO reflections;

-- Recreate indexes. `idx_reflections_source_session` had a partial
-- `WHERE source_session_id IS NOT NULL` predicate in the original
-- 007 -- stripped here for DuckDB compatibility.
CREATE INDEX IF NOT EXISTS idx_reflections_category
    ON reflections(category, namespace);
CREATE INDEX IF NOT EXISTS idx_reflections_tier
    ON reflections(memory_tier);
CREATE INDEX IF NOT EXISTS idx_reflections_source_session
    ON reflections(source_session_id);

-- ============================================================================
-- Table 3: code_graphs
-- Schema reference: storage/migrations/V6__ulid_contract__up.sql
--   (id TEXT PK; repo_path TEXT; commit_hash TEXT; indexed_at TIMESTAMP;
--    nodes_count INTEGER; graph_data TEXT).
-- ============================================================================

CREATE TABLE code_graphs_new (
    id           TEXT PRIMARY KEY,
    repo_path    TEXT NOT NULL,
    commit_hash  TEXT NOT NULL,
    indexed_at   TIMESTAMP NOT NULL,
    nodes_count  INTEGER NOT NULL DEFAULT 0,
    graph_data   TEXT
);

INSERT INTO code_graphs_new (id, repo_path, commit_hash, indexed_at, nodes_count, graph_data)
SELECT uuid7() AS id, repo_path, commit_hash, indexed_at, nodes_count, graph_data
FROM code_graphs;

DROP TABLE code_graphs;
ALTER TABLE code_graphs_new RENAME TO code_graphs;

CREATE INDEX IF NOT EXISTS idx_code_graphs_repo_path
    ON code_graphs(repo_path);
CREATE INDEX IF NOT EXISTS idx_code_graphs_indexed_at
    ON code_graphs(indexed_at DESC);

-- ============================================================================
-- Table 4: session_windows
-- Schema reference: schema_v2.py:365-373 (CROSS_REPO_CHECKPOINT_V2_1_DDL).
-- The v2.1 DDL declares TIMESTAMP WITH TIME ZONE; the pre-007 live
-- table in reflection.duckdb is TIMESTAMP (verified 2026-10-11 via
-- DESCRIBE). The new table matches the live column type so the
-- INSERT SELECT is a no-op cast.
-- Columns: id TEXT PK (UUID7); working_directory TEXT NOT NULL;
--   project TEXT; started_at TIMESTAMP NOT NULL DEFAULT
--   CURRENT_TIMESTAMP; ended_at TIMESTAMP; session_metadata TEXT NOT
--   NULL DEFAULT '{}'.
-- ============================================================================

CREATE TABLE session_windows_new (
    id                 TEXT PRIMARY KEY,
    working_directory  TEXT NOT NULL,
    project            TEXT,
    started_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at           TIMESTAMP,
    session_metadata   TEXT NOT NULL DEFAULT '{}'
);

INSERT INTO session_windows_new (id, working_directory, project, started_at, ended_at, session_metadata)
SELECT uuid7() AS id, working_directory, project, started_at, ended_at,
       COALESCE(session_metadata, '{}')
FROM session_windows;

DROP TABLE session_windows;
ALTER TABLE session_windows_new RENAME TO session_windows;

-- Recreate indexes. `idx_session_windows_project` had a partial
-- `WHERE project IS NOT NULL` predicate -- stripped for DuckDB.
CREATE INDEX IF NOT EXISTS idx_session_windows_started_at
    ON session_windows(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_windows_project
    ON session_windows(project);

-- ============================================================================
-- Table 5: memory_access_log
-- Schema reference: schema_v2.py:161-168. The plan explicitly fixes
-- the stale `reflection_access_log` name: this is the canonical
-- event-log table, not a vestige. The FK to `conversations(id)` is
-- preserved across the rebuild, and the FK target is the new
-- UUID7 conversations table that Table 1 just finished building.
-- Columns: id TEXT PK (UUID7); memory_id TEXT (nullable);
--   access_type TEXT; query_text TEXT;
--   timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP.
--
-- Why we translate memory_id here: in the pre-007 table, memory_id
-- holds whatever id the v0/v2 conversations table had at write
-- time. After Table 1's rebuild, those values are gone -- the new
-- conversations rows have the UUID7s from conv_id_map. The
-- correlated subquery below looks up each row's memory_id in
-- conv_id_map and returns the new UUID7; rows whose memory_id does
-- not match any legacy mapping (NULL, or pointing at a conversation
-- that pre-existed only as legacy v0 and was absorbed by 001's
-- consolidation merge) keep `memory_id` NULL so the FK is never
-- violated.
-- ============================================================================

CREATE TABLE memory_access_log_new (
    id           TEXT PRIMARY KEY,
    memory_id    TEXT,
    access_type  TEXT,
    query_text   TEXT,
    timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
);

INSERT INTO memory_access_log_new (id, memory_id, access_type, query_text, timestamp)
SELECT
    uuid7()                                              AS id,
    (SELECT m.uuid7_id FROM conv_id_map m
        WHERE m.legacy_id = mal.memory_id)               AS memory_id,
    mal.access_type,
    mal.query_text,
    mal.timestamp
FROM memory_access_log_backup mal;

ALTER TABLE memory_access_log_new RENAME TO memory_access_log;

-- Recreate indexes. `idx_access_log_memory` had a partial
-- `WHERE memory_id IS NOT NULL` predicate -- stripped for DuckDB.
CREATE INDEX IF NOT EXISTS idx_access_log_memory
    ON memory_access_log(memory_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_access_log_timestamp
    ON memory_access_log(timestamp DESC);

-- Drop the backup (rows are now in the rebuilt memory_access_log).
DROP TABLE IF EXISTS memory_access_log_backup;

COMMIT;

-- Drop the temporary legacy_id -> uuid7_id mapping table now that
-- the memory_access_log rebuild is complete. TEMP TABLE is scoped
-- to the connection in DuckDB; the explicit DROP keeps the session
-- tidy and signals to operators that the helper artifact is no
-- longer in use.
DROP TABLE IF EXISTS conv_id_map;

-- End of script 007.
--
-- Post-migration invariants:
--   * Every load-bearing table's primary `id` column is TEXT holding
--     a 32-character lowercase hex UUID7 generated by uuid7().
--   * The conv_id_map temp table is dropped; the connection is back
--     to its pre-007 schema state (minus the id-swap itself).
--   * The FK memory_access_log.memory_id -> conversations(id) is
--     satisfied for every row whose legacy memory_id was resolvable
--     in conv_id_map; the rest (NULLs, dangling legacy ids) keep
--     memory_id NULL, which the FK permits (the column is nullable
--     per schema_v2.py:163).
--   * Application-layer writers MUST generate UUID7 values via
--     `uuid.uuid7().hex` (or the registered uuid7() SQL UDF) before
--     INSERT; the rebuild pattern ensures no placeholder default
--     column exists for the writer to forget about.
-- ============================================================================
