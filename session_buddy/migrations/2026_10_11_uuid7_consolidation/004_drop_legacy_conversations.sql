-- Migration: 004_drop_legacy_conversations
-- Phase: Phase 0 — UUID7 consolidation (session-buddy)
-- Date: 2026-10-11
-- Plan: ~/Projects/mahavishnu/docs/plans/2026-10-11-uuid7-only-migration.md
--
-- Purpose:
--   Drop the vestigial `conversations_legacy` table that was created in
--   `001_consolidate_conversations.sql` step 1 by renaming the v0
--   `conversations` table. The v0 rows were already absorbed into the
--   canonical `conversations` table (the renamed v2) by step 3 of 001.
--   Step 1's rename was required to free the `conversations` name so that
--   step 2's `ALTER TABLE conversations_v2 RENAME TO conversations` would
--   not collide; with absorption complete, the legacy table is no longer
--   needed.
--
-- Depends on: 001 (which renamed original conversations to
-- conversations_legacy AND absorbed its v0-unique rows into the canonical
-- conversations table).
--
-- Idempotency: IF EXISTS guard makes the DROP safe to re-run.
--
-- Atomicity: wrapped in BEGIN; ... COMMIT; so that the DROP applies as a
-- single transaction.

BEGIN;

DROP TABLE IF EXISTS conversations_legacy;

COMMIT;