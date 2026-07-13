#!/usr/bin/env python3
"""MCP Common CLI Factory for Session Management MCP Server.

Replaces the custom Typer-based CLI with mcp-common's MCPServerCLIFactory
to provide standard lifecycle commands (start, stop, restart, status, health).
"""

from __future__ import annotations

import asyncio
import os
import warnings

import typer

# Suppress transformers warnings about PyTorch/TensorFlow
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore", message=".*PyTorch.*TensorFlow.*Flax.*")


from mcp_common import MCPServerCLIFactory, RuntimeHealthSnapshot
from oneiric.core.config import OneiricMCPConfig

from session_buddy.mcp.tools.monitoring.health_tools import get_health_status
from session_buddy.utils.runtime_snapshots import update_telemetry_counter


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


def start_server_handler() -> None:
    """Start handler that launches the Session Buddy MCP server.

    This function is called by the CLI factory when 'start' command is executed.

    Pre-bind check: verify the target port is free BEFORE attempting to
    bind. Uvicorn's bind failure mode logs ``EADDRINUSE`` then shuts the
    server down with no actionable signal. Failing fast here gives the
    operator a clear message ("port 8678 is held by PID N") and avoids
    the bind-then-die cycle that previously required manual
    ``/mcp`` reconnects.
    """
    from session_buddy.server_optimized import run_server

    # Start server in HTTP mode with configured ports
    settings = SessionBuddySettings()

    print("🚀 Starting Session Management MCP Server...")
    print(f"HTTP Port: {settings.http_port}")
    print(f"WebSocket Port: {settings.websocket_port}")

    # Pre-bind port check — fail fast with a clear message instead of
    # letting uvicorn log EADDRINUSE and exit silently.
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
    import shutil
    import subprocess

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
    except (subprocess.TimeoutExpired, OSError):
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


def _read_running_pid(settings: OneiricMCPConfig) -> int | None:
    pid_path = settings.pid_path()
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text().strip())
    except (ValueError, OSError):
        return None


def _run_health_probe(settings: OneiricMCPConfig) -> RuntimeHealthSnapshot:
    pid = _read_running_pid(settings)
    health_state = asyncio.run(get_health_status(ready=False))
    snapshot = RuntimeHealthSnapshot(
        orchestrator_pid=pid,
        watchers_running=pid is not None,
        activity_state={"health": health_state},
    )
    update_telemetry_counter(settings, name="health_probes", pid=pid)
    return snapshot


def create_session_buddy_cli() -> MCPServerCLIFactory:
    """Create the Session Buddy CLI using MCPServerCLIFactory.

    Returns:
        Configured MCPServerCLIFactory instance ready for execution

    """
    # Initialize settings
    settings = SessionBuddySettings()

    # Create the CLI factory with start handler
    cli_factory = MCPServerCLIFactory(
        server_name=settings.server_name,
        settings=settings,
        start_handler=start_server_handler,
        health_probe_handler=lambda: _run_health_probe(settings),
    )

    app = cli_factory.create_app()

    # Register session-buddy-specific subcommands. The factory only owns
    # the lifecycle verbs (start/stop/restart/status/health); session-buddy
    # adds ``doctor`` here.
    from session_buddy.doctor import register_doctor_command  # noqa: PLC0415

    register_doctor_command(app)

    @app.callback(invoke_without_command=True)
    def _root(
        version: bool = typer.Option(
            False,
            "--version",
            help="Show the Session Buddy version and exit.",
        ),
    ) -> None:
        if version:
            from session_buddy import __version__

            typer.echo(f"session-buddy version {__version__}")
            raise typer.Exit()

    # Preserve the factory interface expected by callers while returning an
    # object whose create_app() yields the augmented app.
    cli_factory.create_app = lambda: app  # ty: ignore[invalid-assignment]
    return cli_factory


def main() -> None:
    """Main entry point for the Session Buddy MCP CLI."""
    # Create and configure the CLI
    cli_factory = create_session_buddy_cli()

    # Create and run the CLI application
    app = cli_factory.create_app()

    # Execute the CLI
    app()


if __name__ == "__main__":
    main()
