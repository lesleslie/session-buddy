---
status: draft
date: 2026-11-05
last_reviewed: 2026-11-06
role: canonical
topic: memory-architecture
---

# Conversation Transcript Ingestion — Design

*Draft v2 — revised after builder check and fleet storage surveys.*

**Scope:** Session-Buddy (`session_buddy`), with fleet-wide dependencies on
Oneiric, Akosha, and Mahavishnu

## Context

Session-Buddy is the fleet-wide session store: one queryable surface for
session history reachable from any MCP harness, including sessions that ran on
machines whose local `~/.claude/projects` the querying host cannot see.

Today `conversations_v2` holds **52 rows** — 33 synthetic context markers
written by `capture_conversation_context`
(`session_buddy/core/conversation_storage.py:25`), a 155-character header with
project, timestamp, quality score, and `is_manual`; and 19 `category='facts'`
rows migrated from the v1 table. The most recent genuine marker is
**2026-10-31 07:27**. The auto-capture path has written nothing since,
because the `end` / `checkpoint` tools hang inside
`perform_quality_assessment` → `_get_crackerjack_metrics`
(`session_buddy/utils/quality_scoring.py:920`), and the hook scripts in
`~/.claude/scripts/` abort on an uncaught `subprocess.TimeoutExpired`
(10–15 s budgets against a tool that exceeds 90 s).

The receiving schema is **already built for this pipeline**:

| Signal | Location | State |
|---|---|---|
| `source_type` CHECK permits `'claude_code'` | `session_buddy/memory/schema_v2.py:76-80` | present; adapter already writes it |
| `category` value `claude_turn` — *"A single Claude conversation turn (transcript ingester)"* | `schema_v2.py:24-26` | present |
| `turn_parent_id` / `causal_parent_id` — *"so transcript ingesters … can reconstruct the chain"* | `schema_v2.py:81-82`, `reflection_adapter_oneiric.py:1469-1472` | present; adapter already writes them |
| `MemoryCategory.CLAUDE_TURN` | `schema_v2.py:24` | present |
| Redaction allowlist: `source_session`, `parent_uuid_chain`, `tool_names`, `tool_counts`, `model`, `token_usage`, `extracted_at` | `session_buddy/ingesters/redaction.py:21-36` | present |
| `store_conversation` accepts `source_type`, `turn_parent_id`, `causal_parent_id`, `category='claude_turn'`, applies `redact()`/`redact_metadata()`, writes `memory_provenance` | `reflection_adapter_oneiric.py:1450-1490` | **implemented** |

The gap is the *producer*: nothing parses a Claude Code transcript and pushes
turns. This spec builds that producer and the retrieval surface around it.

### Division of labour (canonical, shipped)

`docs/plans/.archive/2026-04-02-storage-consolidation-and-akosha-role.md`
(status `shipped`, role `canonical`) settles ownership:

> "Mahavishnu owns operational persistence … tasks, task runs, dependencies,
> events, searchable documents, embeddings, hybrid search APIs"
> "Session-Buddy remains **best-effort and asynchronous** for context/history
> — session context, **conversation history**, assistant-facing memory,
> best-effort mirrored writes only"
> "Akosha is removed from the critical storage path"

A conversation-transcript store is squarely inside Session-Buddy's lane.
Mahavishnu receives **mirrored, best-effort** writes — not a second copy.
Akosha is **derived intelligence**, not a second source of truth.

### Prior art

- **Letta (MemGPT)** — *recall memory* holds the full chronological log as
  `(role, content, timestamp, tool_calls, tool_call_responses)`, indexed by
  insertion order **and BM25 keyword**; *archival memory* holds agent-curated
  paragraphs, indexed **by vector**. The two stores have no typed relation:
  one is the raw transaction log, the other a curated distillate. Session-Buddy's
  `conversations_v2` ≈ recall memory; `reflections_v2` ≈ archival memory
  (`schema_v2.py` is explicitly "Memori-inspired").
- **Zep / Graphiti** — an *episode subgraph* stores raw inputs as the ground
  truth, "nothing is thrown away here". Episode granularity is one **message**.
  Episodes chain via `saga_previous_episode_uuid`. Crucially, **Zep persists
  the episode synchronously and enriches asynchronously**.
- **Mem0** — deliberately does **not** store raw chat ("Chat history is a
  transcript. Mem0 is a curated notebook."). v3 retrieval is hybrid:
  semantic + BM25 + entity signals.
- **LoCoMo multi-session agent-memory benchmark** — a single vector index
  (0.526) does not significantly beat BM25 alone (0.552, p = 0.36); a BM25 +
  embedder hybrid fused with RRF reaches 0.609 and wins 9/10 conversations.
  Conversational recall is "heavy on exact-token recall", where dense vectors
  *smear* the rare token.

## Goals

1. Store actual session dialog in `conversations_v2`, sourced from live
   sessions on any machine and any harness.
2. Keep capture fast and independent of embedding, so a slow embedder can
   never stall ingestion.
3. Retrieve across both tiers: BM25 over raw turns and vector over embedded
   turns and reflections, fused with RRF — opt-in, with the existing vector
   default preserved.
4. Provide a delete surface covering a single conversation, a whole session, a
   project, and a date range.
5. Retention: raw turns expire; distilled reflections never do. Expiry
   **deletes** by default, and **archives to a cold bucket** when one is
   detected configured and healthy.
6. Start the conversation tier clean: no legacy context markers.
7. Restore the auto-capture path and make a silent capture gap visible as
   `degraded` rather than `healthy`.
8. Make the fleet use **one** embedder, so no component can disagree about
   vector width — including migrating Mahavishnu from 384 to 768 and
   replacing Crackerjack's hash pseudo-vectors with real ones.

## Non-goals

- **No backfill.** The existing 2,435 Claude Code JSONL transcripts (4.0 GB) in
  `~/.claude/projects` are not ingested. The conversation tier starts fresh.
- **No tool-result content.** Tool outputs are not stored. Tool *names* and
  counts are recorded as metadata.
- **Not a transcript archive.** The source is lossy (Claude Code compacts at
  >50 K tokens and previews tool results >50 KB), so this store is not a more
  complete copy of the source.
- No multi-agent consolidation from raw turns into `reflections_v2`.
- No Akosha synchronization of raw turns.
- No repair of the broken Mahavishnu↔Session-Buddy edges (see
  *Out of scope*); this work does not depend on them.

## Architecture

```
 Claude Code session (any machine, any harness)
   │
   │  Stop hook — reads `transcript_path` + `session_id` from its stdin payload
   ▼
 session_buddy/hooks/transcript_ingest.py
   │  parse JSONL → new turns → batch
   │  POST via MCP `ingest_turns`
   ▼
 ┌─────────────────────────────────────────────────────────┐
 │ Session-Buddy (central)                                  │
 │                                                          │
 │  ingest_turns  ──▶ sanitize ──▶ redact ──▶ store         │
 │   (synchronous,     (injection      (allowlist)          │
 │    idempotent)      guard)          │                   │
 │                                       ▼                   │
 │                            conversations_v2                │
 │                            ├ content, searchable_content  │
 │                            ├ embedding (NULL until filled)│
 │                            ├ embedding_status              │
 │                            ├ session_id, turn_parent_id   │
 │                            ├ source_type='claude_code'    │
 │                            └ category='claude_turn'        │
 │                                       │                   │
 │                     ┌─────────────────┘                   │
 │                     ▼                                     │
 │              embed queue (async)                          │
 │                     │                                     │
 │                     ▼                                     │
 │              EmbedWorker ──▶ embedding populated          │
 │                                                          │
 │  FTS index (incremental) over searchable_content ─┐       │
 │  vector index over embedding ─────────────────────┤       │
 │                                                     ▼       │
 │                                    hybrid_search (RRF)       │
 │                                                     ▲       │
 │                            reflections_v2 (vector)       │
 └─────────────────────────────────────────────────────────┘
```

Two writes, deliberately separated in time: the **raw write** is synchronous
inside the `ingest_turns` call; the **embed** is queued and performed by a
background worker. This is Zep's asynchronous-enrichment pattern, and it is
what makes capture immune to embedder latency.

## Components

### NEW: `session_buddy/ingesters/transcript_ingester.py`

Parses a Claude Code JSONL transcript into turn records. Pure function over
text — no I/O, no database. Unit-testable against fixture transcripts.

- Skip records that are not conversational turns: `isMeta` records,
  `type="summary"`, and system-reminder payloads.
- Mark sidechain records (subagent turns) with `metadata["is_sidechain"] = true`.
  Sidechain turns are **skipped by default** — a separate agent's conversation
  dilutes parent recall. A setting turns them on.

  **Correction (verified live against Claude Code v2.1.318, 2026-11-06):**
  subagent turns are **not in the parent transcript at all**. They live in a
  separate file at
  `~/.claude/projects/<slug>/<parent-session-id>/subagents/agent-<agent_id>.jsonl`,
  reached through the `SubagentStop` hook payload's `agent_transcript_path`.
  The parent's `tool_result` for the `Agent` call carries only a pointer, not
  the content. "Skipped by default" therefore means *not consuming
  `agent_transcript_path`*; the parser's `isSidechain` branch is defensive,
  for paths that do embed those records.
- Extract: `uuid`, `parentUuid`, `sessionId`, `timestamp`, `message.role`,
  `message.content`, `message.model`, `message.usage`.
- Split `message.content` into blocks: `text`, `thinking`, `tool_use`,
  `tool_result`, `image`.

### NEW: `session_buddy/ingesters/injection_guard.py`

Sanitizes turn text so tool output cannot impersonate a conversation turn.

Crackerjack already solved this shape for its failure-recording path
(`crackerjack/services/failure_recorder.py:20-30`): it strips `Human:` /
`Assistant:` / `System:` role prefixes and `<system|prompt|instruction>` tags
before writing to Session-Buddy. The same guard runs here, because a raw
transcript contains tool output that an attacker (or a prompt-injection in
fetched content) controls — and the store is read back into agent context.

- Role prefixes are stripped from *tool-result* content only. Genuine
  user/assistant turns are typed by their JSONL `message.role`, not by a
  prefix inside the text.
- `<system|prompt|instruction>` tags are stripped from tool-result content.
- A `metadata["sanitized"] = true` marker is set on any turn whose text was
  modified, so provenance survives.

### MODIFIED: `session_buddy/memory/schema_v2.py`

- **No rename.** The live table is `conversations_v2`. A migration
  (`session_buddy/migrations/2026_10_11_uuid7_consolidation/001_consolidate_conversations.sql:165`)
  records an intent to drop the `_v2` suffix, but that rename is **not present
  in the live database** — verified against a snapshot of
  `~/.local/share/session-buddy/reflection.duckdb`, where `conversations_v2`
  holds 52 rows and `conversations` holds 19. The spec names the live table.
- **New column** `embedding_status TEXT DEFAULT 'pending'` with values
  `pending` | `embedded` | `skipped`. `embedding IS NULL` alone is ambiguous
  between "not yet embedded" and "deliberately not embeddable"; this column
  removes the ambiguity that would otherwise make the worker re-derive every
  prose-free turn on every restart.
- **New unique constraint** `UNIQUE(session_id, turn_uuid)` where `turn_uuid`
  is the source JSONL `uuid`. This is the idempotency key (see *Idempotency*).
  **Correction (verified against DuckDB 2.0.0, 2026-11-06):** it is a
  **unique index**, not a table constraint — DuckDB cannot
  `ALTER TABLE ... ADD CONSTRAINT`, so a table-level `UNIQUE` would only
  exist on freshly created tables and would duplicate the index on every new
  database. `ON CONFLICT (session_id, turn_uuid)` works against a unique
  index. No partial/expression index is needed: **NULLs are distinct** under
  a DuckDB unique index, so the 52 existing rows with `session_id = NULL`
  coexist without a uniqueness violation.
- **New indexes**: `(session_id)`, `(project, timestamp DESC)`.
- **Replace** the btree `idx_conversations_fts` (`schema_v2.py:226`) with a
  DuckDB FTS index — see *Full-text search* below. The btree index on a TEXT
  column provides no tokenized search; it only accelerates whole-string
  matching.
- **A pre-existing defect must be fixed first.** The adapter creates the
  schema with `schema_v2_sql(...).split(";")`
  (`reflection_adapter_oneiric.py:1054`) — a naive split that does not
  understand SQL comments. Two comments in `schema_v2.py` contain a
  semicolon (`:116` and `:196`), which truncates the
  `CREATE TABLE IF NOT EXISTS reflections_v2` statement before its closing
  paren. **Reproduced on 2026-11-06: on a fresh database twelve statements
  fail and `reflections_v2` is never created** — each failure caught by
  `except duckdb.Error` and logged at DEBUG, so it is invisible. The live
  table survives only because an older schema version created it and
  `CREATE TABLE IF NOT EXISTS` no-ops on it. The splitter must understand
  comments, no SQL comment may contain a `;`, and the failure log level must
  rise to WARNING.
- **A second defect hides behind the first:** `reflections_v2.conversation_id`
  is **not in `schema_v2.py` at all**, yet the live table has the column and
  its FK to `conversations_v2(id)` — both from the older schema. Fixing the
  splitter without adding the column would create fresh databases whose
  `reflections_v2` cannot be nulled by the delete path.

### MODIFIED: `session_buddy/adapters/reflection_adapter_oneiric.py`

- `store_conversation` gains a `turn_uuid` parameter and the
  `UNIQUE(session_id, turn_uuid)` upsert path. It already applies redaction,
  provenance, and the transcript-shaped columns — **this work extends it
  rather than adding a parallel writer**.
- `store_conversation` currently derives `id` from `sha256(content)[:16]`
  (`session_buddy/reflection/storage.py:190-199`) with `ON CONFLICT(id) DO
  UPDATE`. Two turns with identical text therefore collide and the second
  overwrites the first. The ingest path must not use a content hash for its
  identity — see *Idempotency*.
- Adds `delete_conversations` (scoped delete) and `prune_conversations`.
- Adds a hybrid retrieval mode to `search_conversations`.

### NEW: `session_buddy/mcp/tools/conversation/ingest_tools.py`

Registers the `ingest_turns` MCP tool.

- Accepts a batch of turns for one session.
- Sanitizes (injection guard), then redacts (`redact()` /
  `redact_metadata()` against `ALLOWED_METADATA_KEYS`).
- Writes rows with `embedding = NULL`, `embedding_status = 'pending'`,
  `source_type = 'claude_code'`, `category = 'claude_turn'`.
- Queues turn ids for embedding.
- Returns accepted / skipped / duplicate / truncated counts.

**Oversized turns are truncated, not rejected.** `redact()` truncates to 64 KB
and appends `[TRUNCATED]`; it only raises `RedactionSizeError` when
`raise_on_oversize=True`, which the adapter never passes — so the adapter's
`except RedactionSizeError` branch is unreachable and the observable behavior
is silent truncation. The ingest path matches that behavior rather than
inventing a new one. The cap is measured on the **redacted content**.

### NEW: `session_buddy/workers/embed_worker.py`

A background asyncio task, started from the server lifespan and stopped on
shutdown.

- Consumes an in-process queue of pending turn ids.
- Embeds `searchable_content` for each and writes the vector back, setting
  `embedding_status = 'embedded'`.
- Embeds **text-bearing turns only**. A turn with no prose is marked
  `embedding_status = 'skipped'` and never re-derived.
- On failure, leaves `embedding` NULL, sets `embedding_status = 'pending'`,
  and increments the feed's `errors_total`. A NULL embedding is not an error
  state for search — BM25 still covers the row.

`session_buddy/server_optimized.py` already uses `asyncio.create_task` for
background work. The server's `timeout_graceful_shutdown` is **30 s**
(mcp-common pins it; the "2 s" in a stale in-code comment at
`server_optimized.py:304` is wrong), so the worker has room to drain. Pending
ids are re-derived at startup from
`WHERE embedding_status = 'pending'`, so a crash mid-batch is recoverable.

### NEW: `session_buddy/mcp/tools/conversation/delete_tools.py`

Registers `delete_conversation`. Scopes, all four required by the operator:

| Scope | Filter |
|---|---|
| Single conversation | `conversation_id` |
| Whole session | `session_id` |
| By project | `project` |
| By date range | `before` / `after` (timestamps) |

At least one scope is required. There is no unfiltered "delete all".

Semantics:

- Deleting a session deletes all of its turns; turns are one logical unit and
  partial session deletion leaves a misleading fragment.
- `turn_parent_id` children of a deleted turn are **cascaded**. A turn whose
  parent no longer exists cannot be reconstructed.
- **Foreign keys are enforced by DuckDB.** Five tables reference
  `conversations_v2(id)`: `memory_entities.memory_id`,
  `memory_promotions.memory_id`, `memory_access_log.memory_id` (all at
  `schema_v2.py:136,160,173`) and `reflections_v2.conversation_id`, plus
  `memory_relationships` transitively — its `from_entity_id` and
  `to_entity_id` are foreign keys to `memory_entities(id)`. Deleting a
  referenced row raises a `ConstraintException` unless the referencing rows are
  handled. Therefore:
  - `memory_entities`, `memory_promotions`, `memory_access_log` rows are
    **deleted** with the turn.
  - **`memory_relationships` is deleted BEFORE `memory_entities`** — it
    references the entity rows, so deleting entities first raises
    `ConstraintException` and aborts the whole delete. The shipped
    `delete_conversation` (`reflection_adapter_oneiric.py:2959`) already
    implements this six-step ordering correctly; the scoped delete extends
    it rather than adding a parallel method.
  - `reflections_v2.conversation_id` is set to **NULL** — reflections are
    never pruned, so the reflection survives with its link broken. **The
    shipped `delete_conversation` does not do this** and will raise on a
    referenced reflection.
  - `memory_provenance.memory_id` has no FK, but `schema_v2.py:239-245`
    explicitly requires an application-level cascade; provenance rows are
    deleted with the turn.
  - **Correction:** `reflections_v2.conversation_id` is not in
    `schema_v2.py`'s `CREATE TABLE` at all — the live table carries it, and
    its FK, from an older schema version. The DDL must add the column (and
    the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` guard) or a fresh
    database has no column to null.
- The vector lives on the same row as the content, so deleting the row
  removes the vector. The FTS index is kept in sync by the incremental index
  (see below).
- Returns counts deleted, by scope.

### NEW: `session_buddy/core/pruner.py`

Retention sweeper for raw turns.

- Selects `conversations_v2` rows with `source_type = 'claude_code'` older
  than `conversation_storage.retention_days` (default **90**).
- **Delete path (default).** Rows are deleted outright, with the same FK
  handling as `delete_conversation`.
- **Archive path (conditional).** When a cold bucket is *detected configured
  and working*, the turns are archived to Session-Buddy's **own** cold bucket
  first, and deleted locally only after a confirmed upload.
  - The bucket and key prefix are **component-scoped**, never the shared
    Oneiric substrate prefix. Per
    `mahavishnu/docs/decisions/2026-11-05-per-component-cold-storage-buckets.md`
    (active, canonical): *"Each component that has a cold tier owns its own
    bucket. The bucket name and the key prefix are component settings, not
    fleet settings."* The shared `cold__prefix` is a fleet-wide env var that
    components cannot override, so two components reading the substrate
    resolve the same prefix and overwrite each other's objects.
  - The upload reuses **Oneiric's existing storage adapter** —
    `oneiric.adapters.storage.s3.S3StorageAdapter`, the same class
    `session_buddy/storage/cloud_sync.py:43-64` already uses. No bespoke
    object-store client.
  - Detection: the bucket is configured **and** a probe write+read succeeds.
    If detection fails, the sweeper falls back to deletion and logs the
    fallback. A broken bucket must never turn into a silent data-loss event.
  - Key layout: `conversations/{session_id}/{turn_uuid}.json` under
    Session-Buddy's own prefix.
- Reflections are never pruned.
- Scheduling: a **lifespan-owned task**. An external cron is not viable —
  DuckDB is single-writer across processes and the live `reflection.duckdb`
  is held open by the running server, which is exactly what
  `session_buddy/reflection/database.py:194` raises `DatabaseLockedError` for.

### NEW: `session_buddy/hooks/transcript_ingest.py`

The push hook. Lives in this repository so it is versioned and reviewable,
rather than as an ad-hoc script in `~/.claude/scripts/`.

- **Stdlib-only**, matching the sibling hooks (`sb_checkpoint.py`,
  `sb_post_tool.py`). No `import session_buddy` — a hook that fails to import
  on a remote machine must not break the session.
- Speaks raw JSON-RPC to `{BASE}/mcp` with an `initialize` handshake and an
  `mcp-session-id` header, exactly as the sibling hooks do.
- Reads the hook payload from stdin. Claude Code supplies `session_id`,
  `transcript_path`, `cwd`, and `hook_event_name`. The existing
  `~/.claude/scripts/sb_post_tool.py:97` already parses this payload and
  ignores the two fields this hook needs.
- Opens `transcript_path`, parses the JSONL, selects turns whose `uuid` is not
  already ingested, and posts one batch to `ingest_turns`.
- Resolves the endpoint from `SESSION_BUDDY_URL`, defaulting to
  `http://localhost:8678`. **This is what makes the path work from a remote
  machine** against a central Session-Buddy.
- **Never fails the session.** Every failure path exits 0 and logs.
- A local offset cache under `~/.cache/session-buddy/ingest/{session_id}.json`
  avoids re-parsing the whole transcript. It is an **optimization only** —
  correctness rests on the unique key, so a lost or stale cache costs time,
  not data.

**Harness coverage.** The `Stop` hook carrying `transcript_path` is a Claude
Code mechanism. Other harnesses reach the same pipeline by calling the
`ingest_turns` MCP tool directly — the tool *is* the harness-agnostic path;
the hook is the convenience wrapper. Cross-machine works because the hook runs
where the session runs and pushes to the central URL.

### MODIFIED: `session_buddy/core/session_manager.py`

The three fixes from the capture-gap audit. **These live in
`core/session_manager.py`, not in the MCP tools module** —
`checkpoint_session` is at `session_manager.py:1246` and `end_session` at
`session_manager.py:1684`; the MCP wrappers are in
`session_buddy/tools/session_tools.py:62,69`. The conversation write is
`_store_conversation_checkpoint_if_enabled` (`session_manager.py:1515`),
called at lines 1349 (checkpoint) and 1743 (end) — both *after* the quality
assessment at lines 1317 and 1738.

1. **Reorder.** The conversation write moves **before**
   `perform_quality_assessment` in both paths. A stalled quality assessment
   can no longer gate the capture.
2. **Bound.** The assessment gets its own timeout. On timeout it logs and
   returns `quality_score = None`; the checkpoint payload keeps the
   `quality_score` key (shape unchanged, value nullable). Because
   `should_auto_store_checkpoint(quality_score=…)` (`session_manager.py:1332`)
   consumes that value, a timed-out assessment **skips auto-storing a
   reflection** for that cycle rather than storing one with a fabricated
   score.
3. **Catch `TimeoutExpired` in the hook scripts.** The three scripts in
   `~/.claude/scripts/` (`sb_session_end.py:23` timeout 15,
   `sb_checkpoint.py:23` timeout 10, `sb_session_start.py:23` timeout 10) each
   contain exactly one `except` clause, catching only `json.JSONDecodeError`.
   An uncaught `subprocess.TimeoutExpired` aborts the hook. The new hook
   scripts catch broadly and exit 0.

### MODIFIED: `session_buddy/mcp/tools/profiles.py`

New tool groups must be registered in **both** `REGISTRATION_MAP` and the
per-tier list in `PROFILE_REGISTRATIONS`, or they register only at `FULL`
via `_register_all_tool_groups`.

- `ingest_turns` → **`standard`** tier. A deployment running
  `SESSION_BUDDY_TOOL_PROFILE=standard` must still expose it; the hook would
  otherwise fail every time and the "never fails the session" rule would mask
  it — the feature would look shipped and ingest nothing.
- `delete_conversation` → **`standard`** tier (operator surface, and it must
  be reachable wherever the store is).

The cross-repo plan `docs/plans/2026-08-05-cross-repo-checkpoint-accounting.md`
(status `built`) additionally requires the registration string in
`STANDARD_REGISTRATIONS` (`session_buddy/mcp/tools/profiles.py:36`).

**Correction (verified against the source, 2026-11-06):** there are **two**
registration points, not four. `_ALL_REGISTERS` no longer exists — it was
removed in commit `c28124e8` during the mcp-common 0.18.0 refactor. The two
are:

1. `REGISTRATION_MAP["register_<group>"] = register_<group>` — keyed by the
   **`register_*` function name**, not the tool name; the registration drift
   test requires the `register_*` names.
2. `STANDARD_REGISTRATIONS.append("register_<group>")` — from which
   `PROFILE_REGISTRATIONS[ToolProfile.STANDARD]` derives automatically.

The new `register_*` functions must also be exported from
`session_buddy/mcp/tools/__init__.py` and
`session_buddy/mcp/tools/conversation/__init__.py`.

### MODIFIED: `session_buddy/mcp/auth.py` usage

Auth uses the **local** `require_auth(optional=False)` from
`session_buddy/mcp/auth.py:91` — *not* `mcp_common.auth`. It verifies the JWT
(`expected_audience="session-buddy"`) and **injects** `user_id` from the token
payload.

This is safe, unlike Mahavishnu's `require_mcp_auth`, which binds identity to
a caller-supplied `user_id` unless the tool declares a `ctx: Context`
parameter — documented in
`mahavishnu/docs/decisions/2026-10-29-learning-pipeline-tools-authz-block.md`
(active, canonical). The ingest tool declares `token: str | None = None` and
does **not** expose `user_id` as a caller-settable field.

**Correction (verified against the source, 2026-11-06):** `require_auth`
injects `user_id` as a **keyword argument** into the wrapped function. A tool
whose signature does not declare `user_id` therefore raises `TypeError` on
every call when a secret is configured. Every new tool must declare
`user_id: str | None = None`; the decorator supplies the value, so it is not
caller-settable in practice. The adapter must also stop hardcoding
`user_id="default"`, or the token identity could never reach the row.

### MODIFIED: health snapshot

`/health` and the MCP health tool currently report feeds for `skills_signer`
and `bodai_events` only. A capture gap is invisible because no feed covers
conversations.

A new **`conversations`** feed joins the aggregate.

**Constraint:** `mcp_common.health.feed.HealthFeedState`
(`mcp_common/health/feed.py:80`) is a fixed dataclass with exactly eight
fields — `entities_count`, `last_updated_timestamp`, `cycles_total`,
`errors_total`, `last_error_at`, `errors_within_window`,
`first_unhealthy_at`, `ingester_running`. There is no `pending_embeddings`
field, and `aggregate_feed_states` derives each verdict **solely** from those
fields.

Consequences, both handled:

- **Empty feed ⇒ 503.** `is_healthy`'s empty-feed branch maps
  `entities_count == 0` + `ingester_running == False` to **FAILED**, and
  `entities_count == 0` + `cycles_total == 0` + `ingester_running == True` to
  **DEGRADED**. Both map to HTTP 503 in `_http_status_for`. A fresh
  deployment with zero ingested conversations would therefore report the
  service as unhealthy *before any ingest has ever happened* — breaking every
  consumer of `/health`.
  **Resolution:** the ingest worker is a lifespan-owned task that is
  **always running**, and it records one successful cycle at boot (a liveness
  marker). `ingester_running = True` and `cycles_total >= 1` from the first
  moment the server is up, so an empty-but-live feed reports healthy. A feed
  that has *never* produced reports degraded — which is the correct signal
  for a genuinely stalled ingester.
- **No `pending_embeddings` field.** The backlog is folded into the existing
  eight fields rather than extending mcp-common: a backlog beyond the
  threshold increments `errors_total` and sets `last_error_at`, which
  `is_healthy` already reads.

The feed reports `entities_count` (conversation rows), `last_updated_timestamp`
(newest ingested turn), `cycles_total` (ingest calls served), `errors_total`,
`ingester_running`, and — folded in — the embed backlog.

Per `mahavishnu/docs/decisions/mcp-backend-wiring-discipline.md` (active,
canonical), every registered tool needs a working data feed, and
disagreement between `pool_health` and `/health` is a bug — one shared
snapshot builder serves both.

## Data model

One row per conversational **message**.

| Column | Value |
|---|---|
| `id` | UUID7 (repo convention: *"Every load-bearing primary key in this project is a UUID7 rendered as 32 lowercase hex characters"*, `reflection/storage.py:190-199`) |
| `session_id` | From the transcript |
| `turn_uuid` (new) | The source JSONL `uuid` |
| `turn_parent_id` | The parent turn's `id`, resolved from `parentUuid` |
| `content` | Role-prefixed text blocks of the message |
| `searchable_content` | Text blocks + thinking blocks, capped. The FTS projection |
| `embedding` | `NULL` until the embed worker fills it |
| `embedding_status` (new) | `pending` \| `embedded` \| `skipped` |
| `category` | `claude_turn` |
| `source_type` | `claude_code` |
| `project` | Normalized repo/dir name — see *Project normalization* |
| `metadata` | Allowlist-filtered: `source_session`, `parent_uuid_chain`, `tool_names`, `tool_counts`, `model`, `token_usage`, `extracted_at` |
| `memory_tier` | `short_term` for raw turns (not the `long_term` default) — see *Tiering* |

### Idempotency

`UNIQUE(session_id, turn_uuid)` is the idempotency key. Re-ingesting a turn is
an upsert on that key, so the hook's repeated reads of a growing transcript
are harmless. This is deliberately **not** a content hash: `store_conversation`
currently derives `id` from `sha256(content)[:16]`, which makes two turns with
identical text collide. The ingest path uses a UUID7 primary key plus the
natural unique key, preserving the repo's PK convention while making re-ingest
safe.

### What is stored, and what is not

| Element | Stored? | Rationale |
|---|---|---|
| User message text | yes | The signal you search for |
| Assistant text | yes | The signal you search for |
| Thinking blocks | searchable only, capped | Real reasoning; often large |
| Tool **names** and **counts** | metadata | Which tools ran — cheap, useful context |
| Tool **inputs** | no | Frequently large, and mostly reproducible |
| Tool **results** | no | The bulk of the bytes, the least likely search target; the assistant's text summarizing the result is stored instead |
| Image blocks | no | Not text |
| Sidechain (subagent) turns | off by default | A different agent's conversation; dilutes parent recall |
| `isMeta` / summary records | no | Not conversational turns |

The consequence to accept: you cannot retrieve "the exact output of that
command". You can retrieve the assistant's account of what that command found,
and the command's name and invocation count. That is the deliberate cost of
the "don't store tool results" decision, and it is what keeps the store small
enough to hold unembedded rows.

### Project normalization

`project` is the **normalized repo/dir name**, not a full path. The
transcript's `cwd` is a full path; the stored value is its normalized short
form, matching what existing rows hold (`mahavishnu`, `session-buddy`).

Normalization lives in **one shared helper**, extracted from the convention
already implemented in `~/.claude/scripts/sb_post_tool.py:_project_name()`
(scan for `Projects/src/repos/code/workspace`). Delete-by-project uses the
same helper, so writes and deletes agree.

### Tiering

Session-Buddy's `MemoryTier` (`working` / `short_term` / `long_term`) is a
**semantic** tier on a row — not a storage tier. Akosha's hot/warm/cold are
**storage** tiers. They are orthogonal, and the SB→Akosha sync already maps
`memory_tier` across (`session_buddy/storage/akosha_sync.py:445`).

Raw ingested turns are written with `memory_tier = 'short_term'`, not the
`'long_term'` column default. A raw turn is recent and low-importance by
construction; labelling it `long_term` would make the retention sweep skip it
and would push it to Akosha as a durable conversation memory.

## Retrieval

Hybrid, fused with Reciprocal Rank Fusion (RRF, constant 60):

1. **BM25 channel** — DuckDB FTS over `conversations_v2.searchable_content`.
   Strong on exact-token recall ("what did I say about `mahavishnu_kv_put`").
2. **Vector channel** — cosine similarity over embedded conversation turns,
   plus `reflections_v2` rows.
3. **Fuse** with RRF, return top-k with both channel scores retained.

This is the empirically best configuration in the LoCoMo benchmark (0.609 vs
0.552 BM25 and 0.526 vector-only).

**`mode` is opt-in.** `search_conversations` gains `mode` ∈
`"vector" | "bm25" | "hybrid"`, **defaulting to `"vector"`** so no existing
caller's behavior or result shape changes. The MCP tool keeps its current
default for the same reason.

**The query cache key gains `mode`.** Today the key is
`compute_cache_key(query=…, project=…, limit=…, kind="conversations",
threshold=…)` with no mode — a hybrid call would hit a vector-mode cache
entry. Separately, `_get_cached_conversations` returns `"score": 1.0` for
every row, which would flatten hybrid's channel scores. The cached path
therefore stores the per-channel scores, and the key includes `mode`.

**A lexical channel already exists.** `_search_conversations_db` falls back
to `_text_search_conversations` — a `content LIKE %token%` OR-match — when
vector search returns nothing above threshold or embeddings are disabled.
The BM25 channel **replaces** that fallback, rather than coexisting with it;
the fallback is retained for the `mode="vector"` path.

### Full-text search

DuckDB 2.0's FTS API differs materially from 1.x. Verified against the
repo's own DuckDB (**2.0.0**):

- **The `fts` extension must be loaded explicitly.** `duckdb_extensions()`
  reports `fts: installed=True, loaded=False`. Autoloading does **not** fire
  for `PRAGMA create_fts_index` — the call fails until `LOAD fts` is issued
  **on that connection**. Every connection that creates, rebuilds, or queries
  the index needs the explicit load.
- **Argument order.** The first argument is the **input table**, not an index
  name:
  ```
  PRAGMA create_fts_index('conversations_v2','id','content', <options>)
  ```
  The shadow schema is derived: `fts_main_conversations_v2.{docs,terms,dict,fields,stats,stopwords}`.
- **`incremental=true` is mandatory.** The default index is a **snapshot**:
  rows inserted after creation are invisible to BM25. With `incremental=true`,
  the index tracks both inserts and deletes. Verified:
  ```
  created (incremental=true)          docs=2   bm25 → t2 (0.292)
  after INSERT t3                     docs=3   bm25 → t3, t2       ← indexed
  after DELETE t1                     docs=2   bm25 → t3, t2       ← removed
  ```
- **`create_fts_boolean_query_macros` requires `layered_search=true`**; it
  errors otherwise.
- **`match_bm25` is a scalar macro**, not a table function. The 1.x form
  (`SELECT * FROM fts_main_x.match_bm25('idx','q')`) raises *"Table Function
  with name match_bm25 does not exist"*. The working form joins the shadow
  `docs` table:
  ```sql
  SELECT d.name, fts_main_conversations_v2.match_bm25(d."name", ?) AS score
  FROM fts_main_conversations_v2.docs d
  WHERE fts_main_conversations_v2.match_bm25(d."name", ?) IS NOT NULL
  ORDER BY score DESC
  ```
  It returns NULL for non-matching docs.
- **Tokenizer.** Supported values are `regex` and `opensearch_standard`.
  `strip_accents=true` is **not** supported with `opensearch_standard`
  (OpenSearch's analyzer lowercases but does not strip accents). Use
  `tokenizer='regex'`, or `opensearch_standard` with `strip_accents` off.
- **The content column is the third positional value.** The real signature is
  `create_fts_index(input_table, input_id, *input_values, **options)` — the
  variadic values name the columns to index. The second positional is the
  *id* column, so `('conversations_v2','id','searchable_content', ...)` indexes
  `searchable_content` keyed by `id`. (The flat parameter list DuckDB reports
  for this pragma omits the variadic and reads misleadingly as
  `input_table, input_id, stemmer, …` — the binder's own candidate signature
  is authoritative.)

## Embedding: one embedder for the fleet

**Decision.** Oneiric's `EmbeddingService` gains an **OpenAI leg** (Bifrost
gateway first, direct OpenAI second), and Session-Buddy and Akosha both use
it. Session-Buddy's own provider chain
(`session_buddy/reflection/embeddings.py`) becomes the *fallback* chain, not
the primary.

**Why.** The fleet currently disagrees about vector width:

| Component | Declared width | Source |
|---|---|---|
| **Session-Buddy** | **768** | `session_buddy/memory/embedding_dim.py:39` (`DEFAULT_EMBEDDING_DIM`), `FLOAT[768]` columns |
| **Akosha** | 384 (hardcoded in `store_memory`) | `akosha/mcp/tools/session_buddy_tools.py` — validates against 384 and only *warns* on mismatch |
| **Mahavishnu** | **384** | `mahavishnu/core/resilient_embeddings.py:53` — `STANDARD_EMBEDDING_DIMENSION = 384`, commented *"Ecosystem standard embedding dimension"* |
| **Oneiric** | 768 / 1024 / 256 / 384 | `akosha/processing/embedding_dim.py` `BACKEND_DEFAULT_DIMS` keyed on the resolved backend |
| **Crackerjack** | 384 — but fake | SHA-256 hash pseudo-vectors, not a model (`crackerjack/services/ai/embeddings.py:99-111`) |

A 384-wide vector cannot bind into a `FLOAT[768]` column, and vice versa.
Akosha's hot store bakes `FLOAT[N]` at startup from its resolved backend
(`akosha/main.py:195-215`), so a width disagreement fails at insert time —
a failure Akosha has already been bitten by (its own comment records the
*"embedding dim mismatch"* break). Oneiric's `BACKEND_DEFAULT_DIMS` has **no
`openai` entry**, so an OpenAI backend would fall back to 384 unless the entry
is added.

**Target width: 768.** OpenAI's `text-embedding-3-small` is Matryoshka-
trained and supports a `dimensions` parameter; 768 is what Session-Buddy's
existing shipped chain already produces (`OPENAI_EMBEDDING_DIM`), and it is
the width both current local fallbacks serve (EmbeddingGemma-300M natively).

**Consequence — this is a fleet-wide migration, and it is in scope.**
Mahavishnu moves 384 → 768, which touches its OTel hot store `FLOAT[384]`
schema, its pgvector `vector(384)` column, and `search.document_embeddings`.
Akosha's hardcoded 384 check in `store_memory` is replaced by the resolved
width. Session-Buddy's `FLOAT[768]` schema does not change.

### NEW (fleet): Crackerjack real embeddings

Crackerjack's semantic index is **per-repo SQLite with BLOB vectors** and no
shared service, so it stays out of cross-store vector joins — but its own
vectors carry no semantic signal, and that is a documented defect, not a
rounding error.

`crackerjack/services/ai/embeddings.py:75` logs *"ONNX session not
implemented yet — using fallback embeddings"* and sets `self._session = None`;
every `generate_embedding` falls through to `_generate_fallback_embedding`
(`:99-111`), which SHA-256s the text, takes the first 96 hex characters,
divides each byte by 255, and repeats each value 8 times → 384 floats.
`is_model_available()` returns `False`.

`crackerjack/fixers/semantic.py:31-37` already documents the consequence:

> "because the fallback embedding is a hash of the *entire* input text (not a
> true semantic encoding), essentially any two different short code snippets
> produce moderately-to-highly similar vectors (cosine similarity commonly
> 0.7-0.85 between totally unrelated strings… The 'similarity' scores this
> agent reports are therefore not meaningfully semantic today."

Measured independently against the shipped code: 500 random unrelated text
pairs score cosine **0.577–0.901 (mean 0.752)**, and **81.4% clear
Crackerjack's default `min_similarity=0.7`**. A genuine paraphrase scores
*below* an unrelated string. The cause is structural — the vector is
`[v₁×8, v₂×8, …, v₄₈×8]` with every value in [0,1], so it carries a large
shared DC offset and every pair's cosine floor sits near 0.58.

`crackerjack/services/vector_store.py:352` scores with those vectors directly
and filters on `min_similarity`, with **no lexical fallback** — so
`search_semantic` returns confidently-scored, essentially arbitrary results.

**The fix.** Crackerjack's `EmbeddingService` gains a real embedder, sourced
from the same Oneiric adapter the rest of the fleet uses:

- **Search path** — the Oneiric OpenAI leg (768), matching the fleet width.
  The per-repo index is rebuilt at 768; the existing BLOBs are 384-wide and
  cannot be widened in place.
- **Fixer path** — a fast *local* model (llama_cpp or EmbeddingGemma-300M,
  also 768). `crackerjack/fixers/semantic.py` explicitly relies on embedding
  generation being "pure stdlib/numpy, deterministic, and fast" with "no
  network access and no slow model download", which is how its tests exercise
  a real `VectorStore` against a `tmp_path` SQLite. A network-backed embedder
  breaks that property; a local model preserves it while still producing real
  vectors. Both paths are 768, so the index keeps one shape.

**A second bug must land with it.** `_discover_semantic_patterns` builds
per-code-element queries with `file_types=["py"]` (no leading dot), while
`VectorStore` stores `file_type` as `Path.suffix` (`".py"`), and
`_get_all_embeddings` filters with exact string matching. The filter never
matches, so that path returns nothing regardless of vector quality.

The per-repo index is gitignored and regenerable — 32 KB and currently empty
in the crackerjack repo — so the rebuild cost is negligible across the 43
`.crackerjack/` directories that exist under `~/Projects`.

**Still excluded from cross-store joins.** Crackerjack's index remains
per-repo SQLite with BLOB vectors, not a shared service. Equalizing widths
does not make it joinable with the fleet's stores, and this work does not
attempt to.

Crackerjack's XDG namespace and state-path cleanup — moving its
user-scoped data out of Session-Buddy's XDG directory, and moving
`runs/` + `logs/` to `$XDG_STATE_HOME/crackerjack/` — is **filed separately**
as `crackerjack/docs/decisions/2026-11-06-cj-xdg-namespace-and-state-paths.md`
and is independent of this plan.

### NEW (fleet): Oneiric OpenAI embedding leg

`oneiric/adapters/observability/embeddings.py` gains an OpenAI leg, probed
before `llama_cpp`:

- `openai_gateway` — the local Bifrost gateway, OpenAI-compatible, serving
  `text-embedding-3-small` with `dimensions=768`.
- `openai_direct` — `api.openai.com`, same model, when a key exists.
- The existing `llama_cpp → minimax → model2vec → mock` chain remains the
  fallback.

The probe order becomes
`openai_gateway → openai_direct → llama_cpp → minimax → model2vec → mock`.
The probe sets `_backend_dim` from the live response width, so
`dimension()` reports 768 without a hardcoded table entry.

`akosha/processing/embedding_dim.py`'s `BACKEND_DEFAULT_DIMS` gains
`"openai": 768` so the pre-initialization fallback matches the live width.

Session-Buddy's own chain (`session_buddy/reflection/embeddings.py`) becomes
the *fallback* path behind the oneiric adapter, rather than a parallel
primary. Its 768 width and OpenAI-first ordering are unchanged — it is simply
no longer the first place the fleet asks.

### NEW (fleet): Mahavishnu 384 → 768

- `mahavishnu/core/resilient_embeddings.py` — `STANDARD_EMBEDDING_DIMENSION`
  moves 384 → 768. Its `_validate_dimension` currently **counts** a mismatch
  and rejects the vector; after the migration the two components agree and
  the counter stops firing.
- `mahavishnu/core/embeddings.py` / `embeddings_oneiric.py` — the documented
  width moves to 768.
- The OTel hot store's `FLOAT[384]` schema (oneiric
  `duckdb_hot_store.py`) becomes `FLOAT[768]`, and the pgvector column
  becomes `vector(768)`. Both require a **rebuild**, not an `ALTER` — the
  stored vectors are 384-wide and cannot be widened in place.
- `search.document_embeddings.embedding` becomes `vector(768)`.

The rebuild is destructive to existing vectors. Migration order: widen the
schema and the embedder **first**, then re-embed. Rows written during the
mixed-width window are re-embedded by a backfill sweep, because a 384 vector
cannot bind into `FLOAT[768]` and a 768 vector cannot bind into `FLOAT[384]`.

## Migration and fresh start

Schema migration (additive, DuckDB):

- Add `embedding_status`, `turn_uuid`, and the `UNIQUE(session_id, turn_uuid)`
  constraint.
- Add the `(session_id)` and `(project, timestamp DESC)` indexes.
- Create the DuckDB FTS index over `content` with `incremental=true`.
- Populate `searchable_content` for existing rows where it is NULL.

Data reset — **conversation tier only**:

| Table | Action | Reason |
|---|---|---|
| `conversations_v2` | **Delete all 52 rows** | 33 synthetic context markers + 19 migrated `facts` rows. None is dialog; they are noise in the FTS and vector indexes. |
| `conversations` (v1) | **Delete all 19 rows** | Legacy pre-v2 table. |
| `reflections_v2` | Keep all 73 rows | Working distilled memory. |
| `code_graphs` | Keep (701 rows) | Unrelated subsystem. |
| `knowledge_graph.duckdb` | Keep | Separate file, separate subsystem. |
| `crackerjack_integration.db` | **Out of scope** | Co-written by Crackerjack (`crackerjack/cli/handlers/health.py:394,424`) into the same tables Session-Buddy owns. Excluded from the retention sweep and from the delete tool's table set. |

This is a destructive operation on live data. It is stated here so it is
explicitly approved, not inferred.

## Error handling

| Failure | Behavior |
|---|---|
| Malformed JSONL line | Skip that line, log at debug, continue. |
| Unreadable / missing `transcript_path` | Exit 0. The hook never blocks a session. |
| Session-Buddy unreachable | Exit 0, log, retry on the next Stop event. |
| Turn exceeds the 64 KB redaction cap | **Truncate** with `[TRUNCATED]`; count as a partial success. |
| `DatabaseLockedError` on write | Return a retryable error; the hook retries next event. |
| Embedding failure | Leave `embedding` NULL, `embedding_status='pending'`, increment `errors_total`. BM25 still covers the row. |
| Worker crash mid-batch | Pending ids are re-derived at startup from `embedding_status='pending'`. |
| Delete with no scope | Reject — a filter is required. |
| Cold bucket not configured or probe fails | Fall back to deletion; log the fallback. |

## Testing

Unit:

- Transcript parser against fixture JSONL: user turn, assistant turn, assistant
  turn with tool_use, tool_result block, thinking block, `isMeta` record,
  summary record, sidechain record, malformed line.
- Injection guard: tool output containing `Human:` / `Assistant:` /
  `System:` prefixes and `<system|prompt|instruction>` tags is neutralized.
- Idempotency: ingesting the same batch twice leaves one row per turn.
- Turn extraction rules: tool results and tool inputs absent from `content`;
  `tool_names` / `tool_counts` present in metadata.
- Project normalization: `cwd` → normalized short name, matching
  `sb_post_tool.py:_project_name()`.
- FTS: insert and delete are reflected in BM25 results (`incremental=true`).
- Hybrid ranking: an exact-token query ranks the BM25 channel first; a
  paraphrase query ranks the vector channel first; the fused result contains
  both.
- Health feed: with `ingester_running=True` and `cycles_total>=1` and zero
  conversations, the aggregate is **healthy** — not 503.

Integration:

- `ingest_turns` → row present with `embedding IS NULL` and
  `embedding_status='pending'`; worker runs → `embedding IS NOT NULL` and
  `embedding_status='embedded'`.
- Ingest → `search_conversations(mode="hybrid")` returns the turn.
- Delete by each of the four scopes → correct counts, and **no
  `ConstraintException`** from the four FK-referencing tables.
- Deleting a turn that a reflection points at → the reflection survives with
  `conversation_id` NULL.
- Health: after an ingest error, `/health` and the MCP health tool both
  report `degraded` — asserting the **aggregator verdict**, not just the feed
  payload.
- Retention: rows older than the window are deleted; reflections are not.
- Cold-archive path: with a configured bucket, a pruned turn is uploaded to
  Session-Buddy's own prefix and then deleted locally; with no bucket
  configured, it is deleted without an upload.
- Hook smoke test: run the hook script against a fixture transcript and
  assert a row lands in the database.
- **Fleet embedding width agreement.** A test asserts that every component
  resolving its embedder reports the same width — Oneiric's adapter, SB's
  `DEFAULT_EMBEDDING_DIM`, Akosha's `resolve_embedding_dim`, and Mahavishnu's
  `STANDARD_EMBEDDING_DIMENSION` — so a drift between repos fails a test
  rather than an insert.
- **Crackerjack semantic search returns real matches.** With the real
  embedder, a query for a concept matches a chunk that discusses it, and an
  unrelated chunk does not clear `min_similarity=0.7`. The regression is
  pinned by asserting that two semantically unrelated strings score **below**
  0.7 — the exact property the hash pseudo-vectors violated.
- **Crackerjack `file_types` filter matches.** A query with
  `file_types=["py"]` and one with `[".py"]` return the same results.

Marker discipline: use the existing project markers (`unit`, `integration`,
`slow`, …). Per-test timeout ceiling 300 s; anything over 10 s is
`@pytest.mark.slow`.

## Decisions taken by the author

Recorded so they are not mistaken for the operator's positions:

- **Target embedding width: 768** (Matryoshka-shortened `text-embedding-3-small`).
- **Retention window: 90 days.** Long enough that a month-old debugging
  session is still findable; short enough that the store does not grow
  without bound. A setting.
- **Raw turns: `memory_tier = 'short_term'`.**
- **Embedding: text-bearing turns only.** Tool-result turns produce no vector
  and are marked `embedding_status='skipped'`.
- **Embed worker: lifespan-owned asyncio task**, not a separate process.
- **Hook script lives in this repository** (`session_buddy/hooks/`), stdlib-only.
  `enable_hook` / `disable_hook` remain stubs; the settings wiring is
  documented instead.
- **No unfiltered delete.** Every delete requires a scope.
- **Sidechain turns off by default**, behind a setting.
- **Hybrid is opt-in**; `search_conversations` keeps its vector default.
- **Cold archive is capability-gated**, with deletion as the fallback and as
  the default when no bucket is configured.
- **No backwards-compatibility shims.** Session-Buddy is 0.37.1 (pre-1.0):
  replace, do not extend.

## Out of scope (deferred)

- Backfilling existing `~/.claude/projects` transcripts.
- Storing tool result content.
- Repairing the broken Mahavishnu↔Session-Buddy edges:
  - `store_memory` is not a Session-Buddy MCP tool (5 Mahavishnu call sites
    silently fail), and the wired client has no public `call_tool`.
  - `search_conversations` returns a **string**; all 5 Mahavishnu readers
    expect `{"conversations": [...]}`, so nothing crosses today.
  - The Akosha push sends `{content, metadata}`; Akosha requires
    `{memory_id, text, embedding, metadata}`.
  These are real bugs worth fixing, but they are not this work's dependency —
  and fixing them would start raw turns flowing into Mahavishnu's learning
  pipeline, which then needs the partition rule this spec defers.
- Consolidating raw turns into `reflections_v2` via an extraction pipeline.
- Akosha synchronization of raw turns.
- Implementing `enable_hook` / `disable_hook`.
- Reconciling Mahavishnu's parallel raw-capture surfaces (`~/.mahavishnu/jot/log.jsonl`
  captures prompt text; `~/.mahavishnu/pane-snapshots/` captures terminal pane
  content) with this pipeline.
- `crackerjack_integration.db` retention.
- `~/.mahavishnu/outbox.duckdb` — declared dead by Session-Buddy's migration
  010 but still constructed by Mahavishnu; not usable as a WAL here.
- Crackerjack's `skill_invocations.user_query` (a dormant second copy of
  prompt text) — retire or explicitly exclude.
- Crackerjack's semantic index becoming a **shareable** tier. It gains real
  vectors in this work, but stays per-repo SQLite with BLOB vectors — not a
  cross-store join target.
- Crackerjack's XDG namespace and state-path cleanup — filed separately as
  `crackerjack/docs/decisions/2026-11-06-cj-xdg-namespace-and-state-paths.md`.

## Integration contract

- **Triggered from:** Claude Code `Stop` hook (any machine, any harness with
  the hook wired), and direct `ingest_turns` MCP calls from any harness.
- **Returns to / updates:** `conversations_v2` rows; `health` snapshot feed
  `conversations`; `search_conversations` gains an opt-in `mode`; a new
  `delete_conversation` tool; `profiles.py` registrations.
- **Demonstrable by:** ingesting a fixture transcript yields a searchable row;
  `search_conversations(mode="hybrid")` returns it; deleting it removes it
  from both channels; `/health` reports the `conversations` feed.
- **Rollback signal:** the `conversations` feed reports `degraded` while
  ingest errors climb, or the embed backlog grows without draining. Roll
  back by removing the `Stop` hook entry from `settings.local.json`; capture
  stops and the existing store is untouched.
- **Observability added:** `conversations` feed in the canonical health
  snapshot (shared by `/health` and the MCP health tool); per-tool ingest and
  delete counters; embed-worker backlog depth.

## References

- Letta (MemGPT) — memory architecture, recall vs archival, compaction:
  <https://github.com/letta-ai/letta>
- Zep: A Temporal Knowledge Graph Architecture for Agent Memory —
  <https://arxiv.org/html/2501.13956v1>
- Graphiti — episodes and provenance: <https://github.com/getzep/graphiti>
- Mem0 — memory layer and v3 hybrid retrieval: <https://github.com/mem0ai/mem0>
- BM25 vs vector vs hybrid on LoCoMo multi-session agent memory —
  <https://www.reddit.com/r/Rag/comments/1ujwwu6/>
- Claude Code context compaction levers —
  <https://learn-claude-agents.vercel.app/en/s06>
- Internal: `session_buddy/core/conversation_storage.py`,
  `session_buddy/core/session_manager.py`,
  `session_buddy/memory/schema_v2.py`,
  `session_buddy/memory/embedding_dim.py`,
  `session_buddy/ingesters/redaction.py`,
  `session_buddy/adapters/reflection_adapter_oneiric.py`,
  `session_buddy/mcp/tools/conversation/conversation_tools.py`,
  `session_buddy/mcp/auth.py`,
  `session_buddy/mcp/tools/profiles.py`,
  `session_buddy/storage/akosha_sync.py`,
  `session_buddy/storage/cloud_sync.py`
- Decisions:
  `mahavishnu/docs/decisions/2026-11-05-per-component-cold-storage-buckets.md`,
  `mahavishnu/docs/decisions/2026-10-29-learning-pipeline-tools-authz-block.md`,
  `mahavishnu/docs/decisions/mcp-backend-wiring-discipline.md`,
  `mahavishnu/docs/plans/.archive/2026-04-02-storage-consolidation-and-akosha-role.md`
- Plans: `session-buddy/docs/plans/2026-08-05-cross-repo-checkpoint-accounting.md`
  (status `built` — registration, auth, and never-breaks conventions apply),
  `session-buddy/docs/plans/2026-10-29-reflection-delete-tool.md`
  (already shipped — the delete-tool pattern to extend),
  `session-buddy/docs/plans/2026-10-29-openai-embedding-provider-chain.md`
  (complete — the provider chain this work moves behind oneiric),
  `session-buddy/docs/plans/2026-10-29-embedding-dimension-migration.md`
  (shipped — 768 canonical).

## Spec self-review checklist

- [x] Every goal has a component that delivers it
- [x] Every component names the files it touches
- [x] The data model is fully specified (no "TBD" columns)
- [x] Destructive operations are stated explicitly, not implied
- [x] Error paths are enumerated
- [x] Tests are specified per component
- [x] Integration contract present
- [x] Non-goals and out-of-scope are separated
- [x] Author decisions are marked as such, not presented as the operator's positions
- [x] Prior-art citations for every non-obvious design choice
- [x] Live-data claims verified against a snapshot of the actual database
