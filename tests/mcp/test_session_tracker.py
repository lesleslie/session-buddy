"""Unit tests for SessionTracker class.

Tests session lifecycle event handling from admin shells via MCP tools.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.core import SessionLifecycleManager
from session_buddy.mcp.event_models import (
    EnvironmentInfo,
    SessionEndEvent,
    SessionStartEvent,
    UserInfo,
)
from session_buddy.mcp.session_tracker import SessionTracker


@pytest.fixture
def mock_lifecycle_manager():
    """Create a mock SessionLifecycleManager."""
    manager = MagicMock(spec=SessionLifecycleManager)
    manager.initialize_session = AsyncMock()
    manager.end_session = AsyncMock()
    return manager


@pytest.fixture
def session_tracker(mock_lifecycle_manager):
    """Create a SessionTracker instance with mocked lifecycle manager."""
    return SessionTracker(mock_lifecycle_manager)


@pytest.fixture
def sample_session_start_event():
    """Create a sample SessionStartEvent for testing."""
    return SessionStartEvent(
        event_version="1.0",
        event_id="550e8400-e29b-41d4-a716-446655440000",
        event_type="session_start",
        component_name="mahavishnu",
        shell_type="MahavishnuShell",
        timestamp="2026-02-06T12:34:56.789Z",
        pid=12345,
        user=UserInfo(username="john", home="/home/john"),
        hostname="server01",
        environment=EnvironmentInfo(
            python_version="3.13.0",
            platform="Linux-6.5.0-x86_64",
            cwd="/home/john/projects/mahavishnu",
        ),
    )


@pytest.fixture
def sample_session_end_event():
    """Create a sample SessionEndEvent for testing."""
    return SessionEndEvent(
        event_type="session_end",
        session_id="mahavishnu-20260206-123456",
        timestamp="2026-02-06T13:45:07.890Z",
        metadata={"exit_reason": "user_exit"},
    )


class TestSessionTrackerInitialization:
    """Tests for SessionTracker initialization."""

    def test_init_with_logger(self, mock_lifecycle_manager):
        """Test SessionTracker initialization with custom logger."""
        import logging

        custom_logger = logging.getLogger("test_logger")
        tracker = SessionTracker(mock_lifecycle_manager, logger=custom_logger)

        assert tracker.session_manager is mock_lifecycle_manager
        assert tracker.logger is custom_logger

    def test_init_without_logger(self, mock_lifecycle_manager):
        """Test SessionTracker initialization without custom logger."""
        tracker = SessionTracker(mock_lifecycle_manager)

        assert tracker.session_manager is mock_lifecycle_manager
        assert tracker.logger is not None
        assert tracker.logger.name == "session_buddy.mcp.session_tracker"

    def test_init_metrics_disabled_explicitly(self, mock_lifecycle_manager):
        """Test metrics remain disabled when explicitly requested."""
        tracker = SessionTracker(mock_lifecycle_manager, enable_metrics=False)

        assert tracker.enable_metrics is False
        assert tracker.metrics is None

    def test_init_metrics_available(self, mock_lifecycle_manager):
        """Test metrics initialization when metrics are available."""
        from session_buddy.mcp import session_tracker as tracker_module

        mock_metrics = MagicMock()
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: mock_metrics)

            tracker = SessionTracker(mock_lifecycle_manager)

        assert tracker.enable_metrics is True
        assert tracker.metrics is mock_metrics

    def test_init_metrics_disabled_when_get_metrics_fails(
        self, mock_lifecycle_manager
    ):
        """Test metrics are disabled when get_metrics raises."""
        from session_buddy.mcp import session_tracker as tracker_module

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(
                tracker_module,
                "get_metrics",
                lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            )

            tracker = SessionTracker(mock_lifecycle_manager)

        assert tracker.enable_metrics is False
        assert tracker.metrics is None


class TestHandleSessionStart:
    """Tests for handle_session_start method."""

    @pytest.mark.asyncio
    async def test_handle_session_start_success(
        self, session_tracker, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test successful session start handling."""
        # Mock successful initialization
        mock_lifecycle_manager.initialize_session.return_value = {
            "success": True,
            "project": "mahavishnu",
            "working_directory": "/home/john/projects/mahavishnu",
            "quality_score": 85,
        }

        result = await session_tracker.handle_session_start(sample_session_start_event)

        assert result.status == "tracked"
        assert result.session_id is not None
        assert result.session_id.startswith("mahavishnu-")
        assert result.error is None

        # Verify lifecycle manager was called
        mock_lifecycle_manager.initialize_session.assert_called_once_with(
            working_directory="/home/john/projects/mahavishnu",
        )

    @pytest.mark.asyncio
    async def test_handle_session_start_initialization_failure(
        self, session_tracker, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test session start handling when initialization fails."""
        # Mock failed initialization
        mock_lifecycle_manager.initialize_session.return_value = {
            "success": False,
            "error": "Directory not found",
        }

        result = await session_tracker.handle_session_start(sample_session_start_event)

        assert result.status == "error"
        assert result.session_id is None
        assert result.error == "Directory not found"

    @pytest.mark.asyncio
    async def test_handle_session_start_unknown_error(
        self, session_tracker, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test session start handling with unknown error."""
        # Mock initialization with success=False but no error message
        mock_lifecycle_manager.initialize_session.return_value = {
            "success": False,
        }

        result = await session_tracker.handle_session_start(sample_session_start_event)

        assert result.status == "error"
        assert result.session_id is None
        assert result.error == "Unknown initialization error"

    @pytest.mark.asyncio
    async def test_handle_session_start_exception_handling(
        self, session_tracker, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test session start handling when exception is raised."""
        # Mock exception
        mock_lifecycle_manager.initialize_session.side_effect = Exception(
            "Unexpected error"
        )

        result = await session_tracker.handle_session_start(sample_session_start_event)

        assert result.status == "error"
        assert result.session_id is None
        assert "Session start failed" in result.error

    @pytest.mark.asyncio
    async def test_handle_session_start_session_id_format(
        self, session_tracker, mock_lifecycle_manager
    ):
        """Test that session_id is formatted correctly."""
        # Create event with specific timestamp
        event = SessionStartEvent(
            event_version="1.0",
            event_id="550e8400-e29b-41d4-a716-446655440000",
            component_name="test-component",
            shell_type="TestShell",
            timestamp="2026-02-06T12:34:56.789Z",
            pid=12345,
            user=UserInfo(username="test", home="/home/test"),
            hostname="testhost",
            environment=EnvironmentInfo(
                python_version="3.13.0",
                platform="Linux-6.5.0-x86_64",
                cwd="/home/test/project",
            ),
        )

        mock_lifecycle_manager.initialize_session.return_value = {
            "success": True,
            "project": "test-project",
        }

        result = await session_tracker.handle_session_start(event)

        assert result.status == "tracked"
        assert result.session_id == "test-component-20260206-123456"

    @pytest.mark.asyncio
    async def test_handle_session_start_records_metrics(
        self, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test successful start records metrics and quality score."""
        from session_buddy.mcp import session_tracker as tracker_module

        mock_metrics = MagicMock()
        mock_lifecycle_manager.initialize_session.return_value = {
            "success": True,
            "quality_score": 88,
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: mock_metrics)
            tracker = SessionTracker(mock_lifecycle_manager)

        result = await tracker.handle_session_start(sample_session_start_event)

        assert result.status == "tracked"
        mock_metrics.record_session_start.assert_called_once()
        mock_metrics.set_session_quality_score.assert_called_once_with(
            component_name="mahavishnu",
            quality_score=88.0,
        )

    @pytest.mark.asyncio
    async def test_handle_session_start_without_metrics(
        self, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test successful start when metrics are disabled."""
        mock_lifecycle_manager.initialize_session.return_value = {
            "success": True,
            "quality_score": 88,
        }
        tracker = SessionTracker(mock_lifecycle_manager, enable_metrics=False)

        result = await tracker.handle_session_start(sample_session_start_event)

        assert result.status == "tracked"
        assert tracker.metrics is None

    @pytest.mark.asyncio
    async def test_handle_session_start_failure_without_metrics(
        self, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test failed start when metrics are disabled."""
        mock_lifecycle_manager.initialize_session.return_value = {
            "success": False,
            "error": "Directory not found",
        }
        tracker = SessionTracker(mock_lifecycle_manager, enable_metrics=False)

        result = await tracker.handle_session_start(sample_session_start_event)

        assert result.status == "error"
        assert result.error == "Directory not found"

    @pytest.mark.asyncio
    async def test_handle_session_start_failed_metrics_path(
        self, mock_lifecycle_manager, sample_session_start_event, caplog
    ):
        """Test failed start records error metrics."""
        import logging
        from session_buddy.mcp import session_tracker as tracker_module

        mock_metrics = MagicMock()
        mock_lifecycle_manager.initialize_session.return_value = {
            "success": False,
            "error": "Directory not found",
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: mock_metrics)
            tracker = SessionTracker(mock_lifecycle_manager)

            with caplog.at_level(logging.ERROR):
                result = await tracker.handle_session_start(sample_session_start_event)

        assert result.status == "error"
        mock_metrics.record_session_start.assert_called_once()
        mock_metrics.record_session_end.assert_called_once()
        assert mock_metrics.record_session_end.call_args.kwargs["component_name"] == "mahavishnu"
        assert mock_metrics.record_session_end.call_args.kwargs["status"] == "error"
        assert mock_metrics.record_session_end.call_args.kwargs["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_handle_session_start_failed_metrics_warning(
        self, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test failed start when metrics recording raises."""
        from session_buddy.mcp import session_tracker as tracker_module

        class FlakyMetrics:
            def record_session_start(self, **kwargs: object) -> None:
                return None

            def record_session_end(self, **kwargs: object) -> None:
                raise RuntimeError("metrics boom")

        mock_lifecycle_manager.initialize_session.return_value = {
            "success": False,
            "error": "Directory not found",
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: FlakyMetrics())
            tracker = SessionTracker(mock_lifecycle_manager)

        result = await tracker.handle_session_start(sample_session_start_event)

        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_handle_session_start_metrics_exception_is_swallowed(
        self, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test metrics errors during start are logged but do not fail the call."""
        from session_buddy.mcp import session_tracker as tracker_module

        class ExplodingMetrics:
            def record_session_start(self, **kwargs: object) -> None:
                raise RuntimeError("metrics boom")

            def record_session_end(self, **kwargs: object) -> None:
                raise RuntimeError("metrics boom")

        mock_lifecycle_manager.initialize_session.return_value = {
            "success": True,
            "quality_score": 88,
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: ExplodingMetrics())
            tracker = SessionTracker(mock_lifecycle_manager)

        result = await tracker.handle_session_start(sample_session_start_event)

        assert result.status == "tracked"

    @pytest.mark.asyncio
    async def test_handle_session_start_exception_metrics_warning(
        self, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test exception path when failure metrics recording also raises."""
        from session_buddy.mcp import session_tracker as tracker_module

        class ExplodingMetrics:
            def record_mcp_event_emit_failure(self, **kwargs: object) -> None:
                raise RuntimeError("metrics boom")

        mock_lifecycle_manager.initialize_session.side_effect = RuntimeError("Unexpected error")

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: ExplodingMetrics())
            tracker = SessionTracker(mock_lifecycle_manager)

        result = await tracker.handle_session_start(sample_session_start_event)

        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_handle_session_start_exception_without_metrics(
        self, mock_lifecycle_manager, sample_session_start_event
    ):
        """Test exception path when metrics are disabled."""
        mock_lifecycle_manager.initialize_session.side_effect = RuntimeError("Unexpected error")
        tracker = SessionTracker(mock_lifecycle_manager, enable_metrics=False)

        result = await tracker.handle_session_start(sample_session_start_event)

        assert result.status == "error"


class TestHandleSessionEnd:
    """Tests for handle_session_end method."""

    @pytest.mark.asyncio
    async def test_handle_session_end_success(
        self, session_tracker, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test successful session end handling."""
        # Mock successful session end
        mock_lifecycle_manager.end_session.return_value = {
            "success": True,
            "summary": {
                "project": "mahavishnu",
                "final_quality_score": 85,
                "working_directory": "/home/john/projects/mahavishnu",
            },
        }

        result = await session_tracker.handle_session_end(sample_session_end_event)

        assert result.status == "ended"
        assert result.session_id == "mahavishnu-20260206-123456"
        assert result.error is None

        # Verify lifecycle manager was called
        mock_lifecycle_manager.end_session.assert_called_once_with(
            working_directory=None,
        )

    @pytest.mark.asyncio
    async def test_handle_session_end_failure(
        self, session_tracker, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test session end handling when end_session fails."""
        # Mock failed session end
        mock_lifecycle_manager.end_session.return_value = {
            "success": False,
            "error": "Session not found",
        }

        result = await session_tracker.handle_session_end(sample_session_end_event)

        assert result.status == "error"
        assert result.session_id == "mahavishnu-20260206-123456"
        assert result.error == "Session not found"

    @pytest.mark.asyncio
    async def test_handle_session_end_unknown_error(
        self, session_tracker, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test session end handling with unknown error."""
        # Mock end with success=False but no error message
        mock_lifecycle_manager.end_session.return_value = {
            "success": False,
        }

        result = await session_tracker.handle_session_end(sample_session_end_event)

        assert result.status == "error"
        assert result.error == "Unknown session end error"

    @pytest.mark.asyncio
    async def test_handle_session_end_exception_handling(
        self, session_tracker, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test session end handling when exception is raised."""
        # Mock exception
        mock_lifecycle_manager.end_session.side_effect = Exception("Unexpected error")

        result = await session_tracker.handle_session_end(sample_session_end_event)

        assert result.status == "error"
        assert result.session_id == "mahavishnu-20260206-123456"
        assert "Session end failed" in result.error

    @pytest.mark.asyncio
    async def test_handle_session_end_with_summary(
        self, session_tracker, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test session end handling with summary data."""
        # Mock successful session end with summary
        mock_lifecycle_manager.end_session.return_value = {
            "success": True,
            "summary": {
                "project": "test-project",
                "final_quality_score": 90,
                "working_directory": "/home/test/project",
                "recommendations": ["Keep up the good work"],
            },
        }

        result = await session_tracker.handle_session_end(sample_session_end_event)

        assert result.status == "ended"

    @pytest.mark.asyncio
    async def test_handle_session_end_without_metrics(
        self, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test successful end when metrics are disabled."""
        mock_lifecycle_manager.end_session.return_value = {
            "success": True,
            "summary": {},
        }
        tracker = SessionTracker(mock_lifecycle_manager, enable_metrics=False)

        result = await tracker.handle_session_end(sample_session_end_event)

        assert result.status == "ended"
        assert tracker.metrics is None

    @pytest.mark.asyncio
    async def test_handle_session_end_failure_without_metrics(
        self, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test failed end when metrics are disabled."""
        mock_lifecycle_manager.end_session.return_value = {
            "success": False,
            "error": "Session not found",
        }
        tracker = SessionTracker(mock_lifecycle_manager, enable_metrics=False)

        result = await tracker.handle_session_end(sample_session_end_event)

        assert result.status == "error"
        assert result.error == "Session not found"

    @pytest.mark.asyncio
    async def test_handle_session_end_records_metrics(
        self, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test successful end records metrics and quality score."""
        from session_buddy.mcp import session_tracker as tracker_module

        mock_metrics = MagicMock()
        mock_lifecycle_manager.end_session.return_value = {
            "success": True,
            "summary": {"final_quality_score": 91},
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: mock_metrics)
            tracker = SessionTracker(mock_lifecycle_manager)

        result = await tracker.handle_session_end(sample_session_end_event)

        assert result.status == "ended"
        mock_metrics.record_session_end.assert_called_once()
        mock_metrics.set_session_quality_score.assert_called_once_with(
            component_name="mahavishnu",
            quality_score=91.0,
        )

    @pytest.mark.asyncio
    async def test_handle_session_end_metrics_warning_on_success(
        self, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test successful end when metrics recording raises."""
        from session_buddy.mcp import session_tracker as tracker_module

        class FlakyMetrics:
            def record_session_end(self, **kwargs: object) -> None:
                raise RuntimeError("metrics boom")

        mock_lifecycle_manager.end_session.return_value = {
            "success": True,
            "summary": {"final_quality_score": 91},
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: FlakyMetrics())
            tracker = SessionTracker(mock_lifecycle_manager)

        result = await tracker.handle_session_end(sample_session_end_event)

        assert result.status == "ended"

    @pytest.mark.asyncio
    async def test_handle_session_end_failure_metrics_warning(
        self, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test failure path when end-session metrics recording raises."""
        from session_buddy.mcp import session_tracker as tracker_module

        class FlakyMetrics:
            def record_session_end(self, **kwargs: object) -> None:
                raise RuntimeError("metrics boom")

        mock_lifecycle_manager.end_session.return_value = {
            "success": False,
            "error": "Session not found",
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: FlakyMetrics())
            tracker = SessionTracker(mock_lifecycle_manager)

        result = await tracker.handle_session_end(sample_session_end_event)

        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_handle_session_end_exception_metrics_path(
        self, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test exception path records failure metrics."""
        from session_buddy.mcp import session_tracker as tracker_module

        class ExplodingMetrics:
            def record_session_end(self, **kwargs: object) -> None:
                raise RuntimeError("metrics boom")

            def record_mcp_event_emit_failure(self, **kwargs: object) -> None:
                raise RuntimeError("metrics boom")

        mock_lifecycle_manager.end_session.side_effect = RuntimeError("Unexpected error")

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: ExplodingMetrics())
            tracker = SessionTracker(mock_lifecycle_manager)

        result = await tracker.handle_session_end(sample_session_end_event)

        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_handle_session_end_exception_metrics_warning(
        self, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test exception path when failure metrics recording raises."""
        from session_buddy.mcp import session_tracker as tracker_module

        class ExplodingMetrics:
            def record_mcp_event_emit_failure(self, **kwargs: object) -> None:
                raise RuntimeError("metrics boom")

        mock_lifecycle_manager.end_session.side_effect = RuntimeError("Unexpected error")

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(tracker_module, "METRICS_AVAILABLE", True)
            monkeypatch.setattr(tracker_module, "get_metrics", lambda: ExplodingMetrics())
            tracker = SessionTracker(mock_lifecycle_manager)

        result = await tracker.handle_session_end(sample_session_end_event)

        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_handle_session_end_exception_without_metrics(
        self, mock_lifecycle_manager, sample_session_end_event
    ):
        """Test exception path when metrics are disabled."""
        mock_lifecycle_manager.end_session.side_effect = RuntimeError("Unexpected error")
        tracker = SessionTracker(mock_lifecycle_manager, enable_metrics=False)

        result = await tracker.handle_session_end(sample_session_end_event)

        assert result.status == "error"


class TestIntegration:
    """Integration tests with Pydantic validation."""

    @pytest.mark.asyncio
    async def test_invalid_event_validation(self, session_tracker):
        """Test that Pydantic validates invalid events."""
        # This should fail Pydantic validation
        with pytest.raises(ValueError):
            event = SessionStartEvent(
                event_version="2.0",  # Invalid version
                event_id="not-a-uuid",  # Invalid UUID
                component_name="invalid component!",  # Invalid characters
                shell_type="TestShell",
                timestamp="invalid-timestamp",
                pid=12345,
                user=UserInfo(username="test", home="/home/test"),
                hostname="testhost",
                environment=EnvironmentInfo(
                    python_version="3.13.0",
                    platform="Linux",
                    cwd="/home/test",
                ),
            )

    @pytest.mark.asyncio
    async def test_valid_event_passes_validation(
        self, session_tracker, mock_lifecycle_manager
    ):
        """Test that valid events pass Pydantic validation."""
        # Create valid event
        event = SessionStartEvent(
            event_version="1.0",
            event_id="550e8400-e29b-41d4-a716-446655440000",
            component_name="valid-component",
            shell_type="ValidShell",
            timestamp="2026-02-06T12:34:56.789Z",
            pid=12345,
            user=UserInfo(username="test", home="/home/test"),
            hostname="testhost",
            environment=EnvironmentInfo(
                python_version="3.13.0",
                platform="Linux-6.5.0-x86_64",
                cwd="/home/test",
            ),
        )

        mock_lifecycle_manager.initialize_session.return_value = {
            "success": True,
            "project": "test",
        }

        # Should not raise validation error
        result = await session_tracker.handle_session_start(event)
        assert result.status == "tracked"


class TestLogging:
    """Tests for logging behavior."""

    @pytest.mark.asyncio
    async def test_session_start_logging(
        self,
        session_tracker,
        mock_lifecycle_manager,
        sample_session_start_event,
        caplog,
    ):
        """Test that session start is logged correctly."""
        import logging

        mock_lifecycle_manager.initialize_session.return_value = {
            "success": True,
            "project": "mahavishnu",
        }

        with caplog.at_level(logging.INFO):
            await session_tracker.handle_session_start(sample_session_start_event)

        # Check that info log was created
        assert any("Session started" in record.message for record in caplog.records)
        assert any(
            "component=mahavishnu" in record.message for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_session_end_logging(
        self,
        session_tracker,
        mock_lifecycle_manager,
        sample_session_end_event,
        caplog,
    ):
        """Test that session end is logged correctly."""
        import logging

        mock_lifecycle_manager.end_session.return_value = {
            "success": True,
            "summary": {"project": "mahavishnu"},
        }

        with caplog.at_level(logging.INFO):
            await session_tracker.handle_session_end(sample_session_end_event)

        # Check that info log was created
        assert any("Session ended" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_error_logging(
        self,
        session_tracker,
        mock_lifecycle_manager,
        sample_session_start_event,
        caplog,
    ):
        """Test that errors are logged correctly."""
        import logging

        mock_lifecycle_manager.initialize_session.return_value = {
            "success": False,
            "error": "Test error",
        }

        with caplog.at_level(logging.ERROR):
            await session_tracker.handle_session_start(sample_session_start_event)

        # Check that error log was created
        assert any("Session start failed" in record.message for record in caplog.records)
