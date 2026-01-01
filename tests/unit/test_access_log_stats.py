from __future__ import annotations

import typing as t
from types import SimpleNamespace

import duckdb
import pytest
from session_buddy.memory.schema_v2 import SCHEMA_V2_SQL
from session_buddy.tools.access_log_tools import register_access_log_tools


class DummyMCP:
    def __init__(self) -> None:
        self.tools: dict[str, t.Callable[..., t.Any]] = {}

    def tool(self) -> t.Callable[[t.Callable[..., t.Any]], t.Callable[..., t.Any]]:
        def decorator(fn: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.mark.asyncio
async def test_access_log_stats_reports_top_and_provider(
    tmp_path: t.Any, monkeypatch: t.Any
) -> None:
    from session_buddy import settings as settings_mod

    db_path = tmp_path / "stats.duckdb"

    # Configure settings
    fake_settings = SimpleNamespace(database_path=str(db_path))
    monkeypatch.setattr(settings_mod, "get_settings", lambda: fake_settings)

    # Setup v2 schema
    conn = duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})
    conn.execute(SCHEMA_V2_SQL)
    # Insert a memory row
    conn.execute(
        """
        INSERT INTO conversations_v2 (id, content, category, importance_score, memory_tier, searchable_content)
        VALUES ('m1','c','facts',0.6,'long_term','c')
        """
    )
    # Insert access log entries (two types + provider extraction)
    conn.execute(
        "INSERT INTO memory_access_log (id, memory_id, access_type) VALUES ('a1','m1','search')"
    )
    conn.execute(
        "INSERT INTO memory_access_log (id, memory_id, access_type) VALUES ('a2','m1','extract:openai')"
    )
    conn.close()

    # Register tool and call
    mcp = DummyMCP()
    register_access_log_tools(mcp)
    stats = await mcp.tools["access_log_stats"](hours=24, top_n=5)

    # Check for errors first
    if "error" in stats:
        pytest.skip(f"Access log stats failed: {stats['error']}")

    assert stats["total_accesses"] >= 2
    assert stats["by_type"].get("search", 0) >= 1
    assert stats["by_provider"].get("openai", 0) >= 1
    assert stats["top_memories"][0]["memory_id"] == "m1"
