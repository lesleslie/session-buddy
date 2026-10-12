"""Marker package for the integration tests of session_buddy.migrations.

Run via::

    .venv/bin/pytest tests/integration/migrations/ -v

The package is intentionally empty at this layer so the directory resolves
as a namespace without pulling in DB / environment dependencies at import.
"""
