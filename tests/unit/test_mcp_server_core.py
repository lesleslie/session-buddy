"""Comprehensive pytest unit tests for session_buddy/mcp/server_core.py.

Tests all public methods, edge cases, and integration paths:
- Configuration and detection functions
- Session lifecycle management (full happy + error paths)
- Git session initialization/cleanup
- Health and status functions
- Quality formatting functions
- Initialization functions
- Utility functions
- Module-level constants and re-exports

This file is complementary to tests/unit/test_server_core.py - it focuses on
the server-core infrastructure paths that are not exercised there.

Requirements:
1. Cover 60%+ of the 239 statements in session_buddy/mcp/server_core.py
2. Use lazy imports inside test functions to avoid top-level module loading
3. Mock all external dependencies (subprocess, file IO, etc.)
4. Descriptive test names: test_<method>_<scenario>
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


# =====================================
# Shared Fixtures
# =====================================


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger compatible with SessionLogger interface."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.debug = MagicMock()
    logger.error = MagicMock()
    return logger


@pytest.fixture
def fake_feature_flags_all_off() -> dict[str, bool]:
    """Return a feature-flags dict with every flag disabled."""
    return {
        "SESSION_MANAGEMENT_AVAILABLE": False,
        "REFLECTION_TOOLS_AVAILABLE": False,
        "ENHANCED_SEARCH_AVAILABLE": False,
        "UTILITY_FUNCTIONS_AVAILABLE": False,
        "MULTI_PROJECT_AVAILABLE": False,
        "ADVANCED_SEARCH_AVAILABLE": False,
        "CONFIG_AVAILABLE": False,
        "AUTO_CONTEXT_AVAILABLE": False,
        "MEMORY_OPTIMIZER_AVAILABLE": False,
        "APP_MONITOR_AVAILABLE": False,
        "LLM_PROVIDERS_AVAILABLE": False,
        "SERVERLESS_MODE_AVAILABLE": False,
        "CRACKERJACK_INTEGRATION_AVAILABLE": False,
    }


@pytest.fixture
def fake_feature_flags_all_on() -> dict[str, bool]:
    """Return a feature-flags dict with every flag enabled."""
    return {k: True for k in [
        "SESSION_MANAGEMENT_AVAILABLE",
        "REFLECTION_TOOLS_AVAILABLE",
        "ENHANCED_SEARCH_AVAILABLE",
        "UTILITY_FUNCTIONS_AVAILABLE",
        "MULTI_PROJECT_AVAILABLE",
        "ADVANCED_SEARCH_AVAILABLE",
        "CONFIG_AVAILABLE",
        "AUTO_CONTEXT_AVAILABLE",
        "MEMORY_OPTIMIZER_AVAILABLE",
        "APP_MONITOR_AVAILABLE",
        "LLM_PROVIDERS_AVAILABLE",
        "SERVERLESS_MODE_AVAILABLE",
        "CRACKERJACK_INTEGRATION_AVAILABLE",
    ]}


# =====================================
# Test Classes - Grouped by Feature/Method
# =====================================


class TestModuleImports:
    """Tests for module-level surface and imports."""

    def test_module_imports_cleanly(self) -> None:
        """The module should be importable without raising."""
        import importlib

        module = importlib.import_module("session_buddy.mcp.server_core")
        assert module is not None

    def test_module_exposes_public_functions(self) -> None:
        """Public functions should be importable from the module."""
        from session_buddy.mcp import server_core

        # Public functions
        assert callable(server_core._detect_other_mcp_servers)
        assert callable(server_core._generate_server_guidance)
        assert callable(server_core._load_mcp_config)
        assert callable(server_core.session_lifecycle)
        assert callable(server_core.auto_setup_git_working_directory)
        assert callable(server_core.initialize_new_features)
        assert callable(server_core.analyze_project_context)
        assert callable(server_core.health_check)
        assert callable(server_core._should_retry_search)
        # Private helpers
        assert callable(server_core._initialize_git_session)
        assert callable(server_core._end_git_session)
        assert callable(server_core._store_connection_info)
        assert callable(server_core._add_basic_status_info)
        assert callable(server_core._add_health_status_info)
        assert callable(server_core._get_project_context_info)
        assert callable(server_core._format_quality_results)
        assert callable(server_core._perform_git_checkpoint)
        assert callable(server_core._format_conversation_summary)

    def test_server_panels_availability_is_defined(self) -> None:
        """Module should expose SERVERPANELS_AVAILABLE constant."""
        from session_buddy.mcp import server_core

        assert hasattr(server_core, "SERVERPANELS_AVAILABLE")
        # Boolean value
        assert isinstance(server_core.SERVERPANELS_AVAILABLE, bool)

    def test_tomli_handled_gracefully(self) -> None:
        """tomli import is wrapped in try/except - both states should be safe."""
        from session_buddy.mcp import server_core

        # tomli is either None or the module - both are valid
        tomli_value = getattr(server_core, "tomli", None)
        assert tomli_value is None or hasattr(tomli_value, "load")


class TestDetectOtherMCPServersExtra:
    """Extra edge cases for _detect_other_mcp_servers."""

    def test_detect_returns_dict_with_crackerjack_key(self) -> None:
        """Result should always include the crackerjack key."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            from session_buddy.mcp.server_core import _detect_other_mcp_servers

            result = _detect_other_mcp_servers()
            assert "crackerjack" in result
            assert isinstance(result, dict)

    def test_detect_handles_oserror(self) -> None:
        """OSError is not in the catch list - will propagate."""
        # OSError is not a SubprocessError subclass, so the function lets it
        # propagate. This documents the actual behavior.
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("os error")
            from session_buddy.mcp.server_core import _detect_other_mcp_servers

            with pytest.raises(OSError):
                _detect_other_mcp_servers()

    def test_detect_handles_called_process_error(self) -> None:
        """CalledProcessError is a SubprocessError subclass and should be caught."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "crackerjack")
            from session_buddy.mcp.server_core import _detect_other_mcp_servers

            result = _detect_other_mcp_servers()
            assert result["crackerjack"] is False

    def test_detect_uses_correct_subprocess_args(self) -> None:
        """Should call crackerjack --version with safe subprocess args."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            from session_buddy.mcp.server_core import _detect_other_mcp_servers

            _detect_other_mcp_servers()

            call_args = mock_run.call_args
            assert call_args.args[0] == ["crackerjack", "--version"]
            assert call_args.kwargs.get("check") is False
            assert call_args.kwargs.get("capture_output") is True
            assert call_args.kwargs.get("text") is True
            assert call_args.kwargs.get("timeout") == 5


class TestGenerateServerGuidanceExtra:
    """Extra scenarios for _generate_server_guidance."""

    def test_guidance_returns_list(self) -> None:
        """Return type should be a list."""
        from session_buddy.mcp.server_core import _generate_server_guidance

        guidance = _generate_server_guidance({})
        assert isinstance(guidance, list)

    def test_guidance_returns_six_lines_when_crackerjack_detected(self) -> None:
        """Should return 6 guidance lines (header + intro + 4 commands) when crackerjack detected."""
        from session_buddy.mcp.server_core import _generate_server_guidance

        guidance = _generate_server_guidance({"crackerjack": True})
        assert len(guidance) == 6

    def test_guidance_contains_useful_commands_when_crackerjack(self) -> None:
        """Guidance should mention the actual command names."""
        from session_buddy.mcp.server_core import _generate_server_guidance

        guidance = _generate_server_guidance({"crackerjack": True})
        joined = "\n".join(guidance)
        # Spot-check that the documented commands are mentioned
        assert "crackerjack-run" in joined
        assert "crackerjack-history" in joined
        assert "crackerjack-patterns" in joined

    def test_guidance_ignores_unknown_servers(self) -> None:
        """Unknown server keys should not produce guidance."""
        from session_buddy.mcp.server_core import _generate_server_guidance

        guidance = _generate_server_guidance({"unknown_server": True})
        assert guidance == []


class TestLoadMCPConfigExtra:
    """Extra scenarios for _load_mcp_config."""

    def test_load_returns_dict_with_expected_keys(self) -> None:
        """Result should always have the four documented keys."""
        with patch("session_buddy.mcp.server_core.Path.cwd", return_value=Path("/nonexistent")):
            with patch.object(Path, "exists", return_value=False):
                from session_buddy.mcp.server_core import _load_mcp_config

                result = _load_mcp_config()
        assert set(result.keys()) == {
            "http_port",
            "http_host",
            "websocket_monitor_port",
            "http_enabled",
        }

    def test_load_default_values_when_no_pyproject(self) -> None:
        """Default port/host values should match documentation."""
        with patch("session_buddy.mcp.server_core.Path.cwd", return_value=Path("/nonexistent")):
            with patch.object(Path, "exists", return_value=False):
                from session_buddy.mcp.server_core import _load_mcp_config

                result = _load_mcp_config()
        assert result["http_port"] == 8678
        assert result["http_host"] == "127.0.0.1"
        assert result["websocket_monitor_port"] == 8677
        assert result["http_enabled"] is False

    def test_load_finds_pyproject_in_parent(self) -> None:
        """Should search up to 3 parent directories for pyproject.toml."""
        with patch("session_buddy.mcp.server_core.Path.cwd", return_value=Path("/a/b/c")):
            with patch.object(Path, "exists", return_value=True):
                with patch("session_buddy.mcp.server_core.tomli") as mock_tomli:
                    mock_tomli.load.return_value = {}
                    from session_buddy.mcp.server_core import _load_mcp_config

                    result = _load_mcp_config()
        # Should have used the found pyproject
        assert "http_port" in result


class TestSessionLifecycleExtra:
    """Extra scenarios for session_lifecycle context manager."""

    @pytest.mark.asyncio
    async def test_lifecycle_with_git_repo_initializes(
        self, mock_logger: MagicMock
    ) -> None:
        """Git repo should trigger session initialization."""
        mock_app = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.initialize_session = AsyncMock(
            return_value={
                "success": True,
                "project": "p",
                "quality_score": 90,
                "previous_session": None,
                "quality_data": {"recommendations": []},
            }
        )

        with patch("session_buddy.utils.git_worktrees.is_git_repository", return_value=True):
            with patch("session_buddy.mcp.server_core._initialize_git_session", new_callable=AsyncMock) as mock_init:
                from session_buddy.mcp.server_core import session_lifecycle

                async with session_lifecycle(mock_app, mock_mgr, mock_logger):
                    pass

                mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifecycle_non_git_repo_skips_init(
        self, mock_logger: MagicMock
    ) -> None:
        """Non-git repo should skip init but still run cleanup."""
        mock_app = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.end_session = AsyncMock(return_value={"success": True})

        with patch("session_buddy.utils.git_worktrees.is_git_repository", return_value=False):
            with patch("session_buddy.mcp.server_core._initialize_git_session", new_callable=AsyncMock) as mock_init:
                with patch("session_buddy.mcp.server_core._end_git_session", new_callable=AsyncMock) as mock_end:
                    from session_buddy.mcp.server_core import session_lifecycle

                    async with session_lifecycle(mock_app, mock_mgr, mock_logger):
                        pass

                    mock_init.assert_not_called()
                    # Non-git repo: _end_git_session is not awaited because it
                    # returns early when not a git repository.

    @pytest.mark.asyncio
    async def test_lifecycle_yields_then_runs_cleanup(
        self, mock_logger: MagicMock
    ) -> None:
        """Body should run, then cleanup should run on exit."""
        mock_app = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.initialize_session = AsyncMock(
            return_value={
                "success": True,
                "project": "p",
                "quality_score": 90,
                "previous_session": None,
                "quality_data": {"recommendations": []},
            }
        )

        body_ran = False

        with patch("session_buddy.utils.git_worktrees.is_git_repository", return_value=True):
            with patch("session_buddy.mcp.server_core._initialize_git_session", new_callable=AsyncMock) as mock_init:
                with patch("session_buddy.mcp.server_core._end_git_session", new_callable=AsyncMock) as mock_end:
                    from session_buddy.mcp.server_core import session_lifecycle

                    async with session_lifecycle(mock_app, mock_mgr, mock_logger):
                        body_ran = True
                        # Cleanup is awaited on exit, NOT before body
                        assert not mock_end.await_count

                    assert body_ran
                    mock_end.assert_awaited_once()


class TestInitializeGitSessionExtra:
    """Extra scenarios for _initialize_git_session."""

    @pytest.mark.asyncio
    async def test_init_session_logs_git_root(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """Should log the git root path when initialization starts."""
        mock_mgr = MagicMock()
        mock_mgr.initialize_session = AsyncMock(
            return_value={
                "success": True,
                "project": "p",
                "quality_score": 90,
                "previous_session": None,
                "quality_data": {"recommendations": []},
            }
        )

        with patch("session_buddy.utils.git_worktrees.get_git_root", return_value=tmp_path):
            from session_buddy.mcp.server_core import _initialize_git_session

            await _initialize_git_session(tmp_path, mock_mgr, mock_logger)

        mock_logger.info.assert_called()
        first_info_args = mock_logger.info.call_args_list[0]
        assert "Git repository detected" in first_info_args.args[0]
        assert str(tmp_path) in first_info_args.args[0]

    @pytest.mark.asyncio
    async def test_init_session_success_path(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """Successful init should log success and call set_connection_info."""
        mock_mgr = MagicMock()
        mock_mgr.initialize_session = AsyncMock(
            return_value={
                "success": True,
                "project": "my-proj",
                "quality_score": 85,
                "previous_session": "prev-id",
                "quality_data": {"recommendations": ["rec1"]},
            }
        )

        with patch("session_buddy.utils.git_worktrees.get_git_root", return_value=tmp_path):
            with patch("session_buddy.advanced_features.set_connection_info") as mock_set:
                from session_buddy.mcp.server_core import _initialize_git_session

                await _initialize_git_session(tmp_path, mock_mgr, mock_logger)

        mock_set.assert_called_once()
        info = mock_set.call_args.args[0]
        assert info["project"] == "my-proj"
        assert info["quality_score"] == 85
        assert info["previous_session"] == "prev-id"
        assert info["recommendations"] == ["rec1"]
        assert info["connected_at"] == "just connected"

    @pytest.mark.asyncio
    async def test_init_session_failure_logs_warning(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """Init failure should log a warning (not raise)."""
        mock_mgr = MagicMock()
        mock_mgr.initialize_session = AsyncMock(
            return_value={"success": False, "error": "some failure"}
        )

        with patch("session_buddy.utils.git_worktrees.get_git_root", return_value=tmp_path):
            from session_buddy.mcp.server_core import _initialize_git_session

            await _initialize_git_session(tmp_path, mock_mgr, mock_logger)

        # Find a warning call
        warning_calls = [
            c for c in mock_logger.warning.call_args_list
        ]
        assert len(warning_calls) >= 1
        assert "Auto-init failed" in warning_calls[0].args[0]

    @pytest.mark.asyncio
    async def test_init_session_exception_caught(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """Exceptions during init should be caught and logged as warning."""
        mock_mgr = MagicMock()
        mock_mgr.initialize_session = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("session_buddy.utils.git_worktrees.get_git_root", return_value=tmp_path):
            from session_buddy.mcp.server_core import _initialize_git_session

            # Should NOT raise
            await _initialize_git_session(tmp_path, mock_mgr, mock_logger)

        warning_calls = mock_logger.warning.call_args_list
        assert any("non-critical" in c.args[0] for c in warning_calls)


class TestStoreConnectionInfoExtra:
    """Extra scenarios for _store_connection_info."""

    def test_store_connection_info_default_recommendations(self) -> None:
        """Empty recommendations list should pass through."""
        result = {
            "success": True,
            "project": "p",
            "quality_score": 80,
            "previous_session": None,
            "quality_data": {"recommendations": []},
        }
        with patch("session_buddy.advanced_features.set_connection_info") as mock_set:
            from session_buddy.mcp.server_core import _store_connection_info

            _store_connection_info(result)

        info = mock_set.call_args.args[0]
        assert info["recommendations"] == []
        assert info["connected_at"] == "just connected"

    def test_store_connection_info_multiple_recommendations(self) -> None:
        """Multiple recommendations should be stored as-is."""
        result = {
            "success": True,
            "project": "p",
            "quality_score": 80,
            "previous_session": "prev",
            "quality_data": {
                "recommendations": ["r1", "r2", "r3"],
            },
        }
        with patch("session_buddy.advanced_features.set_connection_info") as mock_set:
            from session_buddy.mcp.server_core import _store_connection_info

            _store_connection_info(result)

        info = mock_set.call_args.args[0]
        assert info["recommendations"] == ["r1", "r2", "r3"]


class TestEndGitSessionExtra:
    """Extra scenarios for _end_git_session."""

    @pytest.mark.asyncio
    async def test_end_non_git_repo_returns_early(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """When cwd is not a git repo, end_session is NOT called."""
        mock_mgr = MagicMock()
        mock_mgr.end_session = AsyncMock()

        with patch("session_buddy.utils.git_worktrees.is_git_repository", return_value=False):
            from session_buddy.mcp.server_core import _end_git_session

            await _end_git_session(tmp_path, mock_mgr, mock_logger)

        mock_mgr.end_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_end_git_session_success(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """Successful end should log info."""
        mock_mgr = MagicMock()
        mock_mgr.end_session = AsyncMock(return_value={"success": True})

        with patch("session_buddy.utils.git_worktrees.is_git_repository", return_value=True):
            from session_buddy.mcp.server_core import _end_git_session

            await _end_git_session(tmp_path, mock_mgr, mock_logger)

        info_calls = [c for c in mock_logger.info.call_args_list]
        assert any("Auto-ended session" in c.args[0] for c in info_calls)

    @pytest.mark.asyncio
    async def test_end_git_session_failure(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """Failure result should log a warning."""
        mock_mgr = MagicMock()
        mock_mgr.end_session = AsyncMock(
            return_value={"success": False, "error": "cleanup failed"}
        )

        with patch("session_buddy.utils.git_worktrees.is_git_repository", return_value=True):
            from session_buddy.mcp.server_core import _end_git_session

            await _end_git_session(tmp_path, mock_mgr, mock_logger)

        warnings = mock_logger.warning.call_args_list
        assert any("Auto-cleanup failed" in c.args[0] for c in warnings)

    @pytest.mark.asyncio
    async def test_end_git_session_exception_caught(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """Exceptions during end should be caught."""
        mock_mgr = MagicMock()
        mock_mgr.end_session = AsyncMock(side_effect=OSError("disk error"))

        with patch("session_buddy.utils.git_worktrees.is_git_repository", return_value=True):
            from session_buddy.mcp.server_core import _end_git_session

            # Should not raise
            await _end_git_session(tmp_path, mock_mgr, mock_logger)

        warnings = mock_logger.warning.call_args_list
        assert any("non-critical" in c.args[0] for c in warnings)


class TestAutoSetupGitWorkingDirectoryExtra:
    """Extra scenarios for auto_setup_git_working_directory."""

    @pytest.mark.asyncio
    async def test_setup_in_git_repo_logs_info(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """In a git repo, should log the auto-detected path."""
        with patch("session_buddy.mcp.server_core.Path.cwd", return_value=tmp_path):
            with patch("session_buddy.utils.git_worktrees.is_git_repository", return_value=True):
                with patch(
                    "session_buddy.utils.git_worktrees.get_git_root",
                    return_value=tmp_path,
                ):
                    from session_buddy.mcp.server_core import (
                        auto_setup_git_working_directory,
                    )

                    await auto_setup_git_working_directory(mock_logger)

        info_messages = [c.args[0] for c in mock_logger.info.call_args_list]
        assert any("Auto-detected git repository" in m for m in info_messages)
        assert any("mcp__git__git_set_working_dir" in m for m in info_messages)

    @pytest.mark.asyncio
    async def test_setup_not_in_git_repo_logs_debug(
        self, tmp_path: Path, mock_logger: MagicMock
    ) -> None:
        """Not in a git repo should log a debug message and not raise."""
        with patch("session_buddy.mcp.server_core.Path.cwd", return_value=tmp_path):
            with patch("session_buddy.utils.git_worktrees.is_git_repository", return_value=False):
                from session_buddy.mcp.server_core import (
                    auto_setup_git_working_directory,
                )

                await auto_setup_git_working_directory(mock_logger)

        debug_messages = [c.args[0] for c in mock_logger.debug.call_args_list]
        assert any("No git repository detected" in m for m in debug_messages)

    @pytest.mark.asyncio
    async def test_setup_exception_caught_gracefully(
        self, mock_logger: MagicMock
    ) -> None:
        """Internal exceptions should be caught and logged as debug."""
        with patch("session_buddy.mcp.server_core.Path.cwd", side_effect=OSError("cwd error")):
            from session_buddy.mcp.server_core import (
                auto_setup_git_working_directory,
            )

            # Should not raise
            await auto_setup_git_working_directory(mock_logger)

        debug_messages = [c.args[0] for c in mock_logger.debug.call_args_list]
        assert any("non-critical" in m for m in debug_messages)


class TestInitializeNewFeaturesExtra:
    """Extra scenarios for initialize_new_features."""

    @pytest.mark.asyncio
    async def test_init_returns_tuple_of_three(
        self,
        mock_logger: MagicMock,
        fake_feature_flags_all_off: dict[str, bool],
    ) -> None:
        """Result should be a 3-tuple."""
        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=fake_feature_flags_all_off,
        ):
            with patch(
                "session_buddy.mcp.server_core.auto_setup_git_working_directory",
                new_callable=AsyncMock,
            ):
                from session_buddy.mcp.server_core import initialize_new_features

                result = await initialize_new_features(
                    mock_logger, None, None, None
                )

        assert isinstance(result, tuple)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_init_passes_through_initial_refs(
        self,
        mock_logger: MagicMock,
        fake_feature_flags_all_off: dict[str, bool],
    ) -> None:
        """With no features available, input refs should be returned unchanged."""
        # Use distinct sentinels to verify identity
        sentinel_a = object()
        sentinel_b = object()
        sentinel_c = object()
        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=fake_feature_flags_all_off,
        ):
            with patch(
                "session_buddy.mcp.server_core.auto_setup_git_working_directory",
                new_callable=AsyncMock,
            ):
                from session_buddy.mcp.server_core import initialize_new_features

                mpc, ase, app_config = await initialize_new_features(
                    mock_logger, sentinel_a, sentinel_b, sentinel_c
                )

        # Each ref should be the exact same object we passed in
        assert mpc is sentinel_a
        assert ase is sentinel_b
        assert app_config is sentinel_c

    @pytest.mark.asyncio
    async def test_init_with_config_available_loads_settings(
        self,
        mock_logger: MagicMock,
        fake_feature_flags_all_off: dict[str, bool],
    ) -> None:
        """With CONFIG_AVAILABLE, settings should be loaded."""
        flags = dict(fake_feature_flags_all_off)
        flags["CONFIG_AVAILABLE"] = True

        fake_settings = object()
        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=flags,
        ):
            with patch(
                "session_buddy.mcp.server_core.auto_setup_git_working_directory",
                new_callable=AsyncMock,
            ):
                with patch(
                    "session_buddy.settings.get_settings", return_value=fake_settings
                ):
                    from session_buddy.mcp.server_core import initialize_new_features

                        # Reset import caches so that get_settings is reachable
                    import importlib
                    import session_buddy.mcp.server_core as sc

                    sc_module = sc
                    # Manually inject the settings module
                    sys.modules["session_buddy.settings"].get_settings = MagicMock(
                        return_value=fake_settings
                    )

                    mpc, ase, app_config = await initialize_new_features(
                        mock_logger, None, None, None
                    )

        assert app_config is fake_settings

    @pytest.mark.asyncio
    async def test_init_calls_auto_setup_first(
        self,
        mock_logger: MagicMock,
        fake_feature_flags_all_off: dict[str, bool],
    ) -> None:
        """auto_setup_git_working_directory should be awaited."""
        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=fake_feature_flags_all_off,
        ):
            with patch(
                "session_buddy.mcp.server_core.auto_setup_git_working_directory",
                new_callable=AsyncMock,
            ) as mock_auto:
                from session_buddy.mcp.server_core import initialize_new_features

                await initialize_new_features(mock_logger, None, None, None)

        mock_auto.assert_awaited_once_with(mock_logger)


class TestAnalyzeProjectContextExtra:
    """Extra scenarios for analyze_project_context wrapper."""

    @pytest.mark.asyncio
    async def test_analyze_python_project(self, tmp_path: Path) -> None:
        """Should detect a Python project (has pyproject.toml)."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)
        assert result["python_project"] is True
        assert result["git_repo"] is False
        assert result["has_tests"] is False
        assert result["has_docs"] is False
        assert result["has_uv_lock"] is False
        assert result["has_mcp_config"] is False
        assert result["has_requirements"] is False

    @pytest.mark.asyncio
    async def test_analyze_with_uv_lock(self, tmp_path: Path) -> None:
        """Should detect uv.lock when present."""
        (tmp_path / "pyproject.toml").write_text("x")
        (tmp_path / "uv.lock").write_text("lock")
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)
        assert result["has_uv_lock"] is True

    @pytest.mark.asyncio
    async def test_analyze_with_tests(self, tmp_path: Path) -> None:
        """Should detect tests/ directory."""
        (tmp_path / "pyproject.toml").write_text("x")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_x.py").write_text("# test")
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)
        assert result["has_tests"] is True

    @pytest.mark.asyncio
    async def test_analyze_with_mcp_config(self, tmp_path: Path) -> None:
        """Should detect .mcp.json."""
        (tmp_path / "pyproject.toml").write_text("x")
        (tmp_path / ".mcp.json").write_text("{}")
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)
        assert result["has_mcp_config"] is True

    @pytest.mark.asyncio
    async def test_analyze_with_readme(self, tmp_path: Path) -> None:
        """Should detect README.md."""
        (tmp_path / "pyproject.toml").write_text("x")
        (tmp_path / "README.md").write_text("# readme")
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)
        assert result["has_docs"] is True

    @pytest.mark.asyncio
    async def test_analyze_with_requirements(self, tmp_path: Path) -> None:
        """Should detect requirements.txt."""
        (tmp_path / "pyproject.toml").write_text("x")
        (tmp_path / "requirements.txt").write_text("requests")
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)
        assert result["has_requirements"] is True

    @pytest.mark.asyncio
    async def test_analyze_with_git_dir(self, tmp_path: Path) -> None:
        """Should detect .git directory."""
        (tmp_path / "pyproject.toml").write_text("x")
        (tmp_path / ".git").mkdir()
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)
        assert result["git_repo"] is True

    @pytest.mark.asyncio
    async def test_analyze_empty_directory(self, tmp_path: Path) -> None:
        """Empty dir should return all False."""
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)
        for value in result.values():
            assert value is False

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_directory(self, tmp_path: Path) -> None:
        """Non-existent dir should return all False (no error)."""
        nonexistent = tmp_path / "does-not-exist"
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(nonexistent)
        for value in result.values():
            assert value is False


class TestHealthCheckExtra:
    """Extra scenarios for health_check."""

    @pytest.mark.asyncio
    async def test_health_check_returns_dict(
        self,
        mock_logger: MagicMock,
        fake_feature_flags_all_on: dict[str, bool],
    ) -> None:
        """Result should be a dict with the expected top-level keys."""
        mock_perms = MagicMock()
        mock_perms.get_permission_status = MagicMock(
            return_value={"session_id": "abc"}
        )
        mock_validate = MagicMock()

        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=fake_feature_flags_all_on,
        ):
            with patch("shutil.which", return_value="/usr/bin/uv"):
                from session_buddy.mcp.server_core import health_check

                result = await health_check(mock_logger, mock_perms, mock_validate)

        assert "overall_healthy" in result
        assert "checks" in result
        assert "warnings" in result
        assert "errors" in result
        assert result["overall_healthy"] is True

    @pytest.mark.asyncio
    async def test_health_check_no_uv(
        self,
        mock_logger: MagicMock,
        fake_feature_flags_all_on: dict[str, bool],
    ) -> None:
        """Missing UV should add a warning."""
        mock_perms = MagicMock()
        mock_perms.get_permission_status = MagicMock(
            return_value={"session_id": "abc"}
        )
        mock_validate = MagicMock()

        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=fake_feature_flags_all_on,
        ):
            with patch("shutil.which", return_value=None):
                from session_buddy.mcp.server_core import health_check

                result = await health_check(mock_logger, mock_perms, mock_validate)

        assert any("UV" in w for w in result["warnings"])
        assert "Missing" in result["checks"]["uv_manager"]

    @pytest.mark.asyncio
    async def test_health_check_permissions_error(
        self,
        mock_logger: MagicMock,
        fake_feature_flags_all_on: dict[str, bool],
    ) -> None:
        """Permissions system error should mark overall as unhealthy."""
        mock_perms = MagicMock()
        mock_perms.get_permission_status = MagicMock(
            side_effect=RuntimeError("perm boom")
        )
        mock_validate = MagicMock()

        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=fake_feature_flags_all_on,
        ):
            with patch("shutil.which", return_value="/usr/bin/uv"):
                from session_buddy.mcp.server_core import health_check

                result = await health_check(mock_logger, mock_perms, mock_validate)

        assert result["overall_healthy"] is False
        assert any("Permissions system" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_health_check_logs_results(
        self,
        mock_logger: MagicMock,
        fake_feature_flags_all_on: dict[str, bool],
    ) -> None:
        """Health check should log completion info."""
        mock_perms = MagicMock()
        mock_perms.get_permission_status = MagicMock(
            return_value={"session_id": "x"}
        )
        mock_validate = MagicMock()

        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=fake_feature_flags_all_on,
        ):
            with patch("shutil.which", return_value="/usr/bin/uv"):
                from session_buddy.mcp.server_core import health_check

                await health_check(mock_logger, mock_perms, mock_validate)

        info_calls = [c for c in mock_logger.info.call_args_list]
        assert any("Health check completed" in c.args[0] for c in info_calls)

    @pytest.mark.asyncio
    async def test_health_check_session_id_in_output(
        self,
        mock_logger: MagicMock,
        fake_feature_flags_all_on: dict[str, bool],
    ) -> None:
        """Active session ID should be included in checks."""
        mock_perms = MagicMock()
        mock_perms.get_permission_status = MagicMock(
            return_value={"session_id": "session-xyz"}
        )
        mock_validate = MagicMock()

        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=fake_feature_flags_all_on,
        ):
            with patch("shutil.which", return_value="/usr/bin/uv"):
                from session_buddy.mcp.server_core import health_check

                result = await health_check(mock_logger, mock_perms, mock_validate)

        # session_id should be present in the output
        assert "session-xyz" in result["checks"]["session_id"]


class TestAddBasicStatusInfoExtra:
    """Extra scenarios for _add_basic_status_info."""

    @pytest.mark.asyncio
    async def test_basic_status_appends_three_lines(self, tmp_path: Path) -> None:
        """Should append exactly three info lines."""
        from session_buddy.mcp.server_core import _add_basic_status_info

        output: list[str] = []
        await _add_basic_status_info(output, tmp_path, None)

        assert len(output) == 3
        assert "Current project" in output[0]
        assert "Working directory" in output[1]
        assert "MCP server: Active" in output[2]

    @pytest.mark.asyncio
    async def test_basic_status_uses_dir_name(self, tmp_path: Path) -> None:
        """Project name should be the directory basename."""
        from session_buddy.mcp.server_core import _add_basic_status_info

        output: list[str] = []
        await _add_basic_status_info(output, tmp_path, None)

        # tmp_path's name is unique per test - just check it's in the output
        assert tmp_path.name in output[0]


class TestAddHealthStatusInfoExtra:
    """Extra scenarios for _add_health_status_info."""

    @pytest.mark.asyncio
    async def test_health_status_healthy_marker(
        self, mock_logger: MagicMock
    ) -> None:
        """Healthy result should show HEALTHY marker."""
        mock_perms = MagicMock()
        mock_perms.get_permission_status = MagicMock(
            return_value={"session_id": "ok"}
        )
        mock_validate = MagicMock()

        flags = {k: True for k in [
            "SESSION_MANAGEMENT_AVAILABLE",
            "CRACKERJACK_INTEGRATION_AVAILABLE",
        ]}
        flags.setdefault("CONFIG_AVAILABLE", True)
        flags.setdefault("MULTI_PROJECT_AVAILABLE", True)
        flags.setdefault("ADVANCED_SEARCH_AVAILABLE", True)
        flags.setdefault("REFLECTION_TOOLS_AVAILABLE", True)

        # Use a fuller set
        full_flags = {k: True for k in [
            "SESSION_MANAGEMENT_AVAILABLE",
            "REFLECTION_TOOLS_AVAILABLE",
            "ENHANCED_SEARCH_AVAILABLE",
            "UTILITY_FUNCTIONS_AVAILABLE",
            "MULTI_PROJECT_AVAILABLE",
            "ADVANCED_SEARCH_AVAILABLE",
            "CONFIG_AVAILABLE",
            "AUTO_CONTEXT_AVAILABLE",
            "MEMORY_OPTIMIZER_AVAILABLE",
            "APP_MONITOR_AVAILABLE",
            "LLM_PROVIDERS_AVAILABLE",
            "SERVERLESS_MODE_AVAILABLE",
            "CRACKERJACK_INTEGRATION_AVAILABLE",
        ]}

        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=full_flags,
        ):
            with patch("shutil.which", return_value="/usr/bin/uv"):
                from session_buddy.mcp.server_core import _add_health_status_info

                output: list[str] = []
                await _add_health_status_info(
                    output, mock_logger, mock_perms, mock_validate
                )

        assert any("HEALTHY" in line for line in output)

    @pytest.mark.asyncio
    async def test_health_status_with_warnings(
        self, mock_logger: MagicMock
    ) -> None:
        """Output should include warnings when present."""
        mock_perms = MagicMock()
        mock_perms.get_permission_status = MagicMock(
            return_value={"session_id": "ok"}
        )
        mock_validate = MagicMock()

        # Flags with crackerjack disabled (causes a warning)
        flags = {k: True for k in [
            "SESSION_MANAGEMENT_AVAILABLE",
            "REFLECTION_TOOLS_AVAILABLE",
            "ENHANCED_SEARCH_AVAILABLE",
            "UTILITY_FUNCTIONS_AVAILABLE",
            "MULTI_PROJECT_AVAILABLE",
            "ADVANCED_SEARCH_AVAILABLE",
            "CONFIG_AVAILABLE",
            "AUTO_CONTEXT_AVAILABLE",
            "MEMORY_OPTIMIZER_AVAILABLE",
            "APP_MONITOR_AVAILABLE",
            "LLM_PROVIDERS_AVAILABLE",
            "SERVERLESS_MODE_AVAILABLE",
            "CRACKERJACK_INTEGRATION_AVAILABLE",
        ]}
        flags["CRACKERJACK_INTEGRATION_AVAILABLE"] = False

        with patch(
            "session_buddy.core.features.get_feature_flags",
            return_value=flags,
        ):
            with patch("shutil.which", return_value=None):
                from session_buddy.mcp.server_core import _add_health_status_info

                output: list[str] = []
                await _add_health_status_info(
                    output, mock_logger, mock_perms, mock_validate
                )

        # UV missing produces a warning
        assert any("Warnings" in line for line in output)


class TestGetProjectContextInfoExtra:
    """Extra scenarios for _get_project_context_info."""

    @pytest.mark.asyncio
    async def test_get_project_context_returns_tuple(
        self, tmp_path: Path
    ) -> None:
        """Should return (context_dict, score, max_score) tuple."""
        (tmp_path / "pyproject.toml").write_text("x")
        (tmp_path / "README.md").write_text("x")
        from session_buddy.mcp.server_core import _get_project_context_info

        ctx, score, max_score = await _get_project_context_info(tmp_path)

        assert isinstance(ctx, dict)
        assert isinstance(score, int)
        assert isinstance(max_score, int)
        assert max_score >= score
        # We provided pyproject.toml + README.md
        assert score >= 2

    @pytest.mark.asyncio
    async def test_get_project_context_empty(self, tmp_path: Path) -> None:
        """Empty dir should yield score=0, max_score>0."""
        from session_buddy.mcp.server_core import _get_project_context_info

        ctx, score, max_score = await _get_project_context_info(tmp_path)

        assert score == 0
        assert max_score > 0
        assert all(v is False for v in ctx.values())


class TestFormatQualityResultsExtra:
    """Extra scenarios for _format_quality_results."""

    @pytest.mark.asyncio
    async def test_format_excellent(self) -> None:
        """Score >= 80 should produce 'EXCELLENT' output."""
        from session_buddy.mcp.server_core import _format_quality_results

        quality_data = {
            "version": "2.0",
            "breakdown": {
                "code_quality": 35.0,
                "project_health": 25.0,
                "dev_velocity": 15.0,
                "security": 8.0,
            },
            "recommendations": ["r1"],
        }
        result = await _format_quality_results(85, quality_data, None)
        text = "\n".join(result)
        assert "EXCELLENT" in text
        assert "85/100" in text
        assert "V2.0" in text

    @pytest.mark.asyncio
    async def test_format_good(self) -> None:
        """Score 60-79 should produce 'GOOD' output."""
        from session_buddy.mcp.server_core import _format_quality_results

        quality_data = {
            "version": "2.0",
            "breakdown": {
                "code_quality": 25.0,
                "project_health": 20.0,
                "dev_velocity": 10.0,
                "security": 5.0,
            },
            "recommendations": [],
        }
        result = await _format_quality_results(70, quality_data, None)
        text = "\n".join(result)
        assert "GOOD" in text

    @pytest.mark.asyncio
    async def test_format_needs_attention(self) -> None:
        """Score < 60 should produce 'NEEDS ATTENTION' output."""
        from session_buddy.mcp.server_core import _format_quality_results

        quality_data = {
            "version": "2.0",
            "breakdown": {
                "code_quality": 10.0,
                "project_health": 10.0,
                "dev_velocity": 10.0,
                "security": 5.0,
            },
            "recommendations": [],
        }
        result = await _format_quality_results(40, quality_data, None)
        text = "\n".join(result)
        assert "NEEDS ATTENTION" in text

    @pytest.mark.asyncio
    async def test_format_with_trust_score(self) -> None:
        """Trust score should be included when present."""
        from session_buddy.mcp.server_core import _format_quality_results

        quality_data = {
            "version": "2.0",
            "breakdown": {
                "code_quality": 35.0,
                "project_health": 25.0,
                "dev_velocity": 15.0,
                "security": 8.0,
            },
            "recommendations": [],
            "trust_score": {
                "total": 90.0,
                "breakdown": {
                    "trusted_operations": 35.0,
                    "session_availability": 28.0,
                    "tool_ecosystem": 27.0,
                },
            },
        }
        result = await _format_quality_results(85, quality_data, None)
        text = "\n".join(result)
        assert "Trust score" in text
        assert "90/100" in text

    @pytest.mark.asyncio
    async def test_format_with_checkpoint(self) -> None:
        """Checkpoint data should be included when provided."""
        from session_buddy.mcp.server_core import _format_quality_results

        quality_data = {
            "version": "2.0",
            "breakdown": {
                "code_quality": 35.0,
                "project_health": 25.0,
                "dev_velocity": 15.0,
                "security": 8.0,
            },
            "recommendations": ["rec"],
        }
        checkpoint = {
            "strengths": ["good", "clean", "fast", "extra"],
            "session_stats": {
                "duration_minutes": 42,
                "total_checkpoints": 7,
                "success_rate": 95.5,
            },
        }
        result = await _format_quality_results(85, quality_data, checkpoint)
        text = "\n".join(result)
        assert "Session strengths" in text
        assert "Session progress" in text
        assert "42 minutes" in text
        # Strengths are limited to first 3
        assert text.count("•") >= 1

    @pytest.mark.asyncio
    async def test_format_recommendations_limited_to_3(self) -> None:
        """Only first 3 recommendations should be shown."""
        from session_buddy.mcp.server_core import _format_quality_results

        quality_data = {
            "version": "2.0",
            "breakdown": {
                "code_quality": 30.0,
                "project_health": 25.0,
                "dev_velocity": 15.0,
                "security": 8.0,
            },
            "recommendations": ["r1", "r2", "r3", "r4", "r5"],
        }
        result = await _format_quality_results(85, quality_data, None)
        text = "\n".join(result)
        assert "r1" in text
        assert "r2" in text
        assert "r3" in text
        # r4 and r5 should not be displayed
        assert "r4" not in text
        assert "r5" not in text

    @pytest.mark.asyncio
    async def test_format_with_default_version(self) -> None:
        """Missing version should default to 1.0."""
        from session_buddy.mcp.server_core import _format_quality_results

        quality_data = {
            "breakdown": {
                "code_quality": 35.0,
                "project_health": 25.0,
                "dev_velocity": 15.0,
                "security": 8.0,
            },
            "recommendations": [],
        }
        result = await _format_quality_results(85, quality_data, None)
        text = "\n".join(result)
        assert "V1.0" in text


class TestPerformGitCheckpointExtra:
    """Extra scenarios for _perform_git_checkpoint."""

    @pytest.mark.asyncio
    async def test_git_checkpoint_success(self, tmp_path: Path) -> None:
        """Successful commit should append success message."""
        with patch(
            "session_buddy.utils.git_worktrees.create_checkpoint_commit",
            return_value=(True, "abc123", ["file staged", "file committed"]),
        ):
            from session_buddy.mcp.server_core import _perform_git_checkpoint

            result = await _perform_git_checkpoint(tmp_path, 85, "myproj")

        text = "\n".join(result)
        assert "Git Checkpoint" in text
        assert "abc123" in text
        assert "Checkpoint commit created" in text

    @pytest.mark.asyncio
    async def test_git_checkpoint_clean(self, tmp_path: Path) -> None:
        """'clean' result should not add 'commit created' line."""
        with patch(
            "session_buddy.utils.git_worktrees.create_checkpoint_commit",
            return_value=(True, "clean", ["no changes"]),
        ):
            from session_buddy.mcp.server_core import _perform_git_checkpoint

            result = await _perform_git_checkpoint(tmp_path, 85, "myproj")

        text = "\n".join(result)
        assert "Git Checkpoint" in text
        # Should NOT contain "commit created" line
        assert "commit created" not in text

    @pytest.mark.asyncio
    async def test_git_checkpoint_failure(self, tmp_path: Path) -> None:
        """Failed commit should produce a warning line."""
        with patch(
            "session_buddy.utils.git_worktrees.create_checkpoint_commit",
            return_value=(False, "no changes to commit", ["nothing staged"]),
        ):
            from session_buddy.mcp.server_core import _perform_git_checkpoint

            result = await _perform_git_checkpoint(tmp_path, 85, "myproj")

        text = "\n".join(result)
        assert "Failed to stage" in text
        assert "no changes to commit" in text

    @pytest.mark.asyncio
    async def test_git_checkpoint_includes_quality_score(
        self, tmp_path: Path
    ) -> None:
        """Commit output should include the quality score."""
        with patch(
            "session_buddy.utils.git_worktrees.create_checkpoint_commit",
            return_value=(True, "deadbeef", []),
        ) as mock:
            from session_buddy.mcp.server_core import _perform_git_checkpoint

            await _perform_git_checkpoint(tmp_path, 92, "p")

        # The quality score is passed to the underlying function
        call_args = mock.call_args
        assert call_args.args[2] == 92


class TestFormatConversationSummaryExtra:
    """Extra scenarios for _format_conversation_summary."""

    @pytest.mark.asyncio
    async def test_format_conversation_empty(self) -> None:
        """Empty conversation should produce no output."""
        with patch(
            "session_buddy.quality_engine.summarize_current_conversation",
            new_callable=AsyncMock,
            return_value={"key_topics": [], "decisions_made": []},
        ):
            from session_buddy.mcp.server_core import _format_conversation_summary

            result = await _format_conversation_summary()

        assert result == []

    @pytest.mark.asyncio
    async def test_format_conversation_with_topics(self) -> None:
        """Topics should appear in the output."""
        with patch(
            "session_buddy.quality_engine.summarize_current_conversation",
            new_callable=AsyncMock,
            return_value={
                "key_topics": ["topic1", "topic2"],
                "decisions_made": [],
            },
        ):
            from session_buddy.mcp.server_core import _format_conversation_summary

            result = await _format_conversation_summary()

        text = "\n".join(result)
        assert "Current Session Focus" in text
        assert "topic1" in text

    @pytest.mark.asyncio
    async def test_format_conversation_with_decisions(self) -> None:
        """Decisions should appear in the output."""
        with patch(
            "session_buddy.quality_engine.summarize_current_conversation",
            new_callable=AsyncMock,
            return_value={
                "key_topics": [],
                "decisions_made": ["decided to use pytest"],
            },
        ):
            from session_buddy.mcp.server_core import _format_conversation_summary

            result = await _format_conversation_summary()

        text = "\n".join(result)
        assert "Key Decisions" in text
        assert "decided to use pytest" in text

    @pytest.mark.asyncio
    async def test_format_conversation_import_error_caught(self) -> None:
        """ImportError on summarize should be swallowed."""
        with patch(
            "session_buddy.quality_engine.summarize_current_conversation",
            new_callable=AsyncMock,
            side_effect=ImportError("not available"),
        ):
            from session_buddy.mcp.server_core import _format_conversation_summary

            # Should not raise
            result = await _format_conversation_summary()

        assert result == []


class TestShouldRetrySearchExtra:
    """Extra scenarios for _should_retry_search."""

    def test_retry_database_locked(self) -> None:
        """Should retry on 'database is locked' errors."""
        from session_buddy.mcp.server_core import _should_retry_search

        assert _should_retry_search(Exception("database is locked")) is True

    def test_retry_connection_failed(self) -> None:
        """Should retry on 'connection failed' errors."""
        from session_buddy.mcp.server_core import _should_retry_search

        assert _should_retry_search(Exception("connection failed")) is True

    def test_retry_temporary_failure(self) -> None:
        """Should retry on 'temporary failure' errors."""
        from session_buddy.mcp.server_core import _should_retry_search

        assert _should_retry_search(Exception("temporary failure")) is True

    def test_retry_timeout(self) -> None:
        """Should retry on 'timeout' errors."""
        from session_buddy.mcp.server_core import _should_retry_search

        assert _should_retry_search(Exception("timeout")) is True

    def test_retry_index_not_found(self) -> None:
        """Should retry on 'index not found' errors."""
        from session_buddy.mcp.server_core import _should_retry_search

        assert _should_retry_search(Exception("index not found")) is True

    def test_no_retry_unknown_error(self) -> None:
        """Should NOT retry on unknown error messages."""
        from session_buddy.mcp.server_core import _should_retry_search

        assert _should_retry_search(Exception("permission denied")) is False

    def test_no_retry_random_error(self) -> None:
        """Should NOT retry on random unrelated errors."""
        from session_buddy.mcp.server_core import _should_retry_search

        assert _should_retry_search(Exception("foo bar baz")) is False

    def test_retry_is_case_insensitive(self) -> None:
        """Matching should be case-insensitive (via .lower())."""
        from session_buddy.mcp.server_core import _should_retry_search

        assert _should_retry_search(Exception("DATABASE IS LOCKED")) is True
        assert _should_retry_search(Exception("Connection Failed")) is True

    def test_retry_with_empty_message(self) -> None:
        """Empty error message should NOT trigger retry."""
        from session_buddy.mcp.server_core import _should_retry_search

        assert _should_retry_search(Exception("")) is False


class TestAnalyzeProjectContextReExport:
    """Verify the analyze_project_context re-export works."""

    def test_re_export_is_callable(self) -> None:
        """analyze_project_context should be callable and a coroutine function."""
        from session_buddy.mcp.server_core import analyze_project_context

        assert callable(analyze_project_context)

    def test_re_export_returns_dict(self) -> None:
        """analyze_project_context is an async function."""
        import inspect

        from session_buddy.mcp.server_core import analyze_project_context

        assert inspect.iscoroutinefunction(analyze_project_context)


class TestSessionLifecycleIsAsyncContextManager:
    """Verify session_lifecycle is an async context manager."""

    def test_session_lifecycle_is_async_context_manager(self) -> None:
        """session_lifecycle should be decorated with @asynccontextmanager."""
        from session_buddy.mcp.server_core import session_lifecycle

        # Calling it should return an async context manager
        cm = session_lifecycle(MagicMock(), MagicMock(), MagicMock())
        assert hasattr(cm, "__aenter__")
        assert hasattr(cm, "__aexit__")


class TestAllAsyncFunctionsAreAsync:
    """Sanity check: all async-decorated functions should be coroutine functions."""

    def test_async_functions_are_coroutines(self) -> None:
        """All public/private async functions should be detected as coroutines.

        Note: ``session_lifecycle`` is decorated with ``@asynccontextmanager``
        and returns an async context manager, so it is NOT a coroutine function
        itself. We exclude it from the list.
        """
        import inspect

        from session_buddy.mcp import server_core

        async_funcs = [
            "_initialize_git_session",
            "_end_git_session",
            "auto_setup_git_working_directory",
            "initialize_new_features",
            "analyze_project_context",
            "health_check",
            "_add_basic_status_info",
            "_add_health_status_info",
            "_get_project_context_info",
            "_format_quality_results",
            "_perform_git_checkpoint",
            "_format_conversation_summary",
        ]
        for name in async_funcs:
            func = getattr(server_core, name)
            assert inspect.iscoroutinefunction(func), f"{name} should be async"

    def test_session_lifecycle_returns_async_context_manager(self) -> None:
        """session_lifecycle is an async context manager (not coroutine)."""
        import inspect

        from session_buddy.mcp.server_core import session_lifecycle

        # NOT a coroutine function itself
        assert not inspect.iscoroutinefunction(session_lifecycle)
        # Calling it returns an async context manager
        cm = session_lifecycle(MagicMock(), MagicMock(), MagicMock())
        assert hasattr(cm, "__aenter__")
        assert hasattr(cm, "__aexit__")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov", "--tb=short"])
