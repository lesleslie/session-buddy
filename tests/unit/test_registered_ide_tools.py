"""Unit tests for the MCP tool wrappers in session_buddy/mcp/tools/ide.py.

These tests target the registered MCP tool functions (``get_ide_diagnostics``,
``search_code_patterns``, ``get_symbol_info``, ``find_usages``, ``pycharm_health``)
and exercise their try/except success + error paths so the registered
callable surface is covered.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from session_buddy.mcp.tools.ide import (
    PyCharmMCPAdapter,
    get_pycharm_adapter,
    register_ide_tools,
)


@pytest.fixture
def registered() -> dict[str, object]:
    """Register the IDE tools on a fake server and return the captured handlers."""
    fake_server = MagicMock()
    captured: dict[str, object] = {}

    def fake_tool_decorator():
        def decorator(fn):
            captured[fn.__name__] = fn
            return fn

        return decorator

    fake_server.tool = fake_tool_decorator
    # Use a fresh adapter so we don't share state with the singleton
    register_ide_tools(fake_server)
    return captured


@pytest.fixture
def adapter() -> PyCharmMCPAdapter:
    return PyCharmMCPAdapter()


# ============================================================================
# get_ide_diagnostics (registered wrapper)
# ============================================================================


class TestGetIdeDiagnosticsTool:
    @pytest.mark.asyncio
    async def test_returns_success_payload(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()
        monkeypatch.setattr(
            adapter,
            "get_file_problems",
            _async_return(
                [
                    {
                        "severity": "ERROR",
                        "line": 10,
                        "column": 4,
                        "message": "boom",
                        "category": "GENERAL",
                    },
                    {
                        "severity": "WARNING",
                        "line": 12,
                        "column": 0,
                        "message": "minor",
                        "category": "STYLE",
                    },
                ]
            ),
        )

        handler = registered["get_ide_diagnostics"]
        raw = await handler("src/main.py", errors_only=False)
        payload = json.loads(raw)

        assert payload["success"] is True
        assert payload["file_path"] == "src/main.py"
        assert payload["count"] == 2
        # Issue order matches input order
        assert payload["issues"][0]["severity"] == "ERROR"
        assert payload["issues"][0]["message"] == "boom"
        assert payload["issues"][1]["severity"] == "WARNING"

    @pytest.mark.asyncio
    async def test_returns_failure_payload_on_exception(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()

        async def _explode(*_args, **_kwargs):
            raise RuntimeError("diagnostic boom")

        monkeypatch.setattr(adapter, "get_file_problems", _explode)

        handler = registered["get_ide_diagnostics"]
        raw = await handler("anywhere.py", errors_only=True)
        payload = json.loads(raw)

        assert payload["success"] is False
        assert "diagnostic boom" in payload["error"]
        assert payload["file_path"] == "anywhere.py"


# ============================================================================
# search_code_patterns
# ============================================================================


class TestSearchCodePatternsTool:
    @pytest.mark.asyncio
    async def test_returns_success_payload(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()
        # Build a MagicMock that mimics SearchResult
        result = MagicMock()
        result.file_path = "src/foo.py"
        result.line_number = 42
        result.column = 8
        result.match_text = "def hello"
        result.context_before = None
        result.context_after = None
        monkeypatch.setattr(adapter, "search_regex", _async_return([result]))

        handler = registered["search_code_patterns"]
        raw = await handler("def hello", "*.py")
        payload = json.loads(raw)

        assert payload["success"] is True
        assert payload["pattern"] == "def hello"
        assert payload["count"] == 1
        match = payload["results"][0]
        assert match["file_path"] == "src/foo.py"
        assert match["line_number"] == 42

    @pytest.mark.asyncio
    async def test_returns_failure_payload_on_exception(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()

        async def _explode(*_args, **_kwargs):
            raise RuntimeError("search boom")

        monkeypatch.setattr(adapter, "search_regex", _explode)

        handler = registered["search_code_patterns"]
        raw = await handler("foo", None)
        payload = json.loads(raw)

        assert payload["success"] is False
        assert "search boom" in payload["error"]
        assert payload["pattern"] == "foo"


# ============================================================================
# get_symbol_info
# ============================================================================


class TestGetSymbolInfoTool:
    @pytest.mark.asyncio
    async def test_returns_success_payload_when_found(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()
        info = {"name": "MyClass", "kind": "class", "file_path": "src/x.py"}
        monkeypatch.setattr(adapter, "get_symbol_info", _async_return(info))

        handler = registered["get_symbol_info"]
        raw = await handler("MyClass")
        payload = json.loads(raw)

        assert payload["success"] is True
        assert payload["symbol_name"] == "MyClass"
        assert payload["name"] == "MyClass"
        assert payload["kind"] == "class"

    @pytest.mark.asyncio
    async def test_returns_not_found_when_none(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()
        monkeypatch.setattr(adapter, "get_symbol_info", _async_return(None))

        handler = registered["get_symbol_info"]
        raw = await handler("DoesNotExist")
        payload = json.loads(raw)

        assert payload["success"] is False
        assert "not found" in payload["error"]

    @pytest.mark.asyncio
    async def test_returns_failure_on_exception(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()

        async def _explode(*_args, **_kwargs):
            raise RuntimeError("symbol boom")

        monkeypatch.setattr(adapter, "get_symbol_info", _explode)

        handler = registered["get_symbol_info"]
        raw = await handler("X")
        payload = json.loads(raw)

        assert payload["success"] is False
        assert "symbol boom" in payload["error"]


# ============================================================================
# find_usages
# ============================================================================


class TestFindUsagesTool:
    @pytest.mark.asyncio
    async def test_returns_success_payload(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()
        usages = [
            {
                "file_path": "src/a.py",
                "line": 5,
                "column": 0,
                "type": "reference",
                "symbol": "MyClass",
            },
            {
                "file_path": "src/b.py",
                "line": 22,
                "column": 4,
                "type": "call",
                "symbol": "MyClass",
            },
        ]
        monkeypatch.setattr(adapter, "find_usages", _async_return(usages))

        handler = registered["find_usages"]
        raw = await handler("MyClass")
        payload = json.loads(raw)

        assert payload["success"] is True
        assert payload["symbol_name"] == "MyClass"
        assert payload["count"] == 2
        assert payload["usages"][0]["type"] == "reference"
        assert payload["usages"][1]["type"] == "call"

    @pytest.mark.asyncio
    async def test_returns_failure_on_exception(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()

        async def _explode(*_args, **_kwargs):
            raise RuntimeError("usages boom")

        monkeypatch.setattr(adapter, "find_usages", _explode)

        handler = registered["find_usages"]
        raw = await handler("MyClass")
        payload = json.loads(raw)

        assert payload["success"] is False
        assert "usages boom" in payload["error"]


# ============================================================================
# pycharm_health
# ============================================================================


class TestPyCharmHealthTool:
    @pytest.mark.asyncio
    async def test_returns_success_payload(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()
        monkeypatch.setattr(
            adapter,
            "health_check",
            _async_return(
                {
                    "mcp_available": True,
                    "circuit_breaker_open": False,
                    "failure_count": 0,
                    "cache_size": 7,
                }
            ),
        )

        handler = registered["pycharm_health"]
        raw = await handler()
        payload = json.loads(raw)

        assert payload["success"] is True
        assert payload["healthy"] is True
        assert payload["mcp_available"] is True
        assert payload["cache_size"] == 7

    @pytest.mark.asyncio
    async def test_returns_failure_on_exception(
        self, registered: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = get_pycharm_adapter()

        async def _explode(*_args, **_kwargs):
            raise RuntimeError("health boom")

        monkeypatch.setattr(adapter, "health_check", _explode)

        handler = registered["pycharm_health"]
        raw = await handler()
        payload = json.loads(raw)

        assert payload["success"] is False
        assert "health boom" in payload["error"]


# ============================================================================
# helpers
# ============================================================================


def _async_return(value):
    """Build a coroutine that returns ``value`` (avoid async-def boilerplate)."""
    async def _coro(*_args, **_kwargs):
        return value

    return _coro