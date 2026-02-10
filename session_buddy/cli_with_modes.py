#!/usr/bin/env python3
"""Session-Buddy CLI with operational mode support.

This CLI provides mode-based initialization for Session-Buddy:
- Lite mode: In-memory, zero-dependency mode
- Standard mode: Full-featured production mode

Usage:
    session-buddy start --mode=lite
    session-buddy start --mode=standard
    SESSION_BUDDY_MODE=lite session-buddy start
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

# Suppress transformers warnings
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore", message=".*PyTorch.*TensorFlow.*Flax.*")

# Add project root to Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mcp_common import MCPServerCLIFactory, MCPServerSettings, RuntimeHealthSnapshot

from session_buddy.mcp.tools.monitoring.health_tools import get_health_status
from session_buddy.modes import get_mode
from session_buddy.utils.runtime_snapshots import update_telemetry_counter


class SessionBuddySettings(MCPServerSettings):
    """Session Buddy specific MCP server settings."""

    # Session Buddy specific settings
    server_name: str = "session-buddy"

    # HTTP server configuration
    http_port: int = 8678
    websocket_port: int = 8677

    # Process management
    startup_timeout: int = 10
    shutdown_timeout: int = 10
    force_kill_timeout: int = 5

    # Operational mode (lite, standard)
    mode: str = "standard"

    # Adapter registry configuration
    adapter_registry_enabled: bool = True
    adapter_registry_host: str = "localhost"
    adapter_registry_port: int = 8679


def start_server_handler(mode: str = "standard") -> None:
    """Start handler that launches Session-Buddy in the specified mode.

    Args:
        mode: Operational mode (lite, standard)
    """
    from session_buddy.server_optimized import run_server

    # Get mode configuration
    try:
        mode_instance = get_mode(mode)
        mode_config = mode_instance.get_config()

        # Set environment variable for mode
        os.environ["SESSION_BUDDY_MODE"] = mode

        # Print startup message
        print(mode_instance.get_startup_message())
        print(f"Database: {mode_config.database_path}")
        print(f"Storage: {mode_config.storage_backend}")
        print(
            f"Embeddings: {'Enabled' if mode_config.enable_embeddings else 'Disabled'}"
        )
        print(
            f"Multi-Project: {'Enabled' if mode_config.enable_multi_project else 'Disabled'}"
        )

        # Start server in HTTP mode
        settings = SessionBuddySettings()
        print(f"\nHTTP Port: {settings.http_port}")
        print(f"WebSocket Port: {settings.websocket_port}")
        print("-" * 60)

        # Launch the server
        run_server(host="127.0.0.1", port=settings.http_port)

    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to start server: {e}", file=sys.stderr)
        sys.exit(1)


def _read_running_pid(settings: MCPServerSettings) -> int | None:
    """Read running PID from PID file.

    Args:
        settings: MCP server settings

    Returns:
        PID if running, None otherwise
    """
    pid_path = settings.pid_path()
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text().strip())
    except (ValueError, OSError):
        return None


def _run_health_probe(settings: MCPServerSettings) -> RuntimeHealthSnapshot:
    """Run health probe on Session-Buddy server.

    Args:
        settings: MCP server settings

    Returns:
        Runtime health snapshot
    """
    import asyncio

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
    """Create the Session-Buddy CLI using MCPServerCLIFactory.

    Returns:
        Configured MCPServerCLIFactory instance
    """
    # Detect mode from environment
    mode = os.getenv("SESSION_BUDDY_MODE", "standard").lower()

    # Initialize settings with mode
    settings = SessionBuddySettings(mode=mode)

    # Create start handler with mode
    def start_handler() -> None:
        start_server_handler(mode=mode)

    # Create the CLI factory
    return MCPServerCLIFactory(
        server_name=settings.server_name,
        settings=settings,
        start_handler=start_handler,
        health_probe_handler=lambda: _run_health_probe(settings),
    )


def main() -> None:
    """Main entry point for the Session-Buddy MCP CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Session-Buddy MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  session-buddy                    Start in standard mode
  session-buddy --mode=lite        Start in lite mode
  session-buddy --mode=standard    Start in standard mode
  SESSION_BUDDY_MODE=lite session-buddy    Use environment variable

Modes:
  lite         Zero-dependency, in-memory mode (testing, CI/CD)
  standard     Full-featured production mode (default)

For more information, see https://github.com/lesleslie/session-buddy
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["lite", "standard"],
        default=os.getenv("SESSION_BUDDY_MODE", "standard"),
        help="Operational mode (default: standard from env or 'standard')",
    )

    # Parse known args to allow mcp-common to handle its own args
    args, remaining = parser.parse_known_args()

    # Set mode in environment
    os.environ["SESSION_BUDDY_MODE"] = args.mode

    # Create and run CLI
    cli_factory = create_session_buddy_cli()
    app = cli_factory.create_app()

    # Run with remaining args
    sys.argv = [sys.argv[0]] + remaining
    app()


if __name__ == "__main__":
    main()
