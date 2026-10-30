---
status: draft
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

| File | mtime | Size | Note |
|---|---|---|---|
| `workflow_metrics.db` | 2026-04-21 | 2.0M | unwritten for 6 months |
| `correlation_insights.db` | 2026-02-11 | 20K | unwritten for 8 months |
| `team_knowledge.db` | 2026-05-25 | 64K | unwritten for 5 months |
| `sessions.duckdb` | 2026-09-25 | 1.3M | superseded by `sessions/` |
| `sessions/` | 2026-06-06 | 212K | last write in June |
| `legacy_vectors.parquet` | — | 36K | — |

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
| `~/.local/share/session-buddy/` | `reflection.duckdb`, `knowledge_graph.duckdb`, `crackerjack_integration.db`, `tasks_metadata.sqlite` |
| `~/.local/state/session-buddy/` | `interruption_manager.db`, logs, sync state |
| `~/.cache/session-buddy/` | regenerable caches |
| `~/.config/session-buddy/` | settings |
| `~/.local/state/mahavishnu/index-queue/` | the 954M index queue |

The `~/.local/state/<app>/` convention is already established in this
fleet — the global `CLAUDE.md` puts worktrees at
`~/.local/state/mahavishnu/worktrees/`.

## Sequence

1. **Land the resolver.** Add `session_buddy/paths.py` exposing
   `data_dir()`, `state_dir()`, `cache_dir()`, `config_dir()`,
   resolving `$XDG_DATA_HOME` / `$XDG_STATE_HOME` / `$XDG_CACHE_HOME` /
   `$XDG_CONFIG_HOME` with the spec defaults. Point `PathsConfig` and
   `DatabaseConfig` at it; change the YAML to match.
2. **Convert every consumer** in the table above to call the resolver.
   Crackerjack's two defaults and Mahavishnu's `QUEUE_DIR` are
   cross-repo edits and need their own commits in their own repos.
3. **Add the guard.** A test that asserts no module under
   `session_buddy/` constructs a path containing `.claude/data`, plus a
   matching check in crackerjack and mahavishnu. This is what turns a
   silent failure into a loud one next time.
4. **Delete the stale artefacts** listed above rather than migrating
   them.
5. **Stop the server, move the live files, start the server.** The
   DuckDB files are held under an exclusive lock, so this window is
   required — but it comes *after* the code deploy, not before. The
   order matters: the running server must already resolve the new paths
   before the files move, or it will recreate empty databases at the old
   location on its next write.

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
