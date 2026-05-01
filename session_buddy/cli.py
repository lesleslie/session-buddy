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

from mcp_common import MCPServerCLIFactory, MCPServerSettings, RuntimeHealthSnapshot

from session_buddy.mcp.tools.monitoring.health_tools import get_health_status
from session_buddy.utils.runtime_snapshots import update_telemetry_counter


class SessionBuddySettings(MCPServerSettings):
    """Session Buddy specific MCP server settings extending MCPServerSettings."""

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
    """
    from session_buddy.server_optimized import run_server

    # Start server in HTTP mode with configured ports
    settings = SessionBuddySettings()

    print("🚀 Starting Session Management MCP Server...")
    print(f"HTTP Port: {settings.http_port}")
    print(f"WebSocket Port: {settings.websocket_port}")

    # Launch the server with HTTP transport
    run_server(host="127.0.0.1", port=settings.http_port)


def _read_running_pid(settings: MCPServerSettings) -> int | None:
    pid_path = settings.pid_path()
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text().strip())
    except (ValueError, OSError):
        return None


def _run_health_probe(settings: MCPServerSettings) -> RuntimeHealthSnapshot:
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
    cli_factory.create_app = lambda: app  # type: ignore[method-assign]
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
