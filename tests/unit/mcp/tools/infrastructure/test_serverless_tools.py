"""Tests for ``session_buddy.mcp.tools.infrastructure.serverless_tools``.

Covers every private operation wrapper, the public *_impl helpers,
the ``_execute_serverless_operation`` envelope (RuntimeError vs
Exception), and the eight ``register_serverless_tools`` MCP tools.

Pattern: monkeypatch the ``resolve_serverless_manager`` symbol that
``_require_serverless_manager`` calls (closure-over-import pattern),
plus a fake ``ToolMessages.operation_failed`` that returns a known
string to assert the catch-all branch.

Coverage target: 85-100% of source lines in serverless_tools.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.infrastructure import serverless_tools as sl_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Capture tool-registration calls."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *, name=None, description=None):
        def decorator(fn):
            self.tools[name or fn.__name__] = fn
            return fn

        return decorator


def _make_manager(**overrides) -> MagicMock:
    """Build a fake serverless manager with configurable methods."""
    manager = MagicMock()
    manager.create_session = AsyncMock(return_value="sess-abc")
    manager.get_session = AsyncMock(return_value=None)
    manager.update_session = AsyncMock(return_value=True)
    manager.delete_session = AsyncMock(return_value=True)
    manager.list_sessions = AsyncMock(return_value=[])
    manager.cleanup_expired_sessions = AsyncMock(return_value=3)
    manager.test_storage_backends = AsyncMock(
        return_value={
            "redis": {"available": True, "latency_ms": 5.0, "status": "OK"},
            "s3": {"available": False, "error": "no creds"},
        }
    )
    manager.configure_storage = AsyncMock(return_value=True)
    for k, v in overrides.items():
        setattr(manager, k, v)
    return manager


@pytest.fixture
def fake_manager(monkeypatch: pytest.MonkeyPatch):
    """Provide a fake manager and patch the resolver to return it."""
    manager = _make_manager()
    resolver = AsyncMock(return_value=manager)
    monkeypatch.setattr(sl_mod, "resolve_serverless_manager", resolver)
    return manager


@pytest.fixture
def no_manager(monkeypatch: pytest.MonkeyPatch):
    """Make the resolver return None so _require raises."""
    monkeypatch.setattr(
        sl_mod, "resolve_serverless_manager", AsyncMock(return_value=None)
    )
    return None


# ---------------------------------------------------------------------------
# _require_serverless_manager
# ---------------------------------------------------------------------------


async def test_require_serverless_manager_returns_manager(fake_manager) -> None:
    """When the resolver yields a manager, _require returns it."""
    m = await sl_mod._require_serverless_manager()
    assert m is fake_manager


async def test_require_serverless_manager_raises_when_none(no_manager) -> None:
    """When the resolver returns None, _require raises RuntimeError."""
    with pytest.raises(RuntimeError, match="Serverless mode not available"):
        await sl_mod._require_serverless_manager()


# ---------------------------------------------------------------------------
# _execute_serverless_operation envelope
# ---------------------------------------------------------------------------


async def test_execute_serverless_operation_runtime_error_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RuntimeError surfaces as '❌ {e}'."""
    monkeypatch.setattr(
        sl_mod, "_require_serverless_manager", AsyncMock(side_effect=RuntimeError("bad"))
    )

    async def op(_manager):
        return "unreachable"

    out = await sl_mod._execute_serverless_operation("X", op)
    assert out == "❌ bad"


async def test_execute_serverless_operation_other_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generic Exception path uses ToolMessages.operation_failed."""
    monkeypatch.setattr(
        sl_mod, "_require_serverless_manager", AsyncMock(side_effect=ValueError("oops"))
    )

    async def op(_manager):
        return "unreachable"

    out = await sl_mod._execute_serverless_operation("MyOp", op)
    assert "MyOp" in out
    assert "oops" in out


async def test_execute_serverless_operation_returns_operation_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path returns the operation's return value verbatim."""
    captured: dict[str, object] = {}
    fake_mgr = object()

    async def fake_require():
        captured["called"] = True
        return fake_mgr

    monkeypatch.setattr(sl_mod, "_require_serverless_manager", fake_require)

    async def op(manager):
        assert manager is fake_mgr
        return "op-ok"

    out = await sl_mod._execute_serverless_operation("Op", op)
    assert out == "op-ok"
    assert captured["called"] is True


# ---------------------------------------------------------------------------
# create_serverless_session
# ---------------------------------------------------------------------------


async def test_create_session_success(fake_manager) -> None:
    """Successful creation returns session id and TTL message."""
    fake_manager.create_session.return_value = "sess-xyz"
    out = await sl_mod._create_serverless_session_impl(
        "u1", "p1", {"k": "v"}, ttl_hours=12
    )
    assert "✅ Created serverless session: sess-xyz" in out
    assert "🕐 TTL: 12 hours" in out
    fake_manager.create_session.assert_awaited_once_with(
        user_id="u1",
        project_id="p1",
        session_data={"k": "v"},
        ttl_hours=12,
    )


async def test_create_session_default_ttl(fake_manager) -> None:
    """ttl_hours defaults to 24."""
    await sl_mod._create_serverless_session_impl("u1", "p1")
    fake_manager.create_session.assert_awaited_once_with(
        user_id="u1", project_id="p1", session_data=None, ttl_hours=24
    )


async def test_create_session_no_manager_raises(no_manager) -> None:
    """Without a manager the impl returns '❌' message."""
    out = await sl_mod._create_serverless_session_impl("u1", "p1")
    assert out.startswith("❌ Serverless mode not available")


# ---------------------------------------------------------------------------
# get_serverless_session
# ---------------------------------------------------------------------------


async def test_get_session_not_found(fake_manager) -> None:
    """Manager.get_session returns None → '❌ Session not found'."""
    out = await sl_mod._get_serverless_session_impl("missing-id")
    assert out == "❌ Session not found: missing-id"


async def test_get_session_success(fake_manager) -> None:
    """Existing session renders all keys and data lines."""
    fake_manager.get_session.return_value = {
        "user_id": "alice",
        "project_id": "proj-x",
        "created_at": "2026-01-01T00:00:00",
        "expires_at": "2026-01-02T00:00:00",
        "session_data": {"topic": "auth", "score": 7},
    }
    out = await sl_mod._get_serverless_session_impl("sess-1")
    assert "📦 Serverless Session: sess-1" in out
    assert "👤 User ID: alice" in out
    assert "📁 Project ID: proj-x" in out
    assert "📅 Created: 2026-01-01T00:00:00" in out
    assert "⏱️ Expires: 2026-01-02T00:00:00" in out
    assert "📊 Session Data:" in out
    assert "   • topic: auth" in out
    assert "   • score: 7" in out


async def test_get_session_empty_session_data(fake_manager) -> None:
    """Session with no session_data renders no data lines."""
    fake_manager.get_session.return_value = {
        "user_id": "alice",
        "project_id": "proj-x",
        "created_at": "2026-01-01T00:00:00",
        "expires_at": "2026-01-02T00:00:00",
        "session_data": {},
    }
    out = await sl_mod._get_serverless_session_impl("sess-1")
    assert "📊 Session Data:" in out
    # Only the section header is present; no "•" bullet lines
    assert "   •" not in out


# ---------------------------------------------------------------------------
# update_serverless_session
# ---------------------------------------------------------------------------


async def test_update_session_success(fake_manager) -> None:
    """Successful update returns ✅ without TTL line."""
    out = await sl_mod._update_serverless_session_impl(
        "sess-1", {"k": "v"}, extend_ttl_hours=None
    )
    assert out == "✅ Updated session: sess-1"
    fake_manager.update_session.assert_awaited_once_with(
        session_id="sess-1",
        session_data={"k": "v"},
        extend_ttl_hours=None,
    )


async def test_update_session_with_extend_ttl(fake_manager) -> None:
    """Non-None extend_ttl_hours adds a TTL line."""
    out = await sl_mod._update_serverless_session_impl(
        "sess-1", {"k": "v"}, extend_ttl_hours=8
    )
    assert "✅ Updated session: sess-1" in out
    assert "⏱️ Extended TTL by 8 hours" in out


async def test_update_session_not_found(fake_manager) -> None:
    """update_session returns False → '❌ Session not found'."""
    fake_manager.update_session.return_value = False
    out = await sl_mod._update_serverless_session_impl("missing", {"k": "v"})
    assert out == "❌ Session not found: missing"


# ---------------------------------------------------------------------------
# delete_serverless_session
# ---------------------------------------------------------------------------


async def test_delete_session_success(fake_manager) -> None:
    """delete_session returns True → ✅ message."""
    out = await sl_mod._delete_serverless_session_impl("sess-1")
    assert out == "✅ Deleted session: sess-1"
    fake_manager.delete_session.assert_awaited_once_with("sess-1")


async def test_delete_session_not_found(fake_manager) -> None:
    """delete_session returns False → '❌ Session not found'."""
    fake_manager.delete_session.return_value = False
    out = await sl_mod._delete_serverless_session_impl("missing")
    assert out == "❌ Session not found: missing"


# ---------------------------------------------------------------------------
# list_serverless_sessions
# ---------------------------------------------------------------------------


async def test_list_sessions_empty_no_filter(fake_manager) -> None:
    """Empty list with no filters → '🔍 No sessions found'."""
    out = await sl_mod._list_serverless_sessions_impl()
    assert out == "🔍 No sessions found"


async def test_list_sessions_empty_with_user_filter(fake_manager) -> None:
    """Empty list with user_id filter includes the filter in the message."""
    out = await sl_mod._list_serverless_sessions_impl(user_id="alice")
    assert "user_id=alice" in out
    assert "🔍 No sessions found" in out


async def test_list_sessions_empty_with_project_filter(fake_manager) -> None:
    """Empty list with project_id filter includes the filter in the message."""
    out = await sl_mod._list_serverless_sessions_impl(project_id="proj")
    assert "project_id=proj" in out


async def test_list_sessions_empty_with_both_filters(fake_manager) -> None:
    """Both filters joined by comma in the message."""
    out = await sl_mod._list_serverless_sessions_impl(user_id="a", project_id="b")
    assert "user_id=a, project_id=b" in out


async def test_list_sessions_with_results(fake_manager) -> None:
    """Non-empty session list renders each session's metadata."""
    fake_manager.list_sessions.return_value = [
        {
            "session_id": "s1",
            "user_id": "alice",
            "project_id": "proj-x",
            "expires_at": "2026-01-02T00:00:00",
        },
        {
            "session_id": "s2",
            "user_id": "bob",
            "project_id": "proj-y",
            "expires_at": "2026-01-03T00:00:00",
        },
    ]
    out = await sl_mod._list_serverless_sessions_impl(include_expired=True)
    assert "📦 Found 2 serverless session(s):" in out
    assert "• Session ID: s1" in out
    assert "  User: alice" in out
    assert "  Project: proj-x" in out
    fake_manager.list_sessions.assert_awaited_once_with(
        user_id=None, project_id=None, include_expired=True
    )


# ---------------------------------------------------------------------------
# cleanup_serverless_sessions
# ---------------------------------------------------------------------------


async def test_cleanup_sessions_success(fake_manager) -> None:
    """cleanup returns the deleted count formatted as ✅."""
    fake_manager.cleanup_expired_sessions.return_value = 7
    out = await sl_mod._cleanup_serverless_sessions_impl()
    assert out == "✅ Cleaned up 7 expired session(s)"


# ---------------------------------------------------------------------------
# test_serverless_storage
# ---------------------------------------------------------------------------


async def test_test_storage_with_recommendation(fake_manager) -> None:
    """At least one backend available → 'Recommended' line."""
    out = await sl_mod._test_serverless_storage_impl()
    assert "🧪 Storage Backend Test Results:" in out
    assert "✅ REDIS:" in out
    assert "   Latency: 5.0 ms" in out
    assert "❌ S3:" in out
    assert "   Error: no creds" in out
    assert "💡 Recommended: REDIS (lowest latency)" in out


async def test_test_storage_no_backends(fake_manager) -> None:
    """When no backend is available → '⚠️ No storage backends available'."""
    fake_manager.test_storage_backends.return_value = {
        "redis": {"available": False, "error": "down"},
        "s3": {"available": False, "error": "no creds"},
    }
    out = await sl_mod._test_serverless_storage_impl()
    assert "⚠️ No storage backends available" in out


# ---------------------------------------------------------------------------
# configure_serverless_storage
# ---------------------------------------------------------------------------


async def test_configure_storage_success(fake_manager) -> None:
    """configure_storage success → ✅ header + key/value config lines."""
    out = await sl_mod._configure_serverless_storage_impl(
        "redis", {"host": "localhost", "port": 6379}
    )
    assert "✅ Configured REDIS storage backend" in out
    assert "⚙️ Configuration:" in out
    assert "   • host: localhost" in out
    assert "   • port: 6379" in out
    fake_manager.configure_storage.assert_awaited_once_with(
        backend="redis", config={"host": "localhost", "port": 6379}
    )


async def test_configure_storage_failure(fake_manager) -> None:
    """configure_storage returns False → '❌ Failed to configure'."""
    fake_manager.configure_storage.return_value = False
    out = await sl_mod._configure_serverless_storage_impl("redis", {})
    assert out == "❌ Failed to configure redis storage"


# ---------------------------------------------------------------------------
# register_serverless_tools
# ---------------------------------------------------------------------------


def test_register_serverless_tools_registers_all_eight() -> None:
    """register_serverless_tools registers the eight expected tools."""
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    assert set(mcp.tools) == {
        "create_serverless_session",
        "get_serverless_session",
        "update_serverless_session",
        "delete_serverless_session",
        "list_serverless_sessions",
        "cleanup_serverless_sessions",
        "test_serverless_storage",
        "configure_serverless_storage",
    }


# ---------------------------------------------------------------------------
# MCP wrapper tools — round-trip integration
# ---------------------------------------------------------------------------


async def test_create_session_mcp_wrapper(fake_manager) -> None:
    """The registered create_serverless_session tool delegates to impl."""
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    fake_manager.create_session.return_value = "sess-z"
    result = await mcp.tools["create_serverless_session"](
        user_id="u1", project_id="p1", session_data={"a": 1}, ttl_hours=4
    )
    assert "✅ Created serverless session: sess-z" in result
    assert "TTL: 4 hours" in result


async def test_get_session_mcp_wrapper(fake_manager) -> None:
    """get_serverless_session renders the session metadata."""
    fake_manager.get_session.return_value = {
        "user_id": "u1",
        "project_id": "p1",
        "created_at": "c",
        "expires_at": "e",
        "session_data": {"x": 1},
    }
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    out = await mcp.tools["get_serverless_session"](session_id="sess-1")
    assert "📦 Serverless Session: sess-1" in out


async def test_update_session_mcp_wrapper(fake_manager) -> None:
    """update_serverless_session forwards through to manager.update_session."""
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    out = await mcp.tools["update_serverless_session"](
        session_id="sess-1", session_data={"x": 2}, extend_ttl_hours=6
    )
    assert "✅ Updated session: sess-1" in out
    assert "Extended TTL by 6 hours" in out


async def test_delete_session_mcp_wrapper(fake_manager) -> None:
    """delete_serverless_session deletes."""
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    out = await mcp.tools["delete_serverless_session"](session_id="sess-1")
    assert out == "✅ Deleted session: sess-1"


async def test_list_sessions_mcp_wrapper(fake_manager) -> None:
    """list_serverless_sessions with default filters."""
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    out = await mcp.tools["list_serverless_sessions"]()
    assert out == "🔍 No sessions found"


async def test_cleanup_sessions_mcp_wrapper(fake_manager) -> None:
    """cleanup_serverless_sessions returns the count."""
    fake_manager.cleanup_expired_sessions.return_value = 0
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    out = await mcp.tools["cleanup_serverless_sessions"]()
    assert "✅ Cleaned up 0 expired session(s)" in out


async def test_test_storage_mcp_wrapper(fake_manager) -> None:
    """test_serverless_storage renders backends."""
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    out = await mcp.tools["test_serverless_storage"]()
    assert "🧪 Storage Backend Test Results:" in out


async def test_configure_storage_mcp_wrapper(fake_manager) -> None:
    """configure_serverless_storage renders the config."""
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    out = await mcp.tools["configure_serverless_storage"](
        backend="s3", config={"region": "us-east-1"}
    )
    assert "✅ Configured S3 storage backend" in out
    assert "region: us-east-1" in out


# ---------------------------------------------------------------------------
# No-manager error path through MCP wrappers
# ---------------------------------------------------------------------------


async def test_all_mcp_wrappers_when_no_manager(no_manager) -> None:
    """All wrappers gracefully return ❌ when the resolver yields None."""
    mcp = _FakeMCP()
    sl_mod.register_serverless_tools(mcp)
    assert (
        await mcp.tools["create_serverless_session"](user_id="u", project_id="p")
    ).startswith("❌")
    assert (
        await mcp.tools["get_serverless_session"](session_id="x")
    ).startswith("❌")
    assert (
        await mcp.tools["update_serverless_session"](session_id="x", session_data={})
    ).startswith("❌")
    assert (
        await mcp.tools["delete_serverless_session"](session_id="x")
    ).startswith("❌")
    assert (
        await mcp.tools["list_serverless_sessions"]()
    ).startswith("❌")
    assert (
        await mcp.tools["cleanup_serverless_sessions"]()
    ).startswith("❌")
    assert (
        await mcp.tools["test_serverless_storage"]()
    ).startswith("❌")
    assert (
        await mcp.tools["configure_serverless_storage"](backend="x", config={})
    ).startswith("❌")