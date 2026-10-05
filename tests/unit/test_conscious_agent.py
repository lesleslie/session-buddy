from __future__ import annotations

import typing as t

import duckdb
import pytest
from session_buddy.memory.conscious_agent import ConsciousAgent


@pytest.mark.asyncio
async def test_conscious_agent_promotes_and_demotes(
    tmp_path: t.Any, monkeypatch: t.Any
) -> None:
    # Prepare DB with minimal v2 tables and access logs
    db_path = tmp_path / "agent.duckdb"
    conn = duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})
    conn.execute(
        """
        CREATE TABLE conversations_v2 (
            id TEXT PRIMARY KEY,
            content TEXT,
            embedding FLOAT[384],
            category TEXT,
            subcategory TEXT,
            importance_score REAL,
            memory_tier TEXT,
            access_count INTEGER,
            last_accessed TIMESTAMP,
            project TEXT,
            namespace TEXT,
            timestamp TIMESTAMP,
            session_id TEXT,
            user_id TEXT,
            searchable_content TEXT,
            reasoning TEXT
        );
        CREATE TABLE memory_promotions (
            id TEXT PRIMARY KEY,
            memory_id TEXT,
            from_tier TEXT,
            to_tier TEXT,
            reason TEXT,
            priority_score REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE memory_access_log (
            id TEXT PRIMARY KEY,
            memory_id TEXT,
            access_type TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    # One memory, long_term, high importance (will promote)
    conn.execute(
        "INSERT INTO conversations_v2 (id, content, category, importance_score, memory_tier, searchable_content) VALUES ('m1','c','preferences',0.9,'long_term','c')"
    )
    # Access entries to drive frequency
    for _ in range(6):
        conn.execute(
            "INSERT INTO memory_access_log (id, memory_id, access_type) VALUES (random(), 'm1', 'search')"
        )
    conn.close()

    # Patch settings to use tmp db
    from session_buddy import settings as settings_mod

    # New shape (Phase 3a): settings.database.path (nested group),
    # not the legacy flat settings.database_path.
    fake = type(
        "S",
        (),
        {"database": type("D", (), {"path": str(db_path)})()},
    )
    monkeypatch.setattr(settings_mod, "get_settings", lambda: fake)

    # Run analysis/promotion
    agent = ConsciousAgent(reflection_db=None, analysis_interval_hours=6)
    res = await agent.force_analysis()
    assert res["promoted_count"] >= 1

    # Ensure tier updated
    conn = duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})
    tier = conn.execute(
        "SELECT memory_tier FROM conversations_v2 WHERE id='m1'"
    ).fetchone()[0]
    assert tier == "short_term"

    # Demotion path: mark access log far in past (simulate by deleting logs)
    conn.execute("DELETE FROM memory_access_log")
    # Force demotion
    await agent._demote_stale_memories()
    # Tier should be long_term again
    tier2 = conn.execute(
        "SELECT memory_tier FROM conversations_v2 WHERE id='m1'"
    ).fetchone()[0]
    assert tier2 == "long_term"
    conn.close()
