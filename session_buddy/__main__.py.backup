#!/usr/bin/env python3
"""Session Management MCP Server - Module Entry Point.

Provides CLI interface matching crackerjack's server management pattern.

Usage:
    python -m session_buddy --start-mcp-server       # Start server
    python -m session_buddy --stop-mcp-server        # Stop server
    python -m session_buddy --restart-mcp-server     # Restart server
    python -m session_buddy --status                 # Show status
    python -m session_buddy --version                # Show version
"""


def main() -> None:
    """Main entry point for the session management MCP server."""
    from .cli import app

    app()


if __name__ == "__main__":
    main()
