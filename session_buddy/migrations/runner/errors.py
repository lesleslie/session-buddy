"""Exception hierarchy for the UUID7 migration runner.

The migration runner distinguishes three failure shapes:

- :class:`MigrationError` — the base class for any runner-level problem.
- :class:`MigrationStepError` — a single step raised during forward
  execution. Wraps the underlying DuckDB / IO error so the CLI can print a
  single, structured ``{"step": "...", "cause": "..."}`` record.
- :class:`StaleRunningError` — re-exported from :mod:`marker` so callers
  that import from a single namespace (``runner.errors``) get the whole
  hierarchy in one place.

All three are checked exceptions (subclasses of ``Exception``) — DuckDB
does not raise them, so the runner is the sole producer.
"""

from __future__ import annotations

from session_buddy.migrations.runner.marker import (
    StaleRunningError as _StaleRunningError,
)


class MigrationError(Exception):
    """Base class for UUID7 migration runner errors."""


class MigrationStepError(MigrationError):
    """A single forward step failed during ``MigrationRunner.run``.

    Attributes:
        step: The script name (e.g. ``001_consolidate_conversations``)
            whose execution raised the underlying exception.
        cause: The original DuckDB / IO exception. Preserved verbatim so
            debuggers and structured logs can inspect ``__cause__``.
    """

    def __init__(self, step: str, cause: BaseException) -> None:
        super().__init__(f"Step {step} failed: {cause}")
        self.step = step
        self.cause = cause


# Re-export for callers that import ``runner.errors`` as a single namespace.
# The marker implementation is the canonical one; mirror it here so the
# import surface is consistent.
StaleRunningError = _StaleRunningError


__all__ = ["MigrationError", "MigrationStepError", "StaleRunningError"]
