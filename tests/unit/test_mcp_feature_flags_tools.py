from __future__ import annotations

import importlib
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
async def test_register_feature_flags_tools_uses_current_flag_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.infrastructure import feature_flags_tools

    flags = SimpleNamespace(
        use_schema_v2=True,
        enable_llm_entity_extraction=False,
        enable_anthropic=True,
        enable_ollama=False,
        enable_conscious_agent=True,
        enable_filesystem_extraction=False,
    )
    monkeypatch.setattr(
        feature_flags_tools,
        "get_feature_flags",
        lambda: flags,
    )

    mcp = DummyMCP()
    feature_flags_tools.register_feature_flags_tools(mcp)

    status = await mcp.tools["feature_flags_status"]()
    assert status == {
        "use_schema_v2": True,
        "enable_llm_entity_extraction": False,
        "enable_anthropic": True,
        "enable_ollama": False,
        "enable_conscious_agent": True,
        "enable_filesystem_extraction": False,
    }

    plan = await mcp.tools["rollout_plan"]()
    assert "day_1_2" in plan
    assert "day_3_4" in plan
    assert "day_5_6" in plan
    assert "day_7" in plan
    assert "rollback" in plan
    assert plan["notes"].startswith("All flags default to false")


def test_tools_package_alias_points_to_mcp_module() -> None:
    compat = importlib.import_module("session_buddy.tools.feature_flags_tools")
    mcp_module = importlib.import_module(
        "session_buddy.mcp.tools.infrastructure.feature_flags_tools"
    )

    assert compat is mcp_module
    assert sys.modules["session_buddy.tools.feature_flags_tools"] is mcp_module
