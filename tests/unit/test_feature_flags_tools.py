from __future__ import annotations

import typing as t
from types import SimpleNamespace

import pytest
from session_buddy.tools.feature_flags_tools import register_feature_flags_tools


class DummyMCP:
    def __init__(self) -> None:
        self.tools: dict[str, t.Callable[..., t.Any]] = {}

    def tool(self) -> t.Callable[[t.Callable[..., t.Any]], t.Callable[..., t.Any]]:
        def decorator(fn: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.mark.asyncio
async def test_feature_flags_status_shape(monkeypatch: t.Any) -> None:
    # No env settings override; just ensure keys are present
    mcp = DummyMCP()
    register_feature_flags_tools(mcp)
    res = await mcp.tools["feature_flags_status"]()
    keys = {
        "use_schema_v2",
        "enable_llm_entity_extraction",
        "enable_anthropic",
        "enable_ollama",
        "enable_conscious_agent",
        "enable_filesystem_extraction",
    }
    assert keys.issubset(res.keys())


@pytest.mark.asyncio
async def test_rollout_plan_contains_staged_steps() -> None:
    mcp = DummyMCP()
    register_feature_flags_tools(mcp)

    plan = await mcp.tools["rollout_plan"]()

    assert "day_1_2" in plan
    assert "day_3_4" in plan
    assert "rollback" in plan
    assert any("SESSION_MGMT_USE_SCHEMA_V2" in step for step in plan["day_1_2"])
    assert any("trigger_migration" in step for step in plan["rollback"])
