from __future__ import annotations

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


class _FakeResult:
    def __init__(self, payload: dict[str, object]) -> None:
        self.session_id = payload.get("session_id")
        self.status = payload.get("status")
        self._payload = payload

    def model_dump(self) -> dict[str, object]:
        return self._payload


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_BUDDY_SECRET", raising=False)
    try:
        from session_buddy.mcp.auth import _reset_core_config

        _reset_core_config()
    except (ImportError, AttributeError):
        pass


@pytest.mark.asyncio
async def test_register_admin_shell_tracking_tools_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.session import admin_shell_tracking_tools as mod

    async def handle_session_start(event):
        return _FakeResult({"session_id": "sess-123", "status": "tracked"})

    async def handle_session_end(event):
        return _FakeResult({"session_id": event.session_id, "status": "ended"})

    tracker = SimpleNamespace(
        handle_session_start=handle_session_start,
        handle_session_end=handle_session_end,
    )

    monkeypatch.setattr(mod, "_get_session_tracker", lambda: tracker)

    mcp = DummyMCP()
    mod.register_admin_shell_tracking_tools(mcp)

    start_result = await mcp.tools["track_session_start"](
        event_version="1.0",
        event_id="550e8400-e29b-41d4-a716-446655440000",
        event_type="session_start",
        component_name="shell",
        shell_type="zsh",
        timestamp="2026-01-01T00:00:00Z",
        pid=1234,
        user={"username": "u1", "home": "/home/u1"},
        hostname="host-a",
        environment={
            "python_version": "3.13.0",
            "platform": "linux",
            "cwd": "/tmp",
        },
        metadata={"source": "test"},
    )
    end_result = await mcp.tools["track_session_end"](
        session_id="sess-123",
        timestamp="2026-01-01T00:01:00Z",
    )

    assert start_result["session_id"] == "sess-123"
    assert start_result["status"] == "tracked"
    assert end_result["session_id"] == "sess-123"
    assert end_result["status"] == "ended"


@pytest.mark.asyncio
async def test_register_admin_shell_tracking_tools_returns_error_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.tools.session import admin_shell_tracking_tools as mod

    class BrokenTracker:
        async def handle_session_start(self, event):
            raise RuntimeError("boom")

    monkeypatch.setattr(mod, "_get_session_tracker", lambda: BrokenTracker())

    mcp = DummyMCP()
    mod.register_admin_shell_tracking_tools(mcp)

    result = await mcp.tools["track_session_start"](
        event_version="1.0",
        event_id="550e8400-e29b-41d4-a716-446655440001",
        event_type="session_start",
        component_name="shell",
        shell_type="zsh",
        timestamp="2026-01-01T00:00:00Z",
        pid=1234,
        user={"username": "u1", "home": "/home/u1"},
        hostname="host-a",
        environment={
            "python_version": "3.13.0",
            "platform": "linux",
            "cwd": "/tmp",
        },
    )

    assert result["status"] == "error"
    assert "boom" in result["error"]
