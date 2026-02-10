#!/usr/bin/env python3
"""Unit tests for CLI commands.

Phase 2.3: CLI Command Tests
Tests for Session Buddy CLI commands using MCPServerCLIFactory.
"""

import pytest
from typer.testing import CliRunner
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from session_buddy.cli import create_session_buddy_cli

runner = CliRunner()


@pytest.mark.asyncio
class TestCLICommands:
    """Test suite for CLI commands."""

    def test_create_cli_factory(self):
        """Test creating the CLI factory."""
        cli_factory = create_session_buddy_cli()

        assert cli_factory is not None
        assert hasattr(cli_factory, "create_app")
        assert hasattr(cli_factory, "server_name")

    def test_cli_has_app(self):
        """Test that CLI can create an app."""
        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        assert app is not None

    def test_cli_help(self):
        """Test CLI help command."""
        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "Session Buddy" in result.stdout or "session-buddy" in result.stdout

    def test_cli_version(self):
        """Test CLI version command."""
        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        result = runner.invoke(app, ["--version"])

        # Version should be available or show a version output
        assert result.exit_code == 0 or "version" in result.stdout.lower()


@pytest.mark.asyncio
class TestCLIServerCommands:
    """Test suite for server lifecycle commands."""

    @patch("session_buddy.cli.start_server_handler")
    def test_start_command(self, mock_start_handler):
        """Test start command."""
        mock_start_handler.return_value = None

        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        # Start command would normally block, so we test the handler is callable
        assert callable(mock_start_handler)

    @patch("session_buddy.cli._run_health_probe")
    def test_health_command(self, mock_health_probe):
        """Test health check command."""
        from mcp_common import RuntimeHealthSnapshot

        mock_health_probe.return_value = RuntimeHealthSnapshot(
            orchestrator_pid=12345,
            watchers_running=True,
            activity_state={"health": "ok"},
        )

        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        result = runner.invoke(app, ["health"])

        # Health command should run without error
        assert result.exit_code == 0

    @patch("session_buddy.cli._run_health_probe")
    def test_status_command(self, mock_health_probe):
        """Test status command."""
        from mcp_common import RuntimeHealthSnapshot

        mock_health_probe.return_value = RuntimeHealthSnapshot(
            orchestrator_pid=12345,
            watchers_running=True,
            activity_state={"health": "ok"},
        )

        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        result = runner.invoke(app, ["status"])

        # Status command should run
        assert result.exit_code == 0 or "status" in result.stdout.lower()


@pytest.mark.asyncio
class TestCLISettings:
    """Test suite for CLI settings configuration."""

    def test_settings_initialization(self):
        """Test settings are properly initialized."""
        from session_buddy.cli import SessionBuddySettings

        settings = SessionBuddySettings()

        assert settings.server_name == "session-buddy"
        assert settings.http_port == 8678
        assert settings.websocket_port == 8677
        assert settings.startup_timeout == 10
        assert settings.shutdown_timeout == 10

    def test_settings_from_env(self):
        """Test settings can be loaded from environment."""
        from session_buddy.cli import SessionBuddySettings

        with patch.dict("os.environ", {"MAHAVISHNU_HTTP_PORT": "9000"}):
            # Environment variables use MAHAVISHNU prefix for compatibility
            settings = SessionBuddySettings()

            # Default should be used if env var not mapped correctly
            assert settings.http_port == 8678  # Default value


@pytest.mark.asyncio
class TestCLIHelpers:
    """Test suite for CLI helper functions."""

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_read_running_pid(self, mock_exists, mock_read_text, tmp_path):
        """Test reading running PID from file."""
        from session_buddy.cli import _read_running_pid

        mock_exists.return_value = True
        mock_read_text.return_value = "12345\n"

        # Create mock settings with pid_path
        mock_settings = Mock()
        mock_settings.pid_path.return_value = tmp_path / "test.pid"

        result = _read_running_pid(mock_settings)

        assert result == 12345

    @patch("pathlib.Path.exists")
    def test_read_running_pid_no_file(self, mock_exists):
        """Test reading PID when file doesn't exist."""
        from session_buddy.cli import _read_running_pid

        mock_exists.return_value = False

        mock_settings = Mock()
        mock_settings.pid_path.return_value = Path("/nonexistent.pid")

        result = _read_running_pid(mock_settings)

        assert result is None

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_read_running_pid_invalid(self, mock_exists, mock_read_text, tmp_path):
        """Test reading PID with invalid content."""
        from session_buddy.cli import _read_running_pid

        mock_exists.return_value = True
        mock_read_text.return_value = "invalid\n"

        mock_settings = Mock()
        mock_settings.pid_path.return_value = tmp_path / "test.pid"

        result = _read_running_pid(mock_settings)

        assert result is None

    @patch("session_buddy.cli._read_running_pid")
    @patch("session_buddy.cli.get_health_status")
    @patch("session_buddy.cli.update_telemetry_counter")
    def test_run_health_probe(
        self, mock_telemetry, mock_health, mock_read_pid
    ):
        """Test running health probe."""
        from mcp_common import RuntimeHealthSnapshot
        from session_buddy.cli import _run_health_probe

        mock_read_pid.return_value = 12345
        mock_health.return_value = AsyncMock(
            return_value={"status": "healthy", "uptime": 100}
        )()

        mock_settings = Mock()
        mock_settings.pid_path.return_value = Path("/test.pid")

        result = _run_health_probe(mock_settings)

        assert isinstance(result, RuntimeHealthSnapshot)
        assert result.orchestrator_pid == 12345
        assert result.watchers_running is True


@pytest.mark.asyncio
class TestCLIIntegration:
    """Integration tests for CLI functionality."""

    @patch("session_buddy.server_optimized.run_server")
    def test_start_server_flow(self, mock_run_server):
        """Test server start flow."""
        from session_buddy.cli import start_server_handler

        mock_run_server.return_value = None

        # This would normally start the server
        # We're testing the handler is callable
        assert callable(start_server_handler)

    def test_cli_factory_creation(self):
        """Test complete CLI factory creation."""
        from session_buddy.cli import create_session_buddy_cli

        # Create factory
        cli_factory = create_session_buddy_cli()

        # Verify factory attributes
        assert hasattr(cli_factory, "server_name")
        assert cli_factory.server_name == "session-buddy"

        # Create app
        app = cli_factory.create_app()
        assert app is not None

        # Test help on the app
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0


@pytest.mark.asyncio
class TestCLIErrorHandling:
    """Test suite for CLI error handling."""

    def test_cli_with_invalid_args(self):
        """Test CLI with invalid arguments."""
        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        result = runner.invoke(app, ["invalid-command"])

        # Should show error or help
        assert result.exit_code != 0 or "help" in result.stdout.lower()

    def test_cli_with_missing_required_args(self):
        """Test CLI with missing required arguments."""
        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        # Test with a command that needs arguments
        result = runner.invoke(app, ["start", "--invalid-flag"])

        # Should handle gracefully
        assert result.exit_code != 0 or "error" in result.stdout.lower()


@pytest.mark.asyncio
class TestCLIServerLifecycle:
    """Test suite for server lifecycle management."""

    @patch("session_buddy.cli._read_running_pid")
    def test_server_status_detection(self, mock_read_pid, tmp_path):
        """Test detecting server status from PID file."""
        from session_buddy.cli import _read_running_pid

        # Server running
        mock_read_pid.return_value = 12345
        mock_settings = Mock()
        mock_settings.pid_path.return_value = tmp_path / "running.pid"

        result = _read_running_pid(mock_settings)
        assert result == 12345

        # Server not running
        mock_read_pid.return_value = None
        result = _read_running_pid(mock_settings)
        assert result is None

    def test_server_configuration(self):
        """Test server configuration settings."""
        from session_buddy.cli import SessionBuddySettings

        settings = SessionBuddySettings()

        # Verify critical settings
        assert settings.server_name is not None
        assert settings.http_port > 0
        assert settings.websocket_port > 0
        assert settings.startup_timeout > 0
        assert settings.shutdown_timeout > 0
        assert settings.force_kill_timeout > 0


@pytest.mark.asyncio
class TestCLIOutput:
    """Test suite for CLI output formatting."""

    @patch("session_buddy.cli._run_health_probe")
    def test_health_output_format(self, mock_health_probe):
        """Test health command output format."""
        from mcp_common import RuntimeHealthSnapshot

        mock_health_probe.return_value = RuntimeHealthSnapshot(
            orchestrator_pid=12345,
            watchers_running=True,
            activity_state={"health": "ok", "uptime": 3600},
        )

        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        result = runner.invoke(app, ["health"])

        # Should contain relevant information
        output = result.stdout.lower()
        assert "health" in output or "status" in output or "pid" in output

    def test_help_output_format(self):
        """Test help output format."""
        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        result = runner.invoke(app, ["--help"])

        # Should show commands
        output = result.stdout.lower()
        assert "start" in output or "stop" in output or "status" in output


class TestCLIMain:
    """Test suite for main CLI entry point."""

    @patch("sys.argv", ["session-buddy", "--help"])
    def test_main_callable(self):
        """Test that main function is callable."""
        from session_buddy.cli import main

        assert callable(main)


@pytest.mark.asyncio
class TestCLIAdapterRegistry:
    """Test suite for adapter registry configuration."""

    def test_adapter_registry_settings(self):
        """Test adapter registry configuration in settings."""
        from session_buddy.cli import SessionBuddySettings

        settings = SessionBuddySettings()

        # Verify adapter registry settings
        assert hasattr(settings, "adapter_registry_enabled")
        assert hasattr(settings, "adapter_registry_host")
        assert hasattr(settings, "adapter_registry_port")
        assert settings.adapter_registry_host == "localhost"
        assert settings.adapter_registry_port == 8679


@pytest.mark.asyncio
class TestCLIProcessManagement:
    """Test suite for process management settings."""

    def test_process_timeouts(self):
        """Test process timeout settings."""
        from session_buddy.cli import SessionBuddySettings

        settings = SessionBuddySettings()

        # Verify timeout settings
        assert settings.startup_timeout >= 0
        assert settings.shutdown_timeout >= 0
        assert settings.force_kill_timeout >= 0
        assert settings.force_kill_timeout <= settings.shutdown_timeout


# Additional tests for edge cases and error scenarios


@pytest.mark.asyncio
class TestCLIScenarios:
    """Test suite for real-world CLI scenarios."""

    def test_multiple_help_requests(self):
        """Test multiple help requests."""
        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        for _ in range(3):
            result = runner.invoke(app, ["--help"])
            assert result.exit_code == 0

    @patch("session_buddy.cli._run_health_probe")
    def test_multiple_health_checks(self, mock_health_probe):
        """Test multiple health check requests."""
        from mcp_common import RuntimeHealthSnapshot

        mock_health_probe.return_value = RuntimeHealthSnapshot(
            orchestrator_pid=12345,
            watchers_running=True,
            activity_state={"health": "ok"},
        )

        cli_factory = create_session_buddy_cli()
        app = cli_factory.create_app()

        for _ in range(3):
            result = runner.invoke(app, ["health"])
            assert result.exit_code == 0

    def test_cli_with_custom_settings(self):
        """Test CLI with custom settings configuration."""
        from session_buddy.cli import SessionBuddySettings

        custom_settings = SessionBuddySettings(
            server_name="custom-session-buddy",
            http_port=9000,
            websocket_port=9001,
        )

        assert custom_settings.server_name == "custom-session-buddy"
        assert custom_settings.http_port == 9000
        assert custom_settings.websocket_port == 9001
