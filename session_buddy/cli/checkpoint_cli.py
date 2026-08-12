"""Checkpoint CLI: cleanup-snapshots manual command per spec line 388."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import typer

from session_buddy.checkpoint import SnapshotCleanupTask

app = typer.Typer(help="Checkpoint utilities")


@app.command(name="cleanup-snapshots")
def cleanup_snapshots(
    older_than: int = typer.Option(
        7, "--older-than", help="Remove snapshots older than N days"
    ),
    snapshot_dir: Path | None = typer.Option(  # noqa: B008 - typer idiom
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


def register_checkpoint_command(parent: typer.Typer) -> None:
    """Register the ``checkpoint`` subcommand on a Typer ``app``."""

    parent.add_typer(app, name="checkpoint")
