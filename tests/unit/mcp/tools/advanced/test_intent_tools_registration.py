"""Tests for session_buddy.mcp.tools.advanced.intent_tools_registration.

Covers the registration function and all helper formatters/impls in
``intent_tools_registration.py`` (276 lines):

- ``initialize_intent_detector``: lazy-detector fetch + print side-effect
- ``_format_detected_intent``: match object -> success dict
- ``_format_no_intent_match``: detector -> suggestions dict (with/without)
- ``_format_intent_error``: error envelope for ``detect_intent``
- ``_detect_intent_impl``: dispatcher (match vs no-match branches)
- ``_format_suggestions_error``: error envelope for ``get_intent_suggestions``
- ``_get_intent_suggestions_impl``: dispatcher (suggestions vs empty)
- ``_build_tools_info``: patterns -> info dict
- ``_format_list_intents_error``: error envelope for ``list_supported_intents``
- ``_list_supported_intents_impl``: dispatcher
- ``register_intent_detection_tools``: registers 3 tools via ``@server.tool()``

Test approach: monkeypatch
``session_buddy.mcp.tools.advanced.intent_detection_tools.get_intent_detector``
so each impl resolves to a ``MagicMock`` detector with ``AsyncMock`` methods,
mirroring the ``_FakeMCP`` / AsyncMock style used in
``test_knowledge_graph_tools.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.advanced import intent_tools_registration as reg
from session_buddy.mcp.tools.advanced.intent_tools_registration import (
    _build_tools_info,
    _detect_intent_impl,
    _format_detected_intent,
    _format_intent_error,
    _format_list_intents_error,
    _format_no_intent_match,
    _format_suggestions_error,
    _get_intent_suggestions_impl,
    _list_supported_intents_impl,
    initialize_intent_detector,
    register_intent_detection_tools,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


class _FakeMCP:
    """FastMCP stand-in recording tool registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _make_detector(
    *,
    match: Any = None,
    suggestions: list[dict[str, Any]] | None = None,
    patterns: dict[str, list[str]] | None = None,
    semantic_examples: dict[str, list[str]] | None = None,
    argument_extraction: dict[str, dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a stub IntentDetector with AsyncMock methods.

    Defaults are empty so each test only sets up the bits it cares about.
    """
    detector = MagicMock()
    detector.detect_intent = AsyncMock(return_value=match)
    detector.get_suggestions = AsyncMock(return_value=suggestions or [])
    detector.patterns = patterns or {}
    detector.semantic_examples = semantic_examples or {}
    detector.argument_extraction = argument_extraction or {}
    return detector


@pytest.fixture
def patch_detector(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Factory fixture returning a function that patches ``get_intent_detector``.

    Usage::

        detector = patch_detector(match=SimpleNamespace(...))
    """
    state: dict[str, Any] = {}

    def _factory(
        *,
        match: Any = None,
        suggestions: list[dict[str, Any]] | None = None,
        patterns: dict[str, list[str]] | None = None,
        semantic_examples: dict[str, list[str]] | None = None,
        argument_extraction: dict[str, dict[str, Any]] | None = None,
    ) -> MagicMock:
        detector = _make_detector(
            match=match,
            suggestions=suggestions,
            patterns=patterns,
            semantic_examples=semantic_examples,
            argument_extraction=argument_extraction,
        )
        state["detector"] = detector

        async def fake_get_intent_detector() -> MagicMock:
            return detector

        monkeypatch.setattr(
            "session_buddy.mcp.tools.advanced.intent_detection_tools"
            ".get_intent_detector",
            fake_get_intent_detector,
        )
        return detector

    state["factory"] = _factory
    return _factory


def _make_match(
    *,
    tool_name: str = "search",
    confidence: float = 0.92,
    extracted_args: dict[str, Any] | None = None,
    disambiguation_needed: bool = False,
    alternatives: list[str] | None = None,
) -> SimpleNamespace:
    """Build a stub ``match`` object with the attributes read by formatters."""
    return SimpleNamespace(
        tool_name=tool_name,
        confidence=confidence,
        extracted_args=extracted_args if extracted_args is not None else {"q": "x"},
        disambiguation_needed=disambiguation_needed,
        alternatives=alternatives if alternatives is not None else [],
    )


# ---------------------------------------------------------------------------
# initialize_intent_detector
# ---------------------------------------------------------------------------


class TestInitializeIntentDetector:
    async def test_calls_get_intent_detector(self, patch_detector: Any) -> None:
        patch_detector()
        with patch("builtins.print") as mock_print:
            await initialize_intent_detector()
        mock_print.assert_called_once()
        assert "intent detection system initialized" in str(mock_print.call_args)

    async def test_propagates_exceptions_from_getter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise RuntimeError("init failed")

        monkeypatch.setattr(
            "session_buddy.mcp.tools.advanced.intent_detection_tools"
            ".get_intent_detector",
            boom,
        )
        with pytest.raises(RuntimeError, match="init failed"):
            await initialize_intent_detector()


# ---------------------------------------------------------------------------
# _format_detected_intent
# ---------------------------------------------------------------------------


class TestFormatDetectedIntent:
    def test_includes_all_match_fields(self) -> None:
        match = _make_match(
            tool_name="query",
            confidence=0.85,
            extracted_args={"k": "v"},
            disambiguation_needed=True,
            alternatives=["alt1", "alt2"],
        )
        out = _format_detected_intent(match)
        assert out["detected"] is True
        assert out["tool_name"] == "query"
        assert out["confidence"] == 0.85
        assert out["extracted_args"] == {"k": "v"}
        assert out["disambiguation_needed"] is True
        assert out["alternatives"] == ["alt1", "alt2"]

    def test_message_includes_tool_name_and_confidence_percent(self) -> None:
        match = _make_match(tool_name="remember", confidence=0.5)
        out = _format_detected_intent(match)
        assert "remember" in out["message"]
        assert "50%" in out["message"]
        assert "/remember" in out["message"]

    def test_zero_confidence_renders_as_0_percent(self) -> None:
        match = _make_match(tool_name="x", confidence=0.0)
        out = _format_detected_intent(match)
        assert "0%" in out["message"]


# ---------------------------------------------------------------------------
# _format_no_intent_match
# ---------------------------------------------------------------------------


class TestFormatNoIntentMatch:
    async def test_with_suggestions_includes_each_tool(self, patch_detector: Any) -> None:
        detector = patch_detector(
            suggestions=[
                {"tool": "remember", "confidence": 0.42},
                {"tool": "search", "confidence": 0.31},
            ]
        )
        out = await _format_no_intent_match(detector, "do thing")
        assert out["detected"] is False
        assert "remember (42%)" in out["message"]
        assert "search (31%)" in out["message"]
        assert out["suggestions"] == [
            {"tool": "remember", "confidence": 0.42},
            {"tool": "search", "confidence": 0.31},
        ]
        detector.get_suggestions.assert_awaited_once_with("do thing", limit=3)

    async def test_without_suggestions_uses_help_hint(self, patch_detector: Any) -> None:
        patch_detector(suggestions=[])
        # Use a fresh detector so we don't depend on fixture state
        detector = MagicMock()
        detector.get_suggestions = AsyncMock(return_value=[])
        out = await _format_no_intent_match(detector, "?")
        assert out["detected"] is False
        assert "/help" in out["message"]
        assert "suggestions" not in out

    async def test_passes_limit_three_to_detector(self, patch_detector: Any) -> None:
        detector = patch_detector(suggestions=[])
        await _format_no_intent_match(detector, "msg")
        detector.get_suggestions.assert_awaited_once_with("msg", limit=3)


# ---------------------------------------------------------------------------
# _format_intent_error
# ---------------------------------------------------------------------------


class TestFormatIntentError:
    def test_returns_error_envelope_with_message(self) -> None:
        out = _format_intent_error("boom")
        assert out["detected"] is False
        assert out["error"] == "boom"
        assert "Intent detection system encountered an error" in out["message"]

    def test_preserves_empty_message(self) -> None:
        out = _format_intent_error("")
        assert out["error"] == ""


# ---------------------------------------------------------------------------
# _detect_intent_impl
# ---------------------------------------------------------------------------


class TestDetectIntentImpl:
    async def test_match_branch_returns_match_dict(self, patch_detector: Any) -> None:
        match = _make_match(tool_name="remember", confidence=0.9)
        patch_detector(match=match)
        out = await _detect_intent_impl("remember the file", 0.7)
        assert out["detected"] is True
        assert out["tool_name"] == "remember"
        assert out["confidence"] == 0.9

    async def test_match_threshold_forwarded(self, patch_detector: Any) -> None:
        detector = patch_detector(match=None, suggestions=[])
        await _detect_intent_impl("hi", 0.55)
        detector.detect_intent.assert_awaited_once_with("hi", 0.55)

    async def test_no_match_with_suggestions(self, patch_detector: Any) -> None:
        patch_detector(
            match=None,
            suggestions=[{"tool": "search", "confidence": 0.2}],
        )
        out = await _detect_intent_impl("foo", 0.7)
        assert out["detected"] is False
        assert "Possible matches" in out["message"]
        assert out["suggestions"] == [{"tool": "search", "confidence": 0.2}]

    async def test_no_match_without_suggestions(self, patch_detector: Any) -> None:
        patch_detector(match=None, suggestions=[])
        out = await _detect_intent_impl("???", 0.7)
        assert out["detected"] is False
        assert "/help" in out["message"]
        assert "suggestions" not in out


# ---------------------------------------------------------------------------
# _format_suggestions_error
# ---------------------------------------------------------------------------


class TestFormatSuggestionsError:
    def test_returns_error_envelope(self) -> None:
        out = _format_suggestions_error("kaboom")
        assert out["suggestions"] == []
        assert out["error"] == "kaboom"
        assert out["count"] == 0
        assert "Failed to generate suggestions" in out["message"]


# ---------------------------------------------------------------------------
# _get_intent_suggestions_impl
# ---------------------------------------------------------------------------


class TestGetIntentSuggestionsImpl:
    async def test_returns_suggestions_with_count(self, patch_detector: Any) -> None:
        patch_detector(
            suggestions=[
                {"tool": "a", "confidence": 0.4},
                {"tool": "b", "confidence": 0.3},
            ]
        )
        out = await _get_intent_suggestions_impl("msg", 2)
        assert out["suggestions"] == [
            {"tool": "a", "confidence": 0.4},
            {"tool": "b", "confidence": 0.3},
        ]
        assert out["count"] == 2
        assert "Found 2" in out["message"]

    async def test_returns_empty_envelope_when_no_suggestions(
        self, patch_detector: Any
    ) -> None:
        patch_detector(suggestions=[])
        out = await _get_intent_suggestions_impl("msg", 5)
        assert out["suggestions"] == []
        assert out["count"] == 0
        assert "No matching tools found" in out["message"]

    async def test_passes_user_limit_to_detector(self, patch_detector: Any) -> None:
        detector = patch_detector(suggestions=[])
        await _get_intent_suggestions_impl("msg", 7)
        detector.get_suggestions.assert_awaited_once_with("msg", 7)


# ---------------------------------------------------------------------------
# _build_tools_info
# ---------------------------------------------------------------------------


class TestBuildToolsInfo:
    def test_builds_info_for_each_pattern(self) -> None:
        detector = _make_detector(
            patterns={"remember": ["save it"], "search": ["find it"]},
            semantic_examples={"remember": ["keep this"], "search": ["locate"]},
            argument_extraction={"remember": {"key": "value"}},
        )
        out = _build_tools_info(detector)
        assert set(out) == {"remember", "search"}
        assert out["remember"]["patterns"] == ["save it"]
        assert out["remember"]["semantic_examples"] == ["keep this"]
        assert out["search"]["patterns"] == ["find it"]
        assert out["search"]["semantic_examples"] == ["locate"]

    def test_marks_argument_extraction_presence(self) -> None:
        detector = _make_detector(
            patterns={"a": ["x"], "b": ["y"]},
            argument_extraction={"a": {"k": "v"}},
        )
        out = _build_tools_info(detector)
        assert out["a"]["has_argument_extraction"] is True
        assert out["b"]["has_argument_extraction"] is False

    def test_handles_missing_semantic_examples_with_default(self) -> None:
        detector = _make_detector(patterns={"a": ["x"]}, semantic_examples={})
        out = _build_tools_info(detector)
        assert out["a"]["semantic_examples"] == []

    def test_returns_empty_dict_when_no_patterns(self) -> None:
        detector = _make_detector()
        out = _build_tools_info(detector)
        assert out == {}


# ---------------------------------------------------------------------------
# _format_list_intents_error
# ---------------------------------------------------------------------------


class TestFormatListIntentsError:
    def test_returns_error_envelope(self) -> None:
        out = _format_list_intents_error("nope")
        assert out["tools"] == {}
        assert out["total_tools"] == 0
        assert out["error"] == "nope"
        assert "Failed to list supported intents" in out["message"]


# ---------------------------------------------------------------------------
# _list_supported_intents_impl
# ---------------------------------------------------------------------------


class TestListSupportedIntentsImpl:
    async def test_returns_tools_with_info(self, patch_detector: Any) -> None:
        patch_detector(
            patterns={"remember": ["save"]},
            semantic_examples={"remember": ["keep"]},
            argument_extraction={"remember": {"k": "v"}},
        )
        out = await _list_supported_intents_impl()
        assert out["total_tools"] == 1
        assert "remember" in out["tools"]
        assert out["tools"]["remember"]["has_argument_extraction"] is True
        assert "Intent detection supports 1 tools" in out["message"]

    async def test_handles_zero_tools(self, patch_detector: Any) -> None:
        patch_detector()
        out = await _list_supported_intents_impl()
        assert out["tools"] == {}
        assert out["total_tools"] == 0
        assert "Intent detection supports 0 tools" in out["message"]


# ---------------------------------------------------------------------------
# register_intent_detection_tools
# ---------------------------------------------------------------------------


class TestRegisterIntentDetectionTools:
    def test_registers_three_tools(self) -> None:
        mcp = _FakeMCP()
        register_intent_detection_tools(mcp)
        assert set(mcp.tools) == {
            "detect_intent",
            "get_intent_suggestions",
            "list_supported_intents",
        }

    def test_registered_callables_are_async(self) -> None:
        import inspect

        mcp = _FakeMCP()
        register_intent_detection_tools(mcp)
        for name, fn in mcp.tools.items():
            assert inspect.iscoroutinefunction(fn), f"{name} is not async"

    async def test_registered_detect_intent_match(
        self, patch_detector: Any
    ) -> None:
        patch_detector(match=_make_match(tool_name="remember", confidence=0.88))
        mcp = _FakeMCP()
        register_intent_detection_tools(mcp)
        out = await mcp.tools["detect_intent"]("remember this", 0.7)
        assert out["detected"] is True
        assert out["tool_name"] == "remember"

    async def test_registered_detect_intent_no_match(
        self, patch_detector: Any
    ) -> None:
        patch_detector(match=None, suggestions=[{"tool": "x", "confidence": 0.1}])
        mcp = _FakeMCP()
        register_intent_detection_tools(mcp)
        out = await mcp.tools["detect_intent"]("???", 0.9)
        assert out["detected"] is False
        assert "Possible matches" in out["message"]

    async def test_registered_detect_intent_error_returns_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise RuntimeError("detector unavailable")

        monkeypatch.setattr(
            "session_buddy.mcp.tools.advanced.intent_detection_tools"
            ".get_intent_detector",
            boom,
        )
        mcp = _FakeMCP()
        register_intent_detection_tools(mcp)
        out = await mcp.tools["detect_intent"]("hi", 0.7)
        assert out["detected"] is False
        assert out["error"] == "detector unavailable"
        assert "Intent detection system encountered an error" in out["message"]

    async def test_registered_get_intent_suggestions(
        self, patch_detector: Any
    ) -> None:
        patch_detector(
            suggestions=[
                {"tool": "a", "confidence": 0.3},
                {"tool": "b", "confidence": 0.2},
            ]
        )
        mcp = _FakeMCP()
        register_intent_detection_tools(mcp)
        out = await mcp.tools["get_intent_suggestions"]("msg", 5)
        assert out["count"] == 2
        assert out["suggestions"][0]["tool"] == "a"

    async def test_registered_get_intent_suggestions_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise OSError("disk gone")

        monkeypatch.setattr(
            "session_buddy.mcp.tools.advanced.intent_detection_tools"
            ".get_intent_detector",
            boom,
        )
        mcp = _FakeMCP()
        register_intent_detection_tools(mcp)
        out = await mcp.tools["get_intent_suggestions"]("msg", 5)
        assert out["suggestions"] == []
        assert out["count"] == 0
        assert out["error"] == "disk gone"
        assert "Failed to generate suggestions" in out["message"]

    async def test_registered_list_supported_intents(self, patch_detector: Any) -> None:
        patch_detector(
            patterns={"remember": ["save"]},
            semantic_examples={"remember": ["keep"]},
        )
        mcp = _FakeMCP()
        register_intent_detection_tools(mcp)
        out = await mcp.tools["list_supported_intents"]()
        assert out["total_tools"] == 1
        assert "remember" in out["tools"]

    async def test_registered_list_supported_intents_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> MagicMock:
            raise RuntimeError("nope")

        monkeypatch.setattr(
            "session_buddy.mcp.tools.advanced.intent_detection_tools"
            ".get_intent_detector",
            boom,
        )
        mcp = _FakeMCP()
        register_intent_detection_tools(mcp)
        out = await mcp.tools["list_supported_intents"]()
        assert out["tools"] == {}
        assert out["total_tools"] == 0
        assert out["error"] == "nope"
        assert "Failed to list supported intents" in out["message"]


# ---------------------------------------------------------------------------
# Module sanity: ensure helpers are bound on the module (not None)
# ---------------------------------------------------------------------------


class TestModuleSanity:
    def test_module_exposes_helpers(self) -> None:
        # Sanity: the registration module re-exports its helpers as attributes
        for name in (
            "initialize_intent_detector",
            "_detect_intent_impl",
            "_format_detected_intent",
            "_format_no_intent_match",
            "_format_intent_error",
            "_get_intent_suggestions_impl",
            "_format_suggestions_error",
            "_list_supported_intents_impl",
            "_build_tools_info",
            "_format_list_intents_error",
            "register_intent_detection_tools",
        ):
            assert hasattr(reg, name), f"{name} missing from module"
            assert getattr(reg, name) is not None
