"""Public surface of the migration runner package.

Re-exports the forward-execution entry point, the immutable context type,
the structured error hierarchy, and the marker-store primitives so
callers can write ``from session_buddy.migrations.runner import ...``
rather than reaching into submodule paths.
"""

from session_buddy.migrations.runner.context import MigrationContext
from session_buddy.migrations.runner.errors import (
    MigrationError,
    MigrationStepError,
    StaleRunningError,
)
from session_buddy.migrations.runner.marker import MarkerStore
from session_buddy.migrations.runner.runner import MigrationRunner, StepResult

__all__ = [
    "MarkerStore",
    "MigrationContext",
    "MigrationError",
    "MigrationRunner",
    "MigrationStepError",
    "StaleRunningError",
    "StepResult",
]
