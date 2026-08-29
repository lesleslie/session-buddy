#!/usr/bin/env python3
# ruff: noqa: EXE001
"""OneiricCLIBase subclass for Session-Buddy's main entrypoint.

Adopts the shared Bodai CLI surface from oneiric 0.19.0 so session-buddy
exposes the same ``version`` / ``doctor`` / ``health`` / ``--json`` /
``--version`` UX as the rest of the Core 7 Bodai components.

This module is the canonical home for ``SessionBuddyCLI`` and its
supporting helpers (``SessionBuddySettings``, ``start_server_handler``,
``_port_holder``, ``_read_running_pid``, ``_run_health_probe``). The
legacy ``session_buddy/cli/__init__.py`` re-exports them so callers
that import from either location keep working.

Surface changes vs the legacy MCPServerCLIFactory-based CLI:

- ``session-buddy version`` (was implicit ``--version``).
- ``session-buddy doctor`` — OneiricCLIBase-provided; ``_doctor_checks``
  delegates to ``session_buddy.doctor.run_all_doctor_checks``.
- ``session-buddy health`` — OneiricCLIBase-provided; ``_health_probe``
  delegates to ``session_buddy.mcp.tools.monitoring.health_tools.get_health_status``.
- ``session-buddy server {start,stop,restart,status}`` — mcp-common
  lifecycle verbs mounted under ``server`` to avoid colliding with
  OneiricCLIBase's own ``health`` command.
- ``session-buddy checkpoint cleanup-snapshots`` (unchanged).
- ``session-buddy analytics {sessions,duration,components,errors,
  active,report,sql}`` (unchanged).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import typing as t
import warnings
from pathlib import Path

import typer
from oneiric.cli.base import OneiricCLIBase
from oneiric.core.config import OneiricMCPConfig

logger = logging.getLogger(__name__)

# Suppress transformers warnings about PyTorch/TensorFlow — mirrors the
# pre-adoption behavior so importing it standalone does not produce
# noisy warnings.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
warnings.filterwarnings("ignore", message=".*PyTorch.*TensorFlow.*Flax.*")


from mcp_common import (
    MCPServerCLIFactory,
    MCPServerSettings,
    RuntimeHealthSnapshot,
)


class _HasPidPath(t.Protocol):
    """Structural type: anything with a callable ``pid_path()`` returning Path."""

    def pid_path(self) -> Path: ...


# ---------------------------------------------------------------------------
# Settings + start handler + lifecycle glue (moved here from cli/__init__.py).
# ---------------------------------------------------------------------------


class SessionBuddySettings(OneiricMCPConfig):
    """Session Buddy specific MCP server settings extending OneiricMCPConfig."""

    # Session Buddy specific settings
    server_name: str = "session-buddy"

    # HTTP server configuration
    http_port: int = 8678
    websocket_port: int = 8677

    # Process management
    startup_timeout: int = 10
    shutdown_timeout: int = 10
    force_kill_timeout: int = 5

    # Snapshot freshness threshold (seconds). mcp-common's
    # ``MCPServerCLIFactory._emit_status_output`` reads
    # ``self.settings.health_ttl_seconds``; mirror the upstream default
    # (60.0) here so status/CLI commands work without forcing callers to
    # pass a fully-populated MCPServerSettings.
    health_ttl_seconds: float = 60.0

    # Snapshot path helpers (migrated from MCPServerSettings via
    # SessionMgmtSettings in settings.py; replicated here so the
    # CLI-side settings class still satisfies the structural protocol
    # in utils.runtime_snapshots).
    def pid_path(self) -> Path:
        return Path(self.cache_dir) / "mcp_server.pid"

    def health_snapshot_path(self) -> Path:
        return Path(self.cache_dir) / "runtime_health.json"

    def telemetry_snapshot_path(self) -> Path:
        return Path(self.cache_dir) / "runtime_telemetry.json"

    # Shim for mcp-common compatibility: factory.py:387 calls
    # ``self.settings.cache_root`` (Path), but OneiricMCPConfig only
    # exposes ``cache_dir`` (str). Mirror the value into cache_root so
    # mcp-common's ``validate_cache_ownership`` can read it.
    @property
    def cache_root(self) -> Path:
        return Path(self.cache_dir)


def start_server_handler() -> None:
    """Start handler that launches the Session Buddy MCP server.

    Pre-bind check: verify the target port is free BEFORE attempting to
    bind. Uvicorn's bind failure mode logs ``EADDRINUSE`` then shuts the
    server down with no actionable signal. Failing fast here gives the
    operator a clear message ("port 8678 is held by PID N") and avoids
    the bind-then-die cycle that previously required manual
    ``/mcp`` reconnects.
    """
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


def _port_holder(port: int) -> tuple[int, str] | None:
    """Return (pid, command) of the process listening on ``port``, or None.

    Uses ``lsof`` which is present on macOS and Linux. Returns None if
    no process is listening or ``lsof`` is unavailable.
    """
    if shutil.which("lsof") is None:
        return None
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpc"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except subprocess.TimeoutExpired, OSError:
        return None
    if result.returncode != 0 or not result.stdout:
        return None

    # lsof -F output: lines starting with 'p' are PIDs, 'c' are commands.
    pid: int | None = None
    command = ""
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("c") and pid is not None and not command:
            command = line[1:].strip()
    if pid is None:
        return None
    return (pid, command)


def _read_running_pid(settings: _HasPidPath) -> int | None:
    pid_path = settings.pid_path()
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text().strip())
    except ValueError, OSError:
        return None


def _run_health_probe(settings: SessionBuddySettings) -> RuntimeHealthSnapshot:
    """Run ``get_health_status`` and return a ``RuntimeHealthSnapshot``.

    Returned snapshot mirrors the pre-adoption shape so the mcp-common
    ``server status`` / ``server health`` commands keep rendering the
    same JSON they always did (``snapshot.as_dict()``). The
    OneiricCLIBase-provided ``session-buddy health`` command delegates
    to ``_health_probe`` instead of this helper, so the two surfaces
    stay deliberately separate.
    """
    from mcp_common import RuntimeHealthSnapshot

    from session_buddy.mcp.tools.monitoring.health_tools import get_health_status
    from session_buddy.utils.runtime_snapshots import update_telemetry_counter

    pid = _read_running_pid(settings)
    health_state = asyncio.run(get_health_status(ready=False))
    update_telemetry_counter(settings, name="health_probes", pid=pid)
    return RuntimeHealthSnapshot(
        orchestrator_pid=pid,
        watchers_running=pid is not None,
        activity_state={"health": health_state},
    )


def _doctor_checks_dict() -> dict[str, dict[str, t.Any]]:
    """Run :func:`session_buddy.doctor.run_all_doctor_checks` and convert.

    Returns a dict of ``check_name -> {status, detail, latency_ms,
    metadata}`` matching the shape OneiricCLIBase expects. Latency is
    folded into ``detail`` for the text rendering path; full JSON mode
    preserves the raw structure.
    """
    from session_buddy.doctor import run_all_doctor_checks

    results = asyncio.run(run_all_doctor_checks())
    out: dict[str, dict[str, t.Any]] = {}
    for r in results:
        detail = r.message
        if r.latency_ms is not None:
            detail = f"{r.message} ({r.latency_ms:.1f}ms)"
        out[r.name] = {
            "status": str(r.status),
            "detail": detail,
            "latency_ms": r.latency_ms,
            "metadata": r.metadata.copy(),
        }
    return out


class SessionBuddyCLI(OneiricCLIBase):
    """Session-Buddy's main Typer app, subclass of oneiric ``OneiricCLIBase``.

    - ``version`` / ``doctor`` / ``health`` come from OneiricCLIBase and
      dispatch into session-buddy's existing diagnostic surfaces.
    - The mcp-common lifecycle verbs (``start``, ``stop``, ``restart``,
      ``status``) are mounted under the ``server`` sub-Typer to avoid
      colliding with OneiricCLIBase's own ``health`` command.
    - The session-buddy-specific subcommand groups ``checkpoint`` and
      ``analytics`` are mounted at the top level to preserve the
      pre-adoption CLI surface.
    """

    def __init__(
        self,
        *,
        help: str | None = None,
        settings: t.Any | None = None,
        start_handler: t.Callable[[], None] | None = None,
        **kwargs: t.Any,
    ) -> None:
        super().__init__(
            component_name="session-buddy",
            help=help
            or "Session-Buddy MCP Server CLI (Bodai Core 7 — oneiric 0.19 OneiricCLIBase).",
            **kwargs,
        )
        self._settings = settings
        self._start_handler = start_handler
        self._mount_lifecycle_subtyper()
        self._mount_session_buddy_subcommands()

    # ------------------------------------------------------------------
    # OneiricCLIBase subclass hooks — REAL implementations.
    # ------------------------------------------------------------------
    def _doctor_checks(self) -> dict[str, t.Any]:
        """Override OneiricCLIBase's stub with a real doctor run.

        Calls ``session_buddy.doctor.run_all_doctor_checks`` (the same
        surface the legacy ``doctor`` Typer command used). Returns the
        list as a dict keyed by check name so OneiricCLIBase can render it
        consistently across components.
        """
        return _doctor_checks_dict()

    def _health_probe(self) -> dict[str, t.Any]:
        """Override OneiricCLIBase's stub with a real health probe.

        Calls ``session_buddy.mcp.tools.monitoring.health_tools.get_health_status``
        (the same surface the legacy ``health`` lifecycle command used)
        and returns the raw dict so OneiricCLIBase can render it as JSON
        or text. The wrapped lifecycle ``server health`` command keeps
        using ``mcp_common.RuntimeHealthSnapshot`` semantics — the two
        surfaces are deliberately separate.
        """
        from session_buddy.mcp.tools.monitoring.health_tools import get_health_status

        return asyncio.run(get_health_status(ready=False))

    # ------------------------------------------------------------------
    # Sub-Typer wiring.
    # ------------------------------------------------------------------
    def _mount_lifecycle_subtyper(self) -> None:
        """Mount the mcp-common lifecycle verbs under ``session-buddy server``.

        The lifecycle verbs (``start``, ``stop``, ``restart``, ``status``,
        ``health``) come from :class:`mcp_common.MCPServerCLIFactory`.
        We mount the factory's Typer sub-app under the name ``server``
        so the OneiricCLIBase-provided ``health`` command is not shadowed
        by the mcp-common variant. ``server health`` is still available
        for operators who want the RuntimeHealthSnapshot shape.
        """
        sb_settings = self._settings or SessionBuddySettings()
        factory = MCPServerCLIFactory(
            server_name=sb_settings.server_name,
            settings=t.cast("MCPServerSettings", sb_settings),
            start_handler=self._start_handler or start_server_handler,
            health_probe_handler=lambda: _run_health_probe(sb_settings),
        )
        lifecycle_app = factory.create_app()
        self.add_typer(lifecycle_app, name="server")

    def _mount_session_buddy_subcommands(self) -> None:
        """Mount the session-buddy-specific subcommand groups.

        - ``checkpoint cleanup-snapshots`` (and any future checkpoint verbs)
          from :mod:`session_buddy.cli.checkpoint_cli`.
        - ``analytics {sessions,duration,components,errors,active,report,sql}``
          from :mod:`session_buddy.analytics.cli`.
        """
        from session_buddy.cli.checkpoint_cli import register_checkpoint_command

        register_checkpoint_command(self)

        from session_buddy.analytics.cli import app as analytics_app

        self.add_typer(analytics_app, name="analytics")

    # ------------------------------------------------------------------
    # Backward compatibility shim.
    # ------------------------------------------------------------------
    def create_app(self) -> typer.Typer:
        """Return ``self`` so legacy ``cli.create_app()`` callers still work.

        ``tests/unit/test_cli.py`` calls ``cli = create_session_buddy_cli();
        app = cli.create_app()`` and then ``cli_runner.invoke(app, ...)``.
        Now that the CLI is a Typer app directly (not a factory), we
        return ``self`` so the call shape is unchanged.
        """
        return self


__all__ = [
    "SessionBuddyCLI",
    "SessionBuddySettings",
    "_doctor_checks_dict",
    "_port_holder",
    "_read_running_pid",
    "_run_health_probe",
    "start_server_handler",
]
