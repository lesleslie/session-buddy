"""Unit tests for session_buddy/shell/adapter.py.

Covers:
- SessionBuddyShell initialization (component name, version, banner,
  namespace helpers, session tracker wiring)
- _emit_session_start / _emit_session_end (with stubbed SessionEventEmitter)
- close() lifecycle (calls _emit_session_end then tracker.close)
- All four placeholder helper functions (_list_sessions, _list_active_sessions,
  _show_quality_metrics, _show_insights) print their "not yet implemented"
  banners without raising.
- _get_component_version handles the importlib.metadata.PackageNotFoundError
  gracefully (returns "unknown").
- _get_adapters_info returns an empty list.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.shell import SessionBuddyShell


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def shell(mock_manager: MagicMock) -> SessionBuddyShell:
    return SessionBuddyShell(mock_manager)


# ============================================================================
# Construction & namespace
# ============================================================================


class TestInit:
    def test_session_id_starts_none(self, shell: SessionBuddyShell) -> None:
        assert shell._session_id is None

    def test_session_tracker_uses_session_buddy_component(
        self, shell: SessionBuddyShell
    ) -> None:
        assert shell.session_tracker.component_name == "session-buddy"

    def test_namespace_includes_helper_aliases(
        self, shell: SessionBuddyShell
    ) -> None:
        assert "ps" in shell.namespace
        assert "active" in shell.namespace
        assert "quality" in shell.namespace
        assert "insights" in shell.namespace
        # Class is exposed for direct access in the REPL
        from session_buddy.core.session_manager import SessionLifecycleManager

        assert shell.namespace["SessionLifecycleManager"] is SessionLifecycleManager


# ============================================================================
# Banner + version
# ============================================================================


class TestBanner:
    def test_banner_contains_session_buddy_name(
        self, shell: SessionBuddyShell
    ) -> None:
        banner = shell._get_banner()
        assert "Session-Buddy Admin Shell" in banner
        assert "ps()" in banner
        assert "active()" in banner
        assert "quality()" in banner
        assert "insights(n=10)" in banner


class TestComponentMetadata:
    def test_get_component_name(self, shell: SessionBuddyShell) -> None:
        assert shell._get_component_name() == "session-buddy"

    def test_get_adapters_info_returns_empty_list(
        self, shell: SessionBuddyShell
    ) -> None:
        assert shell._get_adapters_info() == []

    def test_get_component_version_handles_missing_package(
        self, shell: SessionBuddyShell
    ) -> None:
        with patch(
            "importlib.metadata.version",
            side_effect=Exception("not found"),
        ):
            assert shell._get_component_version() == "unknown"

    def test_get_component_version_returns_string_when_present(
        self, shell: SessionBuddyShell
    ) -> None:
        with patch("importlib.metadata.version", return_value="9.9.9"):
            assert shell._get_component_version() == "9.9.9"


# ============================================================================
# Helper placeholders
# ============================================================================


class TestPlaceholderHelpers:
    """The four helpers print a banner; they should not raise."""

    def test_list_sessions_prints_placeholder(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The lambdas in the namespace call asyncio.run(...).
        ps_helper = shell.namespace["ps"]
        ps_helper()
        captured = capsys.readouterr()
        assert "Session listing not yet implemented" in captured.out

    def test_active_prints_placeholder(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell.namespace["active"]()
        captured = capsys.readouterr()
        assert "Active session listing not yet implemented" in captured.out

    def test_quality_prints_placeholder(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell.namespace["quality"]()
        captured = capsys.readouterr()
        assert "Quality metrics not yet implemented" in captured.out

    def test_insights_uses_default_limit(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell.namespace["insights"]()
        captured = capsys.readouterr()
        assert "limit=10" in captured.out
        assert "Insights listing" in captured.out

    def test_insights_uses_custom_limit(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell.namespace["insights"](25)
        captured = capsys.readouterr()
        assert "limit=25" in captured.out


# ============================================================================
# Session start / end
# ============================================================================


class TestEmitSessionStart:
    @pytest.mark.asyncio
    async def test_emits_session_start_with_metadata(
        self, shell: SessionBuddyShell
    ) -> None:
        shell.session_tracker = MagicMock()
        shell.session_tracker.emit_session_start = AsyncMock(return_value="sess-xyz")
        shell.session_tracker.close = AsyncMock()

        await shell._emit_session_start()

        assert shell._session_id == "sess-xyz"
        shell.session_tracker.emit_session_start.assert_awaited_once()
        kwargs = shell.session_tracker.emit_session_start.await_args.kwargs
        assert kwargs["shell_type"] == "SessionBuddyShell"
        assert "version" in kwargs["metadata"]
        assert kwargs["metadata"]["adapters"] == []

    @pytest.mark.asyncio
    async def test_handles_emit_failure_gracefully(
        self, shell: SessionBuddyShell
    ) -> None:
        shell.session_tracker = MagicMock()
        shell.session_tracker.emit_session_start = AsyncMock(
            side_effect=RuntimeError("MCP unreachable")
        )

        # Must not raise even if the underlying emit fails
        await shell._emit_session_start()
        assert shell._session_id is None

    @pytest.mark.asyncio
    async def test_logs_when_tracker_returns_none(
        self, shell: SessionBuddyShell
    ) -> None:
        shell.session_tracker = MagicMock()
        shell.session_tracker.emit_session_start = AsyncMock(return_value=None)

        await shell._emit_session_start()
        assert shell._session_id is None


class TestEmitSessionEnd:
    @pytest.mark.asyncio
    async def test_skips_when_no_session_id(
        self, shell: SessionBuddyShell
    ) -> None:
        shell.session_tracker = MagicMock()
        shell.session_tracker.emit_session_end = AsyncMock()

        await shell._emit_session_end()
        shell.session_tracker.emit_session_end.assert_not_called()

    @pytest.mark.asyncio
    async def test_emits_end_and_clears_session_id(
        self, shell: SessionBuddyShell
    ) -> None:
        shell._session_id = "sess-abc"
        shell.session_tracker = MagicMock()
        shell.session_tracker.emit_session_end = AsyncMock()

        await shell._emit_session_end()

        shell.session_tracker.emit_session_end.assert_awaited_once_with(
            session_id="sess-abc",
            metadata={},
        )
        assert shell._session_id is None

    @pytest.mark.asyncio
    async def test_handles_end_failure_gracefully(
        self, shell: SessionBuddyShell
    ) -> None:
        shell._session_id = "sess-abc"
        shell.session_tracker = MagicMock()
        shell.session_tracker.emit_session_end = AsyncMock(
            side_effect=RuntimeError("boom")
        )

        # Failure must not raise, but session id must still be cleared
        await shell._emit_session_end()
        assert shell._session_id is None


# ============================================================================
# close() lifecycle
# ============================================================================


class TestClose:
    @pytest.mark.asyncio
    async def test_close_emits_end_then_closes_tracker(
        self, shell: SessionBuddyShell
    ) -> None:
        shell._session_id = "sess-1"
        shell.session_tracker = MagicMock()
        shell.session_tracker.emit_session_end = AsyncMock()
        shell.session_tracker.close = AsyncMock()

        await shell.close()

        shell.session_tracker.emit_session_end.assert_awaited_once()
        shell.session_tracker.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_closes_tracker_when_no_active_session(
        self, shell: SessionBuddyShell
    ) -> None:
        # No active session id — _emit_session_end is a no-op
        shell._session_id = None
        shell.session_tracker = MagicMock()
        shell.session_tracker.emit_session_end = AsyncMock()
        shell.session_tracker.close = AsyncMock()

        await shell.close()

        shell.session_tracker.emit_session_end.assert_not_called()
        shell.session_tracker.close.assert_awaited_once()
