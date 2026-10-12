-- Migration 004 down: re-create `conversations_legacy` (v0 schema).
--
-- Reverses 004_drop_legacy_conversations.sql, which dropped the
-- vestigial `conversations_legacy` table that 001 step 1 had created
-- by renaming the v0 `conversations` table.
--
-- Pre-migration row count for the v0 conversations table: 1195.
-- After 001 step 3: 265 v0-unique rows were absorbed into the
-- canonical `conversations` table; 1195 rows remained in
-- conversations_legacy (the source is left intact; INSERT...SELECT
-- with NOT EXISTS does not delete from the source). 004 then dropped
-- conversations_legacy entirely.
--
-- The 1195 v0 rows are not recoverable from any post-004 source:
-- 004's DROP is the irreversible event. The down-script re-creates
-- `conversations_legacy` as an empty table with the v0 schema so
-- any 001-step-1 rename that pre-dated the merge can be re-run
-- (and so a re-application of 001 + 004 reaches a state consistent
-- with the pre-001 DB shape, minus the 1195 v0 rows that were
-- dropped in 004).
--
-- Data loss: 1195 v0 conversations rows. Unrecoverable. The 265
-- v0-unique rows that were absorbed into `conversations` (and
-- subsequently moved into `conversations_v2` via the 001_down
-- rename) are also indistinguishable from the original v2 rows --
-- see 001_down.sql for the data-fidelity note.
--
-- Idempotency: CREATE TABLE IF NOT EXISTS is idempotent.
-- Atomicity: the CREATE is a single DDL statement; BEGIN/COMMIT
-- is included for parity with the up-script.

BEGIN;

CREATE TABLE IF NOT EXISTS conversations_legacy (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],
    project TEXT,
    timestamp TIMESTAMP,
    metadata JSON
);

COMMIT;
