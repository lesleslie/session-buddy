"""Typed-envelope contract for ``_start_impl``.

Task 1.5 of the 2026-08-05 cross-repo-checkpoint-accounting plan:

- ``_start_impl`` must return ``tuple[str, str]`` — ``(prose, conversation_id)``.
  The ``conversation_id`` is a 26-char Crockford ULID persisted to the
  ``session_windows.id`` column.
- The ``start_session_tool`` wrapper (re-exported from
  ``session_buddy.tools.session_tools``) keeps returning ``str`` so existing
  callers do not break.

The ``session_windows`` table is added in Task 2 of the plan; during the
Task 1.5 cycle the test fixture creates it ad-hoc against the test's
isolated reflection DB (see :data:`SESSION_BUDDY_REFLECTION_DB_PRECONDITION`).

Important precondition — env var
-------------------------------
The brief originally instructed the fixture to set ``SESSION_BUDDY_REFLECTION_DB``.
``require_reflection_database()`` does NOT read that env var directly.
The resolution chain is:

  ``require_reflection_database()``
    -> :func:`get_reflection_database` (``session_buddy.utils.instance_managers``)
    -> :func:`init_reflection_adapter` (``session_buddy.adapters.lifecycle``)
    -> :func:`get_reflection_settings`
    -> :func:`ReflectionAdapterSettings.from_settings`
       (``session_buddy.adapters.settings``)
    -> :func:`get_settings().data_dir` (``session_buddy.settings``)

``SessionMgmtSettings`` extends Oneiric's ``OneiricMCPConfig`` which sets
``env_prefix="ONEIRIC_MCP_"``. So the correct env var for overriding the
DB path is ``ONEIRIC_MCP_DATABASE_PATH`` (or ``ONEIRIC_MCP_DATA_DIR`` to
shift the parent dir from which ``reflection.duckdb`` is derived).

The autouse ``isolated_test_db_path`` fixture in ``tests/conftest.py``
already redirects the singleton via :func:`monkeypatch.setattr`; our
fixture only needs to create the ``session_windows`` table on top of
that. Documented here to keep the brief's verification step honest.
"""

from __future__ import annotations

import re

import duckdb
import pytest

from session_buddy.mcp.tools.session.session_tools import _start_impl
from session_buddy.tools.session_tools import start_session_tool


ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$", re.IGNORECASE)

# Honesty note for the verification step (see module docstring): the env var
# that the actual code reads is ONEIRIC_MCP_DATABASE_PATH, not
# SESSION_BUDDY_REFLECTION_DB. The autouse isolated_test_db_path fixture in
# tests/conftest.py is what actually redirects the DB; this is the canonical
# pattern in this codebase.
SESSION_BUDDY_REFLECTION_DB_PRECONDITION = "ONEIRIC_MCP_DATABASE_PATH"


@pytest.fixture
def session_windows_setup(tmp_path):
    """Create the ``session_windows`` table in the test's reflection DB.

    Tests rely on the autouse ``isolated_test_db_path`` fixture from
    :mod:`tests.conftest` to redirect ``get_settings().database_path`` to
    ``tmp_path / session-buddy-data / reflection.duckdb``. This fixture
    creates the ``session_windows`` table on that same file so the
    ``initialize_session`` path can INSERT into it.

    The table DDL matches what Task 2 will emit; we add it eagerly here so
    the test runs before Task 2 lands.
    """
    from session_buddy.settings import get_settings

    db_path = get_settings().database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS session_windows ("
        "id TEXT PRIMARY KEY, working_directory TEXT NOT NULL, project TEXT, "
        "started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "ended_at TIMESTAMP WITH TIME ZONE, session_metadata JSON NOT NULL DEFAULT '{}')"
    )
    conn.close()
    return db_path


@pytest.mark.asyncio
async def test_start_impl_returns_parseable_conversation_id(
    tmp_path,
    monkeypatch,
    session_windows_setup,
) -> None:
    """``_start_impl`` must return ``(prose, conversation_id)`` and the ULID is canonical."""
    prose, conversation_id = await _start_impl(working_directory=str(tmp_path))
    assert ULID_RE.match(conversation_id), (
        f"conversation_id {conversation_id!r} is not a 26-char Crockford ULID"
    )
    # Sanity: prose is a non-empty string (the existing contract is preserved).
    assert isinstance(prose, str)
    assert prose, "prose must not be empty"


def test_start_session_tool_wrapper_preserves_prose_string() -> None:
    """Wrapper must still return ``str`` (not the tuple) so existing callers don't break.

    The brief's reference used ``inspect.signature(...).return_annotation is str``,
    but ``session_buddy/tools/session_tools.py`` declares
    ``from __future__ import annotations``, which turns annotations into
    forward-reference strings. ``get_type_hints`` evaluates them, so this
    check catches a real regression to ``tuple[str, str]`` while passing
    for the unchanged ``-> str`` contract.
    """
    from typing import get_type_hints

    hints = get_type_hints(start_session_tool)
    assert hints["return"] is str, (
        f"start_session_tool return type regressed: {hints['return']!r}"
    )
