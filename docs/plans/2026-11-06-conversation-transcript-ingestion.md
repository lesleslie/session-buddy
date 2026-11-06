---
status: draft
role: implementation
date: 2026-11-06
last_reviewed: 2026-11-06
superseded_by: null
blocks_on: []
topic: memory-architecture
---

# Conversation Transcript Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store real session dialog in `conversations_v2` — ingested from Claude Code transcripts on any machine, retrievable by BM25 or vector or both, deletable by four scopes, expired by a retention sweeper, and visible in `/health`.

**Architecture:** A stdlib-only, synchronous hook script reads a Claude Code JSONL transcript, selects new turns by byte offset, and posts one batch to a new `ingest_turns` MCP tool. The tool sanitizes each turn through an injection guard, redacts it against the metadata allowlist, and writes rows with `embedding = NULL` and `embedding_status = 'pending'` — with the adapter's inline embedding suppressed. A lifespan-owned background worker fills the vectors. A DuckDB FTS index over `searchable_content` provides the BM25 channel; the existing vector index provides the other. `search_conversations` gains an opt-in `mode` that fuses the two with Reciprocal Rank Fusion. Deletion, retention, and health each get their own surface.

**Tech Stack:** Python 3.14, DuckDB 2.0 (FTS extension, `FLOAT[768]`), FastMCP via mcp-common, **stdlib-only `urllib.request`** for the hook's JSON-RPC, pytest.

**Spec:** `session-buddy/docs/specs/2026-11-05-conversation-transcript-ingestion-design.md`. The spec travels with this plan; executors read both.

**Sequencing:** This plan is **independent** of `docs/plans/2026-11-06-fleet-embedding-width-768.md`. Its only width dependency, `session_buddy.memory.embedding_dim.DEFAULT_EMBEDDING_DIM`, already exists at 768 and the fleet-width plan does not change it. The operator chose to run the fleet-width plan first as a preference; nothing here waits on it. Task A13 does depend on that plan's Oneiric OpenAI leg — **A13 is the one task that waits**, and it is last so everything else can ship first.

> **Revised after an 8-agent multi-lens review** (3 lenses × 2 plans, then an adversarial adjudicator per plan). 35 findings were confirmed against the source and are folded in here. The ones that changed the design: the DDL splitter is broken **today** and must be fixed before anything else; the delete path extends the shipped `delete_conversation` rather than adding a parallel method; the hook registers four events with a byte-offset cursor instead of a line offset; and `reflections_v2.conversation_id` is missing from the schema DDL entirely, which the splitter bug has been hiding.

## Global Constraints

- **Embedding width: 768.** `session_buddy.memory.embedding_dim.DEFAULT_EMBEDDING_DIM` is already 768 and **does not change**. `FLOAT[768]` columns do not change.
- **The live table is `conversations_v2`.** No rename. The `_v2` suffix is not dropped.
- **Idempotency key: `UNIQUE(session_id, turn_uuid)`** where `turn_uuid` is the source JSONL `uuid`. The primary key is a **UUID7 rendered as 32 lowercase hex characters** (`session_buddy/reflection/storage.py:190-199`). **Never** a content hash — `sha256(content)[:16]` makes two identical-text turns collide.
- **Raw turns are written with `memory_tier = 'short_term'`,** not the `long_term` column default.
- **`source_type = 'claude_code'`, `category = 'claude_turn'`** on every ingested row.
- **The ingest path must not embed synchronously.** `store_conversation` gains an explicit suppression so the raw write never blocks on a network embed. This is what makes Goal 2 real.
- **Oversized turns are truncated, not rejected.** `redact()` truncates to 64 KB (`MAX_REDACTION_BYTES = 65536`) and appends `[TRUNCATED]`. The adapter's `except RedactionSizeError` branch is unreachable because the adapter never passes `raise_on_oversize=True`. The ingest path matches that behavior.
- **Metadata is allowlist-filtered** against `session_buddy.ingesters.redaction.ALLOWED_METADATA_KEYS`. Keys outside the allowlist move into a `_redacted` bucket. `sanitized` and `is_sidechain` are **added to that allowlist** — otherwise the spec's provenance marker is relocated into `_redacted` and the row's provenance is lost.
- **Injection-guard scope (resolved):** role prefixes (`Human:` / `Assistant:` / `System:`) and the three exact tags `<system>`, `<prompt>`, `<instruction>` are stripped from **all stored text**. The store re-adds the true role from the JSONL `message.role`, so stripping a user-supplied prefix is harmless and closes the impersonation vector. `<system-reminder>` and other `<system…>` variants are **not** stripped — only the three exact names.
- **Sidechain (subagent) turns are off by default.** Subagent turns are **not** in the parent transcript; they live in a separate file reached via the `SubagentStop` payload's `agent_transcript_path`. "Off by default" therefore means *not consuming `agent_transcript_path`*. The parser still defensively skips `isSidechain` records, in case another path embeds them.
- **Tool inputs and tool results are never stored.** Tool *names* and *counts* are metadata.
- **No unfiltered delete.** Every `delete_conversation` call requires at least one scope.
- **Raw turns never reach Akosha.** The `sync_to_akosha` push must exclude `source_type = 'claude_code'` rows. `memory_tier = 'short_term'` is **not** a substitute — `memory_tier` is passed through as metadata, not used as a predicate.
- **Hybrid retrieval is opt-in.** `search_conversations` keeps `mode="vector"` as its default; no existing caller's behavior or result shape changes.
- **RRF constant: 60.**
- **The `fts` extension must be loaded explicitly** (`LOAD fts`) on **every** connection that creates, rebuilds, or queries the index. DuckDB does not autoload it for `PRAGMA create_fts_index`.
- **DuckDB FTS call shapes** (re-verified against DuckDB 2.0.0 on 2026-11-06). **One shape, used everywhere:**
  ```sql
  LOAD fts;
  PRAGMA create_fts_index('conversations_v2', 'id', 'searchable_content',
                           incremental=true, tokenizer='regex');
  ```
  - The **first argument is the input table**, the second is the **id column**, and the variadic values name the columns to index. Passing an index name first fails with *"Catalog Error: Table with name turns_fts does not exist!"*.
  - The shadow schema is derived from the **input table** name: input table `conversations_v2` → `fts_main_conversations_v2`, holding `docs`, `terms`, `dict`, `fields`, `stats`, `stopwords`.
  - `incremental=true` is **mandatory** — the default index is a snapshot and misses later inserts. With it, the index tracks **both** inserts and deletes (probe: insert `t3` → BM25 finds `t3`; delete `t2` → BM25 no longer returns `t2`).
  - `tokenizer='regex'` — `strip_accents=true` is rejected with `opensearch_standard`. **Do not** add `stopwords=` or `ignore=`: the earlier draft of this plan specified two different call shapes for the same index, and the built index depended on which section the implementer followed.
  - `match_bm25` is a **scalar macro**, not a table function. Working form:
    ```sql
    SELECT d.name, fts_main_conversations_v2.match_bm25(d."name", ?) AS score
    FROM fts_main_conversations_v2.docs d
    WHERE fts_main_conversations_v2.match_bm25(d."name", ?) IS NOT NULL
    ORDER BY score DESC
    ```
- **Auth is the local `require_auth(optional=False)`** from `session_buddy/mcp/auth.py:91`, which verifies the JWT with `expected_audience="session-buddy"` and **injects** `user_id` as a **keyword argument** into the wrapped function. Every tool that calls it **must declare a `user_id` parameter** or the call raises `TypeError`. Do **not** use `mcp_common.auth.require_mcp_auth`.
- **MCP tools return `ToolMessages` strings,** not raw dicts — `session_buddy/utils/messages.py` provides `operation_failed`, `success`, `validation_error`, `empty_results`, `not_available`. Follow the shipped `delete_reflection` tool's pattern.
- **The MCP tools resolve the adapter with `await require_reflection_database()`** (`session_buddy/utils/database_tools.py:26`), which returns a `ReflectionDatabaseAdapter`. Do **not** use `ReflectionDatabase` from `session_buddy/reflection/database.py` — it does not accept `mode=`, `source_type=`, or `turn_uuid=`, and every call would raise `TypeError`.
- **There are two registration points, not four.** `REGISTRATION_MAP["register_ingest_tools"] = register_ingest_tools` and `STANDARD_REGISTRATIONS.append("register_ingest_tools")`; `PROFILE_REGISTRATIONS[ToolProfile.STANDARD]` derives from `STANDARD_REGISTRATIONS` automatically. **Key both by the `register_*` function name, not the tool name** — the drift test requires `register_*` names. `_ALL_REGISTERS` **no longer exists** (removed in commit `c28124e8`); do not add it.
- **The health feed's eight fields are fixed** by `mcp_common.health.feed.HealthFeedState`. There is no `pending_embeddings` field; the embed backlog is folded into `errors_total` + `last_error_at`.
- **An empty-but-live feed is `warming_up`, not `healthy`.** mcp-common's `is_healthy` returns `WARMING_UP` with `healthy=False` for `entities_count == 0` + `ingester_running=True` + `cycles_total >= 1`. `WARMING_UP` maps to **HTTP 200**, so the service is not reported as down — but `data_feeds_ok` must treat it as acceptable rather than failing on `healthy`.
- **Pre-1.0 replace, do not extend.** Session-Buddy is 0.38.0.
- **Python 3.14.** `from __future__ import annotations` is the first non-comment line of every source file.
- **Never bump a Bodai `pyproject.toml` version.**
- **Commit only your own changes:** `git add <path>` then `git commit --only <paths> -F <msgfile>`.
- **Commit messages carry no `Co-Authored-By:` trailer.** `Author:` email is `les@wedgwoodwebworks.com`.

### Per-repo lint and test gates

| Repo | ruff select | max-complexity | max-args | pytest timeout | `--cov-fail-under` |
|---|---|---|---|---|---|
| oneiric | `C901, F, I, UP` | 15 | — | — | 78.75 |
| **session-buddy** | **`BLE001`, `C901, F, I, UP`** | 15 | — (no `P`) | 600 s | 2.45 |
| akosha | `E, W, F, I, B, C4, UP, ARG, SIM, TCH, PTH, ERA, RUF` (E501 ignored) | — | — | — | 89.0 |
| mahavishnu | `I, N, UP, B, C4, SIM, TCH, ASYNC221/230, BLE001, DTZ001, …` + `P` | 15 | **10** | 300 s | 89.0 |
| crackerjack | `C901, F, I, UP` | **25** | — | — | 68.4 |

- **`BLE001` is selected in session-buddy** — a blind `except Exception` needs `# noqa: BLE001` plus a justification comment. `BLE001` is **not** selected in oneiric, akosha, or crackerjack.
- **Session-Buddy does not enforce `max-args`** (no `P` subset), but the fleet house limit is 10. `store_conversation` is bundled with a dataclass to stay at 10 anyway — 12 positional parameters is poor design even when the linter allows it.
- **`--cov-fail-under` is set in every repo's pytest `addopts`,** so a subset run always ends in a coverage-gate failure. **Every per-task pytest command in this plan uses `--no-cov`,** and its pass criterion is "N passed", not a zero exit code. The full suite is the coverage gate.
- **Markers are per-repo.** Use only markers registered in session-buddy's `pyproject.toml` `[tool.pytest.ini_options] markers` list.

### Claude Code hook semantics (verified live, 2026-11-06)

These are load-bearing for A10 and were established by running `claude -p` against the installed CLI, not inferred:

- **`Stop` fires in print mode**, with a populated `transcript_path`. `claude -p` is not a special case for hook events.
- **`Stop` fires more than once per invocation** — once per main-agent turn, and it can fire mid-turn while background tasks are still running. `prompt_id` changes per turn; `session_id` does not.
- **`StopFailure` fires instead of `Stop`** when a turn ends in an API error (rate limit, overload, auth). Without a `StopFailure` registration, every rate-limited turn is silently dropped.
- **`SessionEnd` fires once at process exit**, with `reason: "other"` in print mode. **On SIGTERM it is the only hook that runs** — no `Stop`, no `StopFailure`. Its default timeout is **1.5 s** (cap 60 s).
- **`SubagentStop` carries `agent_transcript_path`** — the subagent's own transcript. The parent transcript does **not** contain the subagent's turns; its `tool_result` for the `Agent` call holds only a pointer.
- **`--bare` disables hooks entirely**, and the docs say bare "will become the default for `-p` in a future release".
- **Async hooks (`"async": true`) are killed at `-p` teardown.** The hook must be **synchronous**.
- **The transcript lags** the in-memory conversation. The current turn's text comes from `last_assistant_message`, not the transcript's tail.
- **`--no-session-persistence` yields a `transcript_path` to a file that does not exist.**
- **The transcript JSONL format is explicitly documented as unstable.** Parse defensively; skip unknown record types.

## Review Focus

1. **A transcript line that is not valid JSON** — Claude Code writes a partial line when a session is killed mid-write. Expected: that line is skipped, every other line still ingests, and the skip is counted and logged at debug.
2. **A tool result whose text embeds `Human:` or `<system>`** — an injection attempt arriving through fetched web content. Expected: the prefixes and tags are stripped, and the turn carries `metadata["sanitized"] = true`.
3. **The same transcript ingested twice** — `Stop` fires per turn and `SessionEnd` fires at exit, so the same turns are offered repeatedly. Expected: one row per turn, no duplicates, no error, and the second call reports the turns as duplicates.
4. **A turn whose text exceeds 64 KB** — a pasted file, a huge tool summary. Expected: truncated with `[TRUNCATED]`, the row still lands, and the truncation is counted as a partial success.
5. **A `delete_conversation` that removes a turn a reflection points at.** Expected: the reflection survives with `conversation_id` NULL, no `ConstraintException` from any FK-referencing table, and the delete reports per-scope counts.

---

### Task A1: Repair the schema DDL splitter, and add the conversation-turn columns

**Files:**
- Modify: `session_buddy/memory/schema_v2.py` — the `reflections_v2` DDL, the `conversations_v2` DDL, the index block
- Modify: `session_buddy/adapters/reflection_adapter_oneiric.py` — `_create_v2_schema`'s statement splitter
- Create: `session_buddy/memory/fts_index.py` — the FTS index lifecycle
- Test: `tests/unit/test_schema_v2_conversation_turns.py` (create)
- Test: `tests/unit/test_schema_v2_ddl_splitter.py` (create)
- Test: `tests/unit/test_fts_index.py` (create)

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `session_buddy.memory.fts_index.ensure_fts_index(conn: duckdb.DuckDBPyConnection) -> None` — loads the extension and creates the incremental index if absent.
  - `session_buddy.memory.fts_index.rebuild_fts_index(conn: duckdb.DuckDBPyConnection) -> None`
  - `session_buddy.memory.fts_index.bm25_search(conn: duckdb.DuckDBPyConnection, query: str, limit: int, project: str | None = None) -> list[tuple[str, float]]` — returns `(id, score)` pairs.

**This task fixes a live bug before it adds anything.** `reflection_adapter_oneiric.py:1054` splits the schema with `schema_v2_sql(self.embedding_dim).split(";")` — a naive split that does not understand SQL comments. Two comments in `schema_v2.py` contain a semicolon:

- `schema_v2.py:116` — `-- v2 rewire missed this on initial rewire; legacy reflections has it.`
- `schema_v2.py:196` — `-- existing rows remain valid; the backfill script`

The first one truncates the `CREATE TABLE IF NOT EXISTS reflections_v2` statement before its closing paren, so **on a fresh database `reflections_v2` is never created** — and then every `ALTER TABLE reflections_v2` and both of its indexes fail too. Reproduced on 2026-11-06: 12 statements fail, and a fresh database ends up with `['causal_links', 'conversations_v2', 'cross_repo_work_v2', 'distilled_skills', 'memory_access_log', 'memory_entities', 'memory_promotions', 'memory_provenance', 'memory_relationships', 'session_windows', 'user_models']` — **no `reflections_v2`**. Each failure is caught by `except duckdb.Error` and logged at **DEBUG**, so it is invisible.

The live database has `reflections_v2` (73 rows, 21 columns) only because it was created by an **older schema version** before those comments were added, and `CREATE TABLE IF NOT EXISTS` no-ops on the existing table.

**A second defect hides behind the first.** `reflections_v2.conversation_id` **is not in `schema_v2.py` at all** — the only `conversation_id` occurrences in that file belong to `cross_repo_work_v2`. Yet the live table has the column **and** a foreign key to `conversations_v2(id)`. The live table carries it from the older schema; the current DDL would create the table without it. So once the splitter is fixed, a fresh database gets a `reflections_v2` with **no `conversation_id` column** — and the spec's delete semantics ("set `reflections_v2.conversation_id` to NULL") would fail there.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_schema_v2_ddl_splitter.py`:

```python
def test_every_statement_in_the_schema_executes_on_a_fresh_database() -> None:
    """No statement in schema_v2_sql() may fail on a fresh DuckDB."""
    con = duckdb.connect(":memory:")
    for stmt in split_schema_statements(schema_v2_sql(768)):
        con.execute(stmt)   # must not raise
    assert "reflections_v2" in created_tables(con)

def test_no_semicolon_appears_inside_a_sql_comment() -> None:
    """A ';' inside a '--' comment truncates the naive splitter."""
    for i, line in enumerate(schema_v2_sql(768).splitlines(), 1):
        if "--" in line and ";" in line[line.index("--"):]:
            pytest.fail(f"semicolon inside a SQL comment at schema_v2.py line {i}")

def test_reflections_v2_declares_conversation_id() -> None:
    """The DDL the live table relies on must exist in the DDL."""
    assert "conversation_id" in reflections_v2_ddl()
```

Create `tests/unit/test_schema_v2_conversation_turns.py`:

```python
def test_conversations_v2_has_embedding_status_and_turn_uuid() -> None:
    """The DDL declares embedding_status and turn_uuid."""
    sql = schema_v2_sql()
    assert "embedding_status TEXT DEFAULT 'pending'" in sql
    assert "turn_uuid TEXT" in sql

def test_unique_index_on_session_and_turn_uuid() -> None:
    """The idempotency key is declared as a unique index."""
    sql = schema_v2_sql()
    assert "idx_conversations_session_turn" in sql
    assert "UNIQUE INDEX" in sql

def test_new_indexes_are_declared() -> None:
    """The (session_id) and (project, timestamp DESC) indexes exist."""
    sql = schema_v2_sql()
    assert "idx_conversations_session_id" in sql
    assert "idx_conversations_project_timestamp" in sql
```

Create `tests/unit/test_fts_index.py`:

```python
def test_bm25_finds_an_inserted_turn(tmp_path: Path) -> None: ...
def test_bm25_drops_a_deleted_turn(tmp_path: Path) -> None: ...
def test_bm25_returns_no_match_for_a_missing_token(tmp_path: Path) -> None: ...
```

Each FTS test creates a DuckDB file with the `conversations_v2` schema, calls `ensure_fts_index`, inserts rows, and asserts through `bm25_search`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_schema_v2_ddl_splitter.py tests/unit/test_schema_v2_conversation_turns.py tests/unit/test_fts_index.py --no-cov -v`
Expected: FAIL — `reflections_v2` is missing from the fresh database, `ModuleNotFoundError` for `fts_index`.

- [ ] **Step 3: Make the splitter understand comments**

In `reflection_adapter_oneiric.py`, replace the naive split with a helper that strips `--` line comments before splitting, or use `duckdb.extract_statements`. Prefer `duckdb.extract_statements` if the installed DuckDB exposes it; otherwise strip `--` comments with a regex that respects string literals.

Put the helper in `session_buddy/memory/schema_v2.py` as `split_schema_statements(sql: str) -> list[str]` so both the adapter and the tests use one implementation. Change `_create_v2_schema` to call it.

Keep the existing per-statement `try/except duckdb.Error` and `logger.debug`, but **raise the log level to WARNING** for a schema statement failure — a swallowed schema error is how this bug survived unnoticed.

- [ ] **Step 4: Remove the semicolons from the SQL comments**

In `schema_v2.py`, rewrite the two offending comments so no `;` appears inside them:

- `schema_v2.py:116` → `-- v2 rewire missed this on initial rewire - legacy reflections has it.`
- `schema_v2.py:196` → `-- existing rows remain valid - the backfill script`

**No semicolon may appear inside any SQL comment in `schema_v2.py`** — including the ones this task adds. The test in Step 1 pins it.

- [ ] **Step 5: Add `conversation_id` to the `reflections_v2` DDL**

Add to the `CREATE TABLE IF NOT EXISTS reflections_v2` block:

```sql
conversation_id TEXT,  -- FK -> conversations_v2(id); NULL when the parent is deleted
```

and add the matching idempotent guard in the ALTER block:

```sql
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS conversation_id TEXT;
```

DuckDB cannot `ALTER TABLE ... ADD CONSTRAINT`, so **existing databases get the column without the foreign key**; only fresh databases get the FK. Therefore the delete path (A4) must null the column **explicitly** and must never rely on the FK to raise — see A4.

- [ ] **Step 6: Extend the `conversations_v2` DDL**

- Add to the `CREATE TABLE IF NOT EXISTS conversations_v2` block:
  ```sql
  embedding_status TEXT DEFAULT 'pending',  -- pending | embedded | skipped
  turn_uuid TEXT,  -- source JSONL uuid - idempotency key with session_id
  ```
  **No semicolon in either comment.**
- Because `CREATE TABLE IF NOT EXISTS` does not add columns to an existing table, add the matching idempotent guards in the ALTER block:
  ```sql
  ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS embedding_status TEXT DEFAULT 'pending';
  ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS turn_uuid TEXT;
  ```
- **The idempotency key is a unique INDEX, not a table constraint.** DuckDB does not support `ALTER TABLE ... ADD CONSTRAINT`, so a table-level `UNIQUE` would only exist on freshly created tables — and adding both would create two redundant indexes on every new database. Use only:
  ```sql
  CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_session_turn
      ON conversations_v2(session_id, turn_uuid);
  ```
  **Verified against DuckDB 2.0.0** (probe, 2026-11-06):
  - `ON CONFLICT (session_id, turn_uuid) DO UPDATE` works against a unique **index** — it does not require a table constraint.
  - A duplicate non-NULL `(session_id, turn_uuid)` is rejected with *"Duplicate key session_id: s1, turn_uuid: u1"*.
  - **NULLs are distinct** under a unique index: the 52 existing rows all have `session_id = NULL`, and they coexist without a uniqueness violation. No partial/expression index is needed.
- Add the two new indexes:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations_v2(session_id);
  CREATE INDEX IF NOT EXISTS idx_conversations_project_timestamp
      ON conversations_v2(project, timestamp DESC);
  ```
- **Leave `idx_conversations_fts` in place.** It is a btree on a TEXT column and is harmless; the DuckDB FTS index lives in a separate `fts_main_*` schema and does not replace it. Note in a comment that it is a whole-string-match accelerator, not a tokenizer.

- [ ] **Step 7: Backfill `searchable_content` for existing rows**

The spec's migration step *"Populate `searchable_content` for existing rows where it is NULL"* had no task. Add it to the schema step, idempotently:

```sql
UPDATE conversations_v2 SET searchable_content = content WHERE searchable_content IS NULL;
```

Add a test asserting no row has a NULL `searchable_content` after the migration.

- [ ] **Step 8: Implement the FTS index lifecycle**

Create `session_buddy/memory/fts_index.py`:

- `ensure_fts_index(conn)`: `LOAD fts;` then, if `information_schema.schemata` has no `fts_main_conversations_v2` schema, run the **single canonical** `PRAGMA create_fts_index` call quoted verbatim in Global Constraints.
- `rebuild_fts_index(conn)`: drop the `fts_main_conversations_v2` schema (`DROP SCHEMA IF EXISTS fts_main_conversations_v2 CASCADE`) and call `ensure_fts_index`.
- `bm25_search(conn, query, limit, project=None)`: run the scalar-macro join shown in Global Constraints against `fts_main_conversations_v2.docs`, joining back to `conversations_v2` on `d.name = c.id` when `project` is given so the filter applies. On a missing FTS schema, **log at ERROR** and return `[]` — a missing index must not break search, but it must be visible.

**Escaping the query.** `match_bm25`'s second argument is a query string. Pass it as a **bound parameter** (`?`), never string-interpolated, so a query containing FTS syntax cannot break the statement.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_schema_v2_ddl_splitter.py tests/unit/test_schema_v2_conversation_turns.py tests/unit/test_fts_index.py --no-cov -v`
Expected: PASS — including the fresh-database test, which now sees `reflections_v2`.

- [ ] **Step 10: Run the wider schema suite**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/ -k "schema or fts or reflection_adapter" --no-cov -v`
Expected: PASS — no existing test depended on the old DDL shape.

- [ ] **Step 11: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/memory/schema_v2.py session_buddy/memory/fts_index.py session_buddy/adapters/reflection_adapter_oneiric.py tests/unit/test_schema_v2_ddl_splitter.py tests/unit/test_schema_v2_conversation_turns.py tests/unit/test_fts_index.py
git commit --only <the same paths> -F /tmp/sb-conversation-schema.txt
```

Commit message subject: `fix(schema): repair the DDL splitter and add the conversation-turn columns`

---

### Task A2: Transcript parser

**Files:**
- Create: `session_buddy/ingesters/transcript_ingester.py`
- Create: `tests/fixtures/transcripts/` — fixture JSONL files
- Test: `tests/unit/test_transcript_ingester.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `session_buddy.ingesters.transcript_ingester.TurnRecord` — a frozen dataclass with fields `uuid: str`, `parent_uuid: str | None`, `session_id: str`, `timestamp: str | None`, `role: str`, `text: str`, `thinking: str`, `tool_names: list[str]`, `tool_counts: dict[str, int]`, `model: str | None`, `token_usage: dict[str, int]`, `is_sidechain: bool`.
  - `session_buddy.ingesters.transcript_ingester.parse_transcript(lines: Sequence[str], *, include_sidechain: bool = False) -> tuple[list[TurnRecord], int]` — returns the parsed turns and the number of skipped lines.
  - `TurnRecord.content -> str` — role-prefixed text blocks.
  - `TurnRecord.searchable_content -> str` — text + thinking blocks, capped at 32,000 characters.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_transcript_ingester.py` with fixture JSONL under `tests/fixtures/transcripts/`:

- `basic.jsonl` — a user turn, an assistant text turn, an assistant turn with a `tool_use` block, a `tool_result` block, a thinking block, an `isMeta` record, a `type="summary"` record, a sidechain record, and one malformed line.

```python
def test_parses_conversational_turns() -> None: ...
def test_skips_is_meta_and_summary_records() -> None: ...
def test_skips_malformed_lines_and_counts_them() -> None: ...
def test_sidechain_turns_are_skipped_by_default() -> None: ...
def test_sidechain_turns_are_included_when_requested() -> None: ...
def test_tool_results_and_inputs_are_not_in_content() -> None: ...
def test_tool_names_and_counts_are_in_metadata() -> None: ...
def test_thinking_is_in_searchable_content_but_not_content() -> None: ...
def test_unknown_record_types_are_skipped_not_fatal() -> None:
    """The transcript format is documented as unstable - unknown types are skipped."""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_transcript_ingester.py --no-cov -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the parser**

Create `session_buddy/ingesters/transcript_ingester.py`:

- **Pure function over text.** No I/O, no database, no network. **Stdlib only** — A10's hook loads this module by file path, so it must not pull in a third-party dependency.
- `parse_transcript(lines, *, include_sidechain=False)` iterates lines, and for each line:
  - `json.loads` it; on `json.JSONDecodeError` increment the skipped counter and continue.
  - Skip records where `record.get("isMeta")` is truthy, or `record.get("type") == "summary"`.
  - Skip records whose `message` is absent or whose `message.role` is not `"user"` or `"assistant"`.
  - Skip records whose `isSidechain` is truthy unless `include_sidechain` is `True` (in which case set `is_sidechain=True` on the record). **Subagent turns are normally not in this file at all** — they live under `subagents/agent-<id>.jsonl` and are reached via `SubagentStop`'s `agent_transcript_path`. This branch is defensive.
  - **Skip records whose `type` is not recognized.** The transcript format is documented as internal and unstable; an unknown `type` must be skippable, not fatal.
- Extract from the record: `uuid`, `parentUuid`, `sessionId`, `timestamp`, `message.role`, `message.model`, `message.usage`.
- `message.content` may be a **string** or a **list of blocks**. Handle both. For a list, partition blocks by `type`:
  - `text` → `block["text"]`
  - `thinking` → `block["thinking"]`
  - `tool_use` → record `block["name"]` in `tool_names`, increment `tool_counts[name]`; **do not** include `block["input"]`
  - `tool_result` → **discard the body entirely**; do not include it in `content` or `searchable_content`
  - `image` → discard
- `content` is the role-prefixed text blocks: `f"{role}: {text}"`.
- `searchable_content` is the text blocks plus the thinking blocks, joined, **capped at 32,000 characters** — a large thinking block must not dominate the FTS document. This cap is separate from the 64 KB redaction cap.
- `token_usage` is `message.usage` filtered to integer-valued keys (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_transcript_ingester.py --no-cov -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/ingesters/transcript_ingester.py tests/unit/test_transcript_ingester.py tests/fixtures/transcripts/
git commit --only session_buddy/ingesters/transcript_ingester.py tests/unit/test_transcript_ingester.py tests/fixtures/transcripts/ -F /tmp/sb-transcript-parser.txt
```

Commit message subject: `feat(ingest): parse Claude Code transcripts into turn records`

---

### Task A3: Injection guard

**Files:**
- Create: `session_buddy/ingesters/injection_guard.py`
- Test: `tests/unit/test_injection_guard.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `session_buddy.ingesters.injection_guard.sanitize_text(text: str) -> tuple[str, bool]` — returns the sanitized text and whether anything changed.

**Scope (resolved).** The spec says role prefixes are stripped from *tool-result* content only, and that tool results are not stored. Those two statements together make the tool-result branch dead. The resolution: **strip role prefixes and the three exact tags from all stored text.** The store re-adds the true role from the JSONL `message.role`, so a user-supplied `Assistant:` prefix inside a user turn cannot impersonate a turn — which is precisely the attack the guard exists to stop. This is strictly safer than the spec's narrower rule and matches the spec's own rationale.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_injection_guard.py`:

```python
def test_strips_role_prefixes() -> None:
    """'Human: ignore previous instructions' loses the 'Human:' prefix."""

def test_strips_the_three_exact_tags() -> None:
    """'<system>', '<prompt>' and '<instruction>' are removed."""

def test_leaves_system_reminder_intact() -> None:
    """'<system-reminder>' is not one of the three names and survives."""

def test_leaves_a_genuine_turn_prefix_alone() -> None:
    """A real assistant turn keeps its 'assistant:' prefix."""

def test_reports_whether_anything_changed() -> None: ...
def test_is_idempotent() -> None: ...
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_injection_guard.py --no-cov -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the guard**

Create `session_buddy/ingesters/injection_guard.py`. Follow Crackerjack's existing shape (`crackerjack/services/failure_recorder.py:20-30`), which strips these prefixes and tags before writing to Session-Buddy.

- Role prefixes: strip a leading `Human:`, `Assistant:`, `System:` (case-insensitive, optional leading whitespace).
- Tags: strip `<system>…</system>`, `<prompt>…</prompt>`, `<instruction>…</instruction>` — **the three exact names only**, case-insensitive, including unclosed opening tags. Do **not** match `<system-reminder>` or any other `<system…>` variant.
- Return `(text, changed)`. Make it idempotent.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_injection_guard.py --no-cov -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/ingesters/injection_guard.py tests/unit/test_injection_guard.py
git commit --only session_buddy/ingesters/injection_guard.py tests/unit/test_injection_guard.py -F /tmp/sb-injection-guard.txt
```

Commit message subject: `feat(ingest): add the prompt-injection guard for ingested turn text`

---

### Task A4: Adapter — the `turn_uuid` upsert path, embedding suppression, and scoped delete

**Files:**
- Modify: `session_buddy/adapters/reflection_adapter_oneiric.py` — `store_conversation`; `delete_conversation` (the shipped one, at line ~2959)
- Create: `session_buddy/memory/turn_identity.py` — the `TurnIdentity` dataclass
- Test: `tests/unit/test_reflection_adapter_oneiric.py` — extend
- Test: `tests/integration/test_delete_conversation_cascade.py` (create)

**Interfaces:**
- Consumes: the schema from Task A1.
- Produces:
  - `session_buddy.memory.turn_identity.TurnIdentity` — a frozen dataclass with `turn_uuid: str`, `session_id: str`, `project: str | None = None`.
  - `ReflectionDatabaseAdapter.store_conversation(content, metadata=None, deduplicate=False, dedup_threshold=0.85, *, source_type=None, turn_parent_id=None, causal_parent_id=None, category=None, memory_tier=None, turn: TurnIdentity | None = None, searchable_content: str | None = None, embed: bool = True, user_id: str | None = None) -> str` — ten parameters, at the fleet house limit. The three new identity fields are bundled into `turn` rather than added individually.
  - `ReflectionDatabaseAdapter.delete_conversations(*, conversation_id=None, session_id=None, project=None, before=None, after=None) -> dict[str, int]` — the scoped variant.

**Extend the shipped delete, do not duplicate it.** `reflection_adapter_oneiric.py:2959` already implements `delete_conversation(memory_id) -> int` with a correct **six-step** cascade, in this order: `memory_access_log` → `memory_provenance` → `memory_relationships` → `memory_entities` → `memory_promotions` → `conversations_v2`. The relationships-before-entities ordering is **load-bearing**: `memory_relationships.from_entity_id` and `.to_entity_id` are foreign keys to `memory_entities(id)`, so deleting entities first raises `ConstraintException`.

`delete_conversations` therefore **extends** that method with scoped/batch semantics and reuses its cascade. It must add one step the shipped method lacks: **`UPDATE reflections_v2 SET conversation_id = NULL WHERE conversation_id IN (…)`** — `reflections_v2.conversation_id` carries a foreign key to `conversations_v2(id)` in the live database, so deleting a referenced turn raises `ConstraintException` unless the reflection is nulled first. Reflections are never pruned; the reflection survives with its link broken.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_reflection_adapter_oneiric.py`, add:

```python
async def test_store_conversation_uses_turn_uuid_as_the_idempotency_key() -> None: ...
async def test_store_conversation_does_not_collide_on_identical_text() -> None: ...
async def test_store_conversation_writes_embedding_status_pending() -> None: ...
async def test_store_conversation_with_embed_false_leaves_embedding_null() -> None:
    """The ingest path must not embed synchronously."""
async def test_store_conversation_threads_searchable_content() -> None:
    """The FTS projection is the caller's, not a copy of content."""
async def test_store_conversation_records_the_authenticated_user_id() -> None:
    """The row's user_id comes from the token, not from a default."""
```

Create `tests/integration/test_delete_conversation_cascade.py`:

```python
async def test_delete_by_conversation_id_removes_one_row() -> None: ...
async def test_delete_by_session_id_removes_all_its_turns() -> None: ...
async def test_delete_by_project_removes_only_that_project() -> None: ...
async def test_delete_by_date_range_removes_only_matching_rows() -> None: ...
async def test_delete_cascades_relationships_before_entities() -> None:
    """Deleting a turn with an extracted entity and a relationship must not raise."""
async def test_delete_cascades_entities_promotions_access_log_and_provenance() -> None: ...
async def test_delete_nulls_reflection_conversation_id_and_keeps_the_reflection() -> None: ...
async def test_delete_cascades_turn_children() -> None: ...
async def test_delete_with_no_scope_is_rejected() -> None: ...
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/integration/test_delete_conversation_cascade.py --no-cov -v`
Expected: FAIL — `TypeError: delete_conversations() got an unexpected keyword argument 'conversation_id'`.

- [ ] **Step 3: Create `TurnIdentity` and extend `store_conversation`**

Create `session_buddy/memory/turn_identity.py` with the frozen dataclass. In `reflection_adapter_oneiric.py`:

- Add the four keyword-only parameters to `store_conversation`: `turn`, `searchable_content`, `embed`, `user_id`.
- When `turn` is supplied (and `turn.session_id` and `turn.turn_uuid` are both set), use a UUID7 hex as the row `id` and write with an upsert on the `(session_id, turn_uuid)` unique key:
  ```sql
  INSERT INTO conversations_v2 (...) VALUES (...)
  ON CONFLICT (session_id, turn_uuid) DO UPDATE SET
      content = EXCLUDED.content,
      searchable_content = EXCLUDED.searchable_content,
      metadata = EXCLUDED.metadata,
      timestamp = EXCLUDED.timestamp
  ```
  **Do not** set `embedding` in the update clause — a re-ingest of an already-embedded turn must not clear its vector. **Do not** overwrite `embedding_status` on an update.
- When `turn` is `None`, preserve the current `sha256(content)[:16]` behavior exactly, so every existing caller is unaffected.
- Write `embedding_status = 'pending'` when the row is newly inserted and no embedding is supplied.
- `searchable_content`: when supplied, bind it into the `searchable_content` column instead of the redacted content. When omitted, keep today's copy-of-content behavior for every existing caller.
- `embed: bool = True` — when `False`, **skip the inline embedding entirely** and leave `embedding` NULL. This is what makes the ingest path independent of embedder latency.
- `user_id: str | None = None` — write the supplied value, falling back to `"default"`. The adapter hardcodes `"default"` today, so the token identity could never reach the row.
- Accept and write `project` from `turn.project`.

- [ ] **Step 4: Extend the shipped delete with scoped semantics**

In `reflection_adapter_oneiric.py`:

- Add `delete_conversations(*, conversation_id=None, session_id=None, project=None, before=None, after=None) -> dict[str, int]`.
- Require at least one scope; raise `ValueError` naming the accepted scopes when none is given.
- Build the `WHERE` clause from the supplied scopes, ANDing them.
- Resolve the target row ids first, then **expand the set to include descendants**: repeatedly select rows whose `turn_parent_id` is in the set, until no new ids appear.
- Reuse the shipped cascade's ordering, and add the reflections nulling:
  1. `DELETE FROM memory_access_log WHERE memory_id IN (…)`
  2. `DELETE FROM memory_provenance WHERE memory_id IN (…)`
  3. look up the entity ids for the target set → `DELETE FROM memory_relationships WHERE from_entity_id IN (…) OR to_entity_id IN (…)`
  4. `DELETE FROM memory_entities WHERE memory_id IN (…)`
  5. `DELETE FROM memory_promotions WHERE memory_id IN (…)`
  6. `UPDATE reflections_v2 SET conversation_id = NULL WHERE conversation_id IN (…)`
  7. `DELETE FROM conversations_v2 WHERE id IN (…)`
- Return the per-table counts.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/integration/test_delete_conversation_cascade.py tests/unit/test_reflection_adapter_oneiric.py --no-cov -v`
Expected: PASS — including the pre-existing adapter tests, which must not regress.

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/memory/turn_identity.py session_buddy/adapters/reflection_adapter_oneiric.py tests/unit/test_reflection_adapter_oneiric.py tests/integration/test_delete_conversation_cascade.py
git commit --only <the same paths> -F /tmp/sb-conversation-adapter.txt
```

Commit message subject: `feat(storage): add the turn_uuid upsert path and the scoped conversation delete`

---

### Task A5: `ingest_turns` tool, the project-name helper, and the registration

**Files:**
- Create: `session_buddy/core/project_name.py`
- Create: `session_buddy/mcp/tools/conversation/ingest_tools.py`
- Modify: `session_buddy/mcp/tools/__init__.py` — export `register_ingest_tools`
- Modify: `session_buddy/mcp/tools/conversation/__init__.py` — export `register_ingest_tools`
- Modify: `session_buddy/mcp/tools/profiles.py` — `REGISTRATION_MAP` and `STANDARD_REGISTRATIONS`
- Modify: `session_buddy/ingesters/redaction.py` — add `sanitized` and `is_sidechain` to `ALLOWED_METADATA_KEYS`
- Test: `tests/unit/test_project_name.py` (create)
- Test: `tests/integration/test_ingest_turns_tool.py` (create)

**Interfaces:**
- Consumes: `TurnRecord` (A2), `sanitize_text` (A3), `store_conversation` (A4), `require_reflection_database` (`session_buddy/utils/database_tools.py:26`), `ALLOWED_METADATA_KEYS` / `redact` / `redact_metadata`.
- Produces:
  - `session_buddy.core.project_name.normalize_project_name(path: str) -> str` — **idempotent**. If the input contains no path separator, return it unchanged. Otherwise scan for `Projects` / `src` / `repos` / `code` / `workspace` in the path parts and return the following part; else return the parent directory's name. This matches `~/.claude/scripts/sb_post_tool.py:_project_name()`, except that helper returns `""` for an already-normalized bare name, which would make `delete_conversation(project="mahavishnu")` delete nothing while the full-path form deleted the right rows.
  - `session_buddy.mcp.tools.conversation.ingest_tools.register_ingest_tools(mcp_server: FastMCP) -> None`
  - `session_buddy.mcp.tools.conversation.ingest_tools.ingest_turns(turns: list[dict], project: str | None = None, include_sidechain: bool = False, token: str | None = None, user_id: str | None = None) -> str` — returns a `ToolMessages` string. `user_id` is **populated by the auth decorator**, not by the caller.
  - `session_buddy.ingesters.redaction.ALLOWED_METADATA_KEYS` gains `"sanitized"` and `"is_sidechain"`.

**Metadata construction (explicit).** The tool populates exactly these keys, all of which must be in the allowlist:

| Key | Value |
|---|---|
| `source_session` | the transcript's session id |
| `parent_uuid_chain` | `[turn.parent_uuid]` (or `[]`) |
| `tool_names` | the turn's tool names |
| `tool_counts` | the turn's tool counts |
| `model` | the turn's model |
| `token_usage` | the turn's token usage |
| `extracted_at` | the ISO-8601 ingestion timestamp |
| `sanitized` | `True` when the guard changed the text |
| `is_sidechain` | `True` for a sidechain turn |

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_project_name.py`:

```python
def test_normalizes_a_projects_path() -> None: ...
def test_normalizes_a_src_path() -> None: ...
def test_normalizes_a_repos_path() -> None: ...
def test_falls_back_to_the_parent_directory_name() -> None: ...
def test_is_idempotent_for_a_bare_name() -> None:
    """normalize_project_name("mahavishnu") == "mahavishnu"."""
def test_matches_the_hook_helper() -> None:
    """For a full path, the result equals sb_post_tool.py:_project_name()."""
```

Create `tests/integration/test_ingest_turns_tool.py`:

```python
async def test_ingest_writes_a_pending_row() -> None:
    """A row lands with embedding NULL and embedding_status 'pending'."""

async def test_ingest_does_not_embed_synchronously() -> None:
    """No embedding call happens on the write path."""

async def test_ingest_is_idempotent() -> None:
    """The same batch twice leaves one row per turn, and the second reports duplicates."""

async def test_ingest_truncates_oversized_turns() -> None: ...
async def test_ingest_sanitizes_tool_result_text() -> None: ...
async def test_ingest_records_the_sanitized_flag_in_the_allowlisted_metadata() -> None:
    """The provenance marker is at row['metadata']['sanitized'], not in _redacted."""

async def test_ingest_drops_non_allowlisted_metadata() -> None: ...
async def test_ingest_writes_the_metadata_mapping() -> None:
    """source_session, parent_uuid_chain, tool_names, tool_counts, model,
    token_usage and extracted_at are all present."""

async def test_ingest_writes_the_turn_parent_id() -> None:
    """parentUuid resolves to the parent's row id."""

async def test_ingest_records_the_authenticated_user_id() -> None: ...
async def test_ingest_returns_a_retryable_envelope_on_a_locked_database() -> None: ...
async def test_ingest_skips_sidechains_by_default() -> None: ...
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_project_name.py tests/integration/test_ingest_turns_tool.py --no-cov -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the project-name helper**

Create `session_buddy/core/project_name.py` with an **idempotent** `normalize_project_name(path: str) -> str`.

- [ ] **Step 4: Extend the metadata allowlist**

In `session_buddy/ingesters/redaction.py`, add `"sanitized"` and `"is_sidechain"` to `ALLOWED_METADATA_KEYS`, with a comment saying they are provenance markers, not secrets. Without them the guard's marker is relocated into the `_redacted` bucket and the row's provenance is lost.

- [ ] **Step 5: Implement `ingest_turns`**

Create `session_buddy/mcp/tools/conversation/ingest_tools.py`:

- Resolve the adapter with `await require_reflection_database()` — **not** `ReflectionDatabase`.
- The tool declares `token: str | None = None` **and** `user_id: str | None = None`. `require_auth` injects `user_id` as a keyword argument; a signature without it raises `TypeError` when a secret is configured. `user_id` is not a caller-settable field in practice — FastMCP derives the schema from the wrapped signature, and the auth decorator supplies the value.
- For each turn:
  1. Build the content and run `sanitize_text(...)`. If anything changed, set `metadata["sanitized"] = True`.
  2. Redact: `redact(content)` for the content and `redact_metadata(metadata, set(ALLOWED_METADATA_KEYS))` for the metadata — **pass a `set`**, matching the parameter's declared type.
  3. Resolve `parentUuid` → the parent's row `id`: maintain a `uuid → id` map within the batch, falling back to `SELECT id FROM conversations_v2 WHERE session_id = ? AND turn_uuid = ?`. Leave `turn_parent_id` NULL only when the parent is genuinely absent (it predates the retained window).
  4. Write via `store_conversation(..., source_type="claude_code", category="claude_turn", memory_tier="short_term", turn=TurnIdentity(...), searchable_content=turn.searchable_content, embed=False, user_id=user_id, turn_parent_id=...)`.
- **The `duplicate` count needs a defined mechanism.** `store_conversation` returns only the id, so the tool cannot distinguish an upsert from an insert on its own. Choose: the tool performs `SELECT id FROM conversations_v2 WHERE session_id = ? AND turn_uuid = ?` **before** writing and counts a hit as `duplicate`. State the choice in the Interfaces block. (The alternative — changing `store_conversation`'s return type — would break every existing caller.)
- **After writing each row, call `await get_embed_worker().enqueue([conv_id])`.** Without this the ingest path never reaches the worker and runtime-ingested turns are never embedded.
- **Bound the batch.** A long transcript must not produce an unbounded request. Cap the batch at **200 turns**; above that, split and process sequentially, or reject with a clear message. State the number here and in the Interfaces block.
- **`DatabaseLockedError` → a retryable envelope.** Catch it around the write and return a structured result — e.g. `{"accepted": 0, "retryable": True, "error": "database_locked"}` — so the hook can distinguish it from any other failure. A generic failure is indistinguishable from "nothing to do".
- Return a `ToolMessages` string: `ToolMessages.success(...)` with the counts in the details, `ToolMessages.operation_failed(...)` on failure.

- [ ] **Step 6: Register the tool**

In `session_buddy/mcp/tools/profiles.py`:

- `REGISTRATION_MAP["register_ingest_tools"] = register_ingest_tools`
- `STANDARD_REGISTRATIONS.append("register_ingest_tools")` — `PROFILE_REGISTRATIONS[ToolProfile.STANDARD]` derives from it automatically.

In `session_buddy/mcp/tools/__init__.py` and `session_buddy/mcp/tools/conversation/__init__.py`, export `register_ingest_tools` and add it to `__all__`.

**Do not** add `_ALL_REGISTERS` — it no longer exists.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_project_name.py tests/integration/test_ingest_turns_tool.py --no-cov -v`
Expected: PASS.

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/mcp/ tests/integration/test_mcp_registration_standard_profile.py --no-cov -v`
Expected: PASS — the registration drift test must actually run.

- [ ] **Step 8: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/core/project_name.py session_buddy/mcp/tools/conversation/ingest_tools.py session_buddy/mcp/tools/__init__.py session_buddy/mcp/tools/conversation/__init__.py session_buddy/mcp/tools/profiles.py session_buddy/ingesters/redaction.py tests/unit/test_project_name.py tests/integration/test_ingest_turns_tool.py
git commit --only <the same paths> -F /tmp/sb-ingest-tool.txt
```

Commit message subject: `feat(mcp): register the ingest_turns tool at the standard profile tier`

---

### Task A6: Embed worker

**Files:**
- Create: `session_buddy/workers/embed_worker.py`
- Modify: `session_buddy/server_optimized.py` — start and stop the worker in the lifespan
- Test: `tests/unit/test_embed_worker.py` (create)
- Test: `tests/integration/test_embed_worker_lifecycle.py` (create)

**Interfaces:**
- Consumes: `embedding_status` and `turn_uuid` (A1); the adapter's upsert path (A4).
- Produces:
  - `session_buddy.workers.embed_worker.EmbedWorker` with:
    - `EmbedWorker(adapter, embedder, *, batch_size: int = 16, poll_interval: float = 5.0)`
    - `async def start(self) -> None` — spawns the background task and records one boot-time liveness cycle.
    - `async def stop(self) -> None` — cancels the task and awaits it.
    - `async def enqueue(self, turn_ids: Sequence[str]) -> None`
    - `async def drain_once(self) -> int` — returns the number of turns embedded.
    - `async def recover_pending(self) -> int` — re-queues pending rows; returns the count.
    - `backlog_depth -> int`
  - `session_buddy.workers.embed_worker.get_embed_worker() -> EmbedWorker | None` — module-level accessor, mirroring `session_buddy/mcp/signer_feed.py:get_signer_feed_state()`. This is how A5 reaches the worker.
  - **The counter contract** A11 reads: `cycles_total: int`, `errors_total: int`, `last_error_at: float | None`, `entities_count: int`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_embed_worker.py`:

```python
async def test_drain_once_embeds_a_pending_turn() -> None: ...
async def test_drain_once_marks_a_prose_free_turn_skipped() -> None: ...
async def test_drain_once_leaves_a_failed_turn_pending() -> None: ...
async def test_recover_pending_requeues_the_backlog() -> None: ...
async def test_recover_pending_is_bounded_and_chunked() -> None:
    """A large backlog is drained in chunks of 500, not one unbounded query."""
```

Create `tests/integration/test_embed_worker_lifecycle.py`:

```python
async def test_worker_is_running_from_the_first_moment_the_server_is_up() -> None:
    """ingester_running is True and cycles_total >= 1 before any ingest."""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_embed_worker.py --no-cov -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the worker**

Create `session_buddy/workers/embed_worker.py`:

- The worker holds an `asyncio.Queue[str]` of turn ids and an `asyncio.Task`.
- `start()` creates the task and **records one successful boot cycle** — a liveness marker, not a real embed. The health feed's empty-feed branch maps `entities_count == 0` + `cycles_total == 0` + `ingester_running == True` to **DEGRADED**, and both DEGRADED and FAILED map to HTTP 503. Without the boot cycle, a fresh deployment with zero ingested conversations would report the whole service unhealthy before any ingest ever happened.
- `drain_once()` pops up to `batch_size` ids, reads each row's `searchable_content`, and:
  - If the content is empty or whitespace → set `embedding_status = 'skipped'`.
  - Else embed it and write the vector with `embedding_status = 'embedded'`.
  - On an embedder exception → leave `embedding` NULL, set `embedding_status = 'pending'`, and increment `errors_total` and set `last_error_at`. **A NULL embedding is not an error state for search** — BM25 still covers the row.
  - Increment `cycles_total` once per drain.
- `recover_pending()` runs at startup, **bounded and chunked**: `SELECT id FROM conversations_v2 WHERE embedding_status = 'pending' ORDER BY timestamp LIMIT 500`, repeated until exhausted, enqueueing as it goes. An unbounded `SELECT` over a large backlog is a memory hazard.
- `backlog_depth` counts rows with `embedding_status = 'pending'`.
- Add `get_embed_worker()` returning the module-level singleton (or `None` before the lifespan installs it).

- [ ] **Step 4: Wire the worker into the lifespan**

In `session_buddy/server_optimized.py`, inside the lifespan:

- Construct the worker after the adapter is available, `await worker.recover_pending()`, then `await worker.start()`.
- `await worker.stop()` in the shutdown path. The server's `timeout_graceful_shutdown` is **30 s** (mcp-common pins it; the "2 s" in a stale in-code comment at `server_optimized.py:304` is wrong), so the worker has room to drain.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_embed_worker.py tests/integration/test_embed_worker_lifecycle.py --no-cov -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/workers/embed_worker.py session_buddy/server_optimized.py tests/unit/test_embed_worker.py tests/integration/test_embed_worker_lifecycle.py
git commit --only <the same paths> -F /tmp/sb-embed-worker.txt
```

Commit message subject: `feat(workers): add the lifespan-owned embed worker`

---

### Task A7: FTS call site and hybrid retrieval

**Files:**
- Modify: `session_buddy/adapters/reflection_adapter_oneiric.py` — `search_conversations`, `_search_conversations_db`, the FTS call site
- Modify: `session_buddy/mcp/tools/conversation/conversation_tools.py` — the `search_conversations` MCP tool gains `mode`
- Test: `tests/unit/test_hybrid_search.py` (create)
- Test: `tests/integration/test_search_conversations_modes.py` (create)

**Interfaces:**
- Consumes: `bm25_search` (A1), the embed worker (A6).
- Produces:
  - `session_buddy.adapters.reflection_adapter_oneiric.RRF_K = 60`
  - `session_buddy.adapters.reflection_adapter_oneiric.rrf_fuse(rankings: Mapping[str, Sequence[str]], *, k: int = RRF_K) -> dict[str, float]` — takes per-channel ordered id lists and returns each id's fused score, `Σ 1 / (k + rank)` with 1-based ranks. **Named explicitly** so the unit test has a unit under test.
  - `ReflectionDatabaseAdapter.search_conversations(query, limit=10, threshold=0.7, project=None, min_score=None, use_cache=True, mode: str = "vector") -> list[dict[str, Any]]` — gains a trailing `mode` parameter defaulting to `"vector"`.
  - Each returned row gains `"bm25_score": float | None` and `"vector_score": float | None`.

**The three channels.** (1) **BM25** — DuckDB FTS over `conversations_v2.searchable_content`. (2) **Vector** — cosine similarity over embedded turns plus `reflections_v2`. (3) **Fuse** with RRF.

**The existing lexical fallback.** `_search_conversations_db` already falls back to `_text_search_conversations` (a `content LIKE %token%` OR-match) when vector search returns nothing above threshold. The BM25 channel **replaces** that fallback in `mode="bm25"` and `mode="hybrid"`; the `LIKE` fallback is retained for `mode="vector"`.

**The query cache key must gain `mode`.** Today's key is `compute_cache_key(query=…, project=…, limit=…, kind="conversations", threshold=…)` with no mode — a hybrid call would hit a vector-mode cache entry. Separately, `_get_cached_conversations` returns `"score": 1.0` for every row, which would flatten hybrid's channel scores.

**The cache stores ids, not rows.** The cache holds a list of row ids and re-fetches the rows from DuckDB; the flattened `{"score": 1.0}` shape is produced at **read** time. So the fix is to **re-derive the channel scores on a cache hit**, under a mode-scoped key — not to change the stored payload's shape. Name both sites: `_cache_conversation_results` (write) and `_get_cached_conversations` (read).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_hybrid_search.py`:

```python
def test_rrf_k_is_60() -> None: ...
def test_rrf_fuses_two_rankings() -> None:
    """A row ranked 1st in one channel and 2nd in another outranks a row ranked 3rd in both."""
```

Create `tests/integration/test_search_conversations_modes.py`:

```python
async def test_vector_mode_is_the_default_and_is_unchanged() -> None: ...
async def test_bm25_mode_finds_an_exact_token() -> None: ...
async def test_hybrid_mode_returns_both_channel_scores() -> None: ...
async def test_hybrid_ranks_the_exact_token_match_first() -> None: ...
async def test_cache_does_not_cross_modes() -> None: ...
async def test_cached_rows_keep_their_channel_scores() -> None: ...
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_hybrid_search.py tests/integration/test_search_conversations_modes.py --no-cov -v`
Expected: FAIL — `TypeError: search_conversations() got an unexpected keyword argument 'mode'`.

- [ ] **Step 3: Add the production FTS call site**

**Nothing calls `ensure_fts_index` at runtime**, and `bm25_search` swallows the missing-schema error — so the BM25 and hybrid channels would silently return nothing in a deployed server. Add an explicit production call site: call `ensure_fts_index(self.conn)` at the end of `ReflectionDatabaseAdapterOneiric._create_tables()`, inside a `try/except` that logs at **WARNING**. Narrow `bm25_search`'s blanket `except → return []` to log at **ERROR** first.

- [ ] **Step 4: Implement `mode` and RRF**

In `reflection_adapter_oneiric.py`:

- Add `RRF_K = 60` and the named `rrf_fuse(...)` function.
- Add the `mode: str = "vector"` parameter to `search_conversations` and thread it into `_search_conversations_db`.
- Validate `mode` against `{"vector", "bm25", "hybrid"}`; raise `ValueError` otherwise.
- `mode="vector"` — current behavior, unchanged, including the `_text_search_conversations` fallback.
- `mode="bm25"` — call `bm25_search` and map the results to the row shape.
- `mode="hybrid"` — run both channels, compute each row's rank within its channel, then fuse with `rrf_fuse`.
- Every result row carries `bm25_score` and `vector_score` (either may be `None`).

- [ ] **Step 5: Fix the query cache key and the cached scores**

- Add `mode` to the `compute_cache_key(...)` call for the conversations kind.
- Change `_get_cached_conversations` to re-derive the per-channel scores on a cache hit rather than flattening every row to `{"score": 1.0}`.

- [ ] **Step 6: Expose `mode` on the MCP tool**

In `session_buddy/mcp/tools/conversation/conversation_tools.py`, add `mode: str = "vector"` to the `search_conversations` tool and pass it through to the **adapter** (resolved via `require_reflection_database()`). The default stays `"vector"`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_hybrid_search.py tests/integration/test_search_conversations_modes.py tests/unit/test_reflection_adapter_oneiric.py --no-cov -v`
Expected: PASS — including the pre-existing adapter tests.

- [ ] **Step 8: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/adapters/reflection_adapter_oneiric.py session_buddy/mcp/tools/conversation/conversation_tools.py tests/unit/test_hybrid_search.py tests/integration/test_search_conversations_modes.py
git commit --only <the same paths> -F /tmp/sb-hybrid-search.txt
```

Commit message subject: `feat(search): add BM25 and RRF hybrid modes to conversation search`

---

### Task A8: `delete_conversation` tool

**Files:**
- Create: `session_buddy/mcp/tools/conversation/delete_tools.py`
- Modify: `session_buddy/mcp/tools/__init__.py` — export `register_delete_tools`
- Modify: `session_buddy/mcp/tools/conversation/__init__.py` — export `register_delete_tools`
- Modify: `session_buddy/mcp/tools/profiles.py` — `REGISTRATION_MAP` and `STANDARD_REGISTRATIONS`
- Test: `tests/integration/test_delete_conversation_tool.py` (create)

**Interfaces:**
- Consumes: `delete_conversations` (A4), `normalize_project_name` (A5).
- Produces:
  - `session_buddy.mcp.tools.conversation.delete_tools.register_delete_tools(mcp_server: FastMCP) -> None`
  - `session_buddy.mcp.tools.conversation.delete_tools.delete_conversation(conversation_id: str | None = None, session_id: str | None = None, project: str | None = None, before: str | None = None, after: str | None = None, token: str | None = None, user_id: str | None = None) -> str` — returns a `ToolMessages` string.

**The four scopes.** Single conversation (`conversation_id`) · whole session (`session_id`) · by project (`project`) · by date range (`before`/`after`). At least one scope is required. There is no unfiltered "delete all".

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_delete_conversation_tool.py`:

```python
async def test_requires_at_least_one_scope() -> None: ...
async def test_deletes_by_conversation_id() -> None: ...
async def test_deletes_by_session_id() -> None: ...
async def test_deletes_by_project() -> None: ...
async def test_deletes_by_date_range() -> None: ...
async def test_normalizes_the_project_argument() -> None:
    """A bare name and a full path delete the same rows."""
async def test_reports_counts_by_scope() -> None: ...
async def test_reflection_survives_with_a_null_conversation_id() -> None: ...
async def test_requires_auth() -> None: ...
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/integration/test_delete_conversation_tool.py --no-cov -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the tool**

Create `session_buddy/mcp/tools/conversation/delete_tools.py`:

- The four scope parameters, all optional; at least one required.
- `before` / `after` are ISO-8601 strings parsed to datetimes.
- `project` is passed through `normalize_project_name` before it reaches the adapter — the helper is idempotent, so a bare name and a full path agree.
- Resolve the adapter with `await require_reflection_database()`.
- Auth: the **local** `require_auth(optional=False)`; the tool declares `token: str | None = None` **and** `user_id: str | None = None` (the decorator injects the latter).
- Returns `ToolMessages.success(...)` with the per-scope counts, or `ToolMessages.operation_failed(...)` / `ToolMessages.validation_error(...)`.

- [ ] **Step 4: Register the tool**

Same two registration points as A5: `REGISTRATION_MAP["register_delete_tools"] = register_delete_tools` and `STANDARD_REGISTRATIONS.append("register_delete_tools")`, plus the `__init__.py` exports. `delete_conversation` belongs to the **standard** tier.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/integration/test_delete_conversation_tool.py tests/unit/mcp/ tests/integration/test_mcp_registration_standard_profile.py --no-cov -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/mcp/tools/conversation/delete_tools.py session_buddy/mcp/tools/__init__.py session_buddy/mcp/tools/conversation/__init__.py session_buddy/mcp/tools/profiles.py tests/integration/test_delete_conversation_tool.py
git commit --only <the same paths> -F /tmp/sb-delete-tool.txt
```

Commit message subject: `feat(mcp): register the delete_conversation tool at the standard profile tier`

---

### Task A9: Retention sweeper

**Files:**
- Create: `session_buddy/core/pruner.py`
- Modify: `session_buddy/settings.py` — add `retention_days` to `ConversationStorageConfig`
- Modify: `settings/session-buddy.yaml` — the matching default
- Modify: `session_buddy/server_optimized.py` — schedule the sweeper in the lifespan
- Test: `tests/unit/test_pruner.py` (create)

**Interfaces:**
- Consumes: `prune_conversations` (A4), `delete_conversations` (A4), `oneiric.adapters.storage.s3.S3StorageAdapter`.
- Produces:
  - `session_buddy.core.pruner.ConversationPruner` with:
    - `ConversationPruner(adapter, *, retention_days: int = 90, bucket: str | None = None, key_prefix: str = "conversations", s3_adapter: S3StorageAdapter | None = None)`
    - `async def sweep_once(self, now: datetime | None = None) -> dict[str, int]` — returns `{"pruned": int, "archived": int, "deleted": int, "failed": int}`.
    - `async def _bucket_available(self) -> bool` — the detection probe.
  - `session_buddy.core.pruner.DEFAULT_RETENTION_DAYS = 90`
  - `session_buddy.settings.ConversationStorageConfig.retention_days: int = 90`

**The archive path.** When a cold bucket is *detected configured and working*, the turns are archived to Session-Buddy's **own** cold bucket **first**, and deleted locally only after a confirmed upload.

- The bucket and key prefix are **component-scoped**, never the shared Oneiric substrate prefix. Per `mahavishnu/docs/decisions/2026-11-05-per-component-cold-storage-buckets.md` (active, canonical): *"Each component that has a cold tier owns its own bucket. The bucket name and the key prefix are component settings, not fleet settings."*
- The upload reuses **Oneiric's existing storage adapter** — `oneiric.adapters.storage.s3.S3StorageAdapter`, the same class `session_buddy/storage/cloud_sync.py:43-64` already uses. **No bespoke object-store client.**
- **The real API is `await s3_adapter.upload(key, data)` and `data = await s3_adapter.download(key)`** — there is no `put` method.
- **One source of truth for the bucket.** Either drop the `bucket` constructor argument and read it from the injected adapter's `S3StorageSettings.bucket`, or keep `bucket` and require the pruner to construct its own `S3StorageAdapter(S3StorageSettings(bucket=bucket, …))`. Two independent sources is how the sweeper ends up writing to a bucket it never probed.
- **Detection:** the bucket is configured **and** a probe write+read succeeds, using a fixed reserved key (`conversations/.probe`) that is uploaded, downloaded, and deleted. If detection fails, the sweeper falls back to deletion and logs the fallback. **A broken bucket must never turn into a silent data-loss event.**
- **Key layout:** `conversations/{session_id}/{turn_uuid}.json` under Session-Buddy's own prefix.

**Scheduling.** A **lifespan-owned task** running every **6 hours**. An external cron is not viable — DuckDB is single-writer across processes and the live `reflection.duckdb` is held open by the running server.

**Reflections are never pruned.**

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_pruner.py`:

```python
async def test_sweep_deletes_rows_older_than_the_window() -> None: ...
async def test_sweep_keeps_rows_inside_the_window() -> None: ...
async def test_sweep_never_deletes_reflections() -> None: ...
async def test_sweep_archives_to_the_component_bucket_before_deleting() -> None: ...
async def test_sweep_falls_back_to_deletion_when_the_bucket_probe_fails() -> None: ...
async def test_sweep_does_not_delete_when_the_upload_fails() -> None: ...
async def test_key_layout_is_component_scoped() -> None: ...
async def test_probe_uses_a_reserved_key_and_cleans_it_up() -> None: ...
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_pruner.py --no-cov -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Add the retention setting**

In `session_buddy/settings.py`, add `retention_days: int = 90` to `ConversationStorageConfig`, and the matching `retention_days: 90` in `settings/session-buddy.yaml`. The spec names `conversation_storage.retention_days`; **that setting did not exist**, and the plan previously hardcoded the window in a module constant. `DEFAULT_RETENTION_DAYS` references the setting.

- [ ] **Step 4: Implement the pruner**

Create `session_buddy/core/pruner.py`:

- `sweep_once(now=None)`:
  1. `cutoff = now - timedelta(days=self._retention_days)`.
  2. `rows = await adapter.prune_conversations(cutoff, limit=1000)`.
  3. If no rows → return zeros.
  4. If the bucket is available: for each row, upload `conversations/{session_id}/{turn_uuid}.json` (the row's JSON, minus the embedding) via `s3_adapter.upload(key, data)`. **Only after a confirmed upload** for that row, delete it. If an upload raises, leave that row in place, count it in `failed`, and continue.
  5. If the bucket is unavailable: delete the rows outright and log the fallback.
  6. Delete via `adapter.delete_conversations(...)` — **not** a raw `DELETE FROM conversations_v2`, which would raise `ConstraintException` on referenced rows.
- `_bucket_available()`: True only when a bucket is configured **and** the probe write+read+delete succeeds. Cache the result for the sweep's duration so a per-row probe does not run 1,000 times.

- [ ] **Step 5: Schedule it in the lifespan**

In `session_buddy/server_optimized.py`, start a lifespan-owned periodic task calling `sweep_once()` every 6 hours. Cancel and await it on shutdown.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_pruner.py --no-cov -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/core/pruner.py session_buddy/settings.py settings/session-buddy.yaml session_buddy/server_optimized.py tests/unit/test_pruner.py
git commit --only <the same paths> -F /tmp/sb-pruner.txt
```

Commit message subject: `feat(retention): add the conversation retention sweeper with a cold-archive path`

---

### Task A10: The hook script, the capture-gap fixes, and the launcher guard

**Files:**
- Create: `session_buddy/hooks/transcript_ingest.py`
- Modify: `session_buddy/core/session_manager.py` — reorder and bound
- Modify: `mahavishnu/mahavishnu/workers/registry.py` — the `--bare` launcher guard
- Modify (outside the repo): `~/.claude/scripts/sb_checkpoint.py`, `~/.claude/scripts/sb_session_end.py`, `~/.claude/scripts/sb_session_start.py`
- Create: `docs/runbooks/install-transcript-hook.md`
- Test: `tests/integration/test_transcript_ingest_hook.py` (create)
- Test: `mahavishnu/tests/unit/test_worker_launcher_hooks.py` (create, in the mahavishnu repo)

**Interfaces:**
- Consumes: `parse_transcript` (A2), `ingest_turns` (A5), `normalize_project_name` (A5).
- Produces:
  - `session_buddy/hooks/transcript_ingest.py` — a **stdlib-only, synchronous** executable script. Reads the hook payload from stdin, parses the transcript, posts one batch to `ingest_turns`, and **always exits 0**.
  - `session_buddy/hooks/transcript_ingest.py::main() -> int` — returns 0 on every path.
  - The endpoint resolves from `SESSION_BUDDY_URL`, defaulting to `http://localhost:8678`. **This is what makes the path work from a remote machine** against a central Session-Buddy.

**The hook event set.** Register **four** events, all idempotent, all keyed on `(session_id, prompt_id, hook_event_name)`:

| Event | Why |
|---|---|
| `Stop` | per-turn granularity; the primary trigger |
| `SessionEnd` | end-of-process coverage; **the only hook that runs on SIGTERM**; print-mode reason is `other` |
| `StopFailure` | fires *instead of* `Stop` on an API error — without it, rate-limited turns vanish silently |
| `SubagentStop` | carries `agent_transcript_path`, the subagent's own transcript |

**Why stdlib-only and synchronous.** No `import session_buddy` — a hook that fails to import on a remote machine must not break the session. And **async hooks are killed at `-p` teardown**, so `"async": true` must never be set on this hook.

**The cursor is a byte offset, not a line offset.** `Stop` fires more than once per invocation and `SessionEnd` fires again at exit, so the same turns are offered repeatedly. Keep a per-`transcript_path` **byte offset** under `~/.cache/session-buddy/ingest/{session_id}.json`, seek to it, and consume forward. Correctness rests on the unique key, so a lost or stale cache costs time, not data.

**The parser is loaded by sibling path, not by import.** The hook is installed outside the repo, so `import session_buddy` cannot work. The runbook copies `transcript_ingester.py` **next to** the hook, and the hook loads it with `importlib.util.spec_from_file_location` from its own directory. There is **no inline fallback parser** — an unspecified fallback is the code that actually runs on a remote machine.

**The current turn comes from `last_assistant_message`,** not the transcript tail — the transcript lags the in-memory conversation.

**The hook must stat the transcript** before reading it: `--no-session-persistence` yields a well-formed path to a file that does not exist.

**Auth.** The hook must send a token, or a secret-enabled deployment returns "Authentication failed" on every ingest and the always-exit-0 rule hides it — the feature would ship ingesting nothing. Read the bearer token from `SESSION_BUDDY_TOKEN` and send it as the `token` tool argument. When a secret is configured but no token is available, log at **WARNING** and skip **without advancing the offset cache**.

**Transport.** The hook transmits conversation text to a possibly-remote server, and redaction happens **server-side**. Require `https://` for any non-loopback `SESSION_BUDDY_URL`; refuse plain HTTP for a non-local host.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_transcript_ingest_hook.py`:

```python
async def test_hook_posts_ingested_turns_to_a_fake_server() -> None: ...
async def test_hook_never_raises_when_the_server_is_unreachable() -> None: ...
async def test_hook_exits_zero_on_a_missing_transcript_path() -> None: ...
async def test_hook_exits_zero_on_a_missing_transcript_file() -> None:
    """--no-session-persistence yields a path that does not exist."""
async def test_hook_exits_zero_on_a_malformed_transcript() -> None: ...
async def test_hook_posts_only_new_turns_on_a_second_run() -> None:
    """The byte offset and the idempotency key both prevent duplicates."""
async def test_hook_requires_https_for_a_non_loopback_url() -> None: ...
async def test_hook_warns_and_skips_when_no_token_is_available() -> None: ...
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/integration/test_transcript_ingest_hook.py --no-cov -v`
Expected: FAIL — the hook script does not exist.

- [ ] **Step 3: Implement the hook script**

Create `session_buddy/hooks/transcript_ingest.py`:

- **Stdlib only:** `json`, `os`, `sys`, `pathlib`, `urllib.request`, `importlib.util`. No third-party imports. **Synchronous** — no asyncio, no `"async": true`.
- `main()`:
  1. Read the JSON payload from stdin. On a JSON error → log and return 0.
  2. Read `session_id`, `transcript_path`, `cwd`, `prompt_id`, and `last_assistant_message` from the payload.
  3. **Stat the transcript.** If it does not exist → log and return 0.
  4. Enforce the transport rule: if `SESSION_BUDDY_URL` is non-loopback and not `https://` → log at ERROR and return 0.
  5. Load the parser from the sibling `transcript_ingester.py` via `importlib.util.spec_from_file_location`.
  6. Read the cached byte offset for this `transcript_path`; open the file in binary mode, seek to the offset, read the remainder, and decode.
  7. Parse the lines; for each turn, take the current turn's text from `last_assistant_message` when the turn is the last assistant turn of this payload, otherwise from the transcript.
  8. POST one batch to `ingest_turns` over raw JSON-RPC, with the `token` argument from `SESSION_BUDDY_TOKEN` and `project` = `normalize_project_name(cwd)`.
  9. **Advance the offset cache only on success.** If the server reports a retryable result (A5's `retryable: true`), do not advance — retry on the next event. If no token is available and the server requires auth, warn and skip without advancing.
  10. On **any** exception → log and return 0.
- The script must never `sys.exit(1)`. Every path returns 0.

- [ ] **Step 4: Fix the capture gap in `session_manager.py`**

In `session_buddy/core/session_manager.py` — **these live in `core/session_manager.py`, not in the MCP tools module** — three changes:

1. **Reorder.** In `checkpoint_session` (around line 1317/1349) and `end_session` (around line 1738/1743), move the `_store_conversation_checkpoint_if_enabled(...)` call **before** `perform_quality_assessment(...)`. A stalled quality assessment can no longer gate the capture.
   - **The reorder leaves `quality_score` unbound.** Call it as `_store_conversation_checkpoint_if_enabled(checkpoint_type=…, quality_score=None, is_manual=…)` — the stored marker carries `quality_score=None` until the assessment completes. The quality-dependent steps (`record_quality_score`, `should_auto_store_checkpoint`) stay **after** the assessment.
   - If the score must survive into the marker, run the assessment concurrently with the write (`asyncio.gather`) instead of strictly before it.
2. **Bound.** Give the assessment its own timeout (30 s). On timeout it logs and returns `quality_score = None`; the checkpoint payload **keeps the `quality_score` key** (shape unchanged, value nullable). Because `should_auto_store_checkpoint(quality_score=…)` consumes that value, a timed-out assessment **skips auto-storing a reflection** rather than storing one with a fabricated score.
   - `record_quality_score(self.current_project, quality_score)` must **not** be called with `None` — skip that call when the assessment timed out.
3. Update the module docstring for `end_session`, which currently says *"End-of-session cleanup must stay under FastMCP's hardcoded `timeout_graceful_shutdown=2`"* — that comment is **stale** (mcp-common pins 30 s).

- [ ] **Step 5: Fix the hook scripts' timeout handling**

In `~/.claude/scripts/sb_checkpoint.py` (timeout 10), `~/.claude/scripts/sb_session_end.py` (timeout 15), and `~/.claude/scripts/sb_session_start.py` (timeout 10): each contains **exactly one** `except` clause, catching only `json.JSONDecodeError`. An uncaught `subprocess.TimeoutExpired` aborts the hook. Add a second `except subprocess.TimeoutExpired:` clause that logs and exits 0.

These files are outside any repository. Make the edit in place and **record the change in the completion notes** — the operator must be told these three files were modified outside the repo.

- [ ] **Step 6: Guard the worker launcher against `--bare`**

`mahavishnu/mahavishnu/workers/registry.py:223` builds the `terminal-claude` worker command:

```
sh -lc 'claude -p --verbose --output-format stream-json --permission-mode {permission_mode} "$MAHAVISHNU_PROMPT" …'
```

It is correct **today** — no `--bare`, no `--no-session-persistence`. But `--bare` disables hooks entirely, and the docs say bare "will become the default for `-p` in a future release". A future Claude Code release would then **silently stop every worker's capture**, with no error anywhere.

Add a guard: a module-level constant listing the flags that disable hook execution (`--bare`), and an assertion or explicit-failure check that the built `terminal-claude` command contains none of them. A startup check that fails loudly beats a silent capture outage.

Create `mahavishnu/tests/unit/test_worker_launcher_hooks.py` asserting the `terminal-claude` command contains neither `--bare` nor `--no-session-persistence`.

- [ ] **Step 7: Document the installation**

Add `docs/runbooks/install-transcript-hook.md`:
- Copy `session_buddy/hooks/transcript_ingest.py` **and** `session_buddy/ingesters/transcript_ingester.py` to `~/.claude/scripts/`.
- Register the four hook events (`Stop`, `SessionEnd`, `StopFailure`, `SubagentStop`) in `settings.local.json`, pointing at the script. Set a per-hook `timeout` above the 1.5 s `SessionEnd` default (cap 60 s).
- Note that the hook reads `SESSION_BUDDY_URL` (default `http://localhost:8678`) and `SESSION_BUDDY_TOKEN`. For a remote machine, set `SESSION_BUDDY_URL` to the **central** Session-Buddy over `https://`.
- Note that **redaction is server-side** and the wire carries unredacted text.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/integration/test_transcript_ingest_hook.py --no-cov -v`
Expected: PASS.

Run: `cd ~/Projects/mahavishnu && .venv/bin/pytest tests/unit/test_worker_launcher_hooks.py --no-cov -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/hooks/transcript_ingest.py session_buddy/core/session_manager.py docs/runbooks/install-transcript-hook.md tests/integration/test_transcript_ingest_hook.py
git commit --only <the same paths> -F /tmp/sb-transcript-hook.txt
```

```bash
cd ~/Projects/mahavishnu
git add mahavishnu/workers/registry.py tests/unit/test_worker_launcher_hooks.py
git commit --only mahavishnu/workers/registry.py tests/unit/test_worker_launcher_hooks.py -F /tmp/mvn-launcher-guard.txt
```

Commit message subjects: `feat(hooks): add the transcript ingest hook and restore the capture path` and `fix(workers): guard the Claude Code launcher against hook-disabling flags`.

---

### Task A11: The `conversations` health feed

**Files:**
- Modify: `session_buddy/server_optimized.py` — `_build_health_snapshot`
- Test: `tests/integration/test_conversations_health_feed.py` (create)

**Interfaces:**
- Consumes: the embed worker's counter contract (A6), `mcp_common.health.feed.HealthFeedState`, `mcp_common.health.aggregator.aggregate_feed_states`.
- Produces: the health snapshot gains a `conversations` entry under `checks`, with the four canonical wire fields (`entities_count`, `last_updated_timestamp`, `cycles_total`, `errors_total`) alongside `ok`, `status`, and `reason_codes`.

**The empty-feed state is `warming_up`, not `healthy`.** `is_healthy` returns `WARMING_UP` with `healthy=False` for `entities_count == 0` + `ingester_running == True` + `cycles_total >= 1`. `WARMING_UP` maps to **HTTP 200**, so the service is not reported as down — but:

- The `data_feeds_ok` conjunction must treat `warming_up` as acceptable: `healthy or status == "warming_up"`. Otherwise a fresh deployment reports `data_feeds_ok: false`.
- The test asserts `status == "warming_up"` and `status_code == 200` — **not** "healthy". Rename it to reflect "not 503" rather than "healthy".

The boot cycle from A6 is what keeps the state at `warming_up` rather than `degraded`/`failed` (which map to 503).

**No `pending_embeddings` field.** The backlog is folded into the existing eight fields: a backlog beyond the threshold increments `errors_total` and sets `last_error_at`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_conversations_health_feed.py`:

```python
async def test_empty_but_live_feed_is_not_503() -> None:
    """ingester_running=True and cycles_total>=1 with zero conversations:
    status == 'warming_up' and the HTTP status is 200."""

async def test_a_stalled_feed_is_degraded() -> None:
    """ingester_running=False reports degraded, and the HTTP status is 503."""

async def test_the_aggregator_verdict_is_asserted_not_just_the_payload() -> None:
    """The test asserts snap['status'], not only the feed's fields."""

async def test_both_health_surfaces_agree() -> None:
    """GET /health and the get_health MCP tool report the same conversations feed."""

async def test_the_backlog_folds_into_errors_total() -> None: ...
async def test_a_failed_archive_flips_the_feed_to_degraded() -> None:
    """The sweeper's failures are visible."""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/integration/test_conversations_health_feed.py --no-cov -v`
Expected: FAIL — no `conversations` feed in the snapshot.

- [ ] **Step 3: Add the feed to the snapshot builder**

In `session_buddy/server_optimized.py`, inside `_build_health_snapshot`:

- Build a `HealthFeedState` for `conversations` from the embed worker's counters: `entities_count` = conversation rows, `last_updated_timestamp` = the newest ingested turn's timestamp, `cycles_total`, `errors_total`, `last_error_at`, `ingester_running`.
- Fold the embed backlog in: when `backlog_depth` exceeds **1000**, increment `errors_total` and set `last_error_at` to now.
- Fold the **sweeper's** counters in too: `pruner_failures` increments `errors_total` and sets `last_error_at`.
- Add `"conversations": conversations_state_snapshot` to the `aggregate_feed_states({...})` call.
- Add the `conversations` entry to `checks`, with `ok`, `status`, `reason_codes`, and the four canonical wire fields.
- Update `checks["_aggregate"]["data_feeds_ok"]` to include the conversations verdict, **accepting `warming_up`**: `verdict["healthy"] or verdict["status"].value == "warming_up"`.
- **One shared snapshot builder serves both surfaces.** `/health` and the MCP health tool must not disagree.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/integration/test_conversations_health_feed.py --no-cov -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/server_optimized.py tests/integration/test_conversations_health_feed.py
git commit --only session_buddy/server_optimized.py tests/integration/test_conversations_health_feed.py -F /tmp/sb-health-feed.txt
```

Commit message subject: `feat(health): add the conversations feed to the canonical health snapshot`

---

### Task A12: Keep raw turns out of the Akosha sync

**Files:**
- Modify: `session_buddy/storage/akosha_sync.py` — the conversation query and the incremental filter
- Modify: `session_buddy/storage/cloud_sync.py` — the module docstring
- Test: `tests/unit/test_akosha_sync_conversation_filter.py` (create)

**Interfaces:**
- Consumes: `source_type = 'claude_code'` and `category = 'claude_turn'` written by the ingest path (A5).
- Produces: `HttpSyncMethod._fetch_conversations(incremental, batch_size)` excludes raw ingested turns, and its incremental filter uses a column that exists. **The method belongs to `HttpSyncMethod`, not `HybridAkoshaSync`** — the hybrid orchestrator has no such method.

**Two defects, both verified against the live store on 2026-11-06.**

1. **There is no filter.** `_fetch_conversations` selects every row from `conversations_v2` — its only optional predicate is the incremental timestamp filter. There is no `source_type` or `category` predicate, so every ingested raw turn is serialized and pushed to Akosha on a full sync. The spec's Non-goal *"No Akosha synchronization of raw turns"* is **not** satisfied by the current code. The `memory_tier = 'short_term'` on raw turns does not help: `memory_tier` is passed through to Akosha as metadata (`akosha_sync.py:445`), not used as a predicate.
2. **The incremental path is dead.** The incremental filter is built as `WHERE updated_at > ? OR timestamp > ?` — but `conversations_v2` has **no `updated_at` column**. Verified against a copy of the live store: its columns are `id, content, embedding, category, subcategory, importance_score, memory_tier, access_count, last_accessed, project, namespace, timestamp, session_id, user_id, searchable_content, reasoning, fingerprint, metadata, source_type, turn_parent_id, causal_parent_id`. DuckDB raises a binder error, the `except (duckdb.Error, OSError, ValueError)` swallows it, and the method returns `[]`. An incremental sync therefore silently pushes **nothing**.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_akosha_sync_conversation_filter.py`:

```python
async def test_fetch_excludes_raw_ingested_turns(tmp_path: Path) -> None: ...
async def test_fetch_keeps_non_ingested_conversations(tmp_path: Path) -> None: ...
async def test_incremental_fetch_uses_a_column_that_exists(tmp_path: Path) -> None:
    """The incremental predicate does not reference updated_at."""
```

Construct an `HttpSyncMethod` in each test.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_akosha_sync_conversation_filter.py --no-cov -v`
Expected: FAIL — the raw turn is returned, and the incremental fetch returns `[]`.

- [ ] **Step 3: Filter the query and fix the incremental predicate**

In `session_buddy/storage/akosha_sync.py`, in `HttpSyncMethod._fetch_conversations`:

- Add to the base `WHERE` clause (composed with the optional incremental predicate, not replacing it):
  ```sql
  AND (source_type IS NULL OR source_type <> 'claude_code')
  AND (category IS NULL OR category <> 'claude_turn')
  ```
- Change the incremental predicate from `WHERE updated_at > ? OR timestamp > ?` to `WHERE timestamp > ?`.
- When `incremental` is true and the fetch returns **zero** rows, log at **WARNING** — that is the signature of a broken predicate, and it is what made defect 2 invisible.

- [ ] **Step 4: Check the cloud sync path and record the outcome**

`session_buddy/storage/cloud_sync.py:43-64` pushes **whole DuckDB files** to the S3 adapter. Raw turns therefore ride along in the uploaded file. That is acceptable — it is Session-Buddy's own bucket, and the retention sweeper archives there too — but it must be recorded, not assumed. Add a note to the module docstring stating that whole-file uploads include ingested raw turns and are governed by the retention sweeper's deletion, not by the Akosha exclusion. The `method="cloud"` path (`CloudSyncMethod`) is unaffected by the HTTP predicate.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_akosha_sync_conversation_filter.py --no-cov -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/storage/akosha_sync.py session_buddy/storage/cloud_sync.py tests/unit/test_akosha_sync_conversation_filter.py
git commit --only session_buddy/storage/akosha_sync.py session_buddy/storage/cloud_sync.py tests/unit/test_akosha_sync_conversation_filter.py -F /tmp/sb-akosha-exclusion.txt
```

Commit message subject: `fix(sync): exclude raw ingested turns from the Akosha push`

---

### Task A13: Move Session-Buddy's provider chain behind the Oneiric adapter

**Files:**
- Modify: `session_buddy/reflection/embeddings.py` — the provider chain
- Test: `tests/unit/test_embedding_provider_chain.py` (create)

**Interfaces:**
- Consumes: Oneiric's `EmbeddingService` with the OpenAI leg (the fleet-width plan's B1).
- Produces: `session_buddy.reflection.embeddings.resolve_embedding_provider() -> str` — the name of the resolved provider (`"oneiric"` or a fallback name), so a test can assert which path served a request.

**This task implements a spec requirement that no other task covered.** The spec's decision: *"Oneiric's `EmbeddingService` gains an OpenAI leg … and Session-Buddy and Akosha both use it. Session-Buddy's own provider chain (`session_buddy/reflection/embeddings.py`) becomes the *fallback* chain, not the primary."*

Session-Buddy's own chain (`openai_gateway` → `openai_direct` → local EmbeddingGemma-300M) already produces 768-wide vectors in the right order. The change is **ordering and ownership**: ask Oneiric first, fall back to Session-Buddy's own chain. Akosha already constructs Oneiric's `EmbeddingService` (`akosha/processing/embeddings.py:162`), so the Akosha half of the requirement is already true.

**This is the one task that waits on the fleet-width plan** — it needs Oneiric's OpenAI leg to exist. It is last so everything else ships first.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_embedding_provider_chain.py`:

```python
async def test_oneiric_is_tried_first(monkeypatch) -> None:
    """When Oneiric's service is reachable, it serves the request."""

async def test_falls_back_to_the_local_chain(monkeypatch) -> None:
    """When Oneiric is unavailable, Session-Buddy's own chain serves it."""

async def test_the_fallback_still_produces_768_wide_vectors(monkeypatch) -> None:
    """The fallback's width matches the fleet width."""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_embedding_provider_chain.py --no-cov -v`
Expected: FAIL — the chain does not consult Oneiric first.

- [ ] **Step 3: Implement the ordering**

In `session_buddy/reflection/embeddings.py`:

- Construct Oneiric's `EmbeddingService` and `await` its `initialize()` lazily on first use.
- On an embedding request, try Oneiric first. On success, return its vector.
- On any failure (unreachable, error, wrong width), fall back to Session-Buddy's own existing chain — unchanged, including its OpenAI-first ordering and 768 width.
- **Validate the width** on both paths: a vector that is not 768-wide is rejected rather than written into a `FLOAT[768]` column.
- Expose `resolve_embedding_provider()` for the test and for the health feed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_embedding_provider_chain.py --no-cov -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/session-buddy
git add session_buddy/reflection/embeddings.py tests/unit/test_embedding_provider_chain.py
git commit --only session_buddy/reflection/embeddings.py tests/unit/test_embedding_provider_chain.py -F /tmp/sb-provider-chain.txt
```

Commit message subject: `feat(embeddings): resolve Session-Buddy's embeddings through the oneiric adapter first`

---

### Task A14: Reset the conversation tier (destructive, operator-gated)

**Files:**
- Create: `session_buddy/scripts/reset_conversation_tier.py`
- Test: `tests/unit/test_reset_conversation_tier.py` (create)

**Interfaces:**
- Consumes: the adapter's delete primitives (A4).
- Produces: `session_buddy/scripts/reset_conversation_tier.py` with `def main(argv: list[str] | None = None) -> int` — returns 0 on success, 1 on a refusal, 2 on failure.

**This is destructive on live data and must be gated.** The spec states it explicitly rather than inferring it:

| Table | Action | Reason |
|---|---|---|
| `conversations_v2` | **Delete all 52 rows** | 33 synthetic context markers + 19 migrated `facts` rows. None is dialog; they are noise in the FTS and vector indexes. |
| `conversations` (v1) | **Delete all 19 rows** | Legacy pre-v2 table. |
| `reflections_v2` | Keep all 73 rows | Working distilled memory. |
| `code_graphs` | Keep (701 rows) | Unrelated subsystem. |
| `knowledge_graph.duckdb` | Keep | Separate file, separate subsystem. |
| `crackerjack_integration.db` | **Out of scope** | Co-written by Crackerjack into the same tables Session-Buddy owns. Excluded from the reset and from the delete tool's table set. |

**The target must be explicit.** A second file (`crackerjack_integration.db`) also contains a `conversations_v2` table, so "the conversation tables" is ambiguous without a path. The script takes an **explicit, required target path**, defaulting to `~/.local/share/session-buddy/reflection.duckdb`, prints the resolved absolute path plus the per-table row counts before deleting, and **refuses to run against any path whose basename is not `reflection.duckdb`** without an explicit `--force` flag.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_reset_conversation_tier.py`:

```python
async def test_reset_deletes_the_conversation_tables_only(tmp_path: Path) -> None:
    """conversations_v2 and conversations are emptied; reflections_v2 is not."""

async def test_reset_refuses_without_the_explicit_flag(tmp_path: Path) -> None:
    """Without --yes, the script refuses and deletes nothing."""

async def test_reset_refuses_an_unexpected_target(tmp_path: Path) -> None:
    """A path whose basename is not reflection.duckdb needs --force."""

async def test_dry_run_counts_without_writing(tmp_path: Path) -> None: ...
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_reset_conversation_tier.py --no-cov -v`
Expected: FAIL — `FileNotFoundError`.

- [ ] **Step 3: Implement the reset script**

Create `session_buddy/scripts/reset_conversation_tier.py`:

- Requires `--yes`. Without it, print the table of actions above and exit 1 without touching anything.
- Requires an explicit target path (default `~/.local/share/session-buddy/reflection.duckdb`); refuses a basename other than `reflection.duckdb` without `--force`.
- Supports `--dry-run`: perform every count and report the planned FTS rebuild, writing nothing.
- Prints the resolved absolute path and the row count per table **before** deleting.
- Deletes from `conversations_v2` (using the same FK-handling path as the delete tool, so referenced `memory_entities` / `memory_promotions` / `memory_access_log` rows and `memory_provenance` rows are handled and `reflections_v2.conversation_id` is nulled) and from the legacy `conversations` table.
- Touches **nothing else**.
- Rebuilds the FTS index afterwards so it does not carry the deleted rows.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/Projects/session-buddy && .venv/bin/pytest tests/unit/test_reset_conversation_tier.py --no-cov -v`
Expected: PASS.

- [ ] **Step 5: Commit the script — but do not run it against the live store**

```bash
cd ~/Projects/session-buddy
git add session_buddy/scripts/reset_conversation_tier.py tests/unit/test_reset_conversation_tier.py
git commit --only session_buddy/scripts/reset_conversation_tier.py tests/unit/test_reset_conversation_tier.py -F /tmp/sb-reset-tier.txt
```

Commit message subject: `feat(scripts): add the gated conversation-tier reset`

**Do not run the reset against the live `~/.local/share/session-buddy/reflection.duckdb` as part of this plan.** The operator runs it, after the pipeline has been verified end-to-end.

---

## Integration Contract

- **Triggered from:** the Claude Code `Stop` / `SessionEnd` / `StopFailure` / `SubagentStop` hooks (any machine, any harness with the hook installed), and direct `ingest_turns` MCP calls from any harness.
- **Returns to / updates:** `conversations_v2` rows; the `conversations` feed in the health snapshot; `search_conversations` gains an opt-in `mode`; a new `delete_conversation` tool; the `profiles.py` registrations.
- **Demonstrable by:** ingesting a fixture transcript yields a searchable row; `search_conversations(mode="hybrid")` returns it; deleting it removes it from both channels; `/health` reports the `conversations` feed.
- **Rollback signal:** the `conversations` feed reports `degraded` while ingest errors climb, or the embed backlog grows without draining. Roll back by removing the hook entries from `settings.local.json` — capture stops and the existing store is untouched.
- **Observability added:** the `conversations` feed in the canonical health snapshot (shared by `/health` and the MCP health tool); per-tool ingest and delete counters; the embed worker's backlog depth; the sweeper's archive and failure counters.

## Plan Self-Review

**Spec coverage.** Goal 1 (store real dialog) → A2, A4, A5, A10. Goal 2 (capture independent of embedding) → A4's `embed=False`, A5, A6. Goal 3 (hybrid retrieval) → A7, A1. Goal 4 (delete surface, four scopes) → A4, A8. Goal 5 (retention) → A9. Goal 6 (clean conversation tier) → A14. Goal 7 (restore auto-capture, visible gap) → A10, A11. The spec's decision *"Session-Buddy's own provider chain becomes the fallback chain"* → **A13**. ✅

**Component coverage.** Every "NEW"/"MODIFIED" component in the spec has a task: `transcript_ingester.py` → A2; `injection_guard.py` → A3; `schema_v2.py` → A1; `reflection_adapter_oneiric.py` → A1, A4, A7; `ingest_tools.py` → A5; `embed_worker.py` → A6; `delete_tools.py` → A8; `pruner.py` → A9; `hooks/transcript_ingest.py` → A10; `session_manager.py` → A10; `profiles.py` → A5, A8; the health snapshot → A11; `reflection/embeddings.py` → A13. ✅

**Gaps closed beyond the spec.** (a) The spec does not say where the FTS index is *created* — resolved by A1's `fts_index.py` plus A7's production call site. (b) The spec says the hook is stdlib-only but the parser lives in the package — resolved by A10's sibling-path load with **no** inline fallback. (c) The spec does not mention `searchable_content`'s own cap — resolved by A2's 32,000-character projection cap. (d) The spec does not name the hook script's install path — resolved by A10's runbook. (e) **The schema DDL splitter is broken today and silently drops `reflections_v2` on every fresh database** — resolved by A1. (f) **The schema DDL is missing `reflections_v2.conversation_id` entirely**, which the splitter bug was hiding — resolved by A1 Step 5. (g) The spec does not name the hook events; the live verification established that four are needed — resolved by A10.

**Review findings folded in.** 35 confirmed findings from the multi-lens review are addressed above. The design-changing ones: A1 repairs the DDL splitter before adding anything (a reproduced live defect); A4 extends the shipped `delete_conversation` with the `memory_relationships`-before-`memory_entities` ordering the shipped code already gets right, and adds the `reflections_v2` nulling it lacks; A4 adds `embed=False` so the ingest path cannot stall on a network embed; A5/A7/A8 resolve the adapter via `require_reflection_database()` and return `ToolMessages`; the registration steps use the two real registration points keyed by `register_*` names; the auth signatures declare `user_id` so `require_auth`'s injection does not raise `TypeError`; every test path is under the top-level `tests/` tree; A10 registers four hook events with a byte-offset cursor and authenticates; A11 treats `warming_up` as acceptable; and A12 names `HttpSyncMethod` rather than `HybridAkoshaSync`.

**Review Focus coverage.** Item 1 (malformed line) → A2's `test_skips_malformed_lines_and_counts_them`. Item 2 (injection) → A3's whole test set plus A5's `test_ingest_sanitizes_tool_result_text`. Item 3 (double ingest) → A4's idempotency test, A5's `test_ingest_is_idempotent`, A10's `test_hook_posts_only_new_turns_on_a_second_run`. Item 4 (oversized turn) → A5's `test_ingest_truncates_oversized_turns`. Item 5 (delete vs. reflection) → A4's `test_delete_nulls_reflection_conversation_id_and_keeps_the_reflection` plus A8's copy. ✅

**Type consistency.** `TurnRecord` (A2) is the input shape for `ingest_turns` (A5). `TurnIdentity` (A4) carries the identity fields into `store_conversation` (A4). `delete_conversations` (A4) returns the count dict that `delete_conversation` (A8) wraps. `bm25_search` (A1) is the only BM25 entry point; A7 is its only caller. `rrf_fuse` (A7) is the only fusion implementation. `EmbedWorker` counters (A6) are the only source for A11's feed. `normalize_project_name` (A5) is used by A5, A8, and A10. `get_embed_worker` (A6) is how A5 reaches the worker. ✅

**Proportion.** Fourteen tasks, each with one independently testable deliverable. A2 (parser) and A3 (guard) are separate because a reviewer could reject the guard while approving the parser, and they have separate files and separate test cycles. A14 is separate from A1 because the destructive reset must be separately gated and separately reviewed. ✅
