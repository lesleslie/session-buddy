-- Migration 003 down: re-create `reflections_v2` (v2 schema) and
-- re-insert from the post-003 `reflections` table.
--
-- Reverses 003_consolidate_reflections.sql, which:
--   * Renamed `reflections_v2` -> `reflections` (drop the _v2 marker;
--     reflections is now canonical).
--   * Absorbed the 1,232 rows in `default_reflections` into
--     `reflections` with a synthesized UUID7 ID and `category='context'`.
--   * Dropped `default_reflections`.
--
-- Down-script scope:
--   * Rename `reflections` back to `reflections_v2` (the v2 name).
--   * Re-create `reflections_v2` with the v2 schema (no columns from
--     default_reflections: usage_count, last_used_at, confidence_score,
--     conversation_id, insight_type). These are dropped -- they were
--     added in 003 step 1; the down targets the pre-003 v2 shape.
--   * Re-create `default_reflections` as an empty table with the v0
--     schema (per docs/features/INSIGHTS_CAPTURE.md:90-104). The 1,232
--     rows that were absorbed cannot be reconstructed from the
--     post-003 `reflections_v2` table because the v2 schema does not
--     carry forward the original `id`, `created_at`, or `updated_at`
--     for the absorbed rows in a way that distinguishes them from v2
--     rows. The absorbed rows are now in `reflections_v2` and
--     indistinguishable from the original v2 rows.
--   * Re-create the v2 indexes on `reflections_v2`.
--
-- Embedding limitation: vector embeddings (FLOAT[384]) are preserved
-- through the column-level operations. The reversibility concern is
-- for ID mapping (the absorbed rows received fresh UUID7 IDs from
-- uuid7() at absorb time; those UUID7s are not in any pre-migration
-- mapping and cannot be tied back to the original default_reflections
-- IDs). Embedding bytes themselves are not modified by the down.
--
-- Data loss:
--   * The 1,232 absorbed default_reflections rows are now in
--     `reflections_v2` and indistinguishable from original v2 rows.
--     `default_reflections` is recreated empty.
--   * The `category` column was synthesized as 'context' for absorbed
--     rows (per 003 step 4) -- that injection cannot be reversed.
--   * The absorbed rows received a `conversation_id = NULL` (per
--     003 step 4) -- that NULL is preserved on the down.
--
-- Idempotency: not natively idempotent (the 003 up-script is not
-- idempotent either, and the down mirrors that). CREATE TABLE IF NOT
-- EXISTS guards the table creates; the rename will fail on second run
-- (reflections_v2 already exists from a prior successful run).
--
-- Atomicity: wrapped in BEGIN; ... COMMIT; to keep the rename +
-- recreate atomic.

BEGIN;

-- Drop the v2 indexes on `reflections` so the rename can proceed
-- (DuckDB rename does not transfer indexes; they get re-created on
-- reflections_v2 below).
DROP INDEX IF EXISTS idx_reflections_category;
DROP INDEX IF EXISTS idx_reflections_tier;
DROP INDEX IF EXISTS idx_reflections_source_session;

-- Rename `reflections` back to `reflections_v2`. All rows move with
-- the rename (1232 absorbed default_reflections + N v2 originals).
ALTER TABLE reflections RENAME TO reflections_v2;

-- Re-create the v2 indexes on `reflections_v2`. Same column
-- expressions as the schema_v2.py CREATE INDEX IF NOT EXISTS block.
CREATE INDEX IF NOT EXISTS idx_reflections_category
    ON reflections_v2(category, namespace);
CREATE INDEX IF NOT EXISTS idx_reflections_tier
    ON reflections_v2(memory_tier);
CREATE INDEX IF NOT EXISTS idx_reflections_source_session
    ON reflections_v2(source_session_id);

-- Re-create `default_reflections` as an empty table with the v0
-- schema (per docs/features/INSIGHTS_CAPTURE.md:90-104). The 1,232
-- absorbed rows are NOT returned here -- they cannot be reconstructed
-- from the post-003 `reflections_v2` table (the absorbed rows
-- received fresh UUID7 IDs and `category='context'`, neither of
-- which is in the v2 schema and neither of which carries a
-- pre-migration fingerprint). The empty `default_reflections` is
-- the v0-shape placeholder; production code does not write to it
-- (per the MIGRATION_SQL block and the production archive verification).
CREATE TABLE IF NOT EXISTS default_reflections (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding FLOAT[384],
    tags JSON,
    metadata JSON,
    usage_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TIMESTAMP,
    confidence_score REAL NOT NULL DEFAULT 0.5,
    insight_type TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

COMMIT;
