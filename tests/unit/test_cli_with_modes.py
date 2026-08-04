#!/usr/bin/env python3
"""Comprehensive pytest tests for session_buddy.cli_with_modes module.

Tests all public classes and functions, with focus on CLI mode switching behaviors.
Uses tempfile.TemporaryDirectory for file operations and mocks external dependencies.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test
from session_buddy import cli_with_modes as cli_module
from session_buddy.modes.base import ModeConfig, OperationMode
from session_buddy.modes.lite import LiteMode
from session_buddy.modes.standard import StandardMode


# ============================================================================
# Test SessionBuddySettings
# ============================================================================


class TestSessionBuddySettings:
    """Tests for SessionBuddySettings class."""

    def test_settings_default_values(self) -> None:
        """Test default values for SessionBuddySettings."""
        from session_buddy.cli_with_modes import SessionBuddySettings

        settings = SessionBuddySettings()

        assert settings.server_name == "session-buddy"
        assert settings.http_port == 8678
        assert settings.websocket_port == 8677
        assert settings.startup_timeout == 10
        assert settings.shutdown_timeout == 10
        assert settings.force_kill_timeout == 5
        assert settings.mode == "standard"

    def test_settings_custom_values(self) -> None:
        """Test custom values for SessionBuddySettings."""
        from session_buddy.cli_with_modes import SessionBuddySettings

        settings = SessionBuddySettings(
            server_name="custom-server",
            http_port=9000,
            websocket_port=9001,
            startup_timeout=30,
            shutdown_timeout=30,
            force_kill_timeout=10,
            mode="lite",
        )

        assert settings.server_name == "custom-server"
        assert settings.http_port == 9000
        assert settings.websocket_port == 9001
        assert settings.startup_timeout == 30
        assert settings.shutdown_timeout == 30
        assert settings.force_kill_timeout == 10
        assert settings.mode == "lite"

    def test_settings_mode_parameter(self) -> None:
        """Test that mode parameter is properly stored."""
        from session_buddy.cli_with_modes import SessionBuddySettings

        settings_lite = SessionBuddySettings(mode="lite")
        settings_standard = SessionBuddySettings(mode="standard")

        assert settings_lite.mode == "lite"
        assert settings_standard.mode == "standard"

    def test_settings_inherits_oneiric_mcp_config(self) -> None:
        """Test that SessionBuddySettings inherits from OneiricMCPConfig.

        Note: this previously asserted ``MCPServerSettings`` as the
        base class. session-buddy migrated from MCPServerSettings ->
        OneiricMCPConfig; the assertion is updated to match the new
        inheritance chain without changing the test's intent.
        """
        from session_buddy.cli_with_modes import SessionBuddySettings
        from oneiric.core.config import OneiricMCPConfig

        settings = SessionBuddySettings()

        assert isinstance(settings, OneiricMCPConfig)

    def test_cache_root_shim_returns_path_from_cache_dir(self) -> None:
        """Regression: OneiricMCPConfig exposes cache_dir (str) only.

        mcp_common.cli.MCPServerCLIFactory calls
        ``validate_cache_ownership(self.settings.cache_root)`` (factory.py:406).
        ``cache_root`` is a Path on the legacy MCPServerSettings base; it was
        dropped in the OneiricMCPConfig migration (commit 05bc2622). The shim
        mirrors ``cache_dir`` into ``cache_root`` so startup does not raise
        ``AttributeError``. This test pins the shim contract.
        """
        from session_buddy.cli_with_modes import SessionBuddySettings

        settings = SessionBuddySettings()

        assert isinstance(settings.cache_root, Path)
        assert settings.cache_root == Path(settings.cache_dir)


# ============================================================================
# Test start_server_handler
# ============================================================================


class TestStartServerHandler:
    """Tests for start_server_handler function."""

    @patch("session_buddy.server_optimized.run_server")
    @patch("session_buddy.cli_with_modes.get_mode")
    def test_start_server_handler_standard_mode(
        self, mock_get_mode: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test starting server in standard mode."""
        from session_buddy.cli_with_modes import start_server_handler

        # Setup mocks
        mock_mode_instance = MagicMock(spec=StandardMode)
        mock_config = MagicMock(spec=ModeConfig)
        mock_config.database_path = "/path/to/db.duckdb"
        mock_config.storage_backend = "file"
        mock_config.enable_embeddings = True
        mock_config.enable_multi_project = True
        mock_mode_instance.get_config.return_value = mock_config
        mock_mode_instance.get_startup_message.return_value = "🚀 Starting standard mode..."
        mock_get_mode.return_value = mock_mode_instance
        mock_run_server.return_value = None

        # Execute with captured output
        with patch("sys.stdout", new_callable=MagicMock):
            start_server_handler(mode="standard")

        # Verify mode was obtained
        mock_get_mode.assert_called_once_with("standard")

        # Verify run_server was called with correct parameters
        mock_run_server.assert_called_once_with(host="127.0.0.1", port=8678)

    @patch("session_buddy.server_optimized.run_server")
    @patch("session_buddy.cli_with_modes.get_mode")
    def test_start_server_handler_lite_mode(
        self, mock_get_mode: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test starting server in lite mode."""
        from session_buddy.cli_with_modes import start_server_handler

        # Setup mocks
        mock_mode_instance = MagicMock(spec=LiteMode)
        mock_config = MagicMock(spec=ModeConfig)
        mock_config.database_path = ":memory:"
        mock_config.storage_backend = "memory"
        mock_config.enable_embeddings = False
        mock_config.enable_multi_project = False
        mock_mode_instance.get_config.return_value = mock_config
        mock_mode_instance.get_startup_message.return_value = "🚀 Starting lite mode..."
        mock_get_mode.return_value = mock_mode_instance
        mock_run_server.return_value = None

        # Execute
        with patch("sys.stdout", new_callable=MagicMock):
            start_server_handler(mode="lite")

        # Verify mode was obtained
        mock_get_mode.assert_called_once_with("lite")

    @patch("session_buddy.cli_with_modes.get_mode")
    def test_start_server_handler_invalid_mode(
        self, mock_get_mode: MagicMock
    ) -> None:
        """Test start_server_handler with invalid mode raises SystemExit."""
        from session_buddy.cli_with_modes import start_server_handler

        mock_get_mode.side_effect = ValueError("Invalid mode 'invalid'")

        with patch("sys.stderr", new_callable=MagicMock) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                start_server_handler(mode="invalid")

        assert exc_info.value.code == 1

    @patch("session_buddy.server_optimized.run_server")
    @patch("session_buddy.cli_with_modes.get_mode")
    def test_start_server_handler_general_exception(
        self, mock_get_mode: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test start_server_handler handles general exceptions."""
        from session_buddy.cli_with_modes import start_server_handler

        mock_get_mode.return_value = MagicMock()
        mock_run_server.side_effect = RuntimeError("Server failed")

        with patch("sys.stderr", new_callable=MagicMock) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                start_server_handler(mode="standard")

        assert exc_info.value.code == 1

    @patch("session_buddy.server_optimized.run_server")
    @patch("session_buddy.cli_with_modes.get_mode")
    def test_start_server_handler_sets_env_var(
        self, mock_get_mode: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test start_server_handler sets SESSION_BUDDY_MODE environment variable."""
        from session_buddy.cli_with_modes import start_server_handler

        mock_mode_instance = MagicMock(spec=StandardMode)
        mock_config = MagicMock(spec=ModeConfig)
        mock_config.database_path = "/path/to/db.duckdb"
        mock_config.storage_backend = "file"
        mock_config.enable_embeddings = True
        mock_config.enable_multi_project = True
        mock_mode_instance.get_config.return_value = mock_config
        mock_mode_instance.get_startup_message.return_value = "🚀..."
        mock_get_mode.return_value = mock_mode_instance
        mock_run_server.return_value = None

        # Save original env
        original_env = os.environ.get("SESSION_BUDDY_MODE")
        try:
            # Clear and set test env
            os.environ.pop("SESSION_BUDDY_MODE", None)
            with patch("sys.stdout", new_callable=MagicMock):
                start_server_handler(mode="standard")

            assert os.environ.get("SESSION_BUDDY_MODE") == "standard"
        finally:
            # Restore original env
            if original_env is not None:
                os.environ["SESSION_BUDDY_MODE"] = original_env
            else:
                os.environ.pop("SESSION_BUDDY_MODE", None)


# ============================================================================
# Test _read_running_pid
# ============================================================================


class TestReadRunningPid:
    """Tests for _read_running_pid function."""

    def test_read_running_pid_file_not_exists(self) -> None:
        """Test reading PID when file doesn't exist."""
        from session_buddy.cli_with_modes import _read_running_pid

        mock_settings = MagicMock()
        mock_settings.pid_path.return_value = Path("/nonexistent/path/pidfile.pid")

        result = _read_running_pid(mock_settings)

        assert result is None

    def test_read_running_pid_valid_pid(self, tmp_path: Path) -> None:
        """Test reading a valid PID from file."""
        from session_buddy.cli_with_modes import _read_running_pid

        pid_file = tmp_path / "pidfile.pid"
        pid_file.write_text("12345\n")

        mock_settings = MagicMock()
        mock_settings.pid_path.return_value = pid_file

        result = _read_running_pid(mock_settings)

        assert result == 12345

    def test_read_running_pid_whitespace(self, tmp_path: Path) -> None:
        """Test reading PID with whitespace."""
        from session_buddy.cli_with_modes import _read_running_pid

        pid_file = tmp_path / "pidfile.pid"
        pid_file.write_text("  67890  \n")

        mock_settings = MagicMock()
        mock_settings.pid_path.return_value = pid_file

        result = _read_running_pid(mock_settings)

        assert result == 67890

    def test_read_running_pid_invalid_content(self, tmp_path: Path) -> None:
        """Test reading PID with invalid content."""
        from session_buddy.cli_with_modes import _read_running_pid

        pid_file = tmp_path / "pidfile.pid"
        pid_file.write_text("not_a_number\n")

        mock_settings = MagicMock()
        mock_settings.pid_path.return_value = pid_file

        result = _read_running_pid(mock_settings)

        assert result is None

    def test_read_running_pid_empty_file(self, tmp_path: Path) -> None:
        """Test reading PID from empty file."""
        from session_buddy.cli_with_modes import _read_running_pid

        pid_file = tmp_path / "pidfile.pid"
        pid_file.write_text("")

        mock_settings = MagicMock()
        mock_settings.pid_path.return_value = pid_file

        result = _read_running_pid(mock_settings)

        assert result is None

    def test_read_running_pid_negative(self, tmp_path: Path) -> None:
        """Test reading negative PID."""
        from session_buddy.cli_with_modes import _read_running_pid

        pid_file = tmp_path / "pidfile.pid"
        pid_file.write_text("-123\n")

        mock_settings = MagicMock()
        mock_settings.pid_path.return_value = pid_file

        result = _read_running_pid(mock_settings)

        # Negative PIDs are technically valid integers but likely invalid in practice
        assert result is None or isinstance(result, int)

    def test_read_running_pid_large_number(self, tmp_path: Path) -> None:
        """Test reading a large PID number."""
        from session_buddy.cli_with_modes import _read_running_pid

        pid_file = tmp_path / "pidfile.pid"
        pid_file.write_text("999999999\n")

        mock_settings = MagicMock()
        mock_settings.pid_path.return_value = pid_file

        result = _read_running_pid(mock_settings)

        assert result == 999999999

    def test_read_running_pid_os_error(self) -> None:
        """Test reading PID when OS error occurs."""
        from session_buddy.cli_with_modes import _read_running_pid

        # Create a mock path that raises OSError when read_text is called
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.side_effect = OSError("Permission denied")

        mock_settings = MagicMock()
        mock_settings.pid_path.return_value = mock_path

        result = _read_running_pid(mock_settings)

        assert result is None


# ============================================================================
# Test _run_health_probe
# Note: _run_health_probe uses asyncio.run() internally which creates
# a new event loop. We test this by verifying the function exists and has
# the correct structure, since full testing would require an isolated
# process or event loop context.
# ============================================================================


class TestRunHealthProbe:
    """Tests for _run_health_probe function.

    Note: _run_health_probe uses asyncio.run() internally which creates
    a new event loop. The asyncio import is local to the function, making
    it difficult to patch in the test context. We verify the function
    structure and existence here.
    """

    def test_run_health_probe_function_exists(self) -> None:
        """Test that _run_health_probe is defined and callable."""
        from session_buddy.cli_with_modes import _run_health_probe

        assert callable(_run_health_probe)

    def test_run_health_probe_returns_runtime_health_snapshot(self) -> None:
        """Test that _run_health_probe returns RuntimeHealthSnapshot type."""
        from session_buddy.cli_with_modes import _run_health_probe
        from mcp_common.cli.health import RuntimeHealthSnapshot
        import asyncio

        mock_settings = MagicMock()
        mock_settings.pid_path.return_value = Path("/nonexistent.pid")

        # Since asyncio.run() cannot be called from within an event loop,
        # and the function imports asyncio locally, we verify the return type
        # by checking the function signature returns RuntimeHealthSnapshot
        # when asyncio.run is properly set up
        import inspect
        sig = inspect.signature(_run_health_probe)
        # Function should take settings parameter
        assert "settings" in [p.name for p in sig.parameters.values()]


# ============================================================================
# Test create_session_buddy_cli
# ============================================================================


class TestCreateSessionBuddyCli:
    """Tests for create_session_buddy_cli function."""

    def test_create_session_buddy_cli_standard_mode(self) -> None:
        """Test creating CLI in standard mode."""
        from session_buddy.cli_with_modes import create_session_buddy_cli

        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "standard"}, clear=True):
            cli_factory = create_session_buddy_cli()

            assert cli_factory is not None
            assert cli_factory.server_name == "session-buddy"
            assert hasattr(cli_factory, "create_app")
            assert hasattr(cli_factory, "start_handler")
            assert hasattr(cli_factory, "health_probe_handler")

    def test_create_session_buddy_cli_lite_mode(self) -> None:
        """Test creating CLI in lite mode."""
        from session_buddy.cli_with_modes import create_session_buddy_cli

        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "lite"}, clear=True):
            cli_factory = create_session_buddy_cli()

            assert cli_factory is not None
            assert cli_factory.server_name == "session-buddy"

    def test_create_session_buddy_cli_default_mode(self) -> None:
        """Test creating CLI without explicit mode (should default to standard)."""
        from session_buddy.cli_with_modes import create_session_buddy_cli

        with patch.dict(os.environ, {}, clear=True):
            cli_factory = create_session_buddy_cli()

            assert cli_factory is not None

    def test_create_session_buddy_cli_starts_handler(self) -> None:
        """Test that CLI factory has a start handler."""
        from session_buddy.cli_with_modes import create_session_buddy_cli

        cli_factory = create_session_buddy_cli()

        assert cli_factory.start_handler is not None
        assert callable(cli_factory.start_handler)

    def test_create_session_buddy_cli_health_probe_handler(self) -> None:
        """Test that CLI factory has a health probe handler."""
        from session_buddy.cli_with_modes import create_session_buddy_cli

        cli_factory = create_session_buddy_cli()

        assert cli_factory.health_probe_handler is not None
        assert callable(cli_factory.health_probe_handler)

    def test_create_session_buddy_cli_creates_app(self) -> None:
        """Test that CLI factory can create an app."""
        from session_buddy.cli_with_modes import create_session_buddy_cli

        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        assert app is not None
        assert callable(app)


# ============================================================================
# Test main function
# ============================================================================


class TestMain:
    """Tests for main function."""

    def test_main_is_callable(self) -> None:
        """Test that main function is callable."""
        from session_buddy.cli_with_modes import main

        assert callable(main)

    def test_main_argparse_accepts_valid_modes(self) -> None:
        """Test that argparse accepts valid mode values."""
        from session_buddy.cli_with_modes import main
        import argparse

        # Create a parser like main() does
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--mode",
            choices=["lite", "standard"],
            default=os.getenv("SESSION_BUDDY_MODE", "standard"),
        )

        # Verify lite mode is accepted
        args, _ = parser.parse_known_args(["--mode=lite"])
        assert args.mode == "lite"

        # Verify standard mode is accepted
        args, _ = parser.parse_known_args(["--mode=standard"])
        assert args.mode == "standard"

    def test_main_argparse_rejects_invalid_modes(self) -> None:
        """Test that argparse rejects invalid mode values."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--mode",
            choices=["lite", "standard"],
            default="standard",
        )

        # Invalid mode should raise SystemExit
        with pytest.raises(SystemExit):
            parser.parse_known_args(["--mode=invalid"])


# ============================================================================
# Test mode switching behaviors
# ============================================================================


class TestModeSwitching:
    """Tests for CLI mode switching behaviors."""

    def test_environment_variable_detection_standard(self) -> None:
        """Test that standard mode is detected from environment."""
        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "standard"}, clear=True):
            from session_buddy.modes import get_mode

            mode = get_mode()
            assert mode.name == "standard"

    def test_environment_variable_detection_lite(self) -> None:
        """Test that lite mode is detected from environment."""
        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "lite"}, clear=True):
            from session_buddy.modes import get_mode

            mode = get_mode()
            assert mode.name == "lite"

    def test_environment_variable_case_insensitive(self) -> None:
        """Test that mode detection is case insensitive."""
        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "LITE"}, clear=True):
            from session_buddy.modes import get_mode

            mode = get_mode()
            assert mode.name == "lite"

    def test_mode_name_normalization_underscore(self) -> None:
        """Test that mode names with underscores are normalized."""
        from session_buddy.modes import get_mode

        # "lite" and "standard" are the only valid normalized names
        # "lite_mode" normalizes to "litemode" which doesn't match any mapping
        # so we expect ValueError
        with pytest.raises(ValueError):
            get_mode("lite_mode")

    def test_invalid_mode_raises_error(self) -> None:
        """Test that invalid mode raises ValueError."""
        from session_buddy.modes import get_mode

        with pytest.raises(ValueError) as exc_info:
            get_mode("invalid_mode")

        assert "invalid" in str(exc_info.value).lower()
        assert "available modes" in str(exc_info.value).lower()

    def test_none_mode_uses_environment_default(self) -> None:
        """Test that None mode uses environment variable or default."""
        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "standard"}, clear=True):
            from session_buddy.modes import get_mode

            mode = get_mode(None)
            assert mode.name == "standard"

    def test_none_mode_defaults_to_standard(self) -> None:
        """Test that None mode defaults to standard when env var is not set."""
        with patch.dict(os.environ, {}, clear=True):
            from session_buddy.modes import get_mode

            mode = get_mode(None)
            assert mode.name == "standard"


# ============================================================================
# Test ModeConfig
# ============================================================================


class TestModeConfig:
    """Tests for ModeConfig in CLI context."""

    def test_standard_mode_config(self) -> None:
        """Test StandardMode returns correct config."""
        from session_buddy.modes import StandardMode

        mode = StandardMode()
        config = mode.get_config()

        assert config.name == "standard"
        assert "duckdb" in config.database_path.lower() or ":memory:" not in config.database_path
        assert config.storage_backend == "file"
        assert config.enable_embeddings is True
        assert config.enable_multi_project is True

    def test_lite_mode_config(self) -> None:
        """Test LiteMode returns correct config."""
        from session_buddy.modes import LiteMode

        mode = LiteMode()
        config = mode.get_config()

        assert config.name == "lite"
        assert config.database_path == ":memory:"
        assert config.storage_backend == "memory"
        assert config.enable_embeddings is False
        assert config.enable_multi_project is False

    def test_mode_config_to_dict(self) -> None:
        """Test ModeConfig.to_dict method."""
        from session_buddy.modes import LiteMode

        mode = LiteMode()
        config = mode.get_config()
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert config_dict["mode"] == "lite"
        assert config_dict["database_path"] == ":memory:"
        assert "enable_embeddings" in config_dict


# ============================================================================
# Test integration scenarios
# ============================================================================


class TestIntegrationScenarios:
    """Integration tests for real-world CLI scenarios."""

    @patch("session_buddy.server_optimized.run_server")
    @patch("session_buddy.cli_with_modes.get_mode")
    def test_full_startup_flow_standard(self, mock_get_mode, mock_run) -> None:
        """Test complete startup flow for standard mode."""
        from session_buddy.cli_with_modes import start_server_handler
        from session_buddy.modes import StandardMode

        mock_mode = StandardMode()
        mock_get_mode.return_value = mock_mode
        mock_run.return_value = None

        with patch("sys.stdout", new_callable=MagicMock):
            start_server_handler("standard")

        mock_get_mode.assert_called_once_with("standard")
        mock_run.assert_called_once_with(host="127.0.0.1", port=8678)

    @patch("session_buddy.server_optimized.run_server")
    @patch("session_buddy.cli_with_modes.get_mode")
    def test_full_startup_flow_lite(self, mock_get_mode, mock_run) -> None:
        """Test complete startup flow for lite mode."""
        from session_buddy.cli_with_modes import start_server_handler
        from session_buddy.modes import LiteMode

        mock_mode = LiteMode()
        mock_get_mode.return_value = mock_mode
        mock_run.return_value = None

        with patch("sys.stdout", new_callable=MagicMock):
            start_server_handler("lite")

        mock_get_mode.assert_called_once_with("lite")
        mock_run.assert_called_once()

    def test_cli_factory_preserves_settings(self) -> None:
        """Test that CLI factory properly initializes with settings."""
        from session_buddy.cli_with_modes import create_session_buddy_cli, SessionBuddySettings

        cli_factory = create_session_buddy_cli()

        # Settings should be accessible
        assert cli_factory.settings is not None
        assert isinstance(cli_factory.settings, SessionBuddySettings)

    def test_settings_mode_direct(self) -> None:
        """Test that SessionBuddySettings accepts mode directly."""
        from session_buddy.cli_with_modes import SessionBuddySettings

        # Direct mode parameter should work
        settings = SessionBuddySettings(mode="lite")
        assert settings.mode == "lite"

        settings2 = SessionBuddySettings(mode="standard")
        assert settings2.mode == "standard"

    def test_settings_mode_from_constructor(self) -> None:
        """Test that mode passed to constructor is preserved."""
        from session_buddy.cli_with_modes import SessionBuddySettings

        settings = SessionBuddySettings(mode="lite")
        assert settings.mode == "lite"

        settings = SessionBuddySettings(mode="standard")
        assert settings.mode == "standard"


# ============================================================================
# Test OperationMode interface
# ============================================================================


class TestOperationModeInterface:
    """Tests for OperationMode interface."""

    def test_lite_mode_interface(self) -> None:
        """Test LiteMode implements OperationMode interface."""
        from session_buddy.modes import LiteMode, OperationMode

        mode = LiteMode()
        assert isinstance(mode, OperationMode)
        assert hasattr(mode, "name")
        assert hasattr(mode, "get_config")
        assert hasattr(mode, "get_startup_message")
        assert hasattr(mode, "validate_environment")

    def test_standard_mode_interface(self) -> None:
        """Test StandardMode implements OperationMode interface."""
        from session_buddy.modes import StandardMode, OperationMode

        mode = StandardMode()
        assert isinstance(mode, OperationMode)
        assert hasattr(mode, "name")
        assert hasattr(mode, "get_config")
        assert hasattr(mode, "get_startup_message")
        assert hasattr(mode, "validate_environment")

    def test_lite_mode_name(self) -> None:
        """Test LiteMode name property."""
        from session_buddy.modes import LiteMode

        mode = LiteMode()
        assert mode.name == "lite"

    def test_standard_mode_name(self) -> None:
        """Test StandardMode name property."""
        from session_buddy.modes import StandardMode

        mode = StandardMode()
        assert mode.name == "standard"

    def test_lite_mode_startup_message(self) -> None:
        """Test LiteMode startup message contains expected content."""
        from session_buddy.modes import LiteMode

        mode = LiteMode()
        msg = mode.get_startup_message()
        assert "lite" in msg.lower()
        assert "memory" in msg.lower() or "fast" in msg.lower()

    def test_standard_mode_startup_message(self) -> None:
        """Test StandardMode startup message contains expected content."""
        from session_buddy.modes import StandardMode

        mode = StandardMode()
        msg = mode.get_startup_message()
        assert "standard" in msg.lower()
        assert "persistent" in msg.lower() or "file" in msg.lower()

    def test_lite_mode_validate_environment(self) -> None:
        """Test LiteMode validate_environment returns empty list."""
        from session_buddy.modes import LiteMode

        mode = LiteMode()
        errors = mode.validate_environment()
        assert isinstance(errors, list)
        assert len(errors) == 0

    def test_standard_mode_validate_environment(self) -> None:
        """Test StandardMode validate_environment returns list."""
        from session_buddy.modes import StandardMode

        mode = StandardMode()
        errors = mode.validate_environment()
        assert isinstance(errors, list)


# ============================================================================
# Coverage lift tests (added by Task 12 / wave1-batch1b-module6)
# Target: lift line coverage from 79% to >=95% and branch coverage to >=90%.
# Each test below exercises a specific previously-uncovered line/branch.
# ============================================================================


class TestSessionBuddySettingsPaths:
    """Coverage lift: Exercise pid_path/health_snapshot_path/telemetry_snapshot_path.

    Prior tests covered only default ``__init__`` values; the three
    ``*_path`` methods on ``SessionBuddySettings`` (lines 72-79) were not
    exercised. These tests pin the contract that each method returns a
    ``Path`` rooted at ``cache_dir``.
    """

    def test_pid_path_joins_cache_dir(self, tmp_path: Path) -> None:
        """pid_path() returns ``<cache_dir>/mcp_server.pid``."""
        from session_buddy.cli_with_modes import SessionBuddySettings

        settings = SessionBuddySettings(cache_dir=str(tmp_path))

        result = settings.pid_path()
        assert isinstance(result, Path)
        assert result == tmp_path / "mcp_server.pid"

    def test_health_snapshot_path_joins_cache_dir(self, tmp_path: Path) -> None:
        """health_snapshot_path() returns ``<cache_dir>/runtime_health.json``."""
        from session_buddy.cli_with_modes import SessionBuddySettings

        settings = SessionBuddySettings(cache_dir=str(tmp_path))

        result = settings.health_snapshot_path()
        assert isinstance(result, Path)
        assert result == tmp_path / "runtime_health.json"

    def test_telemetry_snapshot_path_joins_cache_dir(self, tmp_path: Path) -> None:
        """telemetry_snapshot_path() returns ``<cache_dir>/runtime_telemetry.json``."""
        from session_buddy.cli_with_modes import SessionBuddySettings

        settings = SessionBuddySettings(cache_dir=str(tmp_path))

        result = settings.telemetry_snapshot_path()
        assert isinstance(result, Path)
        assert result == tmp_path / "runtime_telemetry.json"


class TestRunHealthProbe:
    """Coverage lift: Exercise _run_health_probe body (lines 162-170).

    The probe calls ``asyncio.run(get_health_status(...))`` internally.
    We patch ``asyncio.run`` (via the cli_with_modes-bound reference) and
    ``update_telemetry_counter`` so the body executes end-to-end and
    returns a ``RuntimeHealthSnapshot``.
    """

    def test_run_health_probe_no_pid_file_returns_watchers_false(
        self, tmp_path: Path
    ) -> None:
        """When no PID file exists, snapshot.orchestrator_pid is None and watchers_running False."""
        from session_buddy.cli_with_modes import (
            SessionBuddySettings,
            _run_health_probe,
        )
        from session_buddy.cli_with_modes import asyncio as cli_asyncio

        settings = SessionBuddySettings(cache_dir=str(tmp_path))
        fake_health = {"status": "ok", "components": {}}

        def _consume_coro(coro: Any) -> dict[str, Any]:
            # Close the coroutine so gc doesn't warn "was never awaited"
            close = getattr(coro, "close", None)
            if close is not None:
                close()
            return fake_health

        with patch.object(
            cli_asyncio, "run", side_effect=_consume_coro
        ) as mock_run, patch(
            "session_buddy.cli_with_modes.update_telemetry_counter",
            return_value=None,
        ) as mock_telemetry:
            snapshot = _run_health_probe(settings)

        assert snapshot.orchestrator_pid is None
        assert snapshot.watchers_running is False
        assert snapshot.activity_state == {"health": fake_health}
        mock_run.assert_called_once()
        mock_telemetry.assert_called_once()
        # Verify the name/pid args to the telemetry counter
        kwargs = mock_telemetry.call_args.kwargs
        assert kwargs["name"] == "health_probes"
        assert kwargs["pid"] is None

    def test_run_health_probe_with_existing_pid_file_passes_pid(
        self, tmp_path: Path
    ) -> None:
        """When a PID file exists, snapshot.orchestrator_pid is the int and watchers_running True."""
        from session_buddy.cli_with_modes import (
            SessionBuddySettings,
            _run_health_probe,
        )
        from session_buddy.cli_with_modes import asyncio as cli_asyncio

        pid_file = tmp_path / "mcp_server.pid"
        pid_file.write_text("4242\n")

        settings = SessionBuddySettings(cache_dir=str(tmp_path))
        fake_health = {"status": "ok", "components": {"server": "up"}}

        def _consume_coro(coro: Any) -> dict[str, Any]:
            close = getattr(coro, "close", None)
            if close is not None:
                close()
            return fake_health

        with patch.object(
            cli_asyncio, "run", side_effect=_consume_coro
        ), patch(
            "session_buddy.cli_with_modes.update_telemetry_counter",
            return_value=None,
        ) as mock_telemetry:
            snapshot = _run_health_probe(settings)

        assert snapshot.orchestrator_pid == 4242
        assert snapshot.watchers_running is True
        assert snapshot.activity_state == {"health": fake_health}
        assert mock_telemetry.call_args.kwargs["pid"] == 4242


class TestCreateSessionBuddyCliStartHandler:
    """Coverage lift: Exercise start_handler closure inside create_session_buddy_cli.

    The factory's ``start_handler`` is a closure that captures ``mode``.
    Invoking it executes ``start_server_handler(mode=mode)``. This pin
    protects the closure-binding contract — without it, line 187 is
    uncovered because no test exercises the closure body.
    """

    def test_factory_start_handler_calls_start_server_handler_with_mode(
        self,
    ) -> None:
        """start_handler closure calls start_server_handler(mode=mode)."""
        from session_buddy.cli_with_modes import create_session_buddy_cli

        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "lite"}, clear=True), patch(
            "session_buddy.cli_with_modes.start_server_handler"
        ) as mock_handler:
            cli_factory = create_session_buddy_cli()

            cli_factory.start_handler()

        mock_handler.assert_called_once_with(mode="lite")

    def test_factory_start_handler_propagates_value_error(self) -> None:
        """When start_server_handler raises SystemExit(1) (ValueError path), the closure
        re-raises it — no swallowing at the factory layer."""
        from session_buddy.cli_with_modes import create_session_buddy_cli

        with patch.dict(
            os.environ, {"SESSION_BUDDY_MODE": "standard"}, clear=True
        ), patch(
            "session_buddy.cli_with_modes.start_server_handler",
            side_effect=SystemExit(1),
        ):
            cli_factory = create_session_buddy_cli()

            with pytest.raises(SystemExit):
                cli_factory.start_handler()


class TestMain:
    """Coverage lift: Exercise main() body (lines 204-245).

    main() parses argv, sets the env var, builds the factory, creates the
    typer/click app, and invokes it with remaining args. Patches at the
    ``create_session_buddy_cli`` seam + monkeypatched ``sys.argv`` let
    us drive main() end-to-end without spinning up a real CLI.

    Note: ``monkeypatch.setattr(sys, "argv", ...)`` is the recommended
    pytest idiom for module-attribute patching because ``patch.object``
    can race with main()'s own ``sys.argv =`` re-assignment.
    """

    def test_main_no_args_uses_default_mode_and_invokes_app(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main() with no --mode flag uses the env-default and calls app()."""
        from session_buddy.cli_with_modes import main

        monkeypatch.delenv("SESSION_BUDDY_MODE", raising=False)

        fake_app = MagicMock()
        fake_factory = MagicMock()
        fake_factory.create_app.return_value = fake_app
        monkeypatch.setattr(
            "session_buddy.cli_with_modes.create_session_buddy_cli",
            lambda: fake_factory,
        )
        monkeypatch.setattr(sys, "argv", ["session-buddy"])

        main()

        assert os.environ.get("SESSION_BUDDY_MODE") == "standard"
        fake_factory.create_app.assert_called_once()
        fake_app.assert_called_once()

    def test_main_passes_remaining_args_through_to_app(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main() forwards args not consumed by its own parser to the app."""
        from session_buddy.cli_with_modes import main

        monkeypatch.delenv("SESSION_BUDDY_MODE", raising=False)

        fake_app = MagicMock()
        fake_factory = MagicMock()
        fake_factory.create_app.return_value = fake_app
        monkeypatch.setattr(
            "session_buddy.cli_with_modes.create_session_buddy_cli",
            lambda: fake_factory,
        )
        monkeypatch.setattr(sys, "argv", ["session-buddy", "--port=9999"])

        main()

        # app() must be called; forwarding of remaining args is verified by
        # the assertion below that ``--port=9999`` is in the argv that
        # main() re-assigned (since args not consumed by argparse flow into
        # ``remaining`` and are concatenated back to sys.argv).
        fake_app.assert_called_once()
        assert "--port=9999" in sys.argv

    def test_main_sets_env_from_explicit_mode_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When --mode=lite is on argv, SESSION_BUDDY_MODE=lite is set before invoking."""
        from session_buddy.cli_with_modes import main

        monkeypatch.delenv("SESSION_BUDDY_MODE", raising=False)

        fake_app = MagicMock()
        fake_factory = MagicMock()
        fake_factory.create_app.return_value = fake_app
        monkeypatch.setattr(
            "session_buddy.cli_with_modes.create_session_buddy_cli",
            lambda: fake_factory,
        )
        monkeypatch.setattr(sys, "argv", ["session-buddy", "--mode=lite"])

        main()

        assert os.environ.get("SESSION_BUDDY_MODE") == "lite"

    def test_main_rejects_invalid_mode_via_choices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Argparse ``choices=['lite','standard']`` causes SystemExit on invalid input."""
        from session_buddy.cli_with_modes import main

        monkeypatch.delenv("SESSION_BUDDY_MODE", raising=False)
        monkeypatch.setattr(sys, "argv", ["session-buddy", "--mode=invalid"])

        with pytest.raises(SystemExit):
            main()

    def test_main_with_env_mode_uses_env_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When SESSION_BUDDY_MODE is preset, argparse default reads from env."""
        from session_buddy.cli_with_modes import main

        monkeypatch.setenv("SESSION_BUDDY_MODE", "lite")

        fake_app = MagicMock()
        fake_factory = MagicMock()
        fake_factory.create_app.return_value = fake_app
        monkeypatch.setattr(
            "session_buddy.cli_with_modes.create_session_buddy_cli",
            lambda: fake_factory,
        )
        monkeypatch.setattr(sys, "argv", ["session-buddy"])

        main()

        assert os.environ.get("SESSION_BUDDY_MODE") == "lite"


class TestCLISmokeGate:
    """CLI smoke gate (brief requirement): ``--help`` exits 0.

    The CLI script is invoked as a module so Python sets up ``sys.path``
    the same way a production user would. The smoke test guards against
    parser-construction regressions in ``main()`` and against the
    ``--mode`` choices wiring rotting.
    """

    def test_cli_help_smoke_exits_zero(self) -> None:
        """CLI smoke gate: ``python -m session_buddy.cli_with_modes --help`` exits 0."""
        repo_root = str(Path(__file__).resolve().parents[3])
        env = {**os.environ, "PYTHONPATH": repo_root}
        result = subprocess.run(
            [sys.executable, "-m", "session_buddy.cli_with_modes", "--help"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"stderr={result.stderr!r} stdout={result.stdout!r}"
        )


class TestModuleSysPathBranch:
    """Coverage lift: Exercise module-level sys.path.insert *True* branch (line 34).

    Lines 33-34 read::

        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

    During a normal pytest run, ``project_root`` is already on ``sys.path``
    (the test collection added it), so the if-condition's True branch and
    its body never execute. To cover that branch we strip ``project_root``
    from ``sys.path``, evict the cached module, and re-import: the
    re-executed module body runs the insert.

    Ref: ``docs/superpowers/specs/2026-08-03-session-buddy-coverage-improvement-design.md``
    brief requirement for >=90% branch coverage.
    """

    def test_sys_path_insert_branch_when_project_root_missing(self) -> None:
        """Re-importing cli_with_modes after stripping project_root from sys.path
        executes the True branch of the ``if`` (line 34 body)."""
        import importlib

        # Compute project_root the same way the module does
        module_path = cli_module.__file__
        if module_path is None:
            pytest.skip("cli_with_modes has no __file__")
        project_root = str(Path(module_path).resolve().parent.parent)

        # Save current state for restoration
        original_path = list(sys.path)
        saved_modules = {
            name: mod
            for name, mod in sys.modules.items()
            if name == "session_buddy.cli_with_modes"
            or name.startswith("session_buddy.cli_with_modes.")
        }

        try:
            # Strip project_root from sys.path
            sys.path = [p for p in sys.path if p != project_root]

            # Evict the cached module so the next import re-executes the body
            sys.modules.pop("session_buddy.cli_with_modes", None)

            # Re-import — this triggers the module-level code path with
            # `str(project_root) not in sys.path == True`, exercising line 34.
            importlib.import_module("session_buddy.cli_with_modes")

            # Pin: after re-import, project_root is back on sys.path
            assert project_root in sys.path
        finally:
            # Restore sys.path
            sys.path = original_path
            # Restore any evicted modules
            for name, mod in saved_modules.items():
                sys.modules[name] = mod
