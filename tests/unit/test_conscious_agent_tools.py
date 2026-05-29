"""Tests for mcp.tools.advanced.conscious_agent_tools."""

from __future__ import annotations

import typing as t
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class DummyMCP:
    """Dummy FastMCP for testing tool registration."""

    def __init__(self) -> None:
        self.tools: dict[str, t.Callable[..., t.Any]] = {}

    def tool(
        self,
    ) -> t.Callable[[t.Callable[..., t.Any]], t.Callable[..., t.Any]]:
        def decorator(fn: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.fixture(autouse=True)
def reset_agent_state():
    """Reset _agent global before each test."""
    import session_buddy.mcp.tools.advanced.conscious_agent_tools as tools_mod

    original = tools_mod._agent
    tools_mod._agent = None
    yield
    tools_mod._agent = original


class TestRegisterConsciousAgentTools:
    """Tests for register_conscious_agent_tools function."""

    def test_register_conscious_agent_tools_registers_three_tools(self) -> None:
        """register_conscious_agent_tools should register 3 tools."""
        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mcp = DummyMCP()
        register_conscious_agent_tools(mcp)

        assert len(mcp.tools) == 3
        assert "start_conscious_agent" in mcp.tools
        assert "stop_conscious_agent" in mcp.tools
        assert "force_conscious_analysis" in mcp.tools


class TestStartConsciousAgentTool:
    """Tests for the start_conscious_agent tool behavior."""

    @pytest.mark.asyncio
    async def test_returns_disabled_when_flag_is_off(self) -> None:
        """start_conscious_agent should return disabled status when flag is off."""
        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_feature_flags"
        ) as mock_flags:
            mock_flags.return_value.enable_conscious_agent = False

            register_conscious_agent_tools(mcp)
            result = await mcp.tools["start_conscious_agent"]()

            assert result == {"status": "disabled"}

    @pytest.mark.asyncio
    async def test_returns_error_when_database_not_available(self) -> None:
        """start_conscious_agent should return error when database is None."""
        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_feature_flags"
        ) as mock_flags:
            mock_flags.return_value.enable_conscious_agent = True

            with patch(
                "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_reflection_database",
                new_callable=AsyncMock,
            ) as mock_db:
                mock_db.return_value = None

                register_conscious_agent_tools(mcp)
                result = await mcp.tools["start_conscious_agent"]()

                assert result == {
                    "status": "error",
                    "message": "Database not available",
                }

    @pytest.mark.asyncio
    async def test_starts_agent_with_custom_interval(self) -> None:
        """start_conscious_agent should start agent with custom interval."""
        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mock_db = MagicMock()
        mock_agent = MagicMock()
        mock_agent.start = AsyncMock()

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_feature_flags"
        ) as mock_flags:
            mock_flags.return_value.enable_conscious_agent = True

            with patch(
                "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_reflection_database",
                new_callable=AsyncMock,
            ) as mock_get_db:
                mock_get_db.return_value = mock_db

                with patch(
                    "session_buddy.mcp.tools.advanced.conscious_agent_tools.ConsciousAgent",
                ) as MockAgent:
                    MockAgent.return_value = mock_agent

                    register_conscious_agent_tools(mcp)
                    result = await mcp.tools["start_conscious_agent"](interval_hours=3)

                    MockAgent.assert_called_once()
                    assert MockAgent.call_args[1]["analysis_interval_hours"] == 3
                    mock_agent.start.assert_called_once()
                    assert result == {"status": "started", "interval_hours": 3}

    @pytest.mark.asyncio
    async def test_uses_existing_agent_if_already_started(self) -> None:
        """start_conscious_agent should reuse existing agent."""
        import session_buddy.mcp.tools.advanced.conscious_agent_tools as tools_mod

        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mock_db = MagicMock()
        mock_agent = MagicMock()
        mock_agent.start = AsyncMock()

        tools_mod._agent = mock_agent

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_feature_flags"
        ) as mock_flags:
            mock_flags.return_value.enable_conscious_agent = True

            with patch(
                "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_reflection_database",
                new_callable=AsyncMock,
            ) as mock_get_db:
                mock_get_db.return_value = mock_db

                with patch(
                    "session_buddy.mcp.tools.advanced.conscious_agent_tools.ConsciousAgent",
                ) as MockAgent:
                    register_conscious_agent_tools(mcp)
                    result = await mcp.tools["start_conscious_agent"]()

                    MockAgent.assert_not_called()
                    mock_agent.start.assert_called_once()
                    assert result == {"status": "started", "interval_hours": 6}


class TestStopConsciousAgentTool:
    """Tests for the stop_conscious_agent tool behavior."""

    @pytest.mark.asyncio
    async def test_returns_not_running_when_agent_is_none(self) -> None:
        """stop_conscious_agent should return not_running when agent is None."""
        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mcp = DummyMCP()
        register_conscious_agent_tools(mcp)
        result = await mcp.tools["stop_conscious_agent"]()

        assert result == {"status": "not_running"}

    @pytest.mark.asyncio
    async def test_stops_agent_and_sets_to_none(self) -> None:
        """stop_conscious_agent should stop agent and clear global."""
        import session_buddy.mcp.tools.advanced.conscious_agent_tools as tools_mod

        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mock_agent = MagicMock()
        mock_agent.stop = AsyncMock()

        tools_mod._agent = mock_agent

        mcp = DummyMCP()
        register_conscious_agent_tools(mcp)
        result = await mcp.tools["stop_conscious_agent"]()

        mock_agent.stop.assert_called_once()
        assert tools_mod._agent is None
        assert result == {"status": "stopped"}


class TestForceConsciousAnalysisTool:
    """Tests for the force_conscious_analysis tool behavior."""

    @pytest.mark.asyncio
    async def test_returns_error_when_database_not_available(self) -> None:
        """force_conscious_analysis should return error when database is None."""
        import session_buddy.mcp.tools.advanced.conscious_agent_tools as tools_mod

        tools_mod._agent = None

        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_reflection_database",
            new_callable=AsyncMock,
        ) as mock_db:
            mock_db.return_value = None

            register_conscious_agent_tools(mcp)
            result = await mcp.tools["force_conscious_analysis"]()

            assert result == {
                "status": "error",
                "message": "Database not available",
            }

    @pytest.mark.asyncio
    async def test_creates_agent_if_none_and_runs_analysis(self) -> None:
        """force_conscious_analysis should create agent if None and run analysis."""
        import session_buddy.mcp.tools.advanced.conscious_agent_tools as tools_mod

        tools_mod._agent = None

        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mock_db = MagicMock()
        mock_agent = MagicMock()
        mock_analysis_result = {
            "promoted_count": 2,
            "demoted_count": 1,
            "patterns_analyzed": 10,
        }
        mock_agent.force_analysis = AsyncMock(return_value=mock_analysis_result)

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_reflection_database",
            new_callable=AsyncMock,
        ) as mock_get_db:
            mock_get_db.return_value = mock_db

            with patch(
                "session_buddy.mcp.tools.advanced.conscious_agent_tools.ConsciousAgent",
            ) as MockAgent:
                MockAgent.return_value = mock_agent

                register_conscious_agent_tools(mcp)
                result = await mcp.tools["force_conscious_analysis"]()

                MockAgent.assert_called_once()
                mock_agent.force_analysis.assert_called_once()
                assert result == mock_analysis_result
                assert tools_mod._agent is mock_agent

    @pytest.mark.asyncio
    async def test_uses_existing_agent_if_available(self) -> None:
        """force_conscious_analysis should use existing agent if available."""
        import session_buddy.mcp.tools.advanced.conscious_agent_tools as tools_mod

        from session_buddy.mcp.tools.advanced.conscious_agent_tools import (
            register_conscious_agent_tools,
        )

        mock_db = MagicMock()
        mock_agent = MagicMock()
        mock_analysis_result = {"promoted_count": 0, "demoted_count": 0}
        mock_agent.force_analysis = AsyncMock(return_value=mock_analysis_result)

        tools_mod._agent = mock_agent

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.advanced.conscious_agent_tools.get_reflection_database",
            new_callable=AsyncMock,
        ) as mock_get_db:
            mock_get_db.return_value = mock_db

            with patch(
                "session_buddy.mcp.tools.advanced.conscious_agent_tools.ConsciousAgent",
            ) as MockAgent:
                register_conscious_agent_tools(mcp)
                result = await mcp.tools["force_conscious_analysis"]()

                MockAgent.assert_not_called()
                mock_agent.force_analysis.assert_called_once()
                assert result == mock_analysis_result