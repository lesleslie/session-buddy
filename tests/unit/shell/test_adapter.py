"""Unit tests for ``session_buddy.shell.adapter``.

Covers ``SessionBuddyShell`` — the Session-Buddy-specific ``AdminShell``
subclass. The oneiric ``SessionEventEmitter`` is stubbed with
``AsyncMock`` so no Session-Buddy MCP round-trips occur.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from oneiric.shell import ShellConfig

from session_buddy.core.session_manager import SessionLifecycleManager
from session_buddy.shell.adapter import SessionBuddyShell

pytestmark = pytest.mark.unit


@pytest.fixture
def shell() -> SessionBuddyShell:
    """A ``SessionBuddyShell`` with a mocked app and stubbed session tracker."""
    instance = SessionBuddyShell(MagicMock())
    tracker = MagicMock()
    tracker.emit_session_start = AsyncMock(return_value="sess-123")
    tracker.emit_session_end = AsyncMock(return_value=None)
    tracker.close = AsyncMock(return_value=None)
    instance.session_tracker = tracker
    return instance


class TestInit:
    """Constructor behavior."""

    def test_default_config_is_created(self) -> None:
        instance = SessionBuddyShell(MagicMock())

        assert isinstance(instance.config, ShellConfig)

    def test_explicit_config_is_used(self) -> None:
        config = ShellConfig(banner="custom", table_max_width=80)

        instance = SessionBuddyShell(MagicMock(), config)

        assert instance.config is config
        assert instance.config.table_max_width == 80

    def test_app_is_stored(self) -> None:
        app = MagicMock()

        instance = SessionBuddyShell(app)

        assert instance.app is app

    def test_session_id_starts_none(self) -> None:
        instance = SessionBuddyShell(MagicMock())

        assert instance._session_id is None

    def test_session_tracker_uses_session_buddy_component_name(self) -> None:
        with patch("session_buddy.shell.adapter.SessionEventEmitter") as emitter_cls:
            instance = SessionBuddyShell(MagicMock())

        emitter_cls.assert_called_once_with(component_name="session-buddy")
        assert instance.session_tracker is emitter_cls.return_value


class TestNamespace:
    """``_add_session_buddy_namespace`` wiring."""

    @pytest.mark.parametrize(
        "key", ["SessionLifecycleManager", "ps", "active", "quality", "insights"]
    )
    def test_namespace_contains_key(self, shell: SessionBuddyShell, key: str) -> None:
        assert key in shell.namespace

    def test_session_lifecycle_manager_is_the_real_class(
        self, shell: SessionBuddyShell
    ) -> None:
        assert shell.namespace["SessionLifecycleManager"] is SessionLifecycleManager

    @pytest.mark.parametrize("key", ["ps", "active", "quality", "insights"])
    def test_helper_is_callable(self, shell: SessionBuddyShell, key: str) -> None:
        assert callable(shell.namespace[key])

    def test_base_namespace_entries_are_preserved(
        self, shell: SessionBuddyShell
    ) -> None:
        # ``update()`` must not clobber the base ``AdminShell`` namespace.
        assert "app" in shell.namespace

    def test_ps_helper_runs_the_coroutine(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell.namespace["ps"]()

        assert "Session listing not yet implemented" in capsys.readouterr().out

    def test_active_helper_runs_the_coroutine(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell.namespace["active"]()

        assert "Active session listing not yet implemented" in capsys.readouterr().out

    def test_quality_helper_runs_the_coroutine(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell.namespace["quality"]()

        assert "Quality metrics not yet implemented" in capsys.readouterr().out

    def test_insights_helper_uses_default_limit(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell.namespace["insights"]()

        assert "limit=10" in capsys.readouterr().out

    def test_insights_helper_forwards_explicit_limit(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell.namespace["insights"](5)

        assert "limit=5" in capsys.readouterr().out


class TestPlaceholderCoroutines:
    """The four async placeholder helpers."""

    async def test_list_sessions(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert await shell._list_sessions() is None
        assert "Session listing not yet implemented" in capsys.readouterr().out

    async def test_list_active_sessions(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert await shell._list_active_sessions() is None
        assert "Active session listing not yet implemented" in capsys.readouterr().out

    async def test_show_quality_metrics(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert await shell._show_quality_metrics() is None
        assert "Quality metrics not yet implemented" in capsys.readouterr().out

    async def test_show_insights_default_limit(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        await shell._show_insights()

        assert "Insights listing (limit=10)" in capsys.readouterr().out

    async def test_show_insights_custom_limit(
        self, shell: SessionBuddyShell, capsys: pytest.CaptureFixture[str]
    ) -> None:
        await shell._show_insights(limit=42)

        assert "Insights listing (limit=42)" in capsys.readouterr().out


class TestComponentMetadata:
    """``_get_component_name`` / ``_get_component_version`` / ``_get_adapters_info``."""

    def test_component_name(self, shell: SessionBuddyShell) -> None:
        assert shell._get_component_name() == "session-buddy"

    def test_component_version_from_metadata(self, shell: SessionBuddyShell) -> None:
        with patch("importlib.metadata.version", return_value="1.2.3"):
            assert shell._get_component_version() == "1.2.3"

    def test_component_version_falls_back_on_package_not_found(
        self, shell: SessionBuddyShell
    ) -> None:
        import importlib.metadata as importlib_metadata

        with patch(
            "importlib.metadata.version",
            side_effect=importlib_metadata.PackageNotFoundError("session-buddy"),
        ):
            assert shell._get_component_version() == "unknown"

    def test_component_version_falls_back_on_arbitrary_error(
        self, shell: SessionBuddyShell
    ) -> None:
        with patch("importlib.metadata.version", side_effect=RuntimeError("boom")):
            assert shell._get_component_version() == "unknown"

    def test_adapters_info_is_empty(self, shell: SessionBuddyShell) -> None:
        assert shell._get_adapters_info() == []


class TestBanner:
    """``_get_banner`` rendering."""

    def test_banner_includes_version(self, shell: SessionBuddyShell) -> None:
        with patch.object(shell, "_get_component_version", return_value="9.9.9"):
            banner = shell._get_banner()

        assert "Session-Buddy Admin Shell v9.9.9" in banner

    def test_banner_reports_cli_enabled(self, shell: SessionBuddyShell) -> None:
        # ``ShellConfig`` is a strict pydantic model, so swap in a stand-in
        # config object that carries the optional preprocessing flag.
        with patch.object(
            shell, "config", SimpleNamespace(cli_preprocessing_enabled=True)
        ):
            assert "CLI Commands: Enabled" in shell._get_banner()

    def test_banner_reports_cli_disabled_when_attribute_missing(
        self, shell: SessionBuddyShell
    ) -> None:
        # ``getattr(..., False)`` default path — attribute is absent by default.
        assert not hasattr(shell.config, "cli_preprocessing_enabled")
        assert "CLI Commands: Disabled" in shell._get_banner()

    def test_banner_reports_cli_disabled_when_attribute_false(
        self, shell: SessionBuddyShell
    ) -> None:
        with patch.object(
            shell, "config", SimpleNamespace(cli_preprocessing_enabled=False)
        ):
            assert "CLI Commands: Disabled" in shell._get_banner()

    def test_banner_reports_self_monitoring(self, shell: SessionBuddyShell) -> None:
        assert "Session Tracking: Enabled (self-monitoring)" in shell._get_banner()

    @pytest.mark.parametrize(
        "fragment", ["ps()", "active()", "quality()", "insights(n=10)", "%help_shell"]
    )
    def test_banner_documents_helper(
        self, shell: SessionBuddyShell, fragment: str
    ) -> None:
        assert fragment in shell._get_banner()


class TestEmitSessionStart:
    """``_emit_session_start`` behavior."""

    async def test_stores_returned_session_id(self, shell: SessionBuddyShell) -> None:
        await shell._emit_session_start()

        assert shell._session_id == "sess-123"

    async def test_passes_shell_type_and_metadata(
        self, shell: SessionBuddyShell
    ) -> None:
        with patch.object(shell, "_get_component_version", return_value="0.1.0"):
            await shell._emit_session_start()

        shell.session_tracker.emit_session_start.assert_awaited_once_with(
            shell_type="SessionBuddyShell",
            metadata={"version": "0.1.0", "adapters": []},
        )

    async def test_logs_info_when_tracking_succeeds(
        self, shell: SessionBuddyShell, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="session_buddy.shell.adapter"):
            await shell._emit_session_start()

        assert "sess-123" in caplog.text

    async def test_none_session_id_logs_debug_and_stays_none(
        self, shell: SessionBuddyShell, caplog: pytest.LogCaptureFixture
    ) -> None:
        shell.session_tracker.emit_session_start = AsyncMock(return_value=None)

        with caplog.at_level(logging.DEBUG, logger="session_buddy.shell.adapter"):
            await shell._emit_session_start()

        assert shell._session_id is None
        assert "Session tracking unavailable" in caplog.text

    async def test_emitter_exception_is_swallowed_and_logged(
        self, shell: SessionBuddyShell, caplog: pytest.LogCaptureFixture
    ) -> None:
        shell.session_tracker.emit_session_start = AsyncMock(
            side_effect=RuntimeError("mcp down")
        )

        with caplog.at_level(logging.ERROR, logger="session_buddy.shell.adapter"):
            await shell._emit_session_start()

        assert shell._session_id is None
        assert "Failed to emit session start" in caplog.text


class TestEmitSessionEnd:
    """``_emit_session_end`` behavior."""

    async def test_noop_when_no_active_session(self, shell: SessionBuddyShell) -> None:
        await shell._emit_session_end()

        shell.session_tracker.emit_session_end.assert_not_awaited()

    async def test_emits_end_and_clears_session_id(
        self, shell: SessionBuddyShell
    ) -> None:
        shell._session_id = "sess-abc"

        await shell._emit_session_end()

        shell.session_tracker.emit_session_end.assert_awaited_once_with(
            session_id="sess-abc",
            metadata={},
        )
        assert shell._session_id is None

    async def test_logs_info_on_success(
        self, shell: SessionBuddyShell, caplog: pytest.LogCaptureFixture
    ) -> None:
        shell._session_id = "sess-abc"

        with caplog.at_level(logging.INFO, logger="session_buddy.shell.adapter"):
            await shell._emit_session_end()

        assert "sess-abc" in caplog.text

    async def test_exception_is_swallowed_and_session_id_still_cleared(
        self, shell: SessionBuddyShell, caplog: pytest.LogCaptureFixture
    ) -> None:
        shell._session_id = "sess-abc"
        shell.session_tracker.emit_session_end = AsyncMock(
            side_effect=RuntimeError("mcp down")
        )

        with caplog.at_level(logging.ERROR, logger="session_buddy.shell.adapter"):
            await shell._emit_session_end()

        assert "Failed to emit session end" in caplog.text
        # ``finally`` must clear the id even on failure.
        assert shell._session_id is None


class TestClose:
    """``close`` lifecycle."""

    async def test_closes_tracker_without_active_session(
        self, shell: SessionBuddyShell
    ) -> None:
        await shell.close()

        shell.session_tracker.emit_session_end.assert_not_awaited()
        shell.session_tracker.close.assert_awaited_once_with()

    async def test_emits_end_then_closes_tracker(
        self, shell: SessionBuddyShell
    ) -> None:
        calls: list[str] = []
        shell._session_id = "sess-abc"
        shell.session_tracker.emit_session_end = AsyncMock(
            side_effect=lambda **_: calls.append("end")
        )
        shell.session_tracker.close = AsyncMock(
            side_effect=lambda *_: calls.append("close")
        )

        await shell.close()

        assert calls == ["end", "close"]
        assert shell._session_id is None

    async def test_close_propagates_tracker_close_error(
        self, shell: SessionBuddyShell
    ) -> None:
        # ``close`` deliberately does not guard the tracker shutdown.
        shell.session_tracker.close = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await shell.close()

    async def test_close_is_idempotent(self, shell: SessionBuddyShell) -> None:
        shell._session_id = "sess-abc"

        await shell.close()
        await shell.close()

        assert shell.session_tracker.emit_session_end.await_count == 1
        assert shell.session_tracker.close.await_count == 2


class TestModuleSurface:
    """Module-level expectations."""

    def test_shell_subclasses_admin_shell(self) -> None:
        from oneiric.shell import AdminShell

        assert issubclass(SessionBuddyShell, AdminShell)

    def test_logger_name(self) -> None:
        from session_buddy.shell import adapter

        assert adapter.logger.name == "session_buddy.shell.adapter"

    def test_overrides_are_not_inherited_verbatim(self) -> None:
        from oneiric.shell import AdminShell

        overridden: list[str] = [
            "_get_component_name",
            "_get_component_version",
            "_get_adapters_info",
            "_get_banner",
        ]
        for name in overridden:
            sub: Any = getattr(SessionBuddyShell, name)
            base: Any = getattr(AdminShell, name)
            assert sub is not base
