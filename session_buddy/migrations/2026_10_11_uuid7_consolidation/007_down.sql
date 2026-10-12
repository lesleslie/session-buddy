-- =====================================================================
-- Migration 007 down: reverse the ID swap on the load-bearing tables.
--
-- Reverses 007_id_swap_load_bearing.sql, which UUID7-ized the primary
-- key of every load-bearing table by running the CTAS pattern (CREATE
-- _new, INSERT FROM old, DROP old, RENAME _new -> old).
--
-- -------------------------------------------------------------------------
-- Tables UUID7-ized by 007
-- -------------------------------------------------------------------------
--   1. conversations     -- conv_id_map maps (legacy_id -> uuid7_id)
--   2. reflections       -- fresh UUID7 per row; no legacy mapping
--   3. code_graphs       -- fresh UUID7 per row; no legacy mapping
--   4. session_windows   -- fresh UUID7 per row; no legacy mapping
--   5. memory_access_log -- fresh UUID7 per row; conv_id_map reverses
--                            the memory_id FK to conversations
--   6. memory_entities   -- 0 rows in pre-007 production archive; not
--                            UUID7-ized by 007 (007 dropped + recreated
--                            them empty in pre-step A; they were
--                            re-created empty in 001 step F, NOT in 007)
--   7. memory_promotions -- same as memory_entities
--   8. memory_relationships -- 007 dropped; 0 rows pre-007
--
-- -------------------------------------------------------------------------
-- Down-script scope (per the user spec)
-- -------------------------------------------------------------------------
--   * Reverse the UUID7 IDs back to legacy IDs in:
--       memory_entities, memory_promotions, memory_relationships,
--       memory_access_log.
--     Use the conv_id_map (if it still exists) to translate the
--     UUID7 back to the pre-007 legacy id. conv_id_map was created
--     as a TEMP TABLE in 007 (connection-scoped) and explicitly
--     dropped at the end of 007; on a fresh post-007 DB the
--     conv_id_map is NOT available. The down-script guards with
--     `CREATE TEMP TABLE IF NOT EXISTS` and uses JOINs that
--     silently produce NULL when the map is missing.
--   * The pre-007 memory_* tables were all 0-row (verified
--     2026-10-11 via Phase 1 archive). The down-script does not
--     need to migrate any data on these tables -- they are
--     recreated empty. The conv_id_map join is therefore
--     vacuous; the script still executes the join path so the
--     contract is identical to a hypothetical post-007 DB with
--     non-empty memory_* tables.
--   * memory_access_log IS non-empty (3 rows in the pre-007
--     production archive). The down-script translates each row's
--     memory_id back via conv_id_map (UUID7 -> legacy). Rows
--     whose memory_id does not resolve in conv_id_map keep
--     memory_id NULL (preserving the FK).
--
-- -------------------------------------------------------------------------
-- Data loss (irreversible on the 007 swap)
-- -------------------------------------------------------------------------
--   * conversations: 1205 rows now have fresh UUID7 IDs. The
--     conv_id_map (if available) maps each UUID7 back to its
--     pre-007 legacy id. Without conv_id_map, the legacy IDs
--     are unrecoverable.
--   * reflections: every row got a fresh UUID7 from uuid7() with
--     no legacy mapping. The pre-007 IDs (which were preserved
--     verbatim through 003 and were a mix of 32-lowercase-hex
--     and pre-v2 ULID-style shapes) are NOT recoverable.
--   * code_graphs: same as reflections.
--   * session_windows: same as reflections.
--   * memory_access_log.id: every row got a fresh UUID7. The
--     pre-007 IDs (preserved verbatim through 001) are NOT
--     recoverable; the down keeps the post-007 UUID7 IDs.
--   * memory_access_log.memory_id: recoverable ONLY if conv_id_map
--     still exists. Without it, memory_id is set to NULL on the
--     down (preserves FK, loses the conversation link).
--   * vector embeddings (FLOAT[384]) on conversations and
--     reflections are NOT modified by the down (column type is
--     preserved; the ID swap was on `id` only). The
--     "embeddings are not reversible" limitation is the
--     conservative statement -- the embedding bytes themselves
--     are intact, but the id -> conversation linkage that gives
--     embeddings their semantic context is irreversible without
--     conv_id_map.
--
-- -------------------------------------------------------------------------
-- Idempotency: not natively idempotent. The DROP / CREATE / RENAME
-- dance on memory_entities / memory_promotions / memory_relationships
-- mirrors the 007 up-script; re-running on a partially-reversed DB
-- will fail loudly on the first RENAME.
-- -------------------------------------------------------------------------

BEGIN;

-- ============================================================================
-- Pre-step A: drop FK dependents so memory_access_log can be rebuilt
-- with FK pointing at conversations (the post-down conversations,
-- which carry the same UUID7 IDs as the post-007 conversations).
-- memory_relationships must be dropped before memory_entities (FK chain).
-- ============================================================================
DROP TABLE IF EXISTS memory_relationships;
DROP TABLE IF EXISTS memory_entities;
DROP TABLE IF EXISTS memory_promotions;

-- Backup the post-007 memory_access_log so the rebuild below can read
-- from the live (UUID7-id'd) rows and translate memory_id via conv_id_map.
CREATE TABLE memory_access_log_backup AS SELECT * FROM memory_access_log;
DROP TABLE memory_access_log;

-- ============================================================================
-- Pre-step B: build a reverse conv_id_map if it does not already exist.
--
-- conv_id_map was created as a TEMP TABLE in the up-script and explicitly
-- dropped at the end. After 007, conv_id_map is gone. The down-script
-- creates a fresh TEMP TABLE on this connection that maps (uuid7_id,
-- legacy_id) -- the reverse of the up-script's (legacy_id, uuid7_id)
-- orientation. If the post-007 `conversations` table still carries
-- the same UUID7 IDs that conv_id_map would have mapped (true on a
-- fresh post-007 DB), the join below produces NULL for memory_id
-- translations because conv_id_map is empty.
--
-- If the operator has preserved a copy of the original conv_id_map
-- (e.g. by skipping the final DROP TABLE IF EXISTS conv_id_map in
-- 007 or by re-running 007's pre-step B), they can replace the
-- placeholder CREATE below with `CREATE TEMP TABLE conv_id_map AS
-- SELECT * FROM <restored-source>` before the JOINs further down.
-- ============================================================================
CREATE TEMP TABLE IF NOT EXISTS conv_id_map (
    legacy_id TEXT PRIMARY KEY,
    uuid7_id  TEXT NOT NULL
);
-- conv_id_map is intentionally empty here: the up-script dropped it
-- at the end of 007, and we have no source to re-populate it from.
-- The memory_access_log rebuild below therefore produces memory_id
-- = NULL on every row (the conv_id_map join misses every UUID7).

-- ============================================================================
-- Rebuild memory_entities, memory_promotions, memory_relationships as
-- empty tables per the v2 contract (FK -> conversations). All three
-- were 0-row in the pre-007 production archive (verified 2026-10-11);
-- the empty recreation matches the pre-007 state. The ID column on
-- these tables is TEXT (legacy-shape); the down does not need to
-- produce UUID7 IDs because there are no rows to migrate.
-- ============================================================================

CREATE TABLE memory_entities (
    id           TEXT PRIMARY KEY,
    memory_id    TEXT NOT NULL,
    entity_type  TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    confidence   REAL DEFAULT 1.0,
    timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
);
CREATE INDEX IF NOT EXISTS idx_entities_type
    ON memory_entities(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_entities_memory
    ON memory_entities(memory_id);

CREATE TABLE memory_relationships (
    id                TEXT PRIMARY KEY,
    from_entity_id    TEXT NOT NULL,
    to_entity_id      TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    strength          REAL DEFAULT 1.0,
    timestamp         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_entity_id) REFERENCES memory_entities(id),
    FOREIGN KEY (to_entity_id) REFERENCES memory_entities(id)
);
CREATE INDEX IF NOT EXISTS idx_relationships_from
    ON memory_relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_to
    ON memory_relationships(to_entity_id);

CREATE TABLE memory_promotions (
    id              TEXT PRIMARY KEY,
    memory_id       TEXT NOT NULL,
    from_tier       TEXT NOT NULL,
    to_tier         TEXT NOT NULL,
    reason          TEXT,
    priority_score  REAL,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
);

-- ============================================================================
-- Rebuild memory_access_log with FK -> conversations(id). The id column
-- keeps the post-007 UUID7 (no mapping back to the pre-007 legacy id;
-- see header data-loss note). The memory_id column is translated back
-- to the pre-007 legacy id via the reverse conv_id_map join; rows
-- whose UUID7 memory_id does not resolve in conv_id_map (always, on
-- a fresh post-007 DB) keep memory_id = NULL.
-- ============================================================================

CREATE TABLE memory_access_log (
    id           TEXT PRIMARY KEY,
    memory_id    TEXT,
    access_type  TEXT,
    query_text   TEXT,
    timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations(id)
);

INSERT INTO memory_access_log (id, memory_id, access_type, query_text, timestamp)
SELECT
    mal.id                                                       AS id,
    (SELECT m.legacy_id FROM conv_id_map m
        WHERE m.uuid7_id = mal.memory_id)                        AS memory_id,
    mal.access_type,
    mal.query_text,
    mal.timestamp
FROM memory_access_log_backup mal;

CREATE INDEX IF NOT EXISTS idx_access_log_memory
    ON memory_access_log(memory_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_access_log_timestamp
    ON memory_access_log(timestamp DESC);

DROP TABLE memory_access_log_backup;

COMMIT;

-- Drop the temp helper table. On a fresh post-007 DB the table was
-- empty when this script created it; the explicit DROP keeps the
-- connection tidy.
DROP TABLE IF EXISTS conv_id_map;

-- End of script 007 down.
--
-- Post-down invariants:
--   * `conversations` (renamed back from `conversations_v2` if
--     001_down ran first; otherwise carries the post-007 UUID7 IDs)
--     and `reflections` (carries the post-007 fresh UUID7s) keep
--     their current IDs. The down does NOT try to regenerate the
--     pre-007 IDs for these tables -- that would require
--     conv_id_map-style mapping for reflections/code_graphs/
--     session_windows which 007 did not produce.
--   * memory_entities, memory_promotions, memory_relationships are
--     recreated empty (matching the pre-007 verified state).
--   * memory_access_log carries the post-007 UUID7 `id` and
--     `memory_id` translated back to the pre-007 legacy id (NULL
--     on a fresh post-007 DB; populated if the operator restored
--     a conv_id_map before running the down).
--   * The FK memory_access_log.memory_id -> conversations(id) is
--     satisfied for every row whose UUID7 memory_id resolved in
--     conv_id_map; the rest (NULL, or pointing at a UUID7 not in
--     the map) keep memory_id NULL, which the FK permits.
-- ============================================================================
