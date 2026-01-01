#!/usr/bin/env python3
"""Session Management MCP Server - Module Entry Point.

Provides MCP Common CLI with standard lifecycle commands.

Usage:
    python -m session_buddy start          # Start server
    python -m session_buddy stop           # Stop server
    python -m session_buddy restart        # Restart server
    python -m session_buddy status         # Show status
    python -m session_buddy health         # Show health
    python -m session_buddy health --probe # Live health probe
"""


def main() -> None:
    """Main entry point for the session management MCP server."""
    from .cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
