from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace


class DummyResult:
    def __init__(self, fetchone_result=None, fetchall_result=None) -> None:
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result or []

    def fetchone(self):
        return self._fetchone_result

    def fetchall(self):
        return self._fetchall_result


class DummyConn:
    def execute(self, sql: str, params):
        if "GROUP BY l.access_type" in sql:
            return DummyResult(
                fetchall_result=[
                    ("search", 5),
                    ("extract:openai", 2),
                    ("extract:anthropic", 1),
                ]
            )
        if "COUNT(DISTINCT l.memory_id)" in sql:
            return DummyResult((3,))
        if "COUNT(*) FROM memory_access_log" in sql:
            return DummyResult((8,))
        if "ORDER BY cnt DESC" in sql:
            return DummyResult(
                fetchall_result=[
                    ("m1", 5, datetime(2026, 1, 1, 12, 0, 0), "facts", "long", 0.9, "p1", "ns1"),
                    ("m2", 3, datetime(2026, 1, 1, 11, 0, 0), None, None, None, None, None),
                ]
            )
        if "ORDER BY l.timestamp DESC" in sql:
            return DummyResult(
                fetchall_result=[
                    ("m1", "search", datetime(2026, 1, 1, 12, 0, 0)),
                    ("m2", None, datetime(2026, 1, 1, 11, 0, 0)),
                ]
            )
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_build_query_config_and_provider_stats() -> None:
    from session_buddy.mcp.tools.infrastructure.access_log_tools import (
        _build_query_config,
        _get_provider_stats,
    )

    cutoff = datetime(2026, 1, 1, 0, 0, 0)
    base = _build_query_config(cutoff, None, None)
    filtered = _build_query_config(cutoff, "proj", "ns")

    assert base == {"where": "l.timestamp >= ?", "params": [cutoff], "join_clause": ""}
    assert filtered["where"] == "l.timestamp >= ? AND c.id = l.memory_id AND c.project = ? AND c.namespace = ?"
    assert filtered["params"] == [cutoff, "proj", "ns"]
    assert filtered["join_clause"] == "JOIN conversations_v2 c ON c.id=l.memory_id"

    assert _get_provider_stats({"search": 5, "extract:openai": 2, "extract:anthropic": 1}) == {
        "openai": 2,
        "anthropic": 1,
    }


def test_access_log_query_helpers_cover_db_paths() -> None:
    from session_buddy.mcp.tools.infrastructure.access_log_tools import (
        _get_access_type_stats,
        _get_distinct_memories,
        _get_recent_accesses,
        _get_top_memories,
        _get_total_accesses,
    )

    conn = DummyConn()
    config = {
        "where": "l.timestamp >= ?",
        "params": [datetime(2026, 1, 1, 0, 0, 0)],
        "join_clause": "",
    }

    assert _get_total_accesses(conn, config) == 8
    assert _get_distinct_memories(conn, config) == 3
    assert _get_access_type_stats(conn, config) == {
        "search": 5,
        "extract:openai": 2,
        "extract:anthropic": 1,
    }

    top = _get_top_memories(conn, config, top_n=2)
    assert top[0]["memory_id"] == "m1"
    assert top[0]["importance_score"] == 0.9
    assert top[1]["category"] is None

    recent = _get_recent_accesses(conn, config, top_n=2)
    assert recent == [
        {
            "memory_id": "m1",
            "access_type": "search",
            "timestamp": "2026-01-01 12:00:00",
        },
        {
            "memory_id": "m2",
            "access_type": None,
            "timestamp": "2026-01-01 11:00:00",
        },
    ]
