"""Extra coverage tests for app_monitor uncovered branches.

Targets branches reported as missing in the coverage report:
- get_active_files recency boost
- should_ignore size threshold
- on_modified handler + _create_activity_event
- _recently_processed_persisted
- psutil exception paths in get_browser_processes / get_focused_application
- empty events in get_context_insights
"""

from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from session_buddy.app_monitor import (
    ActivityDatabase,
    ActivityEvent,
    ApplicationFocusMonitor,
    ApplicationMonitor,
    BrowserDocumentationMonitor,
    IDEFileHandler,
    ProjectActivityMonitor,
)


def _make_event(
    file_path: str,
    *,
    timestamp: str | None = None,
    project_path: str | None = None,
    relevance: float = 0.8,
) -> ActivityEvent:
    """Build a file_change ActivityEvent for testing."""
    return ActivityEvent(
        timestamp=timestamp or datetime.now().isoformat(),
        event_type="file_change",
        application="ide",
        details={"file_path": file_path, "file_name": Path(file_path).name,
                 "file_extension": Path(file_path).suffix},
        project_path=project_path,
        relevance_score=relevance,
    )


class TestGetActiveFilesRecencyBoost:
    """Cover the < 300 second recency boost branch."""

    def test_recent_file_gets_score_boost(self) -> None:
        monitor = ProjectActivityMonitor()
        monitor.add_activity(_make_event("/test/recent.py"))

        active = monitor.get_active_files(minutes=60)
        assert len(active) == 1
        # 1 event, doubled to 2 because timestamp is fresh
        assert active[0]["activity_score"] == 2
        assert active[0]["event_count"] == 1
        assert active[0]["file_path"] == "/test/recent.py"


class TestShouldIgnoreSize:
    """Cover the path.stat() > max_size branch in should_ignore."""

    def test_ignores_oversize_file(self) -> None:
        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        big_file = Path(tempfile.gettempdir()) / "sessionbuddy_big_test.py"
        big_file.write_text("x")
        try:
            # Force stat to report huge size
            fake_stat = Mock(st_size=10 * 1024 * 1024 * 1024)
            with patch.object(Path, "exists", return_value=True), \
                 patch.object(Path, "is_file", return_value=True), \
                 patch.object(Path, "stat", return_value=fake_stat):
                assert handler.should_ignore(str(big_file)) is True
        finally:
            big_file.unlink(missing_ok=True)


class TestOnModifiedHandler:
    """Cover the IDEFileHandler.on_modified code path."""

    def test_on_modified_creates_activity_event(self) -> None:
        monitor = ProjectActivityMonitor(project_paths=["/proj"])
        handler = IDEFileHandler(monitor)

        event = Mock()
        event.is_directory = False
        event.src_path = "/proj/src/app.py"

        handler.on_modified(event)

        assert len(monitor.activity_buffer) == 1
        created = monitor.activity_buffer[0]
        assert created.event_type == "file_change"
        assert created.application == "ide"
        assert created.details["file_path"] == "/proj/src/app.py"
        assert created.project_path == "/proj"

    def test_on_modified_skips_directory_event(self) -> None:
        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        event = Mock()
        event.is_directory = True
        event.src_path = "/test/some_dir"

        handler.on_modified(event)

        assert len(monitor.activity_buffer) == 0

    def test_on_modified_skips_ignored_file(self) -> None:
        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        event = Mock()
        event.is_directory = False
        event.src_path = "/test/.vscode/settings.json"

        handler.on_modified(event)

        assert len(monitor.activity_buffer) == 0


class TestCreateActivityEvent:
    """Cover the _create_activity_event helper directly."""

    def test_create_activity_event_fields(self) -> None:
        monitor = ProjectActivityMonitor(project_paths=["/proj"])
        handler = IDEFileHandler(monitor)

        evt = handler._create_activity_event(Path("/proj/main.py"), "/proj")
        assert evt.event_type == "file_change"
        assert evt.application == "ide"
        assert evt.details["file_name"] == "main.py"
        assert evt.details["file_extension"] == ".py"
        assert evt.details["change_type"] == "modified"
        assert evt.project_path == "/proj"
        # Non-critical file -> default 0.8 relevance
        assert evt.relevance_score == 0.8


class TestRecentlyProcessedPersisted:
    """Cover the SQLite dedupe path in _recently_processed_persisted."""

    def test_returns_false_for_fresh_path(self) -> None:
        monitor = ProjectActivityMonitor(project_paths=["/test"])
        # Point at a temp db so we don't touch the real one
        with tempfile.TemporaryDirectory() as tmp:
            monitor.db_path = str(Path(tmp) / "fresh.db")
            handler = IDEFileHandler(monitor)

            first = handler._recently_processed_persisted("/test/a.py")
            second = handler._recently_processed_persisted("/test/a.py")

            assert first is False
            # Second call within TTL must report True
            assert second is True

    def test_returns_false_on_sqlite_error(self) -> None:
        monitor = ProjectActivityMonitor(project_paths=["/test"])
        handler = IDEFileHandler(monitor)

        with patch("sqlite3.connect", side_effect=RuntimeError("boom")):
            assert handler._recently_processed_persisted("/test/b.py") is False


class TestPsutilExceptionPaths:
    """Cover the (psutil.NoSuchProcess, psutil.AccessDenied) except branches."""

    def test_get_browser_processes_swallows_access_denied(self) -> None:
        monitor = BrowserDocumentationMonitor()

        # Import here so the test only fails if psutil is genuinely missing
        import psutil

        with patch("session_buddy.app_monitor.PSUTIL_AVAILABLE", True), \
             patch("psutil.process_iter", side_effect=psutil.AccessDenied(pid=1)):
            assert monitor.get_browser_processes() == []

    def test_get_focused_application_swallows_no_such_process(self) -> None:
        focus = ApplicationFocusMonitor()

        import psutil

        with patch("session_buddy.app_monitor.PSUTIL_AVAILABLE", True), \
             patch("psutil.process_iter", side_effect=psutil.NoSuchProcess(pid=1)):
            assert focus.get_focused_application() is None


class TestContextInsightsEmpty:
    """Cover the `if not events: return insights` branch."""

    def test_get_context_insights_empty_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitor = ApplicationMonitor(data_dir=tmp, project_paths=["/test"])
            insights = monitor.get_context_insights(hours=1)

            # The early-return for empty events returns the raw template,
            # which uses sets (not lists) — callers must finalize themselves.
            assert insights == {
                "primary_focus": None,
                "technologies_used": set(),
                "active_projects": set(),
                "documentation_topics": [],
                "productivity_score": 0.0,
                "context_switches": 0,
            }


class TestGetEventsWithEndTime:
    """Cover the `if end_time:` branch in ActivityDatabase.get_events."""

    def test_filters_by_end_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = ActivityDatabase(db_path=str(Path(tmp) / "test.db"))
            old = ActivityEvent(
                timestamp="2020-01-01T00:00:00",
                event_type="file_change",
                application="VSCode",
                details={"file_path": "/x.py"},
            )
            new = ActivityEvent(
                timestamp=datetime.now().isoformat(),
                event_type="file_change",
                application="VSCode",
                details={"file_path": "/y.py"},
            )
            db.store_event(old)
            db.store_event(new)

            cutoff = "2021-01-01T00:00:00"
            events = db.get_events(end_time=cutoff, limit=10)
            # Only the old event is older than cutoff
            assert len(events) == 1
            assert events[0].details["file_path"] == "/x.py"
