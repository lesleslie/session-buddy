"""Unit tests for session_buddy.mcp.tools.session.admin_shell_tracking_tools.

Lifts coverage on ``admin_shell_tracking_tools`` from the existing baseline
(23% measured at file scope) to 100% by re-hitting every branch in the
scoped test directory. Mirrors
``tests/unit/test_admin_shell_tracking_tools.py`` with extra coverage for
DI fallback branches and edge-case payloads.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from session_buddy.mcp.tools.session import admin_shell_tracking_tools as mod
from session_buddy.mcp.tools.session.admin_shell_tracking_tools import (
    get_logger,
    register_admin_shell_tracking_tools,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Minimal FastMCP stand-in that captures registered tools."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class _FakeResult:
    """Mimics SessionStartResult / SessionEndResult for tracker returns."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.session_id = payload.get("session_id")
        self.status = payload.get("status")
        self.error = payload.get("error")
        self._payload = payload

    def model_dump(self) -> dict[str, object]:
        return self._payload


def _start_kwargs() -> dict[str, object]:
    return {
        "event_version": "1.0",
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "event_type": "session_start",
        "component_name": "mahavishnu",
        "shell_type": "ZshShell",
        "timestamp": "2026-01-01T00:00:00Z",
        "pid": 1234,
        "user": {"username": "alice", "home": "/home/alice"},
        "hostname": "host-a",
        "environment": {
            "python_version": "3.13.0",
            "platform": "linux",
            "cwd": "/tmp",
        },
        "metadata": {"source": "test"},
    }


# ---------------------------------------------------------------------------
# Autouse fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth gate is a no-op when ``SESSION_BUDDY_SECRET`` is unset."""
    monkeypatch.delenv("SESSION_BUDDY_SECRET", raising=False)
    try:
        from session_buddy.mcp.auth import _reset_core_config

        _reset_core_config()
    except (ImportError, AttributeError):
        pass


@pytest.fixture
def reset_di() -> None:
    """Clear DI state for SessionLifecycleManager / SessionTracker."""
    from session_buddy.di.container import depends

    for key in (
        "session_buddy.core.session_manager.SessionLifecycleManager",
        "session_buddy.mcp.session_tracker.SessionTracker",
    ):
        depends._instances.pop(key, None)  # type: ignore[attr-defined]


@pytest.fixture
def clear_di_managers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``get_sync_typed`` to raise so DI fallback path runs."""
    monkeypatch.setattr(
        mod,
        "get_sync_typed",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            KeyError("Service not registered")
        ),
    )


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


def test_get_logger_returns_module_logger() -> None:
    """``get_logger`` returns a stdlib Logger bound to the module name."""
    logger = get_logger()
    assert isinstance(logger, logging.Logger)
    assert logger.name == mod.__name__


# ---------------------------------------------------------------------------
# Registration smoke tests
# ---------------------------------------------------------------------------


def test_register_registers_both_tools() -> None:
    """Two tools (``track_session_start`` + ``track_session_end``) register."""
    mcp = _FakeMCP()
    register_admin_shell_tracking_tools(mcp)
    assert "track_session_start" in mcp.tools
    assert "track_session_end" in mcp.tools


def test_register_attaches_coroutine_tools() -> None:
    """Both tools are coroutine functions so FastMCP can await them."""
    import inspect

    mcp = _FakeMCP()
    register_admin_shell_tracking_tools(mcp)
    assert inspect.iscoroutinefunction(mcp.tools["track_session_start"])
    assert inspect.iscoroutinefunction(mcp.tools["track_session_end"])


# ---------------------------------------------------------------------------
# track_session_start
# ---------------------------------------------------------------------------


class TestTrackSessionStart:
    @pytest.mark.asyncio
    async def test_happy_path_returns_result_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns the SessionStartResult dict on success."""
        tracker = SimpleNamespace(
            handle_session_start=AsyncMock(
                return_value=_FakeResult(
                    {"session_id": "sess-1", "status": "tracked"}
                ),
            ),
        )
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        result = await mcp.tools["track_session_start"](**_start_kwargs())

        assert result == {"session_id": "sess-1", "status": "tracked"}
        tracker.handle_session_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_defaults_to_empty_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Omitting ``metadata`` substitutes an empty dict."""
        captured: dict[str, object] = {}

        async def handle_session_start(event):
            captured["metadata"] = event.metadata
            return _FakeResult({"session_id": "sess-1", "status": "tracked"})

        tracker = SimpleNamespace(handle_session_start=handle_session_start)
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        kwargs = _start_kwargs()
        kwargs.pop("metadata")
        await mcp.tools["track_session_start"](**kwargs)

        assert captured["metadata"] == {}

    @pytest.mark.asyncio
    async def test_tracker_exception_returns_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tracker raising returns the structured error result."""
        tracker = SimpleNamespace(
            handle_session_start=AsyncMock(
                side_effect=RuntimeError("tracker boom")
            ),
        )
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        result = await mcp.tools["track_session_start"](**_start_kwargs())

        assert result["status"] == "error"
        assert result["session_id"] is None
        assert "tracker boom" in result["error"]

    @pytest.mark.asyncio
    async def test_event_validation_failure_returns_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid event payload triggers the catch-all error path."""
        handle_session_start = AsyncMock()
        tracker = SimpleNamespace(handle_session_start=handle_session_start)
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        bad_kwargs = _start_kwargs()
        # event_type must equal "session_start" for SessionStartEvent validation
        bad_kwargs["event_type"] = "bogus"

        result = await mcp.tools["track_session_start"](**bad_kwargs)

        assert result["status"] == "error"
        assert result["session_id"] is None
        assert result["error"]
        handle_session_start.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_dict_must_be_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing required user fields raise validation error."""

        tracker = SimpleNamespace(handle_session_start=AsyncMock())
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        bad_kwargs = _start_kwargs()
        bad_kwargs["user"] = {"username": "alice"}  # missing 'home'

        result = await mcp.tools["track_session_start"](**bad_kwargs)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_environment_dict_must_be_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing environment fields raise validation error."""

        tracker = SimpleNamespace(handle_session_start=AsyncMock())
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        bad_kwargs = _start_kwargs()
        bad_kwargs["environment"] = {"python_version": "3.13"}  # incomplete

        result = await mcp.tools["track_session_start"](**bad_kwargs)
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# track_session_end
# ---------------------------------------------------------------------------


class TestTrackSessionEnd:
    @pytest.mark.asyncio
    async def test_happy_path_returns_result_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns the SessionEndResult dict on success."""
        tracker = SimpleNamespace(
            handle_session_end=AsyncMock(
                return_value=_FakeResult(
                    {"session_id": "sess-1", "status": "ended"}
                ),
            ),
        )
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        result = await mcp.tools["track_session_end"](
            session_id="sess-1",
            timestamp="2026-01-01T00:01:00Z",
        )

        assert result == {"session_id": "sess-1", "status": "ended"}
        tracker.handle_session_end.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_defaults_to_empty_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Omitting ``metadata`` substitutes an empty dict."""
        captured: dict[str, object] = {}

        async def handle_session_end(event):
            captured["metadata"] = event.metadata
            return _FakeResult(
                {"session_id": event.session_id, "status": "ended"}
            )

        tracker = SimpleNamespace(handle_session_end=handle_session_end)
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        result = await mcp.tools["track_session_end"](
            session_id="sess-1",
            timestamp="2026-01-01T00:01:00Z",
        )

        assert result["status"] == "ended"
        assert captured["metadata"] == {}

    @pytest.mark.asyncio
    async def test_tracker_exception_returns_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tracker raising returns the structured error result."""
        tracker = SimpleNamespace(
            handle_session_end=AsyncMock(
                side_effect=ValueError("kaboom")
            ),
        )
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        result = await mcp.tools["track_session_end"](
            session_id="sess-fail",
            timestamp="2026-01-01T00:01:00Z",
        )

        assert result["status"] == "error"
        assert result["session_id"] == "sess-fail"
        assert "kaboom" in result["error"]

    @pytest.mark.asyncio
    async def test_event_validation_failure_returns_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid event payload triggers the catch-all error path."""
        handle_session_end = AsyncMock()
        tracker = SimpleNamespace(handle_session_end=handle_session_end)
        monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

        mcp = _FakeMCP()
        register_admin_shell_tracking_tools(mcp)
        result = await mcp.tools["track_session_end"](
            session_id="sess-x",
            timestamp="not-a-timestamp",
        )

        assert result["status"] == "error"
        assert result["session_id"] == "sess-x"
        assert result["error"]
        handle_session_end.assert_not_awaited()


# ---------------------------------------------------------------------------
# _get_session_manager — DI branches
# ---------------------------------------------------------------------------


class TestGetSessionManager:
    def test_creates_when_not_registered(
        self, reset_di: None, clear_di_managers: None
    ) -> None:
        """Without a registered manager, a fresh one is built (fallback path)."""
        manager = mod._get_session_manager()  # noqa: SLF001
        assert isinstance(manager, mod.SessionLifecycleManager)

        from session_buddy.di.container import depends

        cached = depends.get_sync(mod.SessionLifecycleManager)
        assert cached is manager

    def test_returns_existing_when_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If DI already has one, it's returned as-is."""
        from session_buddy.di.container import depends

        sentinel = mod.SessionLifecycleManager()
        try:
            depends.set(mod.SessionLifecycleManager, sentinel)
            assert mod._get_session_manager() is sentinel  # noqa: SLF001
        finally:
            depends._instances.pop(  # type: ignore[attr-defined]
                "session_buddy.core.session_manager.SessionLifecycleManager",
                None,
            )

    def test_falls_through_when_di_returns_wrong_type(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-SessionLifecycleManager from DI triggers the fallback path."""
        decoy = SimpleNamespace(name="decoy")
        monkeypatch.setattr(mod, "get_sync_typed", lambda *_a, **_kw: decoy)
        manager = mod._get_session_manager()  # noqa: SLF001
        assert isinstance(manager, mod.SessionLifecycleManager)
        assert manager is not decoy


# ---------------------------------------------------------------------------
# _get_session_tracker — DI branches
# ---------------------------------------------------------------------------


class TestGetSessionTracker:
    def test_creates_when_not_registered(
        self, reset_di: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without a registered tracker, build one wired to a fresh manager."""
        from session_buddy.di.container import depends

        monkeypatch.setattr(depends, "get", lambda _key: None)
        manager = mod.SessionLifecycleManager()
        monkeypatch.setattr(mod, "_get_session_manager", lambda: manager)

        tracker = mod._get_session_tracker()  # noqa: SLF001
        assert isinstance(tracker, mod.SessionTracker)
        assert tracker.session_manager is manager

    def test_returns_existing_when_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If DI has a tracker, it's returned as-is."""
        from session_buddy.di.container import depends

        sentinel = SimpleNamespace(name="sentinel-tracker")
        try:
            depends.set(mod.SessionTracker, sentinel)  # type: ignore[arg-type]
            assert mod._get_session_tracker() is sentinel  # noqa: SLF001
        finally:
            depends._instances.pop(  # type: ignore[attr-defined]
                "session_buddy.mcp.session_tracker.SessionTracker",
                None,
            )

    def test_swallows_get_exception(
        self, reset_di: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``depends.get`` raising is swallowed by ``suppress``."""
        from session_buddy.di.container import depends

        def _explode(_key):
            msg = "deliberate boom"
            raise RuntimeError(msg)

        monkeypatch.setattr(depends, "get", _explode)
        manager = mod.SessionLifecycleManager()
        monkeypatch.setattr(mod, "_get_session_manager", lambda: manager)

        tracker = mod._get_session_tracker()  # noqa: SLF001
        assert isinstance(tracker, mod.SessionTracker)
        assert tracker.session_manager is manager