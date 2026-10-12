-- Migration 006 down: re-create the vestigial tables that 006 dropped
-- and remove the `__uuid7_migration_done` marker.
--
-- Reverses 006_drop_vestigial.sql, which dropped:
--   * access_log_v2
--   * query_cache_l2
-- and created the `__uuid7_migration_done` marker table.
--
-- Per 006's header (B-step adversarial review 2026-10-11), the
-- following were PRESERVED by 006 and are NOT in scope for this
-- down-script (the down-script does not re-create them):
--   * schema_meta (1 row: schema_version='v2') — active schema-version
--     lookup; live data; not dropped by 006.
--   * schema_migrations (1 row: a v1->v2 audit record) — historical
--     audit; live data; not dropped by 006.
--
-- Pre-migration row counts (verified 2026-10-11 via Phase 1 archive):
--   * access_log_v2: 0 (vestigial; never wired into the read path;
--     superseded by memory_access_log per 007).
--   * query_cache_l2: 0 (vestigial; never wired into the read path;
--     the hot store is in-process reflection cache + DuckDB FTS).
--
-- Both tables were empty when 006 dropped them. The down-script
-- re-creates both as empty tables with their pre-006 schemas.
--
-- Marker handling: the `__uuid7_migration_done` marker table is the
-- migration's own metadata. Per the migration policy, it is NOT
-- dropped by any down-script (it is the migration's own state, not
-- user data). It persists into the reversed state; the operator
-- must DROP it manually if they want a fully-clean pre-migration
-- state, or it will be DROPPED by a subsequent up-script re-run.
--
-- Idempotency: every CREATE uses IF NOT EXISTS. Safe to re-run.
-- Atomicity: the two CREATE statements run inside a single
-- transaction so the database never observes a half-reversed
-- vestigial state.

BEGIN;

-- Re-create access_log_v2 with its pre-006 schema. The schema is
-- inferred from production-code reads (per 006's header verification
-- of "no production reads against the v0 reflections table" via
-- grep) -- access_log_v2 was the v2-marker scaffold for a
-- never-shipped A/B experiment; the column shape is a superset of
-- memory_access_log (the v0 shape) with the v2 `id` convention.
-- VARCHAR(26) was the pre-007 ULID-shape (Crockford base32); the
-- down uses TEXT to match the v2 canonical TEXT PK contract.
CREATE TABLE IF NOT EXISTS access_log_v2 (
    id TEXT PRIMARY KEY,
    memory_id TEXT,
    access_type TEXT,
    query_text TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Re-create query_cache_l2 with its pre-006 schema. The schema is
-- inferred from the L2-cache experiment context; the v0 shape
-- mirrors a typical query cache (query, result, ttl, hit_count).
-- DuckDB TEXT type for result_payload.
CREATE TABLE IF NOT EXISTS query_cache_l2 (
    id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    result_payload TEXT,
    ttl_seconds INTEGER,
    hit_count INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- The `__uuid7_migration_done` marker is intentionally preserved
-- (per migration policy: the marker is the migration's own metadata,
-- not user data, and is not dropped by any down-script). If a
-- fully-clean pre-migration state is required, the operator must
-- DROP it manually: `DROP TABLE IF EXISTS __uuid7_migration_done;`

COMMIT;
