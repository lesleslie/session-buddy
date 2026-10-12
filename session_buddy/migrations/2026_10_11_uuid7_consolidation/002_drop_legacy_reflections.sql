-- Migration 002: Drop the vestigial v0 `reflections` table.
--
-- Pre-migration row count: 0 (verified from Phase 1 archive on 2026-10-11).
-- The legacy `reflections` table is the v0 schema that pre-dates the
-- `reflections_v2` consolidation; no production code reads from it (verified
-- by `grep -rE "FROM reflections\\b|INTO reflections\\b" session_buddy/` —
-- all production reads target `reflections_v2`). The v0 table survives as
-- scaffolding only.
--
-- Phase 0 ordering note: this script is renumbered to 002 in the B-step
-- (2026-10-11) so the v0 `reflections` is dropped BEFORE
-- `003_consolidate_reflections.sql` runs. Otherwise
-- `003`'s `ALTER TABLE reflections_v2 RENAME TO reflections` collides with
-- the still-present legacy `reflections` and aborts (the original
-- numbering had 002 before 005, which was the plan-level contradiction
-- the adversarial review caught).
--
-- DuckDB syntax: `DROP TABLE IF EXISTS` is supported; this script targets
-- the live `reflection.duckdb` per Phase 0.5 step 3 (`duckdb
-- <reflection.duckdb> < 002_drop_legacy_reflections.sql`).

BEGIN;

DROP TABLE IF EXISTS reflections;

COMMIT;