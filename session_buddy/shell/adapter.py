"""Session-Buddy admin shell adapter."""

import asyncio
import logging

from oneiric.shell import AdminShell, ShellConfig
from oneiric.shell.session_tracker import SessionEventEmitter

from ..core.session_manager import SessionLifecycleManager

logger = logging.getLogger(__name__)


class SessionBuddyShell(AdminShell):
    """Session-Buddy-specific admin shell.

    Extends the base AdminShell with Session-Buddy-specific namespace,
    formatters, helpers, and magic commands for session management.

    Features:
    - ps(): Show all sessions
    - active(): Show active sessions
    - quality(): Show quality metrics
    - insights(limit=10): Show recent insights
    - %sessions: List all sessions
    - %session <id>: Show session details
    - Session tracking via Session-Buddy MCP (self-monitoring)
    """

    def __init__(
        self, app: SessionLifecycleManager, config: ShellConfig | None = None
    ) -> None:
        """Initialize Session-Buddy shell.

        Args:
            app: SessionLifecycleManager instance
            config: Optional shell configuration
        """
        super().__init__(app, config)
        self._add_session_buddy_namespace()

        # Override session tracker with Session-Buddy-specific metadata
        # SessionEventEmitter tracks shell sessions via Session-Buddy MCP
        # Note: Session-Buddy monitors itself (component_name="session-buddy")
        self.session_tracker = SessionEventEmitter(
            component_name="session-buddy",
        )
        self._session_id: str | None = None

    def _add_session_buddy_namespace(self) -> None:
        """Add Session-Buddy-specific objects to shell namespace."""
        self.namespace.update(
            {
                # Core classes
                "SessionLifecycleManager": SessionLifecycleManager,
                # Convenience helper functions (wrapped for async execution)
                "ps": lambda: asyncio.run(self._list_sessions()),
                "active": lambda: asyncio.run(self._list_active_sessions()),
                "quality": lambda: asyncio.run(self._show_quality_metrics()),
                "insights": lambda limit=10: asyncio.run(
                    self._show_insights(limit)
                ),
            }
        )

    async def _list_sessions(self) -> None:
        """List all sessions."""
        # Placeholder implementation - would call actual session listing
        print("Session listing not yet implemented")

    async def _list_active_sessions(self) -> None:
        """List active sessions."""
        # Placeholder implementation - would call actual active session listing
        print("Active session listing not yet implemented")

    async def _show_quality_metrics(self) -> None:
        """Show quality metrics."""
        # Placeholder implementation - would call actual quality metrics
        print("Quality metrics not yet implemented")

    async def _show_insights(self, limit: int = 10) -> None:
        """Show recent insights.

        Args:
            limit: Maximum number of insights to show
        """
        # Placeholder implementation - would call actual insights listing
        print(f"Insights listing (limit={limit}) not yet implemented")

    def _get_component_name(self) -> str | None:
        """Return Session-Buddy component name for CLI command discovery.

        Overrides base class method to enable CLI command preprocessing.

        Returns:
            Component name "session-buddy" for CLI invocation
        """
        return "session-buddy"

    def _get_component_version(self) -> str:
        """Get Session-Buddy package version.

        Overrides base class method to provide component-specific version
        for session tracking metadata.

        Returns:
            Session-Buddy version string or "unknown" if unavailable
        """
        try:
            import importlib.metadata as importlib_metadata

            return importlib_metadata.version("session-buddy")
        except Exception:
            return "unknown"

    def _get_adapters_info(self) -> list[str]:
        """Get Session-Buddy adapters (empty list - no orchestration adapters).

        Overrides base class method to provide component-specific adapter
        information for session tracking metadata.

        Session-Buddy is a session management system, not an orchestration
        engine, so it has no orchestration adapters.

        Returns:
            Empty list (Session-Buddy has no adapters)
        """
        return []

    def _get_banner(self) -> str:
        """Get Session-Buddy-specific banner."""
        version = self._get_component_version()
        cli_enabled = (
            "Enabled" if self.config.cli_preprocessing_enabled else "Disabled"
        )

        # Session tracking status (self-monitoring)
        session_tracking = "Enabled (self-monitoring)"

        return f"""
Session-Buddy Admin Shell v{version}
{"=" * 60}
Session Management & Quality Monitoring

Session Tracking: {session_tracking}
  Shell sessions tracked via Session-Buddy MCP
  Metadata: version, session count, quality metrics

CLI Commands: {cli_enabled} (no prefix required)
  start                   - Start Session-Buddy server
  stop                    - Stop Session-Buddy server
  status                  - Show server status
  health                  - Run health check

Convenience Functions:
  ps()           - List all sessions
  active()       - Show active sessions
  quality()      - Show quality metrics
  insights(n=10) - Show recent insights

Type 'help()' for Python help or %help_shell for shell commands
{"=" * 60}
"""

    async def _emit_session_start(self) -> None:
        """Emit session start event with Session-Buddy-specific metadata."""
        try:
            metadata = {
                "version": self._get_component_version(),
                "adapters": self._get_adapters_info(),
            }

            self._session_id = await self.session_tracker.emit_session_start(
                shell_type=self.__class__.__name__,
                metadata=metadata,
            )

            if self._session_id:
                logger.info(f"Session-Buddy shell session started: {self._session_id}")
            else:
                logger.debug("Session tracking unavailable (Session-Buddy MCP not reachable)")
        except Exception as e:
            logger.debug(f"Failed to emit session start: {e}")

    async def _emit_session_end(self) -> None:
        """Emit session end event."""
        if not self._session_id:
            return

        try:
            await self.session_tracker.emit_session_end(
                session_id=self._session_id,
                metadata={},
            )
            logger.info(f"Session-Buddy shell session ended: {self._session_id}")
        except Exception as e:
            logger.debug(f"Failed to emit session end: {e}")
        finally:
            self._session_id = None

    async def close(self) -> None:
        """Close shell and cleanup resources."""
        await self._emit_session_end()
        await self.session_tracker.close()
