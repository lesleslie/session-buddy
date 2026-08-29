#!/usr/bin/env python3
# ruff: noqa: EXE001
"""Session-Buddy CLI — OneiricCLIBase adoption (oneiric 0.19.0).

The main entrypoint now subclasses :class:`oneiric.cli.base.OneiricCLIBase`
so session-buddy exposes the standard Bodai Core 7 ``version`` / ``doctor``
/ ``health`` / ``--json`` / ``--version`` surface.

Lifecycle verbs (``start``, ``stop``, ``restart``, ``status``) are kept
but mounted under the ``server`` sub-Typer (see
:mod:`session_buddy.cli.base`) to avoid colliding with OneiricCLIBase's
own ``health`` command.

Backward compatibility: ``create_session_buddy_cli()`` still returns
an object whose ``create_app()`` returns a Typer app, so the legacy
``tests/unit/test_cli.py`` invocation pattern keeps working — though
some tests now need ``["server", "start"]`` instead of ``["start"]``.
"""

from __future__ import annotations

# Re-export the canonical OneiricCLIBase subclass first so callers that
# already do ``from session_buddy.cli import SessionBuddyCLI`` keep
# working. ``cli.base`` is the implementation; ``cli.__init__`` is
# just the backward-compat shim layer.
from session_buddy.cli.base import (  # noqa: F401
    SessionBuddyCLI,
    SessionBuddySettings,
    _port_holder,
    _read_running_pid,
    _run_health_probe,
    start_server_handler,
)


def create_session_buddy_cli() -> SessionBuddyCLI:
    """Create the Session Buddy CLI.

    Returns:
        A :class:`SessionBuddyCLI` (a :class:`oneiric.cli.base.OneiricCLIBase`
        subclass) with the standard Bodai Core 7 ``version`` / ``doctor``
        / ``health`` surface plus session-buddy-specific ``server``,
        ``checkpoint``, and ``analytics`` subcommands.

    The return value is also the Typer app itself (via the
    :meth:`SessionBuddyCLI.create_app` shim), so callers may write
    ``app = create_session_buddy_cli(); app()`` without going through
    ``create_app()`` first.
    """
    return SessionBuddyCLI()


def main() -> None:
    """Main entry point for the Session Buddy MCP CLI.

    Wires the entrypoint app via :meth:`OneiricCLIBase.run` semantics —
    Typer apps are invoked by calling the instance (``app()``), so
    ``OneiricCLIBase.run`` here just means "drive the Typer app to its
    callback dispatch". ``create_session_buddy_cli()`` is the
    authoritative factory; ``main()`` only orchestrates the run.
    """
    # Create the CLI app (OneiricCLIBase subclass) and run it.
    app = create_session_buddy_cli()
    app()


__all__ = [
    "SessionBuddyCLI",
    "SessionBuddySettings",
    "create_session_buddy_cli",
    "main",
    "start_server_handler",
]


# Bodai umbrella entry-point (Phase 5.1)
app = SessionBuddyCLI()


@app.command("shell")
def shell_command() -> None:
    """Start the Session-Buddy admin shell (IPython-based)."""
    import asyncio

    async def _run() -> None:
        from session_buddy.shell import SessionBuddyShell
        from session_buddy.core.session_manager import SessionLifecycleManager

        manager = SessionLifecycleManager()
        shell = SessionBuddyShell(manager)
        shell.start()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
