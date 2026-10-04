"""Reflection database DDL — V2 only.

The V1 reflection tables (conversations, reflections, reflection_tags,
project_groups, project_dependencies, session_links, access_log_v2,
code_graphs) have been retired as of 2026-10-04. The live
``ReflectionDatabase`` class (in ``reflection/database.py``) now
points at the V2 schema defined in ``memory/schema_v2.py``.

Public function names are preserved for compatibility but they now
delegate to V2.
"""

from __future__ import annotations

from session_buddy.memory.schema_v2 import SCHEMA_V2_SQL


def initialize_schema(conn) -> None:
    """Run the V2 schema DDL on the given connection.

    Replaces the V1 schema bootstrap. The connection is the live
    DuckDB connection from ``ReflectionDatabase``.
    """
    conn.execute(SCHEMA_V2_SQL)


def create_conversations_table(conn) -> None:
    """No-op shim — V2 ``conversations_v2`` is created by ``SCHEMA_V2_SQL``."""
    conn.execute(SCHEMA_V2_SQL)


def create_reflections_table(conn) -> None:
    """No-op shim — V2 ``reflections_v2`` is created by ``SCHEMA_V2_SQL``."""
    conn.execute(SCHEMA_V2_SQL)
