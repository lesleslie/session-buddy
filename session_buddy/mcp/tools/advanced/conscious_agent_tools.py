#!/usr/bin/env python3
from __future__ import annotations

import typing as t
from typing import TYPE_CHECKING

from session_buddy.config.feature_flags import get_feature_flags
from session_buddy.memory.conscious_agent import ConsciousAgent
from session_buddy.reflection_tools import get_reflection_database

if TYPE_CHECKING:
    from fastmcp import FastMCP

_agent: ConsciousAgent | None = None


def register_conscious_agent_tools(mcp: FastMCP) -> None:
    @mcp.tool()  # type: ignore[no-untyped-call]
    async def start_conscious_agent(interval_hours: int = 6) -> dict[str, t.Any]:
        """Start background Conscious Agent if enabled by flags."""
        flags = get_feature_flags()
        if not flags.enable_conscious_agent:
            return {"status": "disabled"}
        global _agent
        if _agent is None:
            db = await get_reflection_database()
            _agent = ConsciousAgent(db, analysis_interval_hours=interval_hours)
        await _agent.start()
        return {"status": "started", "interval_hours": interval_hours}

    @mcp.tool()  # type: ignore[no-untyped-call]
    async def stop_conscious_agent() -> dict[str, t.Any]:
        """Stop background Conscious Agent if running."""
        global _agent
        if _agent is None:
            return {"status": "not_running"}
        await _agent.stop()
        _agent = None
        return {"status": "stopped"}

    @mcp.tool()  # type: ignore[no-untyped-call]
    async def force_conscious_analysis() -> dict[str, t.Any]:
        """Force a one-time analysis run."""
        global _agent
        if _agent is None:
            db = await get_reflection_database()
            _agent = ConsciousAgent(db)
        return await _agent.force_analysis()
