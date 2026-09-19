"""Checkpoint CLI: cleanup-snapshots manual command per spec line 388.

Also exposes ``subagent-marker`` for runtime hooks that need to mark or
clear the per-working-tree ``<working_dir>/.session-buddy/subagent.lock``
without going through the MCP tool (e.g., shell scripts, init systems).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import typer

from session_buddy.checkpoint import SnapshotCleanupTask
from session_buddy.checkpoint.subagent_detector import (
    LockfileSignalSource,
    SubagentDetector,
)

app = typer.Typer(help="Checkpoint utilities")


@app.command(name="cleanup-snapshots")
def cleanup_snapshots(
    older_than: int = typer.Option(
        7, "--older-than", help="Remove snapshots older than N days"
    ),
    snapshot_dir: Path | None = typer.Option(
        None, "--snapshot-dir", help="Override snapshot directory"
    ),
) -> None:
    """Remove snapshots older than the TTL."""
    # NOTE: prefer the plain ``int = typer.Option(...)`` form here over
    # ``Annotated[int, typer.Option(...)]``; typer 0.27.1 mis-parses the
    # ``Annotated`` form when the Option's default is a literal int and
    # raises ``AttributeError: 'int' object has no attribute
    # 'isidentifier'`` while collecting the subcommand's parameter
    # declarations.
    sd = snapshot_dir or Path(tempfile.gettempdir()) / "session-buddy-snapshots"
    task = SnapshotCleanupTask(sd, ttl_seconds=older_than * 86400)
    removed = asyncio.run(task.cleanup_once())
    typer.echo(f"removed {removed} snapshots from {sd}")


@app.command(name="subagent-marker")
def subagent_marker(
    action: str = typer.Option(
        ..., "--action", help="mark or clear the subagent lockfile"
    ),
    working_dir: Path = typer.Option(
        ..., "--working-dir", help="Working directory whose lockfile to mutate"
    ),
) -> None:
    """Mark or clear the subagent lockfile for ``--working-dir``.

    ``mark`` creates ``<working_dir>/.session-buddy/subagent.lock`` with
    auto-generated metadata (pid, started_at_ms, node_id, parent_agent_id).
    ``clear`` unlinks it. Runtime hooks (Claude Code Task tool wrappers,
    Mahavishnu ``PoolManager`` worker spawns) call this from shell scripts
    without needing the Python API or the MCP tool.
    """
    if action not in ("mark", "clear"):
        raise typer.BadParameter(
            f"action must be 'mark' or 'clear', got {action!r}"
        )
    lock = working_dir / ".session-buddy" / "subagent.lock"
    detector = SubagentDetector(working_dir, LockfileSignalSource(lock))
    detector.write(active=(action == "mark"))
    typer.echo(f"{action}ed {lock}")


def register_checkpoint_command(parent: typer.Typer) -> None:
    """Register the ``checkpoint`` subcommand on a Typer ``app``."""

    parent.add_typer(app, name="checkpoint")
