---
status: active
role: implementation
kind: decision
date: 2026-09-26
last_reviewed: 2026-09-26
superseded_by: null
topic: mcp-launcher-migration
related_plan: /Users/les/Projects/mahavishnu/docs/plans/2026-09-26-mcp-launcher-standardization.md
related_reqs: [REQ-013, REQ-014, REQ-007]
---

# Session-Buddy `server start` Launcher Migration Discovery

## 0. TL;DR

**Outcome B1 — Replace + preserve pid/signal layer.** The `server start --force` CLI subcommand is **already launcher-shaped** — it is `MCPServerCLIFactory._cmd_start` from mcp-common, not a custom Typer command. The only sb-specific lifecycle work lives in `start_server_handler` (one function, ~30 LOC) and consists of a **port pre-bind check** (`_port_holder` via `lsof`) plus the FastMCP `mcp.run(...)` call. Migration refactors `start_server_handler` so the FastMCP run call becomes `launch(build_server=..., component_name="session-buddy", ...)`. The `--force` flag is **mcp-common's flag** for stale-PID handling — it stays exactly as-is. PID file write/removal, signal handlers, and `/health` snapshotting are all done by mcp-common before `start_handler` is invoked, so they don't need migration.

**Verbatim answers to the discovery questions:**
- **`--force` does**: mcp-common `MCPServerCLIFactory._handle_stale_pid(force=True)` — removes stale PID file (auto-cleaned by default; `--force` preserves the legacy "Removed stale PID file" message wording). **Does NOT kill a live process** — only handles dead/stale PIDs (factory.py:373-427).
- **PID files written**: yes — `cache_dir/mcp_server.pid` via `_write_pid_and_health_snapshot` (factory.py:588-600). sb's `SessionBuddySettings.pid_path()` (base.py:98-99) supplies the path.
- **Signal handlers installed**: yes — `SignalHandler` registers `SIGTERM` and `SIGINT` for graceful shutdown (signals.py:45-48); `SIGHUP` is **only** registered when an `on_reload` callback is supplied, and sb does not supply one. The shutdown callback updates the health snapshot (watchers_running=False) and unlinks the PID file (factory.py:602-619).
- **Line 979 verified**: `uvicorn_config={"timeout_graceful_shutdown": 30}` at `session_buddy/server_optimized.py:979`. Matches the launcher's default — migration is a no-op for this parameter.

---

## 1. The `server start` subcommand surface

### 1.1 Where the subcommand actually lives

The plan's premise — that `session_buddy server start` is a custom Typer subcommand implemented in `session_buddy/cli/server_cli.py` — is **incorrect**. The actual implementation is `MCPServerCLIFactory` from mcp-common, mounted under the `server` Typer sub-app via `SessionBuddyCLI._mount_lifecycle_subtyper()` (`session_buddy/cli/base.py:306-324`):

```python
# session_buddy/cli/base.py:316-324
sb_settings = self._settings or SessionBuddySettings()
factory = MCPServerCLIFactory(
    server_name=sb_settings.server_name,
    settings=t.cast("MCPServerSettings", sb_settings),
    start_handler=self._start_handler or start_server_handler,
    health_probe_handler=lambda: _run_health_probe(sb_settings),
)
lifecycle_app = factory.create_app()
self.add_typer(lifecycle_app, name="server")
```

There is **no `session_buddy/cli/server_cli.py`**. The `server` subcommand group (`start`, `stop`, `restart`, `status`, `health`) comes from mcp-common's `factory.create_app()` and is mounted as a Typer sub-app under the name `server` to avoid colliding with `OneiricCLIBase`'s `health` verb.

### 1.2 What `server start` does — full lifecycle

The handler is `MCPServerCLIFactory._cmd_start` in `mcp_common/cli/factory.py:429-486`:

1. Reads Typer options: `force: bool` (`--force`), `json_output: bool` (`--json`), `health_disable_decay: bool` (`--health-disable-decay`).
2. If `health_disable_decay`, sets `HEALTH_FEED_HALFLIFE_SECONDS=0` and emits an OTel `health.aggregate.decay_disabled` event for incident triage (factory.py:458-480).
3. `_validate_cache_and_check_process(force, json_output)` — calls `validate_cache_ownership(cache_root)` then `_handle_stale_pid(pid_path, force)` (factory.py:541-586).
4. `_write_pid_and_health_snapshot()` — writes `os.getpid()` to `settings.pid_path()` and writes an initial `RuntimeHealthSnapshot(orchestrator_pid=pid, watchers_running=True)` to `settings.health_snapshot_path()` (factory.py:588-600).
5. `_register_signal_handlers(json_output)` — installs `SignalHandler(on_shutdown=shutdown).register()` which catches `SIGTERM` and `SIGINT`. The shutdown callback updates the health snapshot (`watchers_running=False`), unlinks the PID file, and prints "Server stopped" (factory.py:602-619 + signals.py:14-110).
6. `_execute_start_handler(json_output)` — calls `self.start_handler()` (which is sb's `start_server_handler` from `base.py:116-147`). This is the **only sb-specific code path** in the start sequence.
7. `sys.exit(ExitCode.SUCCESS)` — note: the process exits 0 here, so `start_handler` is expected to block (the FastMCP run call inside it blocks until shutdown). See §1.5 below.

### 1.3 What `--force` means — verbatim from the source

The flag is declared at `factory.py:431-432`:

```python
force: bool = typer.Option(
    False, "--force", help="Force start (kill existing process if stale)"
),
```

But the help text is **misleading**. The actual implementation in `_handle_stale_pid` (`factory.py:373-427`) is:

- **Default behavior** (`auto_clean`, the default `stale_pid_action`): the stale PID file is **auto-removed**, no `--force` needed. Per the comment at lines 399-405:
  > "auto-clean because operators almost always want the next start to succeed after a crash — refusing without `--force` was the source of repeated user confusion."
- **`--force`**: removes a stale PID file with the legacy wording `Removed stale PID file (process {pid} not found)` instead of `Auto-removed stale PID file ...`. The wording difference is the only semantic difference vs `auto_clean`.
- **`--force` is required** when the PID file is **corrupted** (cannot parse to an int) — without `--force`, `start` exits with `ExitCode.STALE_PID` (=8) and message `Corrupted PID file (use --force to remove): {e}` (factory.py:388-395).
- **`--force` does NOT kill a live process**. If the PID points to a live process, `start` exits with `ExitCode.SERVER_ALREADY_RUNNING` (=3) regardless of `--force` (factory.py:426-427). To kill a running instance, the operator must run `server stop` first.

The launchd plist `ProgramArguments` passes `--force` unconditionally (`com.mcp.session-buddy.plist:18-25`), so on every launchd restart it bypasses the auto-clean path and uses the legacy wording. This is **a legacy-compat artifact, not a load-bearing behavior** — the auto-clean path would produce equivalent behavior. Migration should preserve `--force` in the plist to avoid breaking REQ-013 backcompat, but the launcher doesn't need to know about it.

### 1.4 PID file management — concrete paths and contents

- **Path**: `cache_dir/mcp_server.pid` where `cache_dir` is the Oneiric `cache_dir` setting. For sb, this resolves via `SessionBuddySettings.cache_root` (which aliases `cache_dir` for mcp-common compat — `base.py:111-113`) to e.g. `~/.cache/session-buddy/mcp_server.pid` on a default install.
- **Write**: `write_pid_file(settings.pid_path(), os.getpid())` in `_write_pid_and_health_snapshot` (factory.py:591-592).
- **Read**: `_handle_stale_pid` reads `pid_path.read_text().strip()` (factory.py:388-389).
- **Remove**: (a) by `_handle_stale_pid` when stale/corrupt + `--force` (factory.py:392-393, 410); (b) by the shutdown callback `signal_handler` unlinks via `pid_path.unlink(missing_ok=True)` (factory.py:612-613).
- sb also has a separate reader `_read_running_pid` (`base.py:184-191`) used by `_run_health_probe` to surface the orchestrator PID in health snapshots.

### 1.5 Signal handlers — concrete handlers installed

`SignalHandler.register()` (`signals.py:45-51`) installs:

- `signal.SIGTERM` → `_handle_shutdown` — graceful shutdown (cleanup callback + `os._exit(0)`).
- `signal.SIGINT` → `_handle_shutdown` — same.
- `signal.SIGHUP` → **NOT installed** (sb does not supply `on_reload`).

The shutdown callback `_handle_shutdown` (`signals.py:53-97`) is **not** a no-op: it calls `on_shutdown()` (which unlinks the PID file and updates the health snapshot) and then uses `os._exit(0)` rather than `sys.exit(0)`. The comment at lines 59-73 explains: `os._exit` is a C-level syscall that skips Python's exception machinery, which matters because `sys.exit(SystemExit)` would propagate through the asyncio event loop and disrupt FastMCP/uvicorn's lifespan teardown — using `os._exit` keeps the process in a clean state after the shutdown callback returns. **This is launchd-relevant**: when launchd sends SIGTERM during `launchctl unload`, this handler guarantees the PID file is removed within the grace window.

### 1.6 Subprocess invocation

**None.** `run_server()` (`session_buddy/server_optimized.py:932-986`) is called directly as a blocking function inside `start_server_handler` (`base.py:147`). No `execvp`, no `Popen`, no daemonization. The process IS the FastMCP server.

### 1.7 Environment variables set

- `_cmd_start` sets `HEALTH_FEED_HALFLIFE_SECONDS=0` only if `--health-disable-decay` is passed (factory.py:458-459). sb's launchd plist does **not** pass this flag.
- `start_server_handler` sets nothing. It instantiates `SessionBuddySettings()` (which reads `MAHAVISHNU__HTTP_PORT` / `SESSION_BUDDY__HTTP_PORT` env vars via Oneiric layer-config).
- The plist's `EnvironmentVariables` (lines 28-37 of the plist) inject `PATH`, `LANG`, `LOG_LEVEL`, `MCP_PORT=8678`, `PYTHONUNBUFFERED`. `MCP_PORT` is **read by mcp-common's `MCPServerSettings`** (not by sb's `start_server_handler` directly), but sb's `SessionBuddySettings.http_port` defaults to `8678` and the plist's `MCP_PORT=8678` is belt-and-braces.

---

## 2. Launcher overlap analysis

### 2.1 Transport — MISMATCH (migration side effect)

- **sb current**: `transport="streamable-http"` at `session_buddy/server_optimized.py:975`.
- **launcher**: `transport="http"` in `launcher.py:187`.

This is a real difference, not a no-op. The launcher comment at `launcher.py:17-20` documents that it pins `transport="http"` for the fleet-standard HTTP endpoint. `streamable-http` is FastMCP's MCP-native streaming HTTP transport; `http` is plain HTTP. They expose the same `/mcp` path but use different protocol semantics (MCP-over-streamable-http vs plain JSON-RPC). sb has been running `streamable-http` successfully since the lifespan/grace timeout work was done; the launcher's `http` choice would either work (FastMCP may accept both) or require a `--transport=streamable-http` kwarg on the launcher.

**Recommendation**: extend the launcher with an optional `transport: str = "http"` kwarg (REQ-007 wording is `transport="http"` but the spec is "HTTP transport" — `streamable-http` is also HTTP). This is a 3-line extension to `launcher.py:199-208` and keeps mcp-common 0.27.x compatible. Alternatively, accept that sb's existing `streamable-http` call is intentional and document it as a per-component closure override.

### 2.2 Uvicorn grace — ALREADY MATCHING (no migration cost)

- **sb current**: `uvicorn_config={"timeout_graceful_shutdown": 30}` at `session_buddy/server_optimized.py:979`. **Verified — line 979 confirmed.**
- **launcher default**: `timeout_graceful_shutdown: int = 30` in `launcher.py:207`, threaded through to `uvicorn_config` in `launcher.py:190`.

Migration is a no-op for this parameter — sb's existing site already matches the launcher's pinned value. The 30-second timeout exists because sb's `session_lifecycle`'s `end_session` cleanup runs PRE/SESSION hooks, `perform_quality_assessment`, and handoff-doc generation during shutdown (see comment at `server_optimized.py:966-973`), and FastMCP's hardcoded 2-second default cuts that work off mid-shutdown. The launcher's default of 30 is exactly what sb needs.

### 2.3 Secrets loading — NEW BEHAVIOR (launcher adds what sb lacks)

- **sb current**: No `~/.config/secrets.env` loading. The launchd plist's `EnvironmentVariables` (`com.mcp.session-buddy.plist:28-37`) injects `PATH`, `LANG`, `LOG_LEVEL`, `MCP_PORT`, `PYTHONUNBUFFERED` — **no API keys**.
- **launcher**: `load_secrets(secrets_path)` reads `~/.config/secrets.env` and merges into `os.environ` via `setdefault` (launcher.py:243-253).

Migration **adds** secrets loading to sb. For sb, the relevant secrets are likely `SESSION_BUDDY_AUTH_*`, `AKOSHA_API_KEY`, `OPENAI_API_KEY` (used by embedding code) — check before merging. If `secrets.env` doesn't exist on the box, `load_secrets` returns `{}` (launcher.py:90-91) and the launch is a no-op for secrets. **Risk**: low — `setdefault` semantics mean an existing env var (from the plist or shell) always wins.

### 2.4 Health feed warming — sb has a feed; warming semantics differ

- **sb current**: `_write_pid_and_health_snapshot` writes a `RuntimeHealthSnapshot(orchestrator_pid, watchers_running=True)` (factory.py:588-600). This is a **runtime health snapshot**, not a `HealthFeedState`. mcp-common has both surfaces: `RuntimeHealthSnapshot` is the CLI-friendly aggregate; `HealthFeedState` is the per-feed state with `is_healthy()` semantics that gate `/health=200`.
- **launcher**: `warm_settings_feed(settings_path)` pre-warms **only** the `settings` feed (launcher.py:117-154). Per `mcp_common/health/feed.py:202-211`, `is_healthy()` returns HEALTHY **only when `entities_count > 0`**, so the launcher reads `settings.yaml` to confirm it parses and calls `record_success(state, entities_count=1)`.
- **sb**: Has `SessionBuddySettings` (Oneiric `OneiricMCPConfig`-based) which reads from the same Oneiric layer-config. sb does **not** currently call `warm_settings_feed`. If `/health` is wired through `HealthFeedState.is_healthy()`, sb's settings feed would currently be `WARMING_UP_EMPTY_FEED` on first probe until a tool call populates it.
- **Migration adds**: `warm_settings_feed(settings.yaml_path)` call inside the `build_server` closure (or as a launcher kwarg). The settings path can be derived from `SessionBuddySettings().paths.config_dir / "settings.yaml"` (or whatever Oneiric exposes for the user config dir — verify).

**Risk**: medium. If sb's `/health` is currently 200 without feed warming, adding warming is a no-op. If `/health` is currently 503 because the settings feed is empty, warming flips it to 200 — that's a migration benefit, not a regression. Verify on a live box before merging.

---

## 3. Decision: migrate or replace?

**Outcome B1 — Replace + preserve pid/signal layer.**

Rationale:

1. The CLI subcommand (`server start --force`) **stays unchanged**. It's mcp-common's `MCPServerCLIFactory._cmd_start`, used by the launchd plist's `ProgramArguments` (`com.mcp.session-buddy.plist:18-25`), and changing the public CLI shape breaks REQ-013 backcompat. The plan's worry about "preserving --force semantics" is moot — `--force` belongs to mcp-common, not sb.
2. PID file write/read/remove: **stays in mcp-common**. The factory's `_write_pid_and_health_snapshot` and `_handle_stale_pid` already do this. sb's `start_server_handler` doesn't touch the PID file directly. Migration does **not** move any pid-file logic into sb.
3. Signal handlers: **stay in mcp-common**. `SignalHandler.register()` in `_register_signal_handlers` already installs `SIGTERM` + `SIGINT`. sb's `start_server_handler` does not install its own handlers.
4. **The only sb-specific migration target** is `start_server_handler` (`session_buddy/cli/base.py:116-147`), and the only piece inside it that's non-launcher is the `_port_holder` pre-bind check.

**Outcome A (drop-in replace) is rejected**: the `_port_holder` check prevents a real failure mode that the launcher doesn't address. Removing it would reintroduce the bind-fail-exit death loop that the check was added to fix (per the docstring at `base.py:117-125`).

**Outcome C (don't migrate) is rejected**: the launcher adds two behaviors sb lacks (secrets loading, settings feed warming) and pins the launcher's transport/http choice for fleet consistency. Keeping sb on `run_server(host, port)` blocks the wire-up contract enforcement goal.

---

## 4. Proposed migration shape (Outcome B1)

### 4.1 Typer command surface — unchanged

`session_buddy server start --force` continues to route through `MCPServerCLIFactory._cmd_start`. **No changes to `session_buddy/cli/base.py`'s CLI registration** (`_mount_lifecycle_subtyper` stays as-is).

### 4.2 `start_server_handler` rewrite — preserves pre-bind check, replaces run call

The current handler (`base.py:116-147`):

```python
def start_server_handler() -> None:
    """Start handler that launches the Session Buddy MCP server."""
    from session_buddy.server_optimized import run_server

    settings = SessionBuddySettings()

    print("🚀 Starting Session Management MCP Server...")
    print(f"HTTP Port: {settings.http_port}")
    print(f"WebSocket Port: {settings.websocket_port}")

    holder = _port_holder(settings.http_port)
    if holder is not None:
        pid, command = holder
        msg = (
            f"Port {settings.http_port} is already in use by PID {pid} "
            f"({command[:60]!r}).\n"
            f"Either stop the existing process or use a different port via "
            f"the MAHAVISHNU__HTTP_PORT / SESSION_BUDDY__HTTP_PORT env var.\n"
            f"Refusing to start to avoid the bind-fail-exit death loop."
        )
        raise SystemExit(msg)

    # Launch the server with HTTP transport
    run_server(host="127.0.0.1", port=settings.http_port)
```

After migration:

```python
def start_server_handler() -> None:
    """Start handler that launches the Session Buddy MCP server via mcp-common launcher."""
    import asyncio
    from mcp_common.server import launch
    from session_buddy.server_optimized import mcp

    settings = SessionBuddySettings()

    print("🚀 Starting Session Management MCP Server...")
    print(f"HTTP Port: {settings.http_port}")
    print(f"WebSocket Port: {settings.websocket_port}")

    holder = _port_holder(settings.http_port)
    if holder is not None:
        pid, command = holder
        msg = (
            f"Port {settings.http_port} is already in use by PID {pid} "
            f"({command[:60]!r}).\n"
            f"Either stop the existing process or use a different port via "
            f"the MAHAVISHNU__HTTP_PORT / SESSION_BUDDY__HTTP_PORT env var.\n"
            f"Refusing to start to avoid the bind-fail-exit death loop."
        )
        raise SystemExit(msg)

    # Launch the FastMCP server via mcp-common launcher.
    # ``mcp`` is the module-level FastMCP instance built in server_optimized.py:287
    # with the session_lifecycle lifespan and version wiring. The launcher handles
    # secrets loading, settings-feed warming, transport="http", and uvicorn
    # timeout_graceful_shutdown=30 — see mcp_common/server/launcher.py.
    asyncio.run(launch(
        build_server=lambda: mcp,
        component_name="session-buddy",
        secrets_path=Path("~/.config/secrets.env"),
        settings_path=None,  # TODO: derive from Oneiric layer config; verify
        host="127.0.0.1",
        port=settings.http_port,
    ))
```

### 4.3 What this rewrites in `run_server`

`run_server(host, port)` (`server_optimized.py:932-986`) currently does both **build** (the `mcp.run(...)` call at line 974) and **run** (the `mcp.run(transport="streamable-http", host=host, port=port, path="/mcp", uvicorn_config={"timeout_graceful_shutdown": 30})` at lines 974-980). After migration, the run call goes to the launcher. **Two options**:

- **(preferred) Split `run_server` into `build_server()` and a thin runner**: extract the `mcp.run(...)` call into the closure (or keep it in `run_server` and have the closure call `run_server`). The module-level `mcp = FastMCP(...)` instance at line 287 is already a buildable object — `lambda: mcp` works without refactor.
- **(simpler) Keep `run_server` and call it from the closure**: `build_server=lambda: (mcp, lambda: run_server(host, port))[1]()` — but this re-enters the `mcp.run(...)` loop, defeating the launcher's transport/grace enforcement. **Reject.**

**Recommended**: extract `run_server` so the module-level `mcp` is the buildable and the runner is gone. The `run_server` function then becomes either (a) deleted, or (b) a thin alias around `asyncio.run(launch(...))` for backward compat (callers in `tests/` may use it).

### 4.4 Launcher kwargs needed

The signature in `launcher.py:199-208` already supports what sb needs:

- `build_server: Callable[..., Any]` — `lambda: mcp` works (sb's `mcp` is the FastMCP instance).
- `component_name: str` — `"session-buddy"`.
- `secrets_path: Path | None = None` — pass `Path("~/.config/secrets.env")`.
- `settings_path: Path | None = None` — **open question**: derive from `SessionBuddySettings().paths.config_dir / "settings.yaml"` or skip (let `/health` 503 until tool calls populate). Pick based on the live `/health` probe in §2.4.
- `host: str = "127.0.0.1"` — sb binds 127.0.0.1.
- `port: int = 8680` — sb uses `settings.http_port` (default 8678).
- `timeout_graceful_shutdown: int = 30` — sb's line 979 already matches; pass-through default is fine.

**No launcher kwarg extensions needed for sb.** If sb needs `transport="streamable-http"`, that's a per-component decision documented in the cookbook, not a launcher kwarg.

### 4.5 `_port_holder` — keep as a pre-launch hook

`_port_holder` (`base.py:150-181`) is `start_server_handler`'s only sb-specific lifecycle work. It does NOT need to move into the launcher — keep it in `start_server_handler` as a guard before the `launch(...)` call. The launcher doesn't have a "port-already-in-use" check (and shouldn't — different components may bind the same port in test scenarios).

---

## 5. Backward Compatibility Test Matrix row for sb

| Component | Public CLI commands | Launchd plist ProgramArguments | Smoke test |
|---|---|---|---|
| **sb (session-buddy)** | `python -m session_buddy server start [--force] [--json] [--health-disable-decay]`<br>`python -m session_buddy server stop [--timeout N] [--force]`<br>`python -m session_buddy server restart [--force]`<br>`python -m session_buddy server status [--json]`<br>`python -m session_buddy server health [--json]`<br>`python -m session_buddy version`<br>`python -m session_buddy doctor [--json]`<br>`python -m session_buddy health` (OneiricCLIBase-provided)<br>`python -m session_buddy checkpoint cleanup-snapshots`<br>`python -m session_buddy analytics {sessions,duration,components,errors,active,report,sql}` | `/Users/les/.local/state/mcp/scripts/launch_with_healthcheck.sh http://127.0.0.1:8678/health --timeout 60 -- /Users/les/Projects/session-buddy/.venv/bin/python -m session_buddy server start --force` | `python -m session_buddy server start --force` (foreground); `curl -fsS http://127.0.0.1:8678/health` returns HTTP 200; `kill -TERM <pid>` exits 0 within `timeout_graceful_shutdown` window |

**Migration validation** for this row:
- `python -m session_buddy server start --force` exits 0 only after pre-bind check passes AND the launcher has bound port 8678.
- `python -m session_buddy server start --json` returns a JSON envelope from `_cmd_start` and then the launcher runs (the JSON exit is from mcp-common's pre-launch sequence; the launcher runs after).
- `python -m session_buddy server stop` cleanly stops the launcher-managed process via SIGTERM and removes the PID file.
- The launchd plist's `ProgramArguments` is unchanged (REQ-013).
- `curl -fsS http://127.0.0.1:8678/health` returns 200 with body containing `"launcher": "mcp_common.server.launcher@0.1.0"` (REQ-005) — **NEW check, not required by current behavior**.
- `kill -TERM <pid>` exits 0 within 30s (REQ-014) — same as current behavior since both mcp-common's pre-launch signal handler and the launcher's `run_with_uvicorn_config` honor SIGTERM.

---

## 6. Risks

### 6.1 `--force` semantics — RESOLVED (no risk)

`--force` is mcp-common's flag, not sb's. The factory handles it identically before and after migration. The only nuance: the launcher's `load_secrets` runs **before** `_cmd_start`'s PID checks (launcher.py:243-253 fires before `start_handler` is called). If secrets loading raises, sb sees the launcher's exception rather than mcp-common's PID-cleanup. This is **better** behavior (secrets problem surfaces immediately, not after PID dance), and the loader catches `OSError` (launcher.py:106-108), so it cannot raise.

### 6.2 `RunAtLoad=true` on the plist — **MEDIUM RISK**

`com.mcp.session-buddy.plist:42-43` has `<key>RunAtLoad</key><true/>`. Per `feedback-macos-reboot-launchd-keepalive-cascade`, plists needing DB readiness should set `RunAtLoad=false` and rely on the `launch_with_healthcheck.sh` wrapper for retry. sb uses **SQLite local file** (no remote DB dependency on boot) but the **`launch_with_healthcheck.sh` wrapper IS the safeguard** (`/Users/les/.local/state/mcp/scripts/launch_with_healthcheck.sh http://127.0.0.1:8678/health --timeout 60`). Per the user's 2026-09 incident retrospective, the cascade-failure was specifically about Redis/Postgres boot-order, not SQLite. **Verdict**: `RunAtLoad=true` is acceptable for sb today; document but don't change.

If sb ever adopts Redis for hot-path (e.g. for `MemoryAggregator`-style cross-pool sync), flip `RunAtLoad` to `false` and rely on the wrapper's `--timeout 60` retry window.

### 6.3 Line 979 `uvicorn_config` — RESOLVED (no risk)

Confirmed at `session_buddy/server_optimized.py:979`. Value `30` matches the launcher's default. Migration is a no-op for this parameter — sb's existing site stays (or gets removed entirely if `run_server` is refactored per §4.3).

### 6.4 Hidden `server start` work — **LOW RISK**

The only places where `start` does work beyond "PID + signal + start_handler" are:

- `_cmd_start` writes `HEALTH_FEED_HALFLIFE_SECONDS=0` if `--health-disable-decay` (factory.py:458-480). sb's plist does **not** pass this; not a migration concern.
- `_cmd_start` emits an OTel `health.aggregate.decay_disabled` event (factory.py:473-480). Same — not triggered by sb's plist.
- The OTel event uses `suppress(ImportError)` so it no-ops if OTel is not installed (factory.py:473).

No supervisor/cron/healthcheck-touching code hidden in the CLI. Migration risk is low.

### 6.5 `transport` mismatch — **LOW RISK**

sb uses `transport="streamable-http"` (server_optimized.py:975); launcher enforces `transport="http"` (launcher.py:187). Migration flips sb to `"http"` unless we add a launcher kwarg. **Verify against live `/mcp` probe** before merging — if Claude Code clients (Claude Code, Claude Desktop, mcp-cli) connect successfully to `streamable-http`, they may also accept `http`. If they don't, sb needs either a launcher kwarg or a one-line `build_server` closure that monkey-patches the FastMCP instance's transport default. **Recommended first step**: smoke test the migration against a real Claude Code client before committing the launcher swap.

### 6.6 Secrets loading — **LOW RISK** but verify before merging

The launcher's `load_secrets` is a **NEW behavior** for sb. If sb currently relies on the plist's `EnvironmentVariables` for keys that should NOT be in `secrets.env`, the launcher's `setdefault` (launcher.py:248) preserves the existing value — no regression. If sb currently relies on `~/.config/secrets.env` being **NOT** loaded (e.g. for test isolation), this is a behavior change. **Verify**: check whether any sb test fixture or local-dev workflow depends on secrets.env being absent from `os.environ`. None found in the search, but worth a regression test in `tests/cli/test_server_start.py`.

### 6.7 Health feed warming — **MEDIUM RISK** if `/health` is currently broken

If sb's `/health` is currently 503 (settings feed empty), warming flips it to 200. If it's currently 200 (e.g. via a different code path), warming is a no-op. **Verify**: `curl -fsS http://127.0.0.1:8678/health` pre-migration, check the `checks.settings.healthy` field. If `false`, the migration is a side benefit. If `true` already, the migration is also fine (warming is idempotent).

---

## 7. Migration steps (for the implementer)

Same 5-gate pattern as vishnu/cj (plan §5 Phase 4a Task 4a.3). Adapted for sb:

- [ ] **Gate 1 — Pre-migration baseline**: `curl /health` on port 8678, record current body. Confirm `kill -TERM <pid>` exits 0 within 30s. Confirm launchd plist starts cleanly after `launchctl unload && launchctl load`.
- [ ] **Gate 2 — Refactor `run_server` into a buildable**: split `server_optimized.py:run_server` so the module-level `mcp` is the buildable returned by a `build_server()` closure, and the FastMCP `mcp.run(...)` call at lines 974-980 is removed (it moves to the launcher).
- [ ] **Gate 3 — Rewrite `start_server_handler`**: replace `run_server(host="127.0.0.1", port=settings.http_port)` with `asyncio.run(launch(build_server=lambda: mcp, component_name="session-buddy", ...))`. Keep the `_port_holder` pre-bind check exactly as-is.
- [ ] **Gate 4 — Add tests**:
  - `tests/cli/test_start_server_handler.py`: `test_start_server_handler_calls_launch_with_lambda_mcp`, `test_start_server_handler_raises_systemexit_when_port_held`, `test_start_server_handler_passes_component_name_session_buddy`.
  - `tests/server/test_launcher_smoke.py` (in session-buddy): spawn the handler in a subprocess, assert `/health=200` and the launcher field is present.
- [ ] **Gate 5 — Commit** (no version bump; user does via `crackerjack run -p minor`):
  ```bash
  git -c user.email=les@wedgwoodwebworks.com -c user.name=les \
      add session_buddy/cli/base.py session_buddy/server_optimized.py \
          tests/cli/test_start_server_handler.py tests/server/test_launcher_smoke.py
  git -c user.email=les@wedgwoodwebworks.com -c user.name=les \
      commit -m "feat(session-buddy): migrate MCP startup to mcp-common launcher (REQ-013)"
  ```

---

## 8. Commit sketch

```bash
# Inside session-buddy repo:
git -c user.email=les@wedgwoodwebworks.com -c user.name=les \
    add session_buddy/cli/base.py session_buddy/server_optimized.py \
        tests/cli/test_start_server_handler.py tests/server/test_launcher_smoke.py
git -c user.email=les@wedgwoodwebworks.com -c user.name=les \
    commit -m "feat(session-buddy): migrate MCP startup to mcp-common launcher (REQ-013)

- Replace run_server() blocking call in start_server_handler with
  mcp_common.server.launcher.launch() so HTTP transport, uvicorn
  timeout_graceful_shutdown=30, secrets loading, and settings feed
  warming are enforced by mcp-common rather than scattered across
  per-component glue.
- Preserve _port_holder pre-bind check to keep the bind-fail-exit
  death loop fix from base.py:117-125.
- Refactor server_optimized.run_server so the module-level FastMCP
  instance (mcp) is the buildable returned by the launcher's
  build_server closure; the mcp.run(...) call moves to the launcher.
- CLI surface (server start --force) and launchd plist
  ProgramArguments unchanged (REQ-013 backcompat)."
```

---

## 9. Cross-references

- Plan: `/Users/les/Projects/mahavishnu/docs/plans/2026-09-26-mcp-launcher-standardization.md` §5 Phase 4b Task 4b.4
- REQ-013: Backward Compatibility Test Matrix
- REQ-014: Signal-handling smoke (kill -TERM exits 0)
- REQ-007: `transport="http"` + `uvicorn_config={"timeout_graceful_shutdown": 30}` enforcement
- sb's CLI mount: `session_buddy/cli/base.py:306-324` (SessionBuddyCLI._mount_lifecycle_subtyper)
- sb's handler: `session_buddy/cli/base.py:116-147` (start_server_handler)
- sb's pre-bind check: `session_buddy/cli/base.py:150-181` (_port_holder)
- sb's uvicorn grace site (verified): `session_buddy/server_optimized.py:979`
- sb's FastMCP instance (buildable for closure): `session_buddy/server_optimized.py:287`
- mcp-common's start verb: `mcp_common/cli/factory.py:429-486` (_cmd_start)
- mcp-common's --force semantics: `mcp_common/cli/factory.py:373-427` (_handle_stale_pid)
- mcp-common's PID write: `mcp_common/cli/factory.py:588-600` (_write_pid_and_health_snapshot)
- mcp-common's signal handler install: `mcp_common/cli/factory.py:602-619` (_register_signal_handlers)
- mcp-common's SignalHandler: `mcp_common/cli/signals.py:14-110`
- mcp-common's launcher: `mcp_common/server/launcher.py:1-273`
- sb launchd plist: `~/Library/LaunchAgents/com.mcp.session-buddy.plist`
