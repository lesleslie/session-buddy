"""Tests for session_buddy.mcp.tools.infrastructure.feature_flags_tools.

Covers the MCP feature flag inspection tools:
- ``register_feature_flags_tools`` registers both tools on the MCP server.
- ``feature_flags_status`` returns current flag values from settings.
- ``rollout_plan`` returns the staged enablement plan.
- The tools are async callables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from session_buddy.mcp.tools.infrastructure import feature_flags_tools as mod
from session_buddy.mcp.tools.infrastructure.feature_flags_tools import (
    register_feature_flags_tools,
)


# ---------------------------------------------------------------------------
# FakeMCP
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Captures @mcp.tool() registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *, name: str | None = None, description: str | None = None):  # noqa: D401
        def decorator(fn: Any) -> Any:
            self.tools[name or fn.__name__] = fn
            return fn

        return decorator


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _FakeFlags:
    use_schema_v2: bool = False
    enable_llm_entity_extraction: bool = False
    enable_anthropic: bool = False
    enable_ollama: bool = False
    enable_conscious_agent: bool = False
    enable_filesystem_extraction: bool = False
    enable_crackerjack_fallback: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def patched_flags(monkeypatch: pytest.MonkeyPatch) -> _FakeFlags:
    flags = _FakeFlags()
    monkeypatch.setattr(
        mod,
        "get_feature_flags",
        lambda: flags,
    )
    return flags


@pytest.fixture
def registered() -> tuple[_FakeMCP, _FakeMCP]:
    mcp = _FakeMCP()
    register_feature_flags_tools(mcp)
    return mcp, mcp


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class TestRegisterFeatureFlagsTools:
    def test_registers_two_tools(self) -> None:
        mcp = _FakeMCP()
        register_feature_flags_tools(mcp)
        assert "feature_flags_status" in mcp.tools
        assert "rollout_plan" in mcp.tools

    def test_does_not_register_extra(self) -> None:
        mcp = _FakeMCP()
        register_feature_flags_tools(mcp)
        assert len(mcp.tools) == 2

    def test_returns_none(self) -> None:
        mcp = _FakeMCP()
        result = register_feature_flags_tools(mcp)
        assert result is None


# ---------------------------------------------------------------------------
# feature_flags_status
# ---------------------------------------------------------------------------


class TestFeatureFlagsStatus:
    def test_returns_all_six_flags(
        self,
        registered,
        patched_flags: _FakeFlags,
    ) -> None:
        _mcp, tools = registered
        result = asyncio_check(tools.tools["feature_flags_status"])
        assert result == {
            "use_schema_v2": False,
            "enable_llm_entity_extraction": False,
            "enable_anthropic": False,
            "enable_ollama": False,
            "enable_conscious_agent": False,
            "enable_filesystem_extraction": False,
        }

    def test_returns_only_documented_flags(
        self,
        registered,
        patched_flags: _FakeFlags,
    ) -> None:
        # Add an extra attribute to make sure it doesn't leak through.
        patched_flags.extras = {"enable_experimental": True}
        _mcp, tools = registered
        result = asyncio_check(tools.tools["feature_flags_status"])
        assert "enable_experimental" not in result
        assert "enable_crackerjack_fallback" not in result

    def test_reflects_current_flag_values(
        self,
        registered,
        patched_flags: _FakeFlags,
    ) -> None:
        patched_flags.use_schema_v2 = True
        patched_flags.enable_anthropic = True
        _mcp, tools = registered
        result = asyncio_check(tools.tools["feature_flags_status"])
        assert result["use_schema_v2"] is True
        assert result["enable_anthropic"] is True
        assert result["enable_ollama"] is False

    def test_all_flags_true(
        self,
        registered,
        patched_flags: _FakeFlags,
    ) -> None:
        for fname in (
            "use_schema_v2",
            "enable_llm_entity_extraction",
            "enable_anthropic",
            "enable_ollama",
            "enable_conscious_agent",
            "enable_filesystem_extraction",
        ):
            setattr(patched_flags, fname, True)
        _mcp, tools = registered
        result = asyncio_check(tools.tools["feature_flags_status"])
        assert all(result.values())


# ---------------------------------------------------------------------------
# rollout_plan
# ---------------------------------------------------------------------------


class TestRolloutPlan:
    def test_returns_expected_keys(self, registered) -> None:
        _mcp, tools = registered
        result = asyncio_check(tools.tools["rollout_plan"])
        assert set(result.keys()) == {
            "day_1_2",
            "day_3_4",
            "day_5_6",
            "day_7",
            "rollback",
            "notes",
        }

    def test_day_segments_are_lists_of_strings(self, registered) -> None:
        _mcp, tools = registered
        result = asyncio_check(tools.tools["rollout_plan"])
        for key in ("day_1_2", "day_3_4", "day_5_6", "day_7", "rollback"):
            assert isinstance(result[key], list)
            for item in result[key]:
                assert isinstance(item, str)
                assert item  # non-empty

    def test_mentions_schema_v2_in_day_1_2(self, registered) -> None:
        _mcp, tools = registered
        result = asyncio_check(tools.tools["rollout_plan"])
        joined = " ".join(result["day_1_2"])
        assert "SESSION_MGMT_USE_SCHEMA_V2" in joined

    def test_mentions_rollback_helpers(self, registered) -> None:
        _mcp, tools = registered
        result = asyncio_check(tools.tools["rollout_plan"])
        joined = " ".join(result["rollback"])
        assert "trigger_migration" in joined
        assert "rollback_migration" in joined

    def test_notes_mentions_monitoring(self, registered) -> None:
        _mcp, tools = registered
        result = asyncio_check(tools.tools["rollout_plan"])
        assert "access_log_stats" in result["notes"]


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


class TestModuleSurface:
    def test_module_has_register_function(self) -> None:
        assert hasattr(mod, "register_feature_flags_tools")
        assert callable(mod.register_feature_flags_tools)


# ---------------------------------------------------------------------------
# Async helper (sync-wrapping for tests)
# ---------------------------------------------------------------------------


def asyncio_check(coro_factory: Any) -> dict[str, Any]:
    """Run an async function or factory and return its dict result."""
    import asyncio

    async def run() -> Any:
        coro = coro_factory
        if asyncio.iscoroutinefunction(coro):
            coro = coro()
        return await coro

    return asyncio.run(run())
