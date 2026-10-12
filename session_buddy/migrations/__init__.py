"""Public surface of the migrations package.

Bundles the UUID7-consolidation forward scripts and the runner core. The
canonical entry points are:

- :mod:`session_buddy.migrations.runner` for programmatic execution
- :mod:`session_buddy.migrations.udf` for the deterministic ULID-to-UUID7
  conversion function that the migration scripts depend on
- :mod:`session_buddy.migrations.2026_10_11_uuid7_consolidation` for the
  ship-time bundle directory (read directly via ``Path``)
"""

from session_buddy.migrations.runner import (
    MigrationContext,
    MigrationError,
    MigrationRunner,
    MigrationStepError,
    StaleRunningError,
)
from session_buddy.migrations.udf import ulid_to_uuid7

__all__ = [
    "MigrationContext",
    "MigrationError",
    "MigrationRunner",
    "MigrationStepError",
    "StaleRunningError",
    "ulid_to_uuid7",
]
