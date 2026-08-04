"""Tests for session_buddy.mcp.tools.session.admin_shell_tracking_tools.

Lifts coverage from 62% baseline to >=95% line / >=90% branch on
``session_buddy.mcp.tools.session.admin_shell_tracking_tools`` (60 statements).

Public surface under test:
    - get_logger
    - register_admin_shell_tracking_tools (defines track_session_start,
      track_session_end as inner coroutine tools)

Internal helpers exercised for coverage:
    - _get_session_manager
    - _get_session_tracker
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


class DummyMCP:
    """Minimal stand-in for a FastMCP server — captures registered tools."""

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
    """Ensure SESSION_BUDDY_SECRET is unset so ``require_auth`` is a no-op."""
    monkeypatch.delenv("SESSION_BUDDY_SECRET", raising=False)
    try:
        from session_buddy.mcp.auth import _reset_core_config

        _reset_core_config()
    except (ImportError, AttributeError):
        pass


@pytest.fixture
def reset_di() -> None:
    """Clear DI state for SessionLifecycleManager / SessionTracker between tests."""
    from session_buddy.di.container import depends

    # Remove any cached SessionLifecycleManager / SessionTracker from prior tests
    for key in (
        "session_buddy.core.session_manager.SessionLifecycleManager",
        "session_buddy.mcp.session_tracker.SessionTracker",
    ):
        depends._instances.pop(key, None)  # type: ignore[attr-defined]


@pytest.fixture
def clear_di_managers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``get_sync_typed`` to raise and ``depends.get`` to return None.

    Without this, autouse fixtures or other tests may call ``di.configure()``
    which registers a real ``SessionLifecycleManager`` in the container; that
    makes the ``isinstance`` branch in ``_get_session_manager`` fire before
    the fallback at lines 88-90 can run.
    """
    import session_buddy.mcp.tools.session.admin_shell_tracking_tools as mod_local

    monkeypatch.setattr(
        mod_local,
        "get_sync_typed",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            KeyError("Service not registered: SessionLifecycleManager")
        ),
    )


# ---------------------------------------------------------------------------
# Public-function smoke tests
# ---------------------------------------------------------------------------


def test_get_logger_returns_logger_instance() -> None:
    """``get_logger`` returns a stdlib Logger for the module."""
    logger = get_logger()
    assert isinstance(logger, logging.Logger)
    assert logger.name == mod.__name__


def test_get_logger_repeated_calls_return_same_logger() -> None:
    """``get_logger`` is idempotent — stdlib caches by name."""
    first = get_logger()
    second = get_logger()
    assert first is second


def test_module_imports_register_admin_shell_tracking_tools() -> None:
    """Public export surface includes the registration entry-point."""
    assert callable(register_admin_shell_tracking_tools)


# ---------------------------------------------------------------------------
# register_admin_shell_tracking_tools — registration smoke + happy paths
# ---------------------------------------------------------------------------


def test_register_registers_both_track_tools() -> None:
    """Registering attaches both ``track_session_start`` and ``track_session_end``."""
    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    assert "track_session_start" in mcp.tools
    assert "track_session_end" in mcp.tools


def test_register_attaches_async_coroutine_tools() -> None:
    """Registered tools are coroutine functions so FastMCP can await them."""
    import inspect

    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    assert inspect.iscoroutinefunction(mcp.tools["track_session_start"])
    assert inspect.iscoroutinefunction(mcp.tools["track_session_end"])


@pytest.mark.asyncio
async def test_track_session_start_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """track_session_start returns the SessionStartResult dict on success."""
    tracker = SimpleNamespace(
        handle_session_start=AsyncMock(
            return_value=_FakeResult(
                {"session_id": "sess-123", "status": "tracked"}
            ),
        ),
    )
    monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    result = await mcp.tools["track_session_start"](**_start_kwargs())

    assert result == {"session_id": "sess-123", "status": "tracked"}
    tracker.handle_session_start.assert_awaited_once()


@pytest.mark.asyncio
async def test_track_session_start_uses_default_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``metadata`` is omitted, the tool substitutes an empty dict."""
    captured: dict[str, object] = {}

    async def handle_session_start(event):
        captured["metadata"] = event.metadata
        return _FakeResult({"session_id": "sess-1", "status": "tracked"})

    tracker = SimpleNamespace(handle_session_start=handle_session_start)
    monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    kwargs = _start_kwargs()
    kwargs.pop("metadata")
    result = await mcp.tools["track_session_start"](**kwargs)

    assert result["status"] == "tracked"
    assert captured["metadata"] == {}


@pytest.mark.asyncio
async def test_track_session_start_returns_error_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the tracker raises, the tool returns a structured error result."""
    tracker = SimpleNamespace(
        handle_session_start=AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    result = await mcp.tools["track_session_start"](**_start_kwargs())

    assert result["status"] == "error"
    assert result["session_id"] is None
    assert "boom" in result["error"]


@pytest.mark.asyncio
async def test_track_session_start_error_when_event_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid event payload triggers the catch-all error path with no tracker call."""

    async def _raise(event):  # pragma: no cover  # reason: negative-control helper — tracker must not be reached when event validation fails
        msg = "tracker should not be called when validation fails"
        raise AssertionError(msg)

    tracker = SimpleNamespace(handle_session_start=_raise)
    monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    bad_kwargs = _start_kwargs()
    # event_type must equal "session_start" for SessionStartEvent
    bad_kwargs["event_type"] = "not_session_start"

    result = await mcp.tools["track_session_start"](**bad_kwargs)

    assert result["status"] == "error"
    assert result["session_id"] is None
    assert result["error"]


@pytest.mark.asyncio
async def test_track_session_end_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """track_session_end returns the SessionEndResult dict on success."""
    tracker = SimpleNamespace(
        handle_session_end=AsyncMock(
            return_value=_FakeResult(
                {"session_id": "sess-xyz", "status": "ended"},
            ),
        ),
    )
    monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    result = await mcp.tools["track_session_end"](
        session_id="sess-xyz",
        timestamp="2026-01-01T00:01:00Z",
    )

    assert result == {"session_id": "sess-xyz", "status": "ended"}
    tracker.handle_session_end.assert_awaited_once()


@pytest.mark.asyncio
async def test_track_session_end_uses_default_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``metadata`` is omitted from track_session_end, defaults to {}."""
    captured: dict[str, object] = {}

    async def handle_session_end(event):
        captured["metadata"] = event.metadata
        return _FakeResult({"session_id": event.session_id, "status": "ended"})

    tracker = SimpleNamespace(handle_session_end=handle_session_end)
    monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    result = await mcp.tools["track_session_end"](
        session_id="sess-1",
        timestamp="2026-01-01T00:00:00Z",
    )

    assert result["status"] == "ended"
    assert captured["metadata"] == {}


@pytest.mark.asyncio
async def test_track_session_end_returns_error_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the tracker raises, track_session_end returns a structured error."""
    tracker = SimpleNamespace(
        handle_session_end=AsyncMock(side_effect=ValueError("kaboom")),
    )
    monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    result = await mcp.tools["track_session_end"](
        session_id="sess-fail",
        timestamp="2026-01-01T00:02:00Z",
    )

    assert result["status"] == "error"
    assert result["session_id"] == "sess-fail"
    assert "kaboom" in result["error"]


@pytest.mark.asyncio
async def test_track_session_end_error_when_event_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid event payload triggers the catch-all error path."""

    async def _raise(event):  # pragma: no cover  # reason: negative-control helper — tracker must not be reached when event validation fails
        msg = "tracker should not be called when validation fails"
        raise AssertionError(msg)

    tracker = SimpleNamespace(handle_session_end=_raise)
    monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

    mcp = DummyMCP()
    register_admin_shell_tracking_tools(mcp)
    bad_kwargs = {
        "session_id": "sess-x",
        "timestamp": "not-a-timestamp",
    }

    result = await mcp.tools["track_session_end"](**bad_kwargs)

    assert result["status"] == "error"
    assert result["session_id"] == "sess-x"
    assert result["error"]


# ---------------------------------------------------------------------------
# _get_session_manager — DI fallback path (lines 83-90)
# ---------------------------------------------------------------------------


def test_get_session_manager_creates_when_not_registered(
    reset_di: None, clear_di_managers: None
) -> None:
    """Without a registered SessionLifecycleManager, a fresh one is built.

    Forces ``get_sync_typed`` to raise so the ``suppress(...)`` block in
    ``_get_session_manager`` falls through to the fallback at lines 88-90
    (create + register + return).
    """
    manager = mod._get_session_manager()  # noqa: SLF001
    assert isinstance(manager, mod.SessionLifecycleManager)

    # After the fallback path runs, the new instance is registered in DI.
    from session_buddy.di.container import depends

    cached = depends.get_sync(mod.SessionLifecycleManager)
    assert cached is manager


def test_get_session_manager_returns_existing_when_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a SessionLifecycleManager is already in DI, it is returned as-is."""
    from session_buddy.di.container import depends

    sentinel = mod.SessionLifecycleManager()
    try:
        depends.set(mod.SessionLifecycleManager, sentinel)
        manager = mod._get_session_manager()  # noqa: SLF001
        assert manager is sentinel
    finally:
        # Clean up so we don't leak the sentinel into other tests
        depends._instances.pop(  # type: ignore[attr-defined]
            "session_buddy.core.session_manager.SessionLifecycleManager",
            None,
        )


def test_get_session_manager_falls_through_when_get_returns_wrong_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If DI returns a non-SessionLifecycleManager, the fallback path runs.

    Exercises branch ``85->88``: the ``isinstance`` check fails, so we drop
    out of the ``suppress`` block and build a fresh manager.
    """
    sentinel = SimpleNamespace(name="not-a-real-manager")

    # Force ``get_sync_typed`` to return an object that is NOT a
    # SessionLifecycleManager; the isinstance check at line 85 fails, so the
    # function falls through to the fallback at lines 88-90.
    monkeypatch.setattr(
        mod,
        "get_sync_typed",
        lambda *_a, **_kw: sentinel,
    )

    manager = mod._get_session_manager()  # noqa: SLF001
    assert isinstance(manager, mod.SessionLifecycleManager)
    assert manager is not sentinel


# ---------------------------------------------------------------------------
# _get_session_tracker — DI fallback path (lines 107-119)
# ---------------------------------------------------------------------------


def test_get_session_tracker_creates_when_not_registered(
    reset_di: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a registered SessionTracker, a fresh one is built with a logger."""
    from session_buddy.di.container import depends

    # Make depends.get(...) return None (no instance in the container).
    monkeypatch.setattr(depends, "get", lambda _key: None)

    # Provide a real SessionLifecycleManager so SessionTracker(...) succeeds.
    manager = mod.SessionLifecycleManager()
    monkeypatch.setattr(
        mod,
        "_get_session_manager",
        lambda: manager,
    )

    tracker = mod._get_session_tracker()  # noqa: SLF001
    assert isinstance(tracker, mod.SessionTracker)
    assert tracker.session_manager is manager
    assert tracker.logger is not None


def test_get_session_tracker_returns_existing_when_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a SessionTracker is already in DI, it is returned as-is."""
    from session_buddy.di.container import depends

    sentinel = SimpleNamespace(name="sentinel-tracker")
    try:
        depends.set(mod.SessionTracker, sentinel)  # type: ignore[arg-type]
        tracker = mod._get_session_tracker()  # noqa: SLF001
        assert tracker is sentinel
    finally:
        depends._instances.pop(  # type: ignore[attr-defined]
            "session_buddy.mcp.session_tracker.SessionTracker",
            None,
        )


def test_get_session_tracker_swallows_get_exception(
    reset_di: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception raised by ``depends.get`` is swallowed by ``suppress``."""

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
