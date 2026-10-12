-- Migration 003: Consolidate reflections table
-- Plan: ~/Projects/mahavishnu/docs/plans/2026-10-11-uuid7-only-migration.md (Phase 0)
--
-- Goal: Rename reflections_v2 -> reflections (drop the _v2 migration marker;
--       reflections is now the canonical table). Add columns needed to
--       absorb the 1,232 rows in default_reflections. Insert those rows
--       with fresh UUID7 ids, then drop default_reflections.
--
-- Depends on:
--   * 001_consolidate_conversations.sql (default_conversations rename
--     already resolved so the renamed `conversations` table exists).
--   * 002_drop_legacy_reflections.sql (v0 `reflections` dropped first so
--     the `reflections` name is free for the rename below; this is the
--     B-step ordering fix — see 002's header comment for the original
--     plan-level contradiction the adversarial review caught).
--
-- Pre-conditions (enforced by the migration runner, not this SQL file):
--   1. The migration runner MUST register a `uuid7()` SQL function (UDF)
--      that returns a 32-character lowercase hex string (no dashes).
--      Examples:
--        * SQLite via aiosqlite: conn.create_function("uuid7", 0, lambda: ...)
--        * DuckDB: con.create_function("uuid7", 0, lambda: ...)
--      Without the UDF, the bulk INSERT below will fail.
--   2. Both `reflections_v2` and `default_reflections` tables must exist in
--      the target database before this script runs.
--
-- Idempotency:
--   * The CTAS rebuild pattern is not natively idempotent: re-running
--     fails at `CREATE TABLE reflections_new` (already exists) and at
--     `ALTER TABLE reflections_v2 RENAME TO reflections` (already renamed
--     to reflections in a prior run). The migration is one-shot; the
--     runner must treat it as such.
--   * `DROP TABLE IF EXISTS`: idempotent (no-op if already absent).
--   * The bulk INSERT is idempotent at the row-count level only if
--     default_reflections was dropped by a prior successful run; otherwise
--     it duplicates rows.
--
-- DuckDB compatibility note: DuckDB 1.5.6 rejects
-- `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT` at the parser
-- level (DuckDB issue #16836). The CTAS rebuild below is the canonical
-- DuckDB migration idiom — also used by 007/008 — and sidesteps the
-- limitation by materializing the new schema in one CREATE TABLE
-- statement. The b-step retry-run on 2026-10-11 caught this in the
-- end-to-end chain test; the original ALTER TABLE ADD COLUMN
-- formulation aborted the chain at step 003.
--
-- UUID7 storage: TEXT (32 lowercase hex chars, no dashes). All new id
-- columns are TEXT PK, never VARCHAR or CHAR(26). The v2 IDs are
-- preserved verbatim in this pass; the formal UUID7 conversion is
-- 007's responsibility (rename id -> legacy_id, add uuid7_id TEXT
-- NOT NULL, UDF-backfill, rebuild with PK).

BEGIN;

-- Step 1: rebuild `reflections_v2` as `reflections_new` with the merged
-- schema (v2 columns plus the columns default_reflections contributes).
-- The new table has the canonical `reflections` shape; we swap it in
-- step 3.
CREATE TABLE reflections_new (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding FLOAT[384],
    category TEXT NOT NULL DEFAULT 'facts',
    subcategory TEXT,
    importance_score REAL DEFAULT 0.5,
    memory_tier TEXT DEFAULT 'long_term',
    tags JSON,
    related_entities TEXT[],
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    project TEXT,
    namespace TEXT DEFAULT 'default',
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    fingerprint TEXT,
    metadata JSON,
    source_session_id TEXT,
    source_artifact_uri TEXT,
    usage_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TIMESTAMP,
    confidence_score REAL NOT NULL DEFAULT 0.5,
    conversation_id TEXT,
    insight_type TEXT
);

-- Step 2: copy the v2 rows into the rebuilt table. COALESCE backfills
-- protect against v2 rows that might have NULL in a column the new
-- schema declares NOT NULL (e.g. legacy v2 rows with NULL category
-- would violate the new NOT NULL DEFAULT 'facts' constraint without
-- the COALESCE). The 'facts' default for v2 rows preserves the original
-- v2 semantics; the 'context' default for absorbed default_reflections
-- rows in step 4 mirrors the v2 rewire (schema_v2.py:435).
INSERT INTO reflections_new (
    id, content, embedding, category, subcategory, importance_score,
    memory_tier, tags, related_entities, timestamp, project, namespace,
    access_count, last_accessed, created_at, updated_at, fingerprint,
    metadata, source_session_id, source_artifact_uri,
    usage_count, last_used_at, confidence_score, conversation_id, insight_type
)
SELECT
    id, content, embedding,
    COALESCE(category, 'facts') AS category,
    subcategory,
    COALESCE(importance_score, 0.5) AS importance_score,
    COALESCE(memory_tier, 'long_term') AS memory_tier,
    tags,
    related_entities,
    COALESCE(timestamp, created_at) AS timestamp,
    project,
    COALESCE(namespace, 'default') AS namespace,
    COALESCE(access_count, 0) AS access_count,
    last_accessed,
    created_at, updated_at,
    COALESCE(fingerprint, '') AS fingerprint,
    metadata,
    source_session_id,
    source_artifact_uri,
    COALESCE(usage_count, 0) AS usage_count,
    last_used_at,
    COALESCE(confidence_score, 0.5) AS confidence_score,
    -- v2 rows never had a conversation FK. The live reflections_v2 schema
    -- (verified via DESCRIBE on the production archive 2026-10-11) does not
    -- include `conversation_id`; populate it as NULL for v2 rows. Default
    -- reflections rows may carry it; their INSERT (lines 144-163 below)
    -- provides the value.
    NULL AS conversation_id,
    COALESCE(insight_type, 'general') AS insight_type
FROM reflections_v2;

-- Step 3: swap into the canonical name. The DROP + RENAME is the
-- v2-to-canonical drop that the original line 47's
-- `ALTER TABLE reflections_v2 RENAME TO reflections` performed; doing
-- it in two steps here so the v2 data is fully transferred first.
DROP TABLE reflections_v2;
ALTER TABLE reflections_new RENAME TO reflections;

-- Step 4: absorb the default_reflections rows. The SELECT column list
-- mirrors the canonical default_reflections schema documented in
-- docs/features/INSIGHTS_CAPTURE.md:90-104. That schema has NO
-- `subcategory` column (the adversarial review caught the original
-- 002's reference to it as bug #2 of 002 — false column, would have
-- raised a Binder Error on the live DB). `category` is NOT NULL on
-- reflections; default_reflections has no category column, so we
-- inject the literal 'context' as the v2 rewire does.
--
-- `conversation_id` is also new on default_reflections (it's a v2
-- column). Absorbed rows get NULL.
INSERT INTO reflections (
    id, content, embedding, category, tags, metadata,
    usage_count, last_used_at, confidence_score, insight_type,
    created_at, updated_at, conversation_id
)
SELECT
    uuid7(),            -- 32-char lowercase hex (registered by migration runner)
    content,
    embedding,
    'context' AS category,
    tags,
    metadata,
    COALESCE(usage_count, 0) AS usage_count,
    last_used_at,
    COALESCE(confidence_score, 0.5) AS confidence_score,
    insight_type,
    created_at,
    updated_at,
    NULL AS conversation_id
FROM default_reflections;

-- Step 5: drop the now-empty legacy table.
DROP TABLE IF EXISTS default_reflections;

COMMIT;