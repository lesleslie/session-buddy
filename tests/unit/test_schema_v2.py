from __future__ import annotations

import typing as t

import duckdb
from session_buddy.memory.schema_v2 import schema_v2_sql


def test_schema_v2_tables_create(tmp_path: t.Any) -> None:
    db_path = tmp_path / "test_schema_v2.duckdb"
    conn = duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})
    conn.execute(schema_v2_sql())

    # Basic existence checks via simple selects
    for table in (
        "conversations_v2",
        "reflections_v2",
        "memory_entities",
        "memory_relationships",
        "memory_promotions",
        "memory_access_log",
    ):
        conn.execute(f"SELECT 1 FROM {table} LIMIT 1")

    conn.close()
