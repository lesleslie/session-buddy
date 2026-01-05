"""Tests for app_monitor module."""

from datetime import datetime
from pathlib import Path

from session_buddy.app_monitor import ActivityEvent, ProjectActivityMonitor


def test_activity_event_creation():
    """Test ActivityEvent dataclass creation."""
    event = ActivityEvent(
        timestamp=str(datetime.now()),
        event_type="file_change",
        application="vscode",
        details={"file_path": "/test/file.py", "content": "test content"}
    )

    assert event.event_type == "file_change"
    assert event.application == "vscode"
    assert event.details["file_path"] == "/test/file.py"
    assert event.details["content"] == "test content"


def test_project_activity_monitor_initialization():
    """Test ProjectActivityMonitor initialization."""
    monitor = ProjectActivityMonitor(
        project_paths=["/test/project"]
    )

    assert monitor.project_paths == ["/test/project"]
    assert len(monitor.activity_buffer) == 0


def test_project_activity_monitor_with_none_paths():
    """Test ProjectActivityMonitor initialization with None paths."""
    monitor = ProjectActivityMonitor()

    assert monitor.project_paths == []
    assert len(monitor.activity_buffer) == 0
