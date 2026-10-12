-- Migration: 005_drop_legacy_default_conversations
-- Phase: Phase 0 — UUID7 consolidation (session-buddy)
-- Date: 2026-10-11
-- Plan: ~/Projects/mahavishnu/docs/plans/2026-10-11-uuid7-only-migration.md
--
-- Purpose:
--   Drop the vestigial `default_conversations` table. Its 5 rows were
--   absorbed into the canonical `conversations` table by step 4 of
--   `001_consolidate_conversations.sql`
--   (`INSERT INTO conversations ... SELECT ... FROM default_conversations
--   WHERE id NOT IN (SELECT id FROM conversations);`). This fixes the
--   asymmetric treatment flagged in the plan: the parallel
--   `default_reflections` table was already absorbed into `reflections`
--   by `003_consolidate_reflections.sql`; `default_conversations` now
--   matches that behavior.
--
--   Final conversations row count: 1,205 = 935 V2 + 265 V0-unique + 5
--   default_conversations.
--
-- Depends on:
--   001 (which absorbed the 5 default_conversations rows into the
--   canonical `conversations` table via step 4's INSERT).
--
-- Idempotency: IF EXISTS guard makes the DROP safe to re-run against a
-- partially-migrated or already-migrated database.
--
-- Atomicity: wrapped in BEGIN; ... COMMIT; so that the DROP applies as a
-- single transaction.

BEGIN;

DROP TABLE IF EXISTS default_conversations;

COMMIT;
