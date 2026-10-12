-- Migration 002 down: re-create the vestigial v0 `reflections` table.
--
-- Reverses 002_drop_legacy_reflections.sql, which dropped the
-- vestigial v0 `reflections` table so the `reflections` name was
-- free for 003 to claim via `ALTER TABLE reflections_v2 RENAME
-- TO reflections`.
--
-- Pre-migration row count for the v0 `reflections` table: 0
-- (verified from Phase 1 archive on 2026-10-11). The 002 up-script
-- dropped the table; no rows were lost.
--
-- The down-script re-creates the v0 `reflections` table as an
-- empty table with the v0 schema. The v0 schema is inferred from
-- the MIGRATION_SQL block in schema_v2.py (the v1 -> v2 migration
-- references these columns: id, content, embedding, tags, timestamp,
-- project). The `tags` column was JSON in v2 and TEXT[] in v2.1
-- in subsequent migrations; on the v0 table the tags column was
-- stored as a JSON list (matching the schema_v2.py v2 column
-- declaration; this is the only shape that v1 -> v2 migration
-- SELECTs against). DuckDB JSON type is used for v0 fidelity.
--
-- Data loss: none. The v0 reflections table was empty when 002
-- dropped it; the down-script recreates it empty.
--
-- Idempotency: CREATE TABLE IF NOT EXISTS is idempotent.
-- Atomicity: the CREATE is a single DDL statement; BEGIN/COMMIT
-- is included for parity with the up-script.
--
-- Post-down state: the database has both `reflections` (v0, empty)
-- and `reflections_v2` (the table 003 went on to consume; populated
-- after 003). The v0 name coexists with the post-003 reflections
-- name -- this is fine for a fresh reversed state but means a
-- re-application of 002 + 003 (or a 003_down first) is required
-- to reach a state where only one of the two survives.

BEGIN;

CREATE TABLE IF NOT EXISTS reflections (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],
    tags JSON,
    timestamp TIMESTAMP,
    project TEXT
);

COMMIT;
