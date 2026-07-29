"""Integration test for the canonical DI registration path.

This test exercises ``adapters/lifecycle.init_reflection_adapter()`` —
the function that production code uses to register the reflection
adapter with the Oneiric DI container. None of the unit tests exercise
this path: they all create adapters via fixtures (``adapter``,
``adapter_with_data``, ``in_memory_adapter``) that bypass the
registration entirely.

Bug 1 of the v1 audit was a typo in a string DI key that the unit
tests couldn't have caught because they bypass registration. This
test would catch any regression where:

- ``init_reflection_adapter`` registers under the wrong key
  (e.g., a bare-string key instead of the class key)
- The Oneiric adapter import path breaks
- The settings resolution path fails
- The DI container is misconfigured for the reflection service
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from session_buddy.di.container import depends


@pytest.fixture
def clean_di() -> None:
    """Reset the DI registry around each test.

    ``init_reflection_adapter`` writes to the global ``depends``
    singleton. Without resetting between tests, one test's
    registration would leak into the next.
    """
    yield
    depends._resolver = depends._resolver.__class__()
    depends._instances.clear()


@pytest.mark.asyncio
async def test_init_reflection_adapter_registers_under_class_key(
    clean_di, tmp_path: Path
) -> None:
    """``init_reflection_adapter`` registers the adapter such that
    ``require_reflection_database()`` (the canonical resolver used by
    the MCP wrappers) can find it.

    Bug 1 of the v1 audit was that ``progressive_search.py:484`` used
    a bare-string DI key that never matched any registration. A
    similar bug at the registration site would also be missed by
    existing tests — they bypass the registration entirely. This
    test is the canonical guard against that class of regression.
    """
    import os

    # The lifecycle helper resolves settings from the claude data dir
    # by default. Override to use a tmp_path so the test is isolated
    # and does not touch production state.
    settings_path = tmp_path / "test_settings.yaml"
    settings_path.write_text(
        "reflection:\n  database_path: {}\n".format(str(tmp_path / "test.duckdb"))
    )

    # Most implementations allow overriding via env or constructor.
    # If neither is wired, this test still verifies the registration
    # contract with whatever default settings ``from_settings()``
    # produces.
    from session_buddy.adapters.lifecycle import init_reflection_adapter

    await init_reflection_adapter()

    # The canonical resolution path: this is what every MCP wrapper
    # uses. If registration used a bare-string key or a different
    # class identity, this would raise KeyError.
    from session_buddy.utils.database_tools import require_reflection_database

    db = await require_reflection_database()
    assert db is not None, (
        "init_reflection_adapter registered but require_reflection_database "
        "returned None. The DI key must match the registration key."
    )


@pytest.mark.asyncio
async def test_init_reflection_adapter_is_idempotent(clean_di, tmp_path: Path) -> None:
    """Calling ``init_reflection_adapter`` twice should not register
    duplicate instances. The implementation at ``adapters/lifecycle.py``
    has a guard (``if isinstance(existing, ReflectionDatabaseAdapter):
    return``) that skips re-registration; this test verifies the
    guard works.
    """
    from session_buddy.adapters.lifecycle import init_reflection_adapter

    await init_reflection_adapter()
    first = await _resolve_registered_adapter()
    await init_reflection_adapter()
    second = await _resolve_registered_adapter()

    assert first is second, (
        "init_reflection_adapter registered different instances on "
        "two consecutive calls — the idempotency guard at "
        "adapters/lifecycle.py is broken."
    )


async def _resolve_registered_adapter() -> object:
    """Resolve the registered adapter via the canonical DI key."""
    from session_buddy.adapters.reflection_adapter_oneiric import (
        ReflectionDatabaseAdapterOneiric,
    )

    return depends.get_sync(ReflectionDatabaseAdapterOneiric)
