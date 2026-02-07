"""Unit tests for Session-Buddy admin shell functionality."""

from unittest.mock import MagicMock

import pytest

from session_buddy.core.session_manager import SessionLifecycleManager
from session_buddy.shell import SessionBuddyShell


@pytest.mark.unit
class TestShellAdapter:
    """Test SessionBuddyShell adapter initialization and configuration."""

    def test_shell_initialization(self):
        """Test shell initializes with SessionLifecycleManager."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert shell.app == mock_manager
        assert "ps" in shell.namespace
        assert "active" in shell.namespace

    def test_shell_namespace_contains_helpers(self):
        """Test shell namespace includes helper functions."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        # Check namespace has required functions
        assert "ps" in shell.namespace
        assert "active" in shell.namespace
        assert "quality" in shell.namespace
        assert "insights" in shell.namespace
        assert "SessionLifecycleManager" in shell.namespace

    def test_shell_banner_contains_session_info(self):
        """Test shell banner displays session management information."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)
        banner = shell._get_banner()

        assert "Session-Buddy Admin Shell" in banner
        assert "Session Management" in banner
        assert "ps()" in banner
        assert "active()" in banner
        assert "quality()" in banner
        assert "insights" in banner

    def test_shell_helpers_are_callable(self):
        """Test shell helper functions are callable."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        # All helpers should be callable
        assert callable(shell.namespace["ps"])
        assert callable(shell.namespace["active"])
        assert callable(shell.namespace["quality"])
        assert callable(shell.namespace["insights"])


@pytest.mark.unit
class TestGetComponentName:
    """Test _get_component_name method."""

    def test_get_component_name_returns_session_buddy(self):
        """Test _get_component_name returns 'session-buddy'."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)
        component_name = shell._get_component_name()

        assert component_name == "session-buddy"

    def test_get_component_name_enables_cli_discovery(self):
        """Test _get_component_name enables CLI command discovery."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        # Component name should be set for CLI preprocessing
        component_name = shell._get_component_name()
        assert component_name is not None
        assert isinstance(component_name, str)
        assert len(component_name) > 0


@pytest.mark.unit
class TestShellHelpers:
    """Test shell helper functions."""

    def test_ps_helper_exists(self):
        """Test ps() helper exists in namespace."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert "ps" in shell.namespace
        assert callable(shell.namespace["ps"])

    def test_active_helper_exists(self):
        """Test active() helper exists in namespace."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert "active" in shell.namespace
        assert callable(shell.namespace["active"])

    def test_quality_helper_exists(self):
        """Test quality() helper exists in namespace."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert "quality" in shell.namespace
        assert callable(shell.namespace["quality"])

    def test_insights_helper_exists(self):
        """Test insights() helper exists in namespace."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert "insights" in shell.namespace
        assert callable(shell.namespace["insights"])

    def test_insights_helper_has_default_limit(self):
        """Test insights() helper has default limit parameter."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        # Helper should be callable with default limit
        insights_func = shell.namespace["insights"]
        assert callable(insights_func)
        # Should work with no arguments (uses default limit=10)
        # and with custom limit
        insights_func()
        insights_func(limit=20)


@pytest.mark.unit
class TestShellNamespace:
    """Test shell namespace composition."""

    def test_namespace_contains_app(self):
        """Test shell namespace contains app instance."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert "app" in shell.namespace
        assert shell.namespace["app"] == mock_manager

    def test_namespace_contains_asyncio(self):
        """Test shell namespace contains asyncio module."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert "asyncio" in shell.namespace
        import asyncio

        assert shell.namespace["asyncio"] == asyncio

    def test_namespace_contains_run_helper(self):
        """Test shell namespace contains run helper."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert "run" in shell.namespace
        import asyncio

        assert shell.namespace["run"] == asyncio.run

    def test_namespace_contains_logger(self):
        """Test shell namespace contains logger."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert "logger" in shell.namespace
        # Logger should be the module logger
        assert shell.namespace["logger"] is not None


@pytest.mark.unit
class TestShellIntegration:
    """Integration tests for shell components."""

    def test_shell_can_be_instantiated(self):
        """Test shell can be instantiated without errors."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        # Should not raise
        shell = SessionBuddyShell(mock_manager)

        assert shell is not None
        assert isinstance(shell, SessionBuddyShell)

    def test_shell_helper_async_wrappers(self):
        """Test shell namespace helpers wrap async functions properly."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        # Helpers should be lambda functions wrapping asyncio.run
        assert callable(shell.namespace["ps"])
        assert callable(shell.namespace["active"])
        assert callable(shell.namespace["quality"])
        assert callable(shell.namespace["insights"])

    def test_shell_with_custom_config(self):
        """Test shell initialization with custom configuration."""
        from oneiric.shell import ShellConfig

        mock_manager = MagicMock(spec=SessionLifecycleManager)
        config = ShellConfig(banner="Custom Session-Buddy Shell")

        shell = SessionBuddyShell(mock_manager, config)

        assert shell.app == mock_manager
        assert shell.config == config

    def test_shell_exposes_session_lifecycle_manager(self):
        """Test shell exposes SessionLifecycleManager class."""
        mock_manager = MagicMock(spec=SessionLifecycleManager)

        shell = SessionBuddyShell(mock_manager)

        assert "SessionLifecycleManager" in shell.namespace
        assert shell.namespace["SessionLifecycleManager"] == SessionLifecycleManager
