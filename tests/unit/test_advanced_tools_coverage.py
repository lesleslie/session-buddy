from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


class DummyMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.mark.asyncio
async def test_conscious_agent_tools_cover_disabled_running_and_force_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.advanced import conscious_agent_tools as tools

    tools._agent = None
    mcp = DummyMCP()
    tools.register_conscious_agent_tools(mcp)

    monkeypatch.setattr(
        tools,
        "get_feature_flags",
        lambda: SimpleNamespace(enable_conscious_agent=False),
    )
    assert await mcp.tools["start_conscious_agent"]() == {"status": "disabled"}

    created = []

    class FakeAgent:
        def __init__(self, db, analysis_interval_hours: int = 6) -> None:
            self.db = db
            self.analysis_interval_hours = analysis_interval_hours
            self.started = False
            self.stopped = False
            created.append(self)

        async def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

        async def force_analysis(self) -> dict[str, str]:
            return {"status": "forced"}

    monkeypatch.setattr(
        tools,
        "get_feature_flags",
        lambda: SimpleNamespace(enable_conscious_agent=True),
    )
    monkeypatch.setattr(tools, "ConsciousAgent", FakeAgent)

    async def fake_missing_db():
        return None

    monkeypatch.setattr(tools, "get_reflection_database", fake_missing_db)
    assert await mcp.tools["start_conscious_agent"]() == {
        "status": "error",
        "message": "Database not available",
    }

    async def fake_db():
        return object()

    monkeypatch.setattr(tools, "get_reflection_database", fake_db)

    started = await mcp.tools["start_conscious_agent"](interval_hours=3)
    assert started == {"status": "started", "interval_hours": 3}
    assert len(created) == 1
    assert created[0].started is True
    assert created[0].analysis_interval_hours == 3

    assert await mcp.tools["stop_conscious_agent"]() == {"status": "stopped"}
    assert created[0].stopped is True
    assert await mcp.tools["stop_conscious_agent"]() == {"status": "not_running"}

    started_again = await mcp.tools["start_conscious_agent"]()
    assert started_again == {"status": "started", "interval_hours": 6}
    assert await mcp.tools["force_conscious_analysis"]() == {"status": "forced"}


@pytest.mark.asyncio
async def test_extract_and_store_memory_cover_disabled_and_enabled_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.advanced import entity_extraction_tools as tools

    tools_module = tools
    monkeypatch.setattr(
        tools_module,
        "get_feature_flags",
        lambda: SimpleNamespace(
            enable_llm_entity_extraction=False,
            use_schema_v2=False,
        ),
    )

    skipped = await tools_module.extract_and_store_memory(
        "user",
        "assistant",
    )
    assert skipped == {"status": "skipped", "reason": "feature_disabled"}

    class FakeProcessedMemory:
        def __init__(self) -> None:
            self.importance_score = 0.2

    class FakeExtractionResult:
        def __init__(self) -> None:
            self.processed_memory = FakeProcessedMemory()
            self.llm_provider = "test-provider"
            self.extraction_time_ms = 12

    class FakeEngine:
        async def extract_entities(self, user_input: str, ai_output: str):
            assert user_input == "user"
            assert ai_output == "assistant"
            return FakeExtractionResult()

    class FakePersist:
        memory_id = "mem-1"
        entity_ids = ["ent-1"]
        relationship_ids = ["rel-1"]

    def fake_insert_processed_memory(
        processed_memory,
        content: str,
        project: str | None = None,
        namespace: str = "default",
        embedding=None,
    ):
        assert content == "User: user\nAssistant: assistant"
        assert project == "proj"
        assert namespace == "ns"
        assert embedding == "embedding"
        return FakePersist()

    class FakeEmbeddingDB:
        async def _generate_embedding(self, content: str):
            assert "Assistant: assistant" in content
            return "embedding"

    class FakeAdapter:
        async def __aenter__(self):
            return FakeEmbeddingDB()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(
        tools_module,
        "get_feature_flags",
        lambda: SimpleNamespace(
            enable_llm_entity_extraction=True,
            use_schema_v2=True,
        ),
    )
    monkeypatch.setattr(tools_module, "EntityExtractionEngine", FakeEngine)
    monkeypatch.setattr(
        tools_module,
        "insert_processed_memory",
        fake_insert_processed_memory,
    )
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter_oneiric",
        SimpleNamespace(ReflectionDatabaseAdapterOneiric=FakeAdapter),
    )
    monkeypatch.setattr(
        "session_buddy.memory.persistence.log_memory_access",
        lambda *args, **kwargs: None,
    )

    result = await tools_module.extract_and_store_memory(
        "user",
        "assistant",
        project="proj",
        namespace="ns",
        activity_score=1.0,
    )

    assert result == {
        "status": "ok",
        "llm_provider": "test-provider",
        "extraction_time_ms": 12,
        "memory_id": "mem-1",
        "entity_ids": ["ent-1"],
        "relationship_ids": ["rel-1"],
    }
