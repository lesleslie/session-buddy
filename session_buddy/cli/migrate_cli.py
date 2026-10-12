"""Typer subcommand group for the UUID7 consolidation migration runner.

Mounts four operators under ``session-buddy migrate``::

    session-buddy migrate run          [--dry-run] [--from-step STEP] [--force] [--json]
    session-buddy migrate status       [--json]
    session-buddy migrate rollback     [--from-step STEP] [--dry-run] [--json]
    session-buddy migrate reset-stuck  [--json]

The CLI follows the same patterns as the existing ``checkpoint`` and
``analytics`` sub-Typers in this package — each verb is a top-level
``@app.command`` on a module-level ``typer.Typer``, and :func:`register`
attaches it to the parent :class:`session_buddy.cli.base.SessionBuddyCLI`
app via ``add_typer(... name="migrate")``.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from oneiric.core.logging import get_logger

from session_buddy.cli.base import SessionBuddyCLI
from session_buddy.migrations.runner import (
    MigrationContext,
    MigrationRunner,
    MigrationStepError,
)

logger = get_logger(__name__)

app = typer.Typer(
    name="migrate",
    help="UUID7 consolidation migration runner (forward / status / rollback / reset-stuck).",
    add_completion=False,
)


# Canonical bundle directory: shipped with this repo at the canonical
# 2026-10-11 path. The runner is bundle-agnostic — pass --bundle-dir to
# point it at a different migration set.
DEFAULT_BUNDLE_DIR = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "2026_10_11_uuid7_consolidation"
)


# Default DB path matches the session-buddy reflection store used by the
# mcp_common settings layout. Operators can override via --db-path.
DEFAULT_DB_PATH = Path(
    "~/.local/state/bodai/session-buddy/reflections.duckdb"
).expanduser()


def _resolve_db_path(db_path: Path | None) -> Path:
    """Resolve the operator-provided path, falling back to the default."""
    if db_path is None:
        return DEFAULT_DB_PATH
    return db_path.expanduser()


def _build_context(
    bundle_dir: Path | None,
    db_path: Path | None,
    dry_run: bool,
    from_step: str | None,
    force: bool,
    json_output: bool,
) -> MigrationContext:
    """Materialize a :class:`MigrationContext` from CLI args.

    Centralizes the ``Path.expanduser`` resolution so the four Typer
    commands share one path-handling code path.
    """
    return MigrationContext(
        bundle_dir=(bundle_dir or DEFAULT_BUNDLE_DIR).expanduser(),
        db_path=_resolve_db_path(db_path),
        dry_run=dry_run,
        from_step=from_step,
        force=force,
        json_output=json_output,
    )


def _print_results(results: list, json_output: bool) -> None:
    """Render a list of :class:`StepResult` as text or JSON.

    ``status()`` returns dicts; ``run()`` returns dataclasses. Both
    support ``__dict__`` access for JSON serialization, so a single
    path here keeps the rendering consistent across verbs.
    """
    if json_output:
        payload = [getattr(r, "__dict__", r) for r in results]
        typer.echo(json.dumps(payload, indent=2, default=str))
        return
    for r in results:
        if isinstance(r, dict):
            typer.echo(
                f"step={r.get('step')!r} state={r.get('state')!r} "
                f"rows_affected={r.get('rows_affected')} "
                f"started_at={r.get('started_at')} "
                f"finished_at={r.get('finished_at')} "
                f"error={r.get('error_message')!r}"
            )
        else:
            err = f" error={r.error!r}" if r.error else ""
            typer.echo(
                f"step={r.step!r} state={r.state!r} "
                f"rows_affected={r.rows_affected} duration_ms={r.duration_ms}{err}"
            )


@app.command(name="run")
def migrate_run(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Open the DB, register the UDF, and report what would run; do not write markers.",
    ),
    from_step: str | None = typer.Option(
        None,
        "--from-step",
        help="Start from this script (e.g. 003_consolidate_reflections); skip anything earlier.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Retry previously-failed steps. Without this, failed steps are skipped.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit structured JSON output."
    ),
    bundle_dir: Path | None = typer.Option(
        None, "--bundle-dir", help="Override the migration bundle directory."
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Override the DuckDB path (default: ~/.local/state/bodai/session-buddy/reflections.duckdb).",
    ),
) -> None:
    """Apply the UUID7 consolidation forward scripts in order.

    By default skips steps already marked as ``done`` (idempotent re-run)
    and skips failed steps; pass ``--force`` to retry failed steps and
    ``--from-step`` to start from a specific script rather than the
    bundle's lex-smallest.
    """
    ctx = _build_context(bundle_dir, db_path, dry_run, from_step, force, json_output)
    runner = MigrationRunner(ctx)
    try:
        results = runner.run()
    except MigrationStepError as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "error": "MigrationStepError",
                        "step": exc.step,
                        "cause": f"{type(exc.cause).__name__}: {exc.cause}",
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"step {exc.step!r} failed: {exc.cause}", err=True)
        raise typer.Exit(1) from exc
    _print_results(results, json_output)
    if any(r.state == "failed" for r in results):
        raise typer.Exit(1)


@app.command(name="status")
def migrate_status(
    json_output: bool = typer.Option(
        False, "--json", help="Emit structured JSON output."
    ),
    bundle_dir: Path | None = typer.Option(
        None,
        "--bundle-dir",
        help="Override the migration bundle directory (unused for status).",
    ),
    db_path: Path | None = typer.Option(
        None, "--db-path", help="Override the DuckDB path."
    ),
) -> None:
    """Show the current marker-state for every recorded step."""
    # ``bundle_dir`` is accepted (and ignored) so the user can paste the
    # same flag set across the four verbs without surprises.
    ctx = _build_context(bundle_dir, db_path, False, None, False, json_output)
    runner = MigrationRunner(ctx)
    rows = runner.status()
    _print_results(rows, json_output)


@app.command(name="rollback")
def migrate_rollback(
    from_step: str | None = typer.Option(
        None,
        "--from-step",
        help="Only roll back this step and any later (lex-greater) reversible step.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would roll back; do not execute."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit structured JSON output."
    ),
    bundle_dir: Path | None = typer.Option(
        None, "--bundle-dir", help="Override the migration bundle directory."
    ),
    db_path: Path | None = typer.Option(
        None, "--db-path", help="Override the DuckDB path."
    ),
) -> None:
    """Run the matching ``*_down.sql`` for every done step, in reverse order.

    Only step IDs ``001``..``007`` are reversible in the canonical bundle;
    ``000_`` (the bootstrap) and ``008+`` (the terminal cleanup) have no
    down-script and are skipped silently.
    """
    ctx = _build_context(bundle_dir, db_path, dry_run, from_step, False, json_output)
    runner = MigrationRunner(ctx)
    try:
        rolled = runner.rollback(from_step=from_step)
    except MigrationStepError as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "error": "MigrationStepError",
                        "step": exc.step,
                        "cause": f"{type(exc.cause).__name__}: {exc.cause}",
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"rollback step {exc.step!r} failed: {exc.cause}", err=True)
        raise typer.Exit(1) from exc

    if json_output:
        typer.echo(json.dumps({"rolled_back": rolled}))
    else:
        typer.echo(f"rolled back {rolled} step(s)")


@app.command(name="reset-stuck")
def migrate_reset_stuck(
    json_output: bool = typer.Option(
        False, "--json", help="Emit structured JSON output."
    ),
    bundle_dir: Path | None = typer.Option(
        None,
        "--bundle-dir",
        help="Override the migration bundle directory (unused for reset-stuck).",
    ),
    db_path: Path | None = typer.Option(
        None, "--db-path", help="Override the DuckDB path."
    ),
) -> None:
    """Move long-stuck ``running`` markers to ``failed``.

    A step is ``stuck`` when its ``started_at`` is older than
    :class:`MarkerStore`'s default 1-hour threshold. After resetting,
    follow up with ``session-buddy migrate run --force`` to retry.
    """
    ctx = _build_context(bundle_dir, db_path, False, None, False, json_output)
    runner = MigrationRunner(ctx)
    moved = runner.reset_stuck()
    if json_output:
        typer.echo(json.dumps({"moved_to_failed": moved}))
    else:
        typer.echo(f"moved {moved} stuck step(s) to failed")


def register_migrate_command(parent: SessionBuddyCLI | typer.Typer) -> None:
    """Attach the ``migrate`` sub-Typer to ``parent``.

    Mirrors the canonical :func:`session_buddy.cli.checkpoint_cli.register_checkpoint_command`
    shape so the parent-boot wiring is symmetric across subcommands.
    """
    parent.add_typer(app, name="migrate")


__all__ = ["app", "register_migrate_command"]
