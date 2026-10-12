-- Migration 005 down: re-create `default_conversations` (v0 schema).
--
-- Reverses 005_drop_legacy_default_conversations.sql, which dropped
-- the vestigial `default_conversations` table that 001 step 4 had
-- absorbed into the canonical `conversations` table.
--
-- Pre-migration row count for the default_conversations table: 5.
-- After 001 step 4: the 5 rows were INSERTed into the canonical
-- `conversations` table (with synthesized category='facts' and
-- source_type='migration'); 005 dropped `default_conversations`.
--
-- The 5 rows are not recoverable from any post-005 source: 005's
-- DROP is the irreversible event, and the 5 rows in
-- `conversations` (now in `conversations_v2` post-001_down rename)
-- are indistinguishable from the original v2 rows. The down-script
-- re-creates `default_conversations` as an empty table with the v0
-- schema so a re-application of 001 + 005 reaches a state
-- consistent with the pre-001 DB shape, minus the 5 rows that
-- were dropped in 005.
--
-- Data loss: 5 default_conversations rows. Unrecoverable.
--
-- Idempotency: CREATE TABLE IF NOT EXISTS is idempotent.
-- Atomicity: the CREATE is a single DDL statement; BEGIN/COMMIT
-- is included for parity with the up-script.

BEGIN;

CREATE TABLE IF NOT EXISTS default_conversations (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],
    subcategory TEXT,
    fingerprint TEXT,
    metadata VARCHAR,
    created_at TIMESTAMP
);

COMMIT;
