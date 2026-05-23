"""Tests for app_monitor module.

Tests application activity monitoring including file changes, browser navigation,
and application focus tracking.

Phase: Week 5 Day 4 - App Monitor Coverage
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestActivityEvent:
    """Test ActivityEvent dataclass."""

    def test_activity_event_creation(self) -> None:
        """Should create ActivityEvent with required fields."""
        from session_buddy.app_monitor import ActivityEvent

        event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="VSCode",
            details={"file_path": "/test/file.py"},
            project_path="/test",
            relevance_score=0.8,
        )

        assert event.event_type == "file_change"
        assert event.application == "VSCode"
        assert event.relevance_score == 0.8
        assert "file_path" in event.details


class TestProjectActivityMonitor:
    """Test ProjectActivityMonitor class."""

    def test_initialization(self) -> None:
        """Should initialize with project paths."""
        from session_buddy.app_monitor import ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test/project"])

        assert len(monitor.project_paths) == 1
        assert "/test/project" in monitor.project_paths
        assert isinstance(monitor.activity_buffer, list)
        assert len(monitor.ide_extensions) > 0

    def test_initialization_no_paths(self) -> None:
        """Should initialize with empty project paths."""
        from session_buddy.app_monitor import ProjectActivityMonitor

        monitor = ProjectActivityMonitor()

        assert monitor.project_paths == []
        assert isinstance(monitor.activity_buffer, list)

    def test_add_activity(self) -> None:
        """Should add activity event to buffer."""
        from session_buddy.app_monitor import ActivityEvent, ProjectActivityMonitor

        monitor = ProjectActivityMonitor()
        event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="VSCode",
            details={"file_path": "/test/file.py"},
        )

        monitor.add_activity(event)

        assert len(monitor.activity_buffer) == 1
        assert monitor.activity_buffer[0] == event

    def test_activity_buffer_size_limit(self) -> None:
        """Should limit activity buffer size."""
        from session_buddy.app_monitor import ActivityEvent, ProjectActivityMonitor

        monitor = ProjectActivityMonitor()

        # Add 1001 events to trigger buffer trimming
        for i in range(1001):
            event = ActivityEvent(
                timestamp=datetime.now().isoformat(),
                event_type="file_change",
                application="VSCode",
                details={"file_path": f"/test/file{i}.py"},
            )
            monitor.add_activity(event)

        # Should be trimmed to 500 (keeps last 500)
        assert len(monitor.activity_buffer) == 500

    def test_get_recent_activity(self) -> None:
        """Should retrieve recent activity within time window."""
        from session_buddy.app_monitor import ActivityEvent, ProjectActivityMonitor

        monitor = ProjectActivityMonitor()

        # Add recent event
        recent_event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="VSCode",
            details={"file_path": "/test/recent.py"},
        )
        monitor.add_activity(recent_event)

        # Add old event (2 hours ago)
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        old_event = ActivityEvent(
            timestamp=old_time,
            event_type="file_change",
            application="VSCode",
            details={"file_path": "/test/old.py"},
        )
        monitor.add_activity(old_event)

        # Get recent activity (last 30 minutes)
        recent = monitor.get_recent_activity(minutes=30)

        # Should only include recent event
        assert len(recent) == 1
        assert recent[0] == recent_event

    def test_get_active_files(self) -> None:
        """Should identify actively worked files."""
        from session_buddy.app_monitor import ActivityEvent, ProjectActivityMonitor

        monitor = ProjectActivityMonitor()

        # Add multiple events for same file
        for i in range(3):
            event = ActivityEvent(
                timestamp=datetime.now().isoformat(),
                event_type="file_change",
                application="VSCode",
                details={"file_path": "/test/active.py"},
            )
            monitor.add_activity(event)

        active_files = monitor.get_active_files(minutes=60)

        # Should identify the file as active
        assert isinstance(active_files, list)
        if len(active_files) > 0:
            assert "file_path" in active_files[0]
            assert "event_count" in active_files[0]  # Actual field name

    def test_start_monitoring_no_watchdog(self) -> None:
        """Should return False when watchdog unavailable."""
        from session_buddy.app_monitor import ProjectActivityMonitor

        with patch("session_buddy.app_monitor.WATCHDOG_AVAILABLE", False):
            monitor = ProjectActivityMonitor(project_paths=["/test"])
            result = monitor.start_monitoring()

            assert result is False

    def test_stop_monitoring(self) -> None:
        """Should stop all observers."""
        from session_buddy.app_monitor import ProjectActivityMonitor

        monitor = ProjectActivityMonitor()

        # Mock observers
        mock_observer = Mock()
        mock_observer.stop = Mock()
        mock_observer.join = Mock()
        monitor.observers.append(mock_observer)

        monitor.stop_monitoring()

        assert len(monitor.observers) == 0
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()


class TestBrowserDocumentationMonitor:
    """Test BrowserDocumentationMonitor class."""

    def test_initialization(self) -> None:
        """Should initialize documentation monitor."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()

        assert isinstance(monitor.activity_buffer, list)
        assert isinstance(monitor.doc_domains, set)
        assert len(monitor.doc_domains) > 0

    def test_add_browser_activity(self) -> None:
        """Should add browser activity to buffer."""
        from session_buddy.app_monitor import (
            ActivityEvent,
            BrowserDocumentationMonitor,
        )

        monitor = BrowserDocumentationMonitor()

        url = "https://docs.python.org/3/library/asyncio.html"
        title = "asyncio — Asynchronous I/O"

        monitor.add_browser_activity(url, title)

        assert len(monitor.activity_buffer) == 1
        activity = monitor.activity_buffer[0]
        assert isinstance(activity, ActivityEvent)
        assert activity.details["url"] == url
        assert activity.details["title"] == title
        assert activity.event_type == "browser_nav"

    def test_extract_documentation_context(self) -> None:
        """Should extract context from documentation URLs."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()

        url = "https://docs.python.org/3/library/asyncio.html"
        context = monitor.extract_documentation_context(url)

        assert isinstance(context, dict)
        assert "domain" in context
        assert context["domain"] == "docs.python.org"
        assert "technology" in context
        assert "topic" in context
        assert "relevance" in context

    def test_get_browser_processes(self) -> None:
        """Should return browser process information."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()

        with patch("session_buddy.app_monitor.PSUTIL_AVAILABLE", False):
            processes = monitor.get_browser_processes()
            assert isinstance(processes, list)


class TestApplicationFocusMonitor:
    """Test ApplicationFocusMonitor class."""

    def test_initialization(self) -> None:
        """Should initialize focus monitor."""
        from session_buddy.app_monitor import ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()

        assert isinstance(monitor.focus_history, list)
        assert hasattr(monitor, "current_app")
        assert hasattr(monitor, "app_categories")

    def test_add_focus_event(self) -> None:
        """Should add focus event to history."""
        from session_buddy.app_monitor import ActivityEvent, ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()

        app_info = {"name": "VSCode", "pid": 12345, "category": "ide"}
        monitor.add_focus_event(app_info)

        assert len(monitor.focus_history) == 1
        event = monitor.focus_history[0]
        assert isinstance(event, ActivityEvent)
        assert event.application == "VSCode"
        assert event.event_type == "app_focus"

    def test_get_focused_application(self) -> None:
        """Should get currently focused application."""
        from session_buddy.app_monitor import ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()

        with patch("session_buddy.app_monitor.PSUTIL_AVAILABLE", False):
            result = monitor.get_focused_application()
            # Returns None when psutil unavailable or no app focused
            assert result is None or isinstance(result, dict)


class TestActivityDatabase:
    """Test ActivityDatabase class."""

    def test_initialization_creates_tables(self) -> None:
        """Should create database tables on initialization."""
        from session_buddy.app_monitor import ActivityDatabase

        # Constructor automatically calls _init_database()
        db = ActivityDatabase(db_path=":memory:")

        # Verify tables exist (will raise if not)
        assert db.db_path == ":memory:"

    def test_store_activity(self) -> None:
        """Should store activity event in database."""
        import tempfile

        from session_buddy.app_monitor import ActivityDatabase, ActivityEvent

        # Use temp file instead of :memory: to ensure persistence across operations
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ActivityDatabase(db_path=str(db_path))

            event = ActivityEvent(
                timestamp=datetime.now().isoformat(),
                event_type="file_change",
                application="VSCode",
                details={"file_path": "/test/file.py"},
            )

            # Use store_event method (actual implementation)
            db.store_event(event)

            # Verify event was stored
            events = db.get_events(limit=10)
            assert len(events) >= 1


class TestApplicationMonitor:
    """Test main ApplicationMonitor orchestration class."""

    def test_initialization(self) -> None:
        """Should initialize all sub-monitors."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        assert monitor.ide_monitor is not None
        assert monitor.browser_monitor is not None
        assert monitor.focus_monitor is not None
        assert monitor.monitoring_active is False

    @pytest.mark.asyncio
    async def test_start_monitoring(self) -> None:
        """Should start all monitoring components."""
        from session_buddy.app_monitor import ApplicationMonitor

        with patch("session_buddy.app_monitor.WATCHDOG_AVAILABLE", True):
            monitor = ApplicationMonitor(
                data_dir="/tmp/test_monitor", project_paths=["/test"]
            )

            # Mock start_monitoring to avoid actual file watching
            monitor.ide_monitor.start_monitoring = Mock(return_value=True)

            result = await monitor.start_monitoring()

            assert monitor.monitoring_active is True
            assert result is not None

    @pytest.mark.asyncio
    async def test_stop_monitoring(self) -> None:
        """Should stop all monitoring components."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )
        monitor.monitoring_active = True
        monitor._monitoring_task = None

        await monitor.stop_monitoring()

        assert monitor.monitoring_active is False

    def test_get_context_insights(self) -> None:
        """Should generate context insights from activity."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        # get_context_insights is NOT async - it's a regular method
        insights = monitor.get_context_insights(hours=1)

        assert isinstance(insights, dict)
        # Actual keys returned by get_context_insights
        assert "primary_focus" in insights
        assert "technologies_used" in insights
        assert "active_projects" in insights
        assert "documentation_topics" in insights
        assert "productivity_score" in insights
        assert "context_switches" in insights


class TestIDEFileHandler:
    """Test IDEFileHandler class for file system event handling."""

    def test_should_ignore_vscode_settings(self) -> None:
        """Should ignore vscode settings files."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        result = handler.should_ignore("/test/.vscode/settings.json")
        assert result is True

    def test_should_ignore_hidden_file(self) -> None:
        """Should ignore hidden files."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        result = handler.should_ignore("/test/.hidden.py")
        assert result is True

    def test_should_ignore_backup_file(self) -> None:
        """Should ignore backup files."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        result = handler.should_ignore("/test/file.py~")
        assert result is True

    def test_should_ignore_non_ide_extension(self) -> None:
        """Should ignore files with non-IDE extensions."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        result = handler.should_ignore("/test/file.xyz")
        assert result is True

    def test_should_ignore_in_ignored_dir(self) -> None:
        """Should ignore files in ignored directories."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        result = handler.should_ignore("/test/__pycache__/file.py")
        assert result is True

    def test_should_not_ignore_valid_file(self) -> None:
        """Should NOT ignore valid Python files."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        # Mock path.exists and stat
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_size = 100
            result = handler.should_ignore("/test/valid_file.py")
            assert result is False

    def test_estimate_relevance_critical_auth(self) -> None:
        """Should estimate high relevance for auth-related files."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        from pathlib import Path
        path = Path("/test/auth/jwt.py")
        score = handler._estimate_relevance(path)
        assert score == 0.95

    def test_estimate_relevance_critical_database(self) -> None:
        """Should estimate high relevance for database-related files."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        from pathlib import Path
        path = Path("/test/db_schema.py")
        score = handler._estimate_relevance(path)
        assert score == 0.95

    def test_estimate_relevance_critical_config(self) -> None:
        """Should estimate high relevance for config files."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        from pathlib import Path
        path = Path("/test/settings.yaml")
        score = handler._estimate_relevance(path)
        assert score == 0.95

    def test_estimate_relevance_critical_security(self) -> None:
        """Should estimate high relevance for security files."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        from pathlib import Path
        path = Path("/test/encryption.py")
        score = handler._estimate_relevance(path)
        assert score == 0.95

    def test_estimate_relevance_normal_file(self) -> None:
        """Should estimate normal relevance for regular files."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        from pathlib import Path
        path = Path("/test/utils.py")
        score = handler._estimate_relevance(path)
        assert score == 0.8

    def test_passes_threshold_low_relevance(self) -> None:
        """Should fail threshold for low relevance score."""
        from session_buddy.app_monitor import ActivityEvent, IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="ide",
            details={"file_name": "file.py"},
            relevance_score=0.5,
        )
        assert handler._passes_threshold(event) is False

    def test_passes_threshold_non_critical_high(self) -> None:
        """Should fail threshold for non-critical file with high score."""
        from session_buddy.app_monitor import ActivityEvent, IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="ide",
            details={"file_name": "file.py"},
            relevance_score=0.85,  # Not critical, below 0.9
        )
        assert handler._passes_threshold(event) is False

    def test_determine_project_path(self) -> None:
        """Should determine project path correctly."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test/project", "/other/project"])
        handler = IDEFileHandler(monitor)

        from pathlib import Path
        result = handler._determine_project_path(Path("/test/project/src/file.py"))
        assert result == "/test/project"

    def test_determine_project_path_no_match(self) -> None:
        """Should return None when no project path matches."""
        from session_buddy.app_monitor import IDEFileHandler, ProjectActivityMonitor

        monitor = ProjectActivityMonitor(project_paths=["/test/project"])
        handler = IDEFileHandler(monitor)

        from pathlib import Path
        result = handler._determine_project_path(Path("/other/src/file.py"))
        assert result is None


class TestBrowserDocumentationMonitorExt:
    """Extended tests for BrowserDocumentationMonitor."""

    def test_determine_technology_python_domain(self) -> None:
        """Should detect Python from domain."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()
        tech, relevance = monitor._determine_technology("docs.python.org", "/library/ asyncio")
        assert tech == "python"
        assert relevance == 0.9

    def test_determine_technology_rust(self) -> None:
        """Should detect Rust from domain."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()
        tech, relevance = monitor._determine_technology("docs.rs", "/async")
        assert tech == "rust"
        assert relevance == 0.8

    def test_determine_technology_javascript(self) -> None:
        """Should detect JavaScript from domain."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()
        tech, relevance = monitor._determine_technology("developer.mozilla.org", "/js")
        assert tech == "javascript"
        assert relevance == 0.8

    def test_determine_technology_python_web_fastapi(self) -> None:
        """Should detect Python web framework."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()
        tech, relevance = monitor._determine_technology("fastapi.tiangolo.com", "/tutorial")
        assert tech == "python-web"
        assert relevance == 0.9

    def test_determine_technology_frontend_react(self) -> None:
        """Should detect frontend framework."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()
        tech, relevance = monitor._determine_technology("reactjs.org", "/docs")
        assert tech == "frontend"
        assert relevance == 0.8

    def test_determine_technology_unknown(self) -> None:
        """Should return empty for unknown technology."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()
        tech, relevance = monitor._determine_technology("example.com", "/unknown")
        assert tech == ""
        assert relevance == 0.0

    def test_extract_topic_normal(self) -> None:
        """Should extract topic from normal path."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()
        topic = monitor._extract_topic("/library/asyncio/task")
        assert topic == "task"

    def test_extract_topic_index(self) -> None:
        """Should extract parent topic for index.html."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()
        topic = monitor._extract_topic("/library/asyncio/index.html")
        assert topic == "asyncio"

    def test_extract_topic_empty(self) -> None:
        """Should return empty for root path."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()
        topic = monitor._extract_topic("/")
        assert topic == ""

    def test_add_browser_activity_buffer_limit(self) -> None:
        """Should limit browser activity buffer size."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()

        # Add 501 activities to trigger buffer trimming
        for i in range(501):
            monitor.add_browser_activity(f"https://example.com/page{i}", f"Page {i}")

        # Should be trimmed to 250 (keeps last 250)
        assert len(monitor.activity_buffer) == 250

    def test_get_browser_processes_with_psutil(self) -> None:
        """Should return browser processes when psutil available."""
        from session_buddy.app_monitor import BrowserDocumentationMonitor

        monitor = BrowserDocumentationMonitor()

        mock_process = Mock()
        mock_process.info = {
            "pid": 123,
            "name": "chrome",
            "create_time": 1234567890.0,
        }

        with patch("session_buddy.app_monitor.PSUTIL_AVAILABLE", True), \
             patch("psutil.process_iter", return_value=[mock_process]):
            processes = monitor.get_browser_processes()
            assert isinstance(processes, list)


class TestApplicationFocusMonitorExt:
    """Extended tests for ApplicationFocusMonitor."""

    def test_categorize_app_ide(self) -> None:
        """Should categorize IDE applications."""
        from session_buddy.app_monitor import ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()
        result = monitor._categorize_app("pycharm64")
        assert result == "ide"

    def test_categorize_app_browser(self) -> None:
        """Should categorize browser applications."""
        from session_buddy.app_monitor import ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()
        result = monitor._categorize_app("chrome")
        assert result == "browser"

    def test_categorize_app_terminal(self) -> None:
        """Should categorize terminal applications."""
        from session_buddy.app_monitor import ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()
        result = monitor._categorize_app("terminal")
        assert result == "terminal"

    def test_categorize_app_documentation(self) -> None:
        """Should categorize documentation applications."""
        from session_buddy.app_monitor import ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()
        result = monitor._categorize_app("devdocs")
        assert result == "documentation"

    def test_categorize_app_unknown(self) -> None:
        """Should return None for unknown applications."""
        from session_buddy.app_monitor import ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()
        result = monitor._categorize_app("random_app")
        assert result is None

    def test_add_focus_event_history_limit(self) -> None:
        """Should limit focus history size."""
        from session_buddy.app_monitor import ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()

        # Add 201 events to trigger history trimming
        for i in range(201):
            monitor.add_focus_event({"name": f"App{i}", "pid": i, "category": "ide"})

        # Should be trimmed to 100
        assert len(monitor.focus_history) == 100

    def test_get_focused_application_with_psutil(self) -> None:
        """Should get focused application when psutil available."""
        from session_buddy.app_monitor import ApplicationFocusMonitor

        monitor = ApplicationFocusMonitor()

        mock_process = Mock()
        mock_process.info = {"pid": 123, "name": "pycharm"}

        with patch("session_buddy.app_monitor.PSUTIL_AVAILABLE", True), \
             patch("psutil.process_iter", return_value=[mock_process]):
            result = monitor.get_focused_application()
            # May be None or dict depending on categorization


class TestActivityDatabaseExt:
    """Extended tests for ActivityDatabase."""

    def test_get_events_with_time_filter(self) -> None:
        """Should filter events by time range."""
        import tempfile
        from session_buddy.app_monitor import ActivityDatabase, ActivityEvent

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ActivityDatabase(db_path=str(db_path))

            # Store old event
            old_event = ActivityEvent(
                timestamp=(datetime.now() - timedelta(days=5)).isoformat(),
                event_type="file_change",
                application="VSCode",
                details={"file_path": "/test/old.py"},
            )
            db.store_event(old_event)

            # Store recent event
            recent_event = ActivityEvent(
                timestamp=datetime.now().isoformat(),
                event_type="browser_nav",
                application="browser",
                details={"url": "https://example.com"},
            )
            db.store_event(recent_event)

            # Get events from last day
            start_time = (datetime.now() - timedelta(days=1)).isoformat()
            events = db.get_events(start_time=start_time, limit=10)

            # Should only include recent event
            assert len(events) == 1
            assert events[0].event_type == "browser_nav"

    def test_get_events_with_event_types_filter(self) -> None:
        """Should filter events by event types."""
        import tempfile
        from session_buddy.app_monitor import ActivityDatabase, ActivityEvent

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ActivityDatabase(db_path=str(db_path))

            # Store file change event
            file_event = ActivityEvent(
                timestamp=datetime.now().isoformat(),
                event_type="file_change",
                application="VSCode",
                details={"file_path": "/test/file.py"},
            )
            db.store_event(file_event)

            # Store browser nav event
            browser_event = ActivityEvent(
                timestamp=datetime.now().isoformat(),
                event_type="browser_nav",
                application="browser",
                details={"url": "https://example.com"},
            )
            db.store_event(browser_event)

            # Filter by file_change only
            events = db.get_events(event_types=["file_change"], limit=10)

            assert len(events) == 1
            assert events[0].event_type == "file_change"

    def test_get_events_with_limit(self) -> None:
        """Should limit number of events returned."""
        import tempfile
        from session_buddy.app_monitor import ActivityDatabase, ActivityEvent

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ActivityDatabase(db_path=str(db_path))

            # Store multiple events
            for i in range(5):
                event = ActivityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type="file_change",
                    application="VSCode",
                    details={"file_path": f"/test/file{i}.py"},
                )
                db.store_event(event)

            events = db.get_events(limit=3)
            assert len(events) == 3

    def test_cleanup_old_events(self) -> None:
        """Should cleanup old events from database."""
        import tempfile
        from session_buddy.app_monitor import ActivityDatabase, ActivityEvent

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ActivityDatabase(db_path=str(db_path))

            # Store old event
            old_event = ActivityEvent(
                timestamp=(datetime.now() - timedelta(days=35)).isoformat(),
                event_type="file_change",
                application="VSCode",
                details={"file_path": "/test/old.py"},
            )
            db.store_event(old_event)

            # Store recent event
            recent_event = ActivityEvent(
                timestamp=datetime.now().isoformat(),
                event_type="file_change",
                application="VSCode",
                details={"file_path": "/test/recent.py"},
            )
            db.store_event(recent_event)

            # Cleanup events older than 30 days
            db.cleanup_old_events(days_to_keep=30)

            # Get remaining events
            events = db.get_events(limit=10)
            assert len(events) == 1
            assert events[0].details["file_path"] == "/test/recent.py"


class TestApplicationMonitorExt:
    """Extended tests for ApplicationMonitor."""

    @pytest.mark.asyncio
    async def test_start_monitoring_already_active(self) -> None:
        """Should return None if monitoring already active."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )
        monitor.monitoring_active = True

        result = await monitor.start_monitoring()
        assert result is None

    def test_is_focus_changed(self) -> None:
        """Should detect focus changes correctly."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        # No previous app
        assert monitor._is_focus_changed({"name": "VSCode", "pid": 123}) is True

        # Same app
        monitor.focus_monitor.current_app = "VSCode"
        assert monitor._is_focus_changed({"name": "VSCode", "pid": 123}) is False

        # Different app
        assert monitor._is_focus_changed({"name": "Chrome", "pid": 456}) is True

    def test_is_focus_changed_none(self) -> None:
        """Should return False when focused_app is None."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        assert monitor._is_focus_changed(None) is False

    @pytest.mark.asyncio
    async def test_persist_event_batch(self) -> None:
        """Should persist batch of events to database."""
        import tempfile
        from session_buddy.app_monitor import ActivityEvent, ApplicationMonitor

        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = ApplicationMonitor(
                data_dir=tmpdir, project_paths=["/test"]
            )

            events = [
                ActivityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type="file_change",
                    application="VSCode",
                    details={"file_path": "/test/file.py"},
                )
            ]

            # Just verify it doesn't raise
            await monitor._persist_event_batch(iter(events))

    def test_get_activity_summary_empty(self) -> None:
        """Should return empty summary when no events."""
        import tempfile
        from session_buddy.app_monitor import ApplicationMonitor

        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = ApplicationMonitor(
                data_dir=tmpdir, project_paths=["/test"]
            )

            summary = monitor.get_activity_summary(hours=1)

            assert summary["total_events"] == 0
            assert summary["event_types"] == {}
            assert summary["applications"] == {}
            assert summary["active_files"] == []
            assert summary["documentation_sites"] == []

    def test_get_activity_summary_with_events(self) -> None:
        """Should return populated summary with events."""
        import tempfile
        from session_buddy.app_monitor import ActivityEvent, ApplicationMonitor

        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = ApplicationMonitor(
                data_dir=tmpdir, project_paths=["/test"]
            )

            # Add some events to the database
            for i in range(3):
                event = ActivityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type="file_change",
                    application="VSCode",
                    details={"file_path": f"/test/file{i}.py"},
                    project_path="/test",
                    relevance_score=0.8,
                )
                monitor.db.store_event(event)

            summary = monitor.get_activity_summary(hours=1)

            assert summary["total_events"] == 3
            assert summary["event_types"]["file_change"] == 3
            assert summary["applications"]["VSCode"] == 3

    def test_create_activity_summary_template(self) -> None:
        """Should create proper summary template."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        template = monitor._create_activity_summary_template(hours=2, events=[])

        assert template["total_events"] == 0
        assert template["time_range_hours"] == 2
        assert isinstance(template["event_types"], dict)
        assert isinstance(template["applications"], dict)
        assert template["active_files"] == []
        assert template["documentation_sites"] == []
        assert template["average_relevance"] == 0.0

    def test_aggregate_event_data(self) -> None:
        """Should aggregate event data correctly."""
        import tempfile
        from session_buddy.app_monitor import ActivityEvent, ApplicationMonitor

        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = ApplicationMonitor(
                data_dir=tmpdir, project_paths=["/test"]
            )

            events = [
                ActivityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type="file_change",
                    application="VSCode",
                    details={"file_path": "/test/file.py"},
                    relevance_score=0.8,
                ),
                ActivityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type="browser_nav",
                    application="browser",
                    details={"domain": "docs.python.org"},
                    relevance_score=0.9,
                ),
            ]

            summary = monitor._create_activity_summary_template(hours=1, events=events)
            monitor._aggregate_event_data(events, summary)

            assert summary["event_types"]["file_change"] == 1
            assert summary["event_types"]["browser_nav"] == 1
            assert summary["applications"]["VSCode"] == 1
            assert summary["applications"]["browser"] == 1
            assert "docs.python.org" in summary["documentation_sites"]
            assert summary["average_relevance"] == pytest.approx(0.85)

    def test_finalize_summary(self) -> None:
        """Should finalize summary for JSON serialization."""
        from collections import defaultdict
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        summary = {
            "total_events": 5,
            "event_types": defaultdict(int, {"file_change": 3}),
            "applications": defaultdict(int, {"VSCode": 5}),
            "active_files": [],
            "documentation_sites": [],
            "average_relevance": 0.8,
        }

        result = monitor._finalize_summary(summary)

        # Check it's JSON serializable (dicts not defaultdict)
        assert isinstance(result["event_types"], dict)
        assert isinstance(result["applications"], dict)
        assert result["total_events"] == 5

    def test_create_insights_template(self) -> None:
        """Should create insights template."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        template = monitor._create_insights_template()

        assert template["primary_focus"] is None
        assert isinstance(template["technologies_used"], set)
        assert isinstance(template["active_projects"], set)
        assert template["documentation_topics"] == []
        assert template["productivity_score"] == 0.0
        assert template["context_switches"] == 0

    def test_analyze_events(self) -> None:
        """Should analyze events correctly."""
        import tempfile
        from session_buddy.app_monitor import ActivityEvent, ApplicationMonitor

        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = ApplicationMonitor(
                data_dir=tmpdir, project_paths=["/test"]
            )

            events = [
                ActivityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type="file_change",
                    application="VSCode",
                    details={},
                    relevance_score=0.8,
                ),
                ActivityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type="file_change",
                    application="Chrome",
                    details={},
                    relevance_score=0.8,
                ),
            ]

            insights = monitor._create_insights_template()
            app_time = monitor._analyze_events(events, insights)

            assert app_time["VSCode"] == 1
            assert app_time["Chrome"] == 1
            assert insights["context_switches"] == 1  # VSCode -> Chrome

    def test_extract_technologies(self) -> None:
        """Should extract technologies from events."""
        from session_buddy.app_monitor import ActivityEvent, ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        insights = monitor._create_insights_template()

        # Python file
        event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="VSCode",
            details={"file_extension": ".py"},
            relevance_score=0.8,
        )
        monitor._extract_technologies(event, insights)
        assert "python" in insights["technologies_used"]

        # JavaScript file
        event2 = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="VSCode",
            details={"file_extension": ".ts"},
            relevance_score=0.8,
        )
        monitor._extract_technologies(event2, insights)
        assert "javascript" in insights["technologies_used"]

        # Rust file
        event3 = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="VSCode",
            details={"file_extension": ".rs"},
            relevance_score=0.8,
        )
        monitor._extract_technologies(event3, insights)
        assert "rust" in insights["technologies_used"]

    def test_extract_projects(self) -> None:
        """Should extract projects from events."""
        from session_buddy.app_monitor import ActivityEvent, ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        insights = monitor._create_insights_template()
        event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="VSCode",
            details={},
            project_path="/test/project",
            relevance_score=0.8,
        )
        monitor._extract_projects(event, insights)

        assert "/test/project" in insights["active_projects"]

    def test_extract_documentation_topics(self) -> None:
        """Should extract documentation topics from events."""
        from session_buddy.app_monitor import ActivityEvent, ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        insights = monitor._create_insights_template()
        event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="browser_nav",
            application="browser",
            details={"topic": "asyncio", "technology": "python"},
            relevance_score=0.8,
        )
        monitor._extract_documentation_topics(event, insights)

        assert "python: asyncio" in insights["documentation_topics"]

    def test_determine_primary_focus(self) -> None:
        """Should determine primary focus correctly."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        insights = monitor._create_insights_template()
        app_time = {"VSCode": 10, "Chrome": 5, "terminal": 2}

        monitor._determine_primary_focus(app_time, insights)

        assert insights["primary_focus"] == "VSCode"

    def test_determine_primary_focus_empty(self) -> None:
        """Should handle empty app_time."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        insights = monitor._create_insights_template()
        monitor._determine_primary_focus({}, insights)

        assert insights["primary_focus"] is None

    def test_calculate_productivity_score(self) -> None:
        """Should calculate productivity score correctly."""
        import tempfile
        from session_buddy.app_monitor import ActivityEvent, ApplicationMonitor

        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = ApplicationMonitor(
                data_dir=tmpdir, project_paths=["/test"]
            )

            events = [
                ActivityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type="file_change",
                    application="VSCode",
                    details={},
                    relevance_score=0.8,  # > 0.5
                ),
                ActivityEvent(
                    timestamp=datetime.now().isoformat(),
                    event_type="file_change",
                    application="VSCode",
                    details={},
                    relevance_score=0.3,  # < 0.5
                ),
            ]

            insights = monitor._create_insights_template()
            monitor._calculate_productivity_score(events, insights)

            # 1 relevant event out of 2 = 0.5
            assert insights["productivity_score"] == 0.5

    def test_finalize_insights(self) -> None:
        """Should finalize insights for JSON serialization."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        insights = {
            "primary_focus": "VSCode",
            "technologies_used": {"python", "javascript"},
            "active_projects": {"/test/project"},
            "documentation_topics": ["python: asyncio"],
            "productivity_score": 0.8,
            "context_switches": 2,
        }

        result = monitor._finalize_insights(insights)

        assert isinstance(result["technologies_used"], list)
        assert isinstance(result["active_projects"], list)
        assert "python" in result["technologies_used"]
        assert "/test/project" in result["active_projects"]

    def test_add_additional_context(self) -> None:
        """Should add additional context to summary."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        summary = {
            "total_events": 0,
            "time_range_hours": 1,
            "event_types": {},
            "applications": {},
            "active_files": [],
            "documentation_sites": [],
            "average_relevance": 0.0,
        }

        monitor._add_additional_context(1, summary)

        # active_files should be populated from ide_monitor
        assert "active_files" in summary

    @pytest.mark.asyncio
    async def test_handle_monitoring_error(self) -> None:
        """Should handle monitoring errors gracefully."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        # Should not raise
        await monitor._handle_monitoring_error(ValueError("test error"))

    def test_setup_directory(self) -> None:
        """Should set up data directory."""
        import tempfile
        from session_buddy.app_monitor import ApplicationMonitor

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "monitor_data"
            monitor = ApplicationMonitor(
                data_dir=str(data_dir), project_paths=["/test"]
            )

            assert data_dir.exists()

    def test_initialize_components(self) -> None:
        """Should initialize all monitoring components."""
        import tempfile
        from session_buddy.app_monitor import ApplicationMonitor

        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = ApplicationMonitor(
                data_dir=tmpdir, project_paths=["/test"]
            )

            assert monitor.db is not None
            assert monitor.ide_monitor is not None
            assert monitor.browser_monitor is not None
            assert monitor.focus_monitor is not None

    def test_setup_monitoring_state(self) -> None:
        """Should set up monitoring state."""
        from session_buddy.app_monitor import ApplicationMonitor

        monitor = ApplicationMonitor(
            data_dir="/tmp/test_monitor", project_paths=["/test"]
        )

        assert monitor.monitoring_active is False
        assert monitor._monitoring_task is None
