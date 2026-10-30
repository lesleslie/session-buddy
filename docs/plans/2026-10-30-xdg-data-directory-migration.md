---
status: shipped
role: implementation
date: 2026-10-30
last_reviewed: 2026-10-30
superseded_by: null
blocks_on: []
topic: data-directory
title: "XDG Data Directory Migration — 2026-10-30"
---

# XDG Data Directory Migration — 2026-10-30

## Question

Should Session-Buddy's runtime data move out of `~/.claude/data` into
XDG locations, and what breaks when it does?

Vish is harness-agnostic, so a component that stores its state under a
Claude-Code-specific directory is a layering violation: the path
asserts "this belongs to Claude Code" when the thing that owns it is
Session-Buddy.

**Verdict: yes, migrate — but as a separate, plan-sized change, and not
with a naive find-and-replace.** The reason is in the next section.

## The headline finding: this fails silently, not loudly

Every hardcoded consumer of a `~/.claude/data` path **creates a fresh
empty database** when the file is missing, rather than raising. None of
them would error out, log an error, or fail a test. The migration would
appear to succeed, and then the fleet would silently start writing to
new, empty databases while the real data sat in the old location.

Concretely, after a naive move:

| Consumer | Failure mode |
|---|---|
| `crackerjack` `CorrelationStorageSQLite` | `mkdir(parents=True, exist_ok=True)` then `sqlite3.connect()` — creates an empty DB |
| `crackerjack` `SessionBuddyDirectClient` | lazy `sqlite3.connect()` — creates an empty DB |
| `session_buddy` `CrackerjackIntegration` | `_init_database()` fails, `except` branch falls back to `/tmp/session-mgmt-mcp/data/` — writes to a temp dir nobody looks at |
| `session_buddy` `akosha_sync` / `cloud_sync` | `duckdb.connect(path)` — creates an empty DuckDB file |
| `session_buddy` `workflow_metrics` | `sqlite3.connect()` — creates an empty DB |
| `session_buddy` `modes/standard.py` | `data_dir.mkdir(parents=True, exist_ok=True)` — re-creates `~/.claude/data` and keeps writing there |

A migration that *looks* like it worked is worse than one that fails
loudly. The plan therefore needs a resolver module and an assertion
that no consumer reaches outside the XDG root — not a search-and-replace.

## Inventory

### Live consumers — currently written (mtime within the last day)

| File | mtime | Size | Owner |
|---|---|---|---|
| `reflection.duckdb` | 2026-10-30 06:48 | 33M | session-buddy |
| `knowledge_graph.duckdb` | 2026-10-30 06:57 | 5.8M | session-buddy |
| `crackerjack_integration.db` | 2026-10-30 06:47 | 1.1M | session-buddy |
| `interruption_manager.db` | 2026-10-30 06:24 | 512K | session-buddy |
| `tasks_metadata.sqlite` | 2026-10-30 03:54 | 12K | session-buddy |
| `mahavishnu-index-queue/` | 2026-10-29 | 954M / 697 files | mahavishnu |

### Stale artifacts — worth deleting rather than migrating

An unwritten file is not automatically a dead file: it may still be
*constructed* by a live code path that recreates it empty at the old
location. Each candidate was traced to its constructor.

| File | mtime | Size | Verdict |
|---|---|---|---|
| `workflow_metrics.db` | 2026-04-21 | 2.0M | **moves, not deleted.** `di/__init__.py:255` constructs `WorkflowMetricsEngine()` → `WorkflowMetricsStore()` during DI setup, and that store's default is the hardcoded `~/.claude/data/workflow_metrics.db`. It is constructed at every startup even though nothing has written it since April. The path must be converted or the file gets recreated empty at the old location — the exact silent failure this audit documents. |
| `correlation_insights.db` | 2026-02-11 | 20K | **genuinely dormant.** Crackerjack's `create_session_buddy_integration` is its only constructor and has no production caller — only tests call it. Built but not wired. Safe to delete. |
| `team_knowledge.db` | 2026-05-25 | 64K | unwritten for 5 months; no constructor found. Safe to delete. |
| `sessions.duckdb` | 2026-09-25 | 1.3M | superseded by the `sessions/` directory. Safe to delete. |
| `sessions/` | 2026-06-06 | 212K | last write in June. Safe to delete. |
| `legacy_vectors.parquet` | — | 36K | no reference found. Safe to delete. |

Deleting these shrinks the move from eleven artefacts to five, and
removes the need to keep crackerjack's two `~/.claude/data` defaults
pointing at anything.

### Hardcoded live code (would create empty databases)

| Location | Path built from |
|---|---|
| `session_buddy/storage/akosha_sync.py:87,91` | `Path.home()/".claude"/"data"/...` |
| `session_buddy/storage/cloud_sync.py:111,115` | `Path.home()/".claude"/"data"/...` |
| `session_buddy/crackerjack_integration.py:191` | `Path.home()/".claude"/"data"/...` (+ temp fallback) |
| `session_buddy/core/workflow_metrics.py:117` | `"~/.claude/data/workflow_metrics.db"` |
| `session_buddy/modes/standard.py:68,107` | `os.path.expanduser("~/.claude/data")` |
| `session_buddy/knowledge_graph_db.py:84` | temp-dir fallback only |
| `crackerjack/crackerjack/integration/session_buddy_integration.py:493,602,735,736` | `"~/.claude/data/workflow_metrics.db"`, `"~/.claude/data/correlation_insights.db"` |
| `mahavishnu/mahavishnu/core/code_index/indexer.py:17` | `Path.home()/".claude"/"data"/"mahavishnu-index-queue"` |

### Scripts (offline tooling — lower risk, still needs updating)

`session-buddy`: `scripts/migrate_embedding_dim.py:589`,
`fix_database_issues.py:66`, `migrate_knowledge_graph_embeddings.py:38`,
`add_kg_embedding_column.py:24`, `activate_phase2_simple.py:21`,
`monitor_crackerjack_metrics.py:101`, `test_database_status.py:61,191,281`,
`deploy_phase4.sh:18`.

`mahavishnu`: `scripts/cleanup_reflection_db.py:60`.

### Already settings-derived (the pattern to copy)

- `session_buddy/adapters/settings.py:14` — `settings.paths.data_dir`
- `session_buddy/core/session_analytics.py:189`,
  `bottleneck_detector.py:148` — `settings.database.path.parent`
- `session_buddy/settings.py:217,245` — `PathsConfig.data_dir`,
  `DatabaseConfig.path`
- `scripts/migrate_graph_database.py:33` — `get_data_dir()`
- `scripts/backfill_reflection_project.py:67` — `paths.data_dir`

### Config layers that pin the literals

- `session-buddy/settings/session-buddy.yaml:47` (`paths.data_dir`),
  `:48` (`paths.log_dir`), `:54` (`database.path`)
- `session-buddy/settings/standard.yaml:8` (`database_path`),
  `:64` (`sessions.local_path`)
- `session-buddy/settings.py:217,221,228,245` (defaults)

### User-level (`~/.claude/`)

- `~/.claude/scripts/pre-commit-validation.sh:143` — excludes
  `*/.claude/data/*` from the large-file scan; needs the new root added
- `~/.claude/settings.json:496-497` — two `Bash(rm -f ...)` allowlist
  entries naming long-dead `mahavishnu-index-queue` files; stale
- `~/.claude/docs/working/*` — documentation only

### Not affected

- **launchd plists** (`~/Library/LaunchAgents/com.mcp.*.plist`) — none
  reference `.claude/data`; the generated plists do not pin DB paths
- **`mcp-ctl`** — no data-path references
- **akosha, oneiric, dhara, mcp-common** — zero references; they reach
  Session-Buddy over the MCP API on 8678, not the files

## There is no single knob

Two independent settings carry the paths, and each needs its own
override:

```
SESSION_BUDDY_PATHS__DATA_DIR     → settings.paths.data_dir
                                     (and the derived KG path)
SESSION_BUDDY_DATABASE__PATH      → settings.database.path
```

Verified: setting only `SESSION_BUDDY_PATHS__DATA_DIR` moves
`paths.data_dir` and `knowledge_graph.duckdb`, but **not**
`database.path` — `reflection.duckdb` stays at the old location. Both
must be set, and the YAML layer pins both literals anyway, so the
YAML has to change too.

This is the strongest argument for a resolver module: a single
`session_buddy.paths.resolve_data_dir()` that every consumer calls,
rather than two settings that have to be kept in agreement by hand.

## Recommended target layout

| XDG root | Contents |
|---|---|
| `~/.local/share/session-buddy/` | `reflection.duckdb`, `knowledge_graph.duckdb`, `crackerjack_integration.db`, `tasks_metadata.sqlite`, `workflow_metrics.db` |
| `~/.local/state/session-buddy/` | `interruption_manager.db`, logs, sync state |
| `~/.cache/session-buddy/` | regenerable caches |
| `~/.config/session-buddy/` | settings |
| `~/.local/state/mahavishnu/index-queue/` | the 954M index queue |

The `~/.local/state/<app>/` convention is already established in this
fleet — the global `CLAUDE.md` puts worktrees at
`~/.local/state/mahavishnu/worktrees/`.

## Where the resolver lives

There is already a home-relative path abstraction in the codebase:
`SessionPaths` in `session_buddy/di/config.py`. It resolves
`claude_dir` (`~/.claude`), `logs_dir`, `commands_dir` and `data_dir`
(`claude_dir / "data"`), is registered in the DI container, and has a
`from_home(home)` classmethod that respects `HOME` for testability.
It is the existing seam — the migration retargets it rather than
adding a parallel module beside it.

But `SessionPaths` is not reachable from the other two repos. Two of
its four roots are genuinely Claude-specific and stay put:
`claude_dir` (`~/.claude`) and `commands_dir` (`~/.claude/commands`).
The two that move are `data_dir` and `logs_dir`.

So the resolution splits by ownership:

- **The XDG root primitives** — `xdg_data_home()`,
  `xdg_state_home()`, `xdg_cache_home()`, `xdg_config_home()` — are a
  platform-level concern, and oneiric already owns the fleet's XDG
  convention: it loads settings from `~/.config/{project}/config.yaml`
  and `~/.config/{project}/local.yaml`, and
  `oneiric/core/config.py:105` already has a `resolve_cache_dir_path`
  with the resolve → mkdir → write-probe → temp-fallback shape this
  should follow. Adding the primitives there avoids three copies.
- **The app-scoped roots** — `~/.local/share/session-buddy`,
  `~/.local/state/session-buddy` — are Session-Buddy's decision, and
  belong in `SessionPaths`.

All three consumer repos already import oneiric directly
(`oneiric>=0.33.2` in mahavishnu, a sentinel pin in crackerjack, and
direct imports in session-buddy's `di/container.py` and `shell/adapter.py`),
so this adds no new dependency edge — it only requires oneiric to ship
the primitives before the consumers import them.

Two details worth carrying over from the existing code:

- The resolver must follow the fleet's unwritable-home convention:
  resolve → `mkdir(parents=True, exist_ok=True)` → write probe →
  fall back to a temp directory. `SessionPaths.from_home()` and
  oneiric's `resolve_cache_dir_path` both do this, and
  `session_buddy/knowledge_graph_db.py:84` already falls back to
  `tempfile.gettempdir() / "session-buddy-home"`.
- `SessionPaths.from_home()` uses `os.path.expanduser("~")` rather than
  `Path.home()` specifically so tests can override `HOME`. The XDG
  resolver should read `XDG_*` the same way, so a test can point them
  at a temp root without touching the real one.

## Sequence

The ordering below is load-bearing. Two facts constrain it:

1. **All three repos must be converted before anything moves.**
   Converting only Session-Buddy while crackerjack still points at
   `~/.claude/data` reproduces the exact silent failure this audit
   documented — crackerjack creates empty databases at the old path
   while Session-Buddy writes to the new one.
2. **The default flip and the file move must happen in the same stopped
   window.** If the code resolves to the new root before the files are
   there, the first write creates a fresh empty database at the new
   path and the real data is orphaned at the old one. If the files move
   before the code resolves to the new root, the old path is recreated
   empty. There is no safe ordering that separates the two.

### Phase 0 — each repo carries its own resolver copy

**As implemented, not as originally planned.** The plan put the XDG
root primitives in oneiric, which would have been the right home — it
already owns the fleet's XDG config convention. But oneiric is a
*released* (non-editable) install in Session-Buddy's venv, and
Session-Buddy and crackerjack are released installs of each other, so
a cross-repo import needs a publish first, and publishing is
operator-gated. Gating a data-layout change on three releases for
twenty lines of `os.environ.get` was not worth it.

Each repo therefore carries its own copy of the resolver:
`session_buddy/paths.py`, `crackerjack/utils/xdg_paths.py`,
`mahavishnu/core/xdg_paths.py`. The semantics are identical across all
three, and the duplication is documented in each module. Moving the
primitives into oneiric later is a natural follow-up, once a release
carrying them can be published.

On this host `XDG_STATE_HOME` is already set to
`/Users/les/.local/state`; the other three are unset, so the spec
defaults apply (`~/.local/share`, `~/.local/state`, `~/.cache`,
`~/.config`).

### Phase 1 — convert the code, leave the YAML as the pin

**As implemented, the wording differs from the original plan.** The
plan said the resolver's `data_dir()` should keep returning
`~/.claude/data` during Phase 1, so that Phase 1 was a pure refactor
with no behaviour change at all. The implemented design puts the pin
one layer up: the **resolver returns the XDG path unconditionally**, and
the **YAML layer is what still pins the legacy locations** until
Phase 2 flips it.

That difference matters, and it is the one place where the split-brain
window is open. Two classes of path exist:

* **YAML-driven** (`paths.data_dir`, `paths.log_dir`, `database.path`)
  — unchanged through Phase 1, because the YAML still pins them. The
  reflection, knowledge-graph and task-metadata databases stay put.
* **Resolver-driven** (`crackerjack_integration.db`,
  `workflow_metrics.db`, `team_knowledge.db`, `activity.db`,
  `interruption_manager.db`, `natural_scheduler.db`, the `sessions/`
  directory, the session logger's directory) — these move to the XDG
  roots on the very first restart after Phase 1 lands, because nothing
  gates them. Every one of their constructors creates a fresh empty
  database when the file is missing rather than raising, so a restart
  before Phase 2 silently empties them.

That is why Phase 2 has to follow Phase 1 immediately, and why the
stopped window has to be a real stop rather than the one `mcp-ctl stop`
gives you (see "The launchd respawn" below).

### Phase 2 — the stopped window

Stop Session-Buddy. Move the live files to the XDG root. Flip the
YAML layer. Start Session-Buddy. Verify.

The DuckDB files are held under an exclusive lock, so the window is
required regardless — but it comes *after* the code deploy, not before.

The stop has to be a `launchctl bootout`, not `mcp-ctl stop`.
`mcp-ctl stop` runs `launchctl kill SIGTERM`, which leaves the job
loaded; the plist's `KeepAlive` is `{SuccessfulExit: False, Crashed:
True}`, so a SIGTERM'd process counts as a crash and launchd respawns
it after the 30-second throttle. The respawn lands in the middle of
the window, before the YAML flip, and creates a fresh empty
`reflection.duckdb` at the old path. Booting the job *out* removes it
from launchd so it cannot respawn; `launchctl bootstrap` puts it back.

### Phase 3 — cleanup

Delete the legacy `~/.claude/data` and the stale artefacts listed
above.

## Deliberately out of scope

- **`~/.claude/` itself.** The directory is Claude Code's; this
  migration only moves Session-Buddy's artefacts out of it.
- **`~/.claude/settings.json:496-497`.** Two `Bash(rm -f ...)` allowlist
  entries naming long-dead `mahavishnu-index-queue` files. Stale
  permission entries, unrelated to the data move — separate cleanup.
- **The Mahavishnu index queue.** `mahavishnu-index-queue/` is
  Mahavishnu's own artefact and Mahavishnu's move to make. This plan
  flags it and converts `QUEUE_DIR` to a resolver; moving the 954M of
  files is Mahavishnu's call.
- **A compatibility symlink or a shim that reads the old path.**
  Session-Buddy is pre-1.0, so the migration replaces rather than
  extends: no fallback reads, no dual-write, no symlink left behind to
  mask a half-finished migration.
- **The stale artefacts listed above.**
  `correlation_insights.db`, `team_knowledge.db`, `sessions.duckdb` and
  `sessions/` are unwritten for one to eight months and have no live
  constructor. They are deleted rather than migrated — but that is a
  data decision, and the operator may want to keep
  `correlation_insights.db` for its history.
  `workflow_metrics.db` is *not* in this group: it moves.

## Integration contract

- **Triggered from** — every Session-Buddy process that resolves its
  data root; crackerjack's `SessionBuddyIntegration`,
  `SessionBuddyDirectClient` and `CorrelationStorageSQLite`
  constructors; mahavishnu's `code_index` indexer when it falls back
  to the local queue.
- **Returns to** — callers get the same resolved absolute paths they
  get today, now rooted under XDG. No signature, return-type, or
  behavioural change: `settings.paths.data_dir` and
  `settings.database.path` still hold resolved paths.
- **Demonstrable by** — a new `tests/unit/test_xdg_paths.py` asserting
  that no module under `session_buddy/` constructs a path containing
  `.claude/data`, plus the matching checks in crackerjack and
  mahavishnu; a live assertion that `settings.paths.data_dir` starts
  with the XDG data root; and — the check that actually matters —
  `get_knowledge_graph_stats` returning `Total Entities: 241` and
  `Embedding Coverage: 100.0%` after the move. A non-empty result is
  the only proof the data was found rather than a fresh empty database.
- **Rollback signal** — `get_knowledge_graph_stats` reports
  `Total Entities: 0` or `Embedding Coverage: 0.0%` where the pre-move
  counts were non-zero; or `store_reflection` succeeds while
  `quick_search` finds nothing; or any consumer logs the creation of a
  new database. All three are the same signal: a consumer resolved to
  a root that has no data.
- **Observability added** — the resolver logs the resolved root once
  per process at startup, so a process running against the wrong root
  is visible in the log without having to inspect the filesystem.

## Notes

- The `~/.claude/data` directory itself should be removed once empty.
  `modes/standard.py` re-creates it today, so that `mkdir` has to be
  removed in step 2.
- `~/.claude/logs/session-buddy.log` is a Session-Buddy artifact in a
  Claude-specific directory; it belongs under `~/.local/state/`.
- The dead-backups cleanup performed on 2026-10-30 removed 1,562 MB of
  width-incompatible DuckDB copies. Two of those
  (`reflection.duckdb.pre-4096-migration.bak` at FLOAT[4096],
  `knowledge_graph.duckdb.pre-migration.bak` at FLOAT[384]) were the
  only pre-migration snapshots; neither was a usable rollback target,
  because the embedding providers serve 768-wide vectors and restoring
  either width would have reintroduced the mismatch.

## Outcome — 2026-10-30

Shipped. Three repos converted and merged, then the data moved.

**Commits.** Session-Buddy `5fc04d43` (49 files), crackerjack
`9704662f` (5 files), mahavishnu `557fdb16` (7 files); the YAML flip
`85feec45`; the examples revival `4178faad`. Nothing pushed.

**The move.** 14 paths, verified by row counts read before and after:
`reflection.duckdb` 705 rows (21 reflections, 1 causal chain, 648 code
graphs), `knowledge_graph.duckdb` 244 rows, `crackerjack_integration.db`
3104 rows, `interruption_manager.db` 717 rows,
`tasks_metadata.sqlite` 2 rows, `activity.db` 12 rows, plus the
`mahavishnu-index-queue` (697 files) and the session-management logs.
After the restart the server reports the same counts (242 KG entities,
2 relationships, 100% embedding coverage, 22 reflections) and holds
`~/.local/share/session-buddy/reflection.duckdb` open; the old location
stayed free of databases.

**Three things went differently than planned**, all recorded above:
the resolver copy is per-repo rather than in oneiric (publish gate);
the YAML layer is the Phase-2 pin rather than the resolver's default;
and the stop needed `launchctl bootout` because `mcp-ctl stop` leaves
the job loaded and launchd respawns it.

**One incident.** The server respawned mid-window (see "The launchd
respawn" above), before the YAML flip, and created an empty
`reflection.duckdb` and `knowledge_graph.duckdb` at the old path. No
data was lost — the real files had already been moved, with all rows
intact — and the two empty files were quarantined. The lesson is the
one in the Phase 2 section: boot the job out, do not just kill it.

**Left for a follow-up, not done here:**

- `scripts/migrate_vector_database.py` still imports `acb.depends` and
  `acb.adapters.vector._base`. The `acb` package is not installed and
  the `vectors.default` schema it migrates to exists nowhere in the
  tree, so the script cannot run. It was dead ACB-era code and has
  been deleted; the repo already asserts the ACB-free runtime in
  `tests/integration/test_phase6_success_criteria.py::test_no_acb_dependencies_import`.
- The stale artefacts in the "Stale artifacts" table were **moved,
  not deleted** — the move was approved as moves-only. `workflow_metrics.db`
  (unwritten since April), `correlation_insights.db` (February),
  `team_knowledge.db` (May), `sessions.duckdb` (September) and
  `sessions/` (June) now sit at the XDG roots and can be pruned.
- The pytest-tmp rows in the live `crackerjack_integration.db` have
  since been deleted, under an explicit operator approval of the
  "all test temp-dir rows" category. The backup was taken and verified
  byte-identical first
  (`.crackerjack_integration.db.pre-testrow-cleanup.bak`); the delete
  ran in FK-safe order, dependents first; `VACUUM` afterwards
  reclaimed 503,808 bytes (1,114,112 → 610,304). `PRAGMA
  integrity_check` is `ok`.

  | table | before | deleted | after |
  |---|---|---|---|
  | `crackerjack_results` | 896 | 492 | 404 |
  | `quality_metrics_history` | 1949 | 759 | 1190 |
  | `progress_snapshots` | 259 | 12 | 247 |

- 135 `quality_metrics_history` rows still point at a `result_id` that
  does not exist. They are **not** leftovers of that delete. The
  orphan count went *down* (390 → 135), every survivor was already
  orphaned beforehand, and all 135 carry
  `project_path = /Users/les/Projects/crackerjack` rather than a temp
  directory — outside the approved category.

  The cause is on the writer side, in
  `crackerjack/cli/handlers/health.py:363`, which mints
  `health_<uuid>` run ids and writes metric rows against them without
  ever inserting a parent row into `crackerjack_results`. SQLite does
  not enforce foreign keys unless asked to, so the violation is silent.
  45 health snapshots × 3 categories = 135. The column is nullable, so
  the rows could be nulled out, but they carry real historical health
  metrics, and the fix belongs in the health writer rather than in the
  data. **Fixed** in crackerjack `c1729abb`: the parent row is written
  before the metric rows, the connection sets `PRAGMA foreign_keys=ON`
  so a regression fails loudly, and six tests cover the association.

## Follow-on — the vestigial v1 tables

Moving the files exposed a second layer the migration plan never
mentioned, because it is about table names rather than paths.

The v2 schema promotion (`cebc6a79`) moved storage to `reflections_v2`
and `conversations_v2`. `session_buddy/reflection/schema.py` creates
*only* the v2 tables — its `create_conversations_table` and
`create_reflections_table` helpers are no-op shims — so the v1 names
do not exist on a freshly initialised database at all. But a dozen
places still hard-coded them:

- `session_buddy/reflection/search.py` read `FROM reflections` — a
  table that exists in the live database but holds **zero rows**, so a
  legacy search for a reflection that demonstrably existed returned
  "no results" with nothing to indicate why.
- The legacy write path inserted into `conversations`, which on a fresh
  database failed outright: *"Table with name conversations does not
  exist! Did you mean conversations_v2?"*
- `core/memory_health.py` counted `reflections`, so the health report
  said "0 reflections" while the store held 24.

All of them now resolve the table through `REFLECTIONS_TABLE` /
`CONVERSATIONS_TABLE` in `session_buddy/reflection/storage.py`, which
is what the Oneiric adapter already did through its own `_table()`
helper.

**The live data moved with it.** 19 SESSION_END conversation snapshots
had been written to the v1 `conversations` table after the promotion,
so they were invisible to every v2 reader. They were migrated with the
canonical `MIGRATION_SQL` (backup at
`.reflection.duckdb.pre-v2-conversation-migration.bak`), and the three
vector indexes were dropped and rebuilt around the checkpoint — a
checkpoint over a WAL containing HNSW-indexed rows hits the DuckDB
2.0.0 `vss` bug, so the indexes have to be out of the way first.

The rebuild also fixed a latent name collision: the adapter creates
`idx_default_conv_embeddings_hnsw` on `conversations_v2`, but an
index of that name already existed on the vestigial `default_conversations`
table, so `CREATE INDEX IF NOT EXISTS` was a no-op and the v2 table
never got a vector index at all.

## Follow-on — why `quick_search` returned nothing

`quick_search` reported "no results" for every query, including exact
substrings of stored reflections. The cause was a threshold, not a
missing row.

The corpus is short technical notes, so the best semantic match for a
keyword query scores around 0.35-0.62, while a query that reproduces a
reflection's full text scores 1.0. The default `min_score` of 0.7
therefore admitted only near-verbatim queries. The legacy search path
falls back to a lexical match when nothing clears the threshold; the
v2 rewire dropped that fallback, because `min_score` became a hard SQL
filter instead. It is restored for both stores.

Two further facts the fix exposed:

- The registered `quick_search` searched **conversations**, not
  reflections. Two tools with that name are registered —
  `mcp/tools/memory/memory_tools.py` searches reflections and
  `mcp/tools/memory/search_tools.py` searches conversations — and the
  latter wins by registration order, so the reflections-searching
  variant was unreachable. The registered one now searches both.
- The DuckDB WAL for this database is poisoned on most startups (the
  `vss` HNSW serialisation bug), and the server recovers by flushing
  it. That is chronic and predates this migration — it happened nine
  times between 2026-10-29 13:11 and 2026-10-30 06:31 at the *old*
  path. It is also why an in-process probe against the same file
  behaved differently from the running server: the poisoned-WAL
  recovery path was the thing making the connection healthy.

