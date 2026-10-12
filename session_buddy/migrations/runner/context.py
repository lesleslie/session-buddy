"""MigrationContext — runtime inputs for the UUID7 migration runner.

All fields are immutable so the runner cannot mutate its inputs mid-flight.
``json_output`` flips the CLI text renderer to print JSON; the runner itself
is renderer-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MigrationContext:
    """Immutable runtime inputs for :class:`MigrationRunner`.

    Attributes:
        bundle_dir: Directory holding the lexicographically-ordered forward
            ``NNN_*.sql`` scripts and the optional ``NNN_*_down.sql`` rollback
            pair. :class:`session_buddy.migrations.runner.discovery.ScriptDiscovery`
            is the only consumer of this path.
        db_path: DuckDB file to open in read-write (or read-only for ``status``)
            mode. The runner opens its own connection per operation so each
            CLI subcommand starts from a clean session.
        dry_run: When ``True`` the runner reports what it would execute but
            does not call ``mark_done`` / ``mark_failed`` against the marker
            store. The SQL scripts still execute against the database so a
            dry run produces observable side effects; flip the ``dry_run``
            flag explicitly to roll back via a fresh DB copy if isolation
            matters.
        from_step: Optional step name (e.g. ``003_consolidate_reflections``)
            that bounds forward execution. Steps lex-smaller than this one
            are skipped silently; ``from_step`` itself and later steps run
            normally. ``None`` runs every discovered step from the start.
        force: When ``True``, retry previously-failed steps. Defaults to
            ``False`` so a partial failure leaves the marker store in its
            current state until the operator explicitly opts in to a retry.
        json_output: Flip the CLI text renderer to emit JSON. The runner
            itself is renderer-agnostic; the flag is read by the migrate
            CLI for status / run / rollback / reset-stuck rendering.
    """

    bundle_dir: Path
    db_path: Path
    dry_run: bool = False
    from_step: str | None = None
    force: bool = False
    json_output: bool = False


__all__ = ["MigrationContext"]
