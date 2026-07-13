"""Unit tests for the registered MCP tool wrappers in
``session_buddy/mcp/tools/advanced/intent_tools_registration.py``.

The existing ``test_intent_tools_registration.py`` exercises the helper
functions and the registration count; this file targets the registered
MCP tool wrappers (the ``server.tool()``-decorated coroutines) and their
try/except success + error paths.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.advanced import intent_tools_registration as module


# Important: import the submodule so the lazy ``from ... import get_intent_detector``
# inside the wrappers resolves to a name that ``patch`` can rebind.
import session_buddy.mcp.tools.advanced.intent_detection_tools  # noqa: F401


# ============================================================================
# Helpers
# ============================================================================


@pytest.fixture
def registered() -> dict[str, object]:
    """Register the intent-detection tools on a fake server."""
    fake_server = MagicMock()
    captured: dict[str, object] = {}

    def fake_tool_decorator():
        def decorator(fn):
            captured[fn.__name__] = fn
            return fn

        return decorator

    fake_server.tool = fake_tool_decorator
    module.register_intent_detection_tools(fake_server)
    return captured


def _make_match(
    tool_name: str = "checkpoint",
    confidence: float = 0.85,
    extracted_args: dict[str, Any] | None = None,
    disambiguation_needed: bool = False,
    alternatives: list[str] | None = None,
) -> MagicMock:
    match = MagicMock()
    match.tool_name = tool_name
    match.confidence = confidence
    match.extracted_args = extracted_args or {"k": "v"}
    match.disambiguation_needed = disambiguation_needed
    match.alternatives = alternatives or []
    return match


# ============================================================================
# detect_intent (registered wrapper)
# ============================================================================


class TestRegisteredDetectIntent:
    @pytest.mark.asyncio
    async def test_success_path_returns_match_payload(
        self, registered: dict[str, object]
    ) -> None:
        detector = MagicMock()
        detector.detect_intent = AsyncMock(return_value=_make_match())
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
                AsyncMock(return_value=detector),
            )
            handler = registered["detect_intent"]
            raw = await handler("save my progress", 0.7)

        payload = json.loads(raw) if isinstance(raw, str) else raw
        # The wrapper returns a dict directly (not JSON) — both forms are accepted
        assert payload["detected"] is True
        assert payload["tool_name"] == "checkpoint"
        assert payload["confidence"] == pytest.approx(0.85)
        assert "I detected" in payload["message"]

    @pytest.mark.asyncio
    async def test_no_match_returns_suggestions(
        self, registered: dict[str, object]
    ) -> None:
        detector = MagicMock()
        detector.detect_intent = AsyncMock(return_value=None)
        detector.get_suggestions = AsyncMock(
            return_value=[
                {"tool": "search", "confidence": 0.6, "match_type": "pattern"},
                {"tool": "find", "confidence": 0.4, "match_type": "semantic"},
            ]
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
                AsyncMock(return_value=detector),
            )
            handler = registered["detect_intent"]
            raw = await handler("vague query", 0.7)

        payload = raw if isinstance(raw, dict) else json.loads(raw)
        assert payload["detected"] is False
        assert "Possible matches" in payload["message"]
        assert len(payload["suggestions"]) == 2

    @pytest.mark.asyncio
    async def test_no_match_no_suggestions_returns_help_message(
        self, registered: dict[str, object]
    ) -> None:
        detector = MagicMock()
        detector.detect_intent = AsyncMock(return_value=None)
        detector.get_suggestions = AsyncMock(return_value=[])
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
                AsyncMock(return_value=detector),
            )
            handler = registered["detect_intent"]
            raw = await handler("xyzzy", 0.7)

        payload = raw if isinstance(raw, dict) else json.loads(raw)
        assert payload["detected"] is False
        assert "couldn't determine" in payload["message"]

    @pytest.mark.asyncio
    async def test_exception_returns_error_payload(
        self, registered: dict[str, object]
    ) -> None:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
                AsyncMock(side_effect=RuntimeError("detector down")),
            )
            handler = registered["detect_intent"]
            raw = await handler("anything", 0.5)

        payload = raw if isinstance(raw, dict) else json.loads(raw)
        assert payload["detected"] is False
        assert "detector down" in payload["error"]
        assert "encountered an error" in payload["message"]


# ============================================================================
# get_intent_suggestions (registered wrapper)
# ============================================================================


class TestRegisteredGetIntentSuggestions:
    @pytest.mark.asyncio
    async def test_success_path(self, registered: dict[str, object]) -> None:
        detector = MagicMock()
        detector.get_suggestions = AsyncMock(
            return_value=[
                {"tool": "a", "confidence": 0.8, "match_type": "pattern"},
                {"tool": "b", "confidence": 0.5, "match_type": "semantic"},
            ]
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
                AsyncMock(return_value=detector),
            )
            handler = registered["get_intent_suggestions"]
            raw = await handler("vague", 3)

        payload = raw if isinstance(raw, dict) else json.loads(raw)
        assert payload["count"] == 2
        assert payload["suggestions"][0]["tool"] == "a"
        assert "Found 2" in payload["message"]

    @pytest.mark.asyncio
    async def test_no_suggestions(self, registered: dict[str, object]) -> None:
        detector = MagicMock()
        detector.get_suggestions = AsyncMock(return_value=[])
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
                AsyncMock(return_value=detector),
            )
            handler = registered["get_intent_suggestions"]
            raw = await handler("nothing", 3)

        payload = raw if isinstance(raw, dict) else json.loads(raw)
        assert payload["count"] == 0
        assert payload["suggestions"] == []
        assert "No matching tools" in payload["message"]

    @pytest.mark.asyncio
    async def test_exception_returns_error(
        self, registered: dict[str, object]
    ) -> None:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
                AsyncMock(side_effect=RuntimeError("boom")),
            )
            handler = registered["get_intent_suggestions"]
            raw = await handler("anything", 5)

        payload = raw if isinstance(raw, dict) else json.loads(raw)
        assert payload["suggestions"] == []
        assert payload["count"] == 0
        assert "boom" in payload["error"]
        assert "Failed to generate suggestions" in payload["message"]


# ============================================================================
# list_supported_intents (registered wrapper)
# ============================================================================


class TestRegisteredListSupportedIntents:
    @pytest.mark.asyncio
    async def test_success_path(self, registered: dict[str, object]) -> None:
        detector = MagicMock()
        detector.patterns = {"checkpoint": ["save progress"]}
        detector.semantic_examples = {"checkpoint": ["saving now"]}
        detector.argument_extraction = {"checkpoint": {"k": {"patterns": ["x"]}}}
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
                AsyncMock(return_value=detector),
            )
            handler = registered["list_supported_intents"]
            raw = await handler()

        payload = raw if isinstance(raw, dict) else json.loads(raw)
        assert payload["total_tools"] == 1
        assert "checkpoint" in payload["tools"]
        assert payload["tools"]["checkpoint"]["has_argument_extraction"] is True
        assert "supports 1 tools" in payload["message"]

    @pytest.mark.asyncio
    async def test_exception_returns_error(
        self, registered: dict[str, object]
    ) -> None:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector",
                AsyncMock(side_effect=RuntimeError("listing boom")),
            )
            handler = registered["list_supported_intents"]
            raw = await handler()

        payload = raw if isinstance(raw, dict) else json.loads(raw)
        assert payload["tools"] == {}
        assert payload["total_tools"] == 0
        assert "listing boom" in payload["error"]
        assert "Failed to list" in payload["message"]
