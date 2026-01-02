from __future__ import annotations

import typing as t
from types import SimpleNamespace

import duckdb
import pytest
from session_buddy.memory.schema_v2 import SCHEMA_V2_SQL
from session_buddy.tools.entity_extraction_tools import register_extraction_tools


class DummyMCP:
    def __init__(self) -> None:
        self.tools: dict[str, t.Callable[..., t.Any]] = {}

    def tool(self) -> t.Callable[[t.Callable[..., t.Any]], t.Callable[..., t.Any]]:
        def decorator(fn: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="Requires LLM provider configuration - skipped in CI/CD environments without API keys"
)
async def test_file_change_extraction_persists_with_activity_weight(
    tmp_path: t.Any, monkeypatch: t.Any
) -> None:
    # Set up temp DB with v2 schema
    db_path = tmp_path / "fs.duckdb"
    conn = duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})
    conn.execute(SCHEMA_V2_SQL)
    conn.close()

    # Monkeypatch settings for DB path
    from session_buddy import settings as settings_mod

    SimpleNamespace(
        database_path=str(db_path),
        llm_extraction_timeout=5,
        llm_extraction_retries=0,
    )
    # Patch get_database_path which is what the persistence module actually uses
    monkeypatch.setattr(settings_mod, "get_database_path", lambda: str(db_path))

    # Monkeypatch feature flags to enable v2 + extraction
    import session_buddy.config.feature_flags as ff
    import session_buddy.tools.entity_extraction_tools as eet

    flags = ff.FeatureFlags(
        use_schema_v2=True,
        enable_llm_entity_extraction=True,
        enable_anthropic=False,
        enable_ollama=False,
        enable_conscious_agent=False,
        enable_filesystem_extraction=True,
    )
    # Patch the symbol used in the tool module so checks pass
    monkeypatch.setattr(eet, "get_feature_flags", lambda: flags)

    # Register extraction tools and call the tool directly
    mcp = DummyMCP()
    register_extraction_tools(mcp)
    extract = mcp.tools["extract_and_store_memory"]

    # Simulate a file-change trigger with context
    user_input = "Updated file: test.py\nContext: {'file_path': 'test.py'}"
    ai_output = "def foo():\n    return 1\n"

    # Use high activity score to bias importance upward
    result = await extract(
        user_input=user_input,
        ai_output=ai_output,
        project="proj",
        namespace="default",
        activity_score=0.9,
    )
    assert result["status"] == "ok"

    # Verify row persisted and importance weighted
    conn = duckdb.connect(str(db_path), config={"allow_unsigned_extensions": True})
    row = conn.execute(
        "SELECT importance_score FROM conversations_v2 WHERE id=?",
        [result["memory_id"]],
    ).fetchone()
    assert row is not None
    imp = float(row[0])
    assert imp >= 0.5
    assert imp <= 1.0
    conn.close()
