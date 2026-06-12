"""Operational health check for session-buddy.

Exposes ``doctor`` checks that surface the "wiring is broken but the
surface looks fine" class of bugs. Each check returns a
:class:`~session_buddy.health_checks.ComponentHealth` so output formatting
and exit-code logic can be shared with the existing health subsystem.

Why this module exists
----------------------
Session-buddy historically accumulated MCP tools and adapter features
faster than it accumulated integration tests for them. As a result,
several pieces of the surface area (code graph listing, v2 migration,
semantic search of codebases, automatic session capture) shipped
partially-broken while the manual / ``/session-buddy:checkpoint`` path
kept working — masking the gaps from daily use. The doctor turns
those gaps into named, fail-fast assertions so the next regression
cannot ship silently.

Usage
-----
::

    from session_buddy.doctor import run_all_doctor_checks

    results = await run_all_doctor_checks()
    for r in results:
        print(r.name, r.status, r.message)

Or via the CLI (registered in :mod:`session_buddy.cli`)::

    python -m session_buddy doctor
    python -m session_buddy doctor --json
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import typer

from session_buddy.health_checks import (
    ComponentHealth,
    HealthStatus,
    check_database_health,
    check_dependencies_health,
    check_file_system_health,
    check_python_environment_health,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Reused checks
# ---------------------------------------------------------------------------
# The four legacy health checks already cover the basics. We just re-export
# them under their existing names so the doctor can call them uniformly.
check_python_env = check_python_environment_health
check_file_system = check_file_system_health
check_dependencies = check_dependencies_health


async def check_database(db_path: Path | None = None) -> ComponentHealth:
    """Doctor wrapper around :func:`check_database_health`.

    Accepts an optional ``db_path`` so the aggregator can centralize path
    resolution. The underlying ``check_database_health`` uses the singleton
    reflection adapter, so the ``db_path`` is currently a no-op for this
    check — the path is plumbed for symmetry with the other DB-using
    checks (``check_v2_migration``, ``check_auto_capture_recent``) so the
    aggregator can resolve the canonical path once and pass it everywhere.
    """
    return await check_database_health()


# ---------------------------------------------------------------------------
# New checks
# ---------------------------------------------------------------------------
async def check_v2_migration(db_path: Path | None = None) -> ComponentHealth:
    """Verify the v2 schema migration has been applied.

    Pass: ``current_version == "v2"`` and ``v2_conversations > 0``.
    Degraded: migration ran but v2 is empty.
    Fail: migration never ran (v1 still current).
    """
    name = "v2_migration"
    try:
        # ``get_migration_status`` in session_buddy.memory.migration is the
        # backing function for the MCP tool. It accepts an optional db_path
        # and returns the same dict shape.
        from session_buddy.memory.migration import get_migration_status

        status = get_migration_status(db_path)
    except Exception as exc:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Failed to read migration status: {exc}",
        )

    # ``status`` shape (per migration_tools.py):
    # { current_version: str, migration_history: list[...], counts: {v1: int, v2: int} }
    if not isinstance(status, dict):
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Migration status returned unexpected shape: {type(status).__name__}",
        )
    version = status.get("current_version", "unknown")
    counts: dict[str, Any] = status.get("counts", {}) or {}
    v2_count = int(counts.get("v2_conversations", 0) or 0)
    history: list[dict[str, Any]] = status.get("migration_history", []) or []

    if version == "v2" and v2_count > 0:
        return ComponentHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            message=f"v2 schema active ({v2_count} conversations)",
            metadata={"version": version, "v2_conversations": v2_count},
        )
    if version == "v2":
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message="v2 active but contains 0 conversations; migration may be partial",
            metadata={"version": version, "v2_conversations": v2_count},
        )
    return ComponentHealth(
        name=name,
        status=HealthStatus.UNHEALTHY,
        message=(
            f"Schema is {version!r}; run trigger_migration(create_backup_first=True) to upgrade"
        ),
        metadata={
            "version": version,
            "history_count": len(history),
            "v2_conversations": v2_count,
        },
    )


async def check_code_graph_adapter() -> ComponentHealth:
    """Regression guard: ``ReflectionDatabaseAdapterOneiric`` must expose ``_get_conn``.

    Background: when the adapter was migrated to the Oneiric / DuckDB
    implementation, it dropped the ``_get_conn`` shim that
    ``code_graph_subscriber`` and ``reflection/storage`` call defensively.
    The resulting ``AttributeError`` crashed ``list_code_graphs``,
    ``code_call_chain``, and ``code_impact_analysis`` at runtime. This
    check ensures the shim stays present.
    """
    name = "code_graph_adapter"
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )
    except ImportError as exc:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Could not import the adapter class: {exc}",
        )
    if hasattr(ReflectionDatabaseAdapterOneiric, "_get_conn"):
        return ComponentHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            message="_get_conn shim present on ReflectionDatabaseAdapterOneiric",
        )
    return ComponentHealth(
        name=name,
        status=HealthStatus.UNHEALTHY,
        message=(
            "ReflectionDatabaseAdapterOneiric is missing _get_conn; "
            "code_graph MCP tools will crash at runtime"
        ),
    )


async def check_code_index_round_trip() -> ComponentHealth:
    """Ingest a marker file, search for its symbols, assert at least one hit.

    This is the round-trip that the production ``code_search_symbols``
    tool depends on. If the underlying knowledge-graph adapter is broken
    (e.g. v2 migration never ran), this check fails with the same error
    the production tool would surface.
    """
    name = "code_index_round_trip"
    marker = f"DoctorMarker_{uuid.uuid4().hex[:8]}"
    src = f"def {marker}():\n    return 42\n"
    with tempfile.TemporaryDirectory(prefix="sb_doctor_") as tmp:
        target = Path(tmp) / f"{marker}.py"
        target.write_text(src)
        try:
            from session_buddy.mcp.tools.code_analysis.tools import (
                _code_ingest_file_impl,
                _code_search_symbols_impl,
            )

            ingest = await _code_ingest_file_impl(
                str(target), project="doctor_round_trip"
            )
            search = await _code_search_symbols_impl(
                marker, project="doctor_round_trip", limit=5
            )
        except Exception as exc:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Round-trip raised: {type(exc).__name__}: {exc}",
            )

    if isinstance(ingest, dict) and ingest.get("status") != "success":
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Ingest failed: {ingest.get('error', 'unknown')}",
            metadata={"ingest": ingest},
        )
    if not isinstance(search, dict):
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Search returned unexpected shape: {type(search).__name__}",
        )
    total = int(search.get("total", 0) or 0)
    symbols: list[dict[str, Any]] = search.get("symbols", []) or []
    matched = [s for s in symbols if s.get("name") == marker]
    if matched:
        return ComponentHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            message=f"Ingested and re-found {marker} ({total} matches)",
            metadata={"marker": marker, "total": total},
        )
    return ComponentHealth(
        name=name,
        status=HealthStatus.UNHEALTHY,
        message=(
            f"Ingested {marker} but search returned {total} hits; "
            f"code graph DB is not storing ingested symbols"
        ),
        metadata={"marker": marker, "search": search},
    )


async def check_auto_capture_recent(db_path: Path | None = None) -> ComponentHealth:
    """The real signal: are auto-captured sessions being recorded?

    Counts checkpoints in the last 24h with ``is_manual=False`` (i.e. the
    lifespan path, not the user-triggered ``/session-buddy:checkpoint``
    tool). If zero, the auto-capture pipeline is broken even if the
    manual path still works.
    """
    name = "auto_capture_recent"
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )
        from session_buddy.adapters.settings import ReflectionAdapterSettings
    except ImportError as exc:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Could not import reflection adapter: {exc}",
        )

    try:
        if db_path is None:
            from session_buddy.settings import get_settings

            settings = get_settings()
            db_path = Path(
                getattr(settings, "database_path", None)
                or getattr(settings, "reflection_db_path", None)
                or ":memory:"
            )
        if str(db_path) == ":memory:":
            # In-memory means no real production data to inspect.
            return ComponentHealth(
                name=name,
                status=HealthStatus.DEGRADED,
                message="Reflection DB is :memory:; cannot inspect auto-capture data",
            )
        adapter_settings = ReflectionAdapterSettings.from_settings()
        db = ReflectionDatabaseAdapterOneiric(
            collection_name="default",
            settings=adapter_settings,
            db_path=str(db_path),
        )
        await db.initialize()
    except Exception as exc:
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message=f"Could not open reflection DB to count checkpoints: {exc}",
        )

    try:
        now = datetime.now(tz=UTC)
        cutoff_24h = (now - timedelta(hours=24)).isoformat()
        cutoff_7d = (now - timedelta(days=7)).isoformat()

        # Aggregate counts so the verdict can distinguish "no Claude Code
        # sessions were started today" (expected if no one used Claude
        # Code in 24h) from "lifespan path is broken" (would show
        # recent total > 0 but recent auto = 0).
        total = db.conn.execute(
            f"SELECT COUNT(*) FROM {db._table('conversations')}"
        ).fetchone()[0]
        recent_24h = db.conn.execute(
            f"SELECT COUNT(*) FROM {db._table('conversations')} WHERE created_at >= ?",
            [cutoff_24h],
        ).fetchone()[0]
        recent_7d = db.conn.execute(
            f"SELECT COUNT(*) FROM {db._table('conversations')} WHERE created_at >= ?",
            [cutoff_7d],
        ).fetchone()[0]
        result = db.conn.execute(
            f"SELECT id, metadata FROM {db._table('conversations')} "
            "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 200",
            [cutoff_24h],
        ).fetchall()
    except Exception as exc:
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message=f"Checkpoint count query failed: {exc}",
        )
    finally:
        with suppress(Exception):
            await db.aclose()

    auto_count_24h = 0
    for _row_id, metadata_json in result:
        if not metadata_json:
            continue
        try:
            md = (
                json.loads(metadata_json)
                if isinstance(metadata_json, str)
                else metadata_json
            )
        except (TypeError, ValueError):
            continue
        # ``is_manual`` may live at the top level of metadata or nested
        # under ``checkpoint_info``. Both are tolerated.
        flag = md.get("is_manual")
        if flag is None and isinstance(md.get("checkpoint_info"), dict):
            flag = md["checkpoint_info"].get("is_manual")
        if flag is False:
            auto_count_24h += 1

    # Distinguish three failure modes:
    #   1. No sessions at all in 24h  → DEGRADED (just no traffic)
    #   2. Recent sessions exist but none are auto → UNHEALTHY (wiring broken)
    #   3. Recent auto sessions exist → HEALTHY
    if auto_count_24h > 0:
        return ComponentHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            message=f"{auto_count_24h} auto-captured session(s) in last 24h",
            metadata={
                "auto_count_24h": auto_count_24h,
                "recent_24h": recent_24h,
                "recent_7d": recent_7d,
                "total": total,
            },
        )
    if recent_24h > 0:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=(
                f"{recent_24h} conversation(s) in last 24h but 0 with is_manual=False. "
                "The lifespan path is not writing auto checkpoints — every "
                "recent session came from the manual tool path."
            ),
            metadata={
                "auto_count_24h": 0,
                "recent_24h": recent_24h,
                "recent_7d": recent_7d,
                "total": total,
            },
        )
    return ComponentHealth(
        name=name,
        status=HealthStatus.DEGRADED,
        message=(
            f"No conversations in last 24h (7d: {recent_7d}, total: {total}). "
            "This is expected if no Claude Code sessions have started today. "
            "Start a session to verify the lifespan path still works."
        ),
        metadata={
            "auto_count_24h": 0,
            "recent_24h": recent_24h,
            "recent_7d": recent_7d,
            "total": total,
        },
    )


async def check_claude_hooks_config() -> ComponentHealth:
    """Verify the global Claude Code hooks config has the expected events.

    Reads ``/Users/les/.claude/settings.local.json`` (the canonical
    session-buddy hooks host) and asserts ``SessionStart`` and
    ``SessionEnd`` are present, and that the script paths they invoke
    resolve on disk.

    Read-only — does NOT modify the file. If hooks are missing, that's
    a configuration problem the user should fix deliberately, not
    something the doctor should auto-rewire.
    """
    name = "claude_hooks_config"
    settings_path = Path("/Users/les/.claude/settings.local.json")
    if not settings_path.exists():
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"{settings_path} does not exist",
        )
    try:
        data = json.loads(settings_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Could not parse {settings_path.name}: {exc}",
        )

    hooks: dict[str, Any] = data.get("hooks", {}) if isinstance(data, dict) else {}
    required = ("SessionStart", "SessionEnd")
    missing = [ev for ev in required if ev not in hooks]
    if missing:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Missing hook events: {', '.join(missing)}",
            metadata={"missing": missing},
        )

    # Resolve script paths. Each event is a list of matcher groups; each
    # group has a ``hooks`` list with ``command`` strings.
    unresolved: list[str] = []
    for event in required:
        for group in hooks.get(event, []) or []:
            for hook in group.get("hooks", []) or []:
                cmd = hook.get("command", "") if isinstance(hook, dict) else ""
                # Heuristic: pull the first path-like token (starts with /).
                tokens = cmd.split()
                for token in tokens:
                    if token.startswith("/") and token.endswith(".py"):
                        if not Path(token).exists():
                            unresolved.append(token)
                        break
    if unresolved:
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message=(
                f"Hook events present but script(s) missing on disk: {unresolved}"
            ),
            metadata={"unresolved": unresolved},
        )
    return ComponentHealth(
        name=name,
        status=HealthStatus.HEALTHY,
        message="SessionStart and SessionEnd hooks present, scripts resolve",
    )


async def check_server_port_bound(port: int = 8678) -> ComponentHealth:
    """Verify the MCP server is actually listening on its port.

    Distinct from a PID file check: a process can be alive without
    holding the port (e.g. mid-shutdown). Catches the "process exists
    but nothing is listening" failure mode.
    """
    name = "server_port_bound"
    if shutil.which("lsof") is None:
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message="lsof not available; cannot probe port",
        )
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message=f"lsof probe failed: {exc}",
        )
    if result.returncode == 0 and result.stdout.strip():
        # First non-header line has the holder PID.
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        return ComponentHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            message=f"Port {port} is listening ({len(lines) - 1} holder line(s))",
            metadata={"port": port},
        )
    return ComponentHealth(
        name=name,
        status=HealthStatus.UNHEALTHY,
        message=(
            f"Port {port} is not bound. The MCP server is not accepting "
            f"connections — clients will fail to connect."
        ),
        metadata={"port": port},
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------
async def run_all_doctor_checks() -> list[ComponentHealth]:
    """Run all doctor checks (existing + new) and return results.

    Failures in individual checks are caught and reported as
    UNHEALTHY components with the exception type in the message —
    a single broken check should not abort the whole doctor run.
    """
    # Resolve the canonical database path ONCE so all DB-using checks
    # point at the same file. We don't share a single connection across
    # checks (DuckDB connections aren't async-safe for concurrent use),
    # but centralising path resolution means the file path is consistent
    # and we can mock it in tests by patching ``get_database_path``.
    db_path: Path | None = None
    with suppress(Exception):
        from session_buddy.settings import get_database_path

        db_path = get_database_path()

    coros = [
        check_python_env(),
        check_file_system(),
        check_database(db_path),
        check_dependencies(),
        check_v2_migration(db_path),
        check_code_graph_adapter(),
        check_code_index_round_trip(),
        check_auto_capture_recent(db_path),
        check_claude_hooks_config(),
        check_server_port_bound(),
    ]
    results: list[ComponentHealth] = []
    for coro in coros:
        try:
            results.append(await coro)
        except Exception as exc:  # defensive: never let one crash stop the rest
            name = getattr(coro, "__name__", "unknown")
            logger.warning("doctor_check_crashed", check=name, error=str(exc))
            results.append(
                ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check itself crashed: {type(exc).__name__}: {exc}",
                )
            )
    return results


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------
def register_doctor_command(app: typer.Typer) -> None:
    """Register the ``doctor`` subcommand on a Typer ``app``.

    Adds ``python -m session_buddy doctor [--json]`` with the
    conventional factory flags. Output uses the existing
    :class:`~mcp_common.ui.panels.ServerPanels` for text and a stable
    JSON shape for scripting.
    """
    import typer  # local import — Typer is a CLI-only dependency

    @app.command("doctor", help="Run operational health checks and report failures.")
    def doctor_cmd(
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Emit JSON instead of a colored table.",
        ),
        only: list[str] | None = typer.Option(
            None,
            "--check",
            help="Run only the named check (repeatable: --check v2_migration).",
        ),
        timeout: float = typer.Option(
            30.0,
            "--timeout",
            help="Total wall-clock budget in seconds for all checks.",
        ),
    ) -> None:
        asyncio.run(
            _run_doctor_cli(json_output=json_output, only=only, timeout=timeout)
        )


async def _run_doctor_cli(
    json_output: bool, only: list[str] | None, timeout: float
) -> None:
    """Body of the ``doctor`` CLI command. Imports heavy deps locally."""
    from mcp_common.cli.factory import ExitCode
    from mcp_common.ui.panels import ServerPanels

    try:
        results = await asyncio.wait_for(run_all_doctor_checks(), timeout=timeout)
    except TimeoutError:
        if json_output:
            print(
                json.dumps(
                    {
                        "status": "timeout",
                        "error": f"doctor exceeded {timeout}s budget",
                    }
                )
            )
        else:
            print(f"Doctor timed out after {timeout}s")
        raise SystemExit(ExitCode.HEALTH_CHECK_FAILED)

    if only:
        wanted = set(only)
        results = [r for r in results if r.name in wanted]
        if not results:
            if json_output:
                print(
                    json.dumps(
                        {"status": "error", "error": f"no checks matched {only}"}
                    )
                )
            else:
                print(f"No checks matched --check {only}")
            raise SystemExit(ExitCode.CONFIGURATION_ERROR)

    if json_output:
        payload = {
            "status": _aggregate_status(results),
            "exit_code": _exit_code_for(results),
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "checks": [
                {
                    "name": r.name,
                    "status": r.status,
                    "message": r.message,
                    "latency_ms": r.latency_ms,
                    "metadata": r.metadata,
                }
                for r in results
            ],
            "summary": _summary(results),
        }
        print(json.dumps(payload))
    else:
        rows = [(r.name, _format_status(r.status), r.message) for r in results]
        # ServerPanels.status_table prints the rendered table to stdout
        # directly and returns None. Don't wrap in print() or we'll
        # also print "None".
        ServerPanels.status_table(
            title="Session-Buddy Doctor",
            rows=rows,
            headers=("Check", "Status", "Details"),
        )
        print(_format_summary(results))

    raise SystemExit(_exit_code_for(results))


def _aggregate_status(results: list[ComponentHealth]) -> str:
    if any(r.status == HealthStatus.UNHEALTHY for r in results):
        return "unhealthy"
    if any(r.status == HealthStatus.DEGRADED for r in results):
        return "degraded"
    return "healthy"


def _summary(results: list[ComponentHealth]) -> dict[str, int]:
    return {
        "healthy": sum(1 for r in results if r.status == HealthStatus.HEALTHY),
        "degraded": sum(1 for r in results if r.status == HealthStatus.DEGRADED),
        "unhealthy": sum(1 for r in results if r.status == HealthStatus.UNHEALTHY),
    }


def _format_status(status: HealthStatus) -> str:
    if status == HealthStatus.HEALTHY:
        return "✅ Healthy"
    if status == HealthStatus.DEGRADED:
        return "⚠️ Degraded"
    return "❌ Failed"


def _format_summary(results: list[ComponentHealth]) -> str:
    s = _summary(results)
    total = sum(s.values())
    return (
        f"Summary: {s['healthy']} healthy, {s['degraded']} degraded, "
        f"{s['unhealthy']} failed (of {total} checks)"
    )


def _exit_code_for(results: list[ComponentHealth]) -> int:
    """Map aggregated status to ExitCode."""
    # Local import to avoid hard import at module load (doctor may run
    # in environments where mcp_common isn't on the path).
    from mcp_common.cli.factory import ExitCode

    if any(r.status == HealthStatus.UNHEALTHY for r in results):
        return ExitCode.HEALTH_CHECK_FAILED
    return ExitCode.SUCCESS
