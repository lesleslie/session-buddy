from __future__ import annotations

import typing as t
from pathlib import Path

from session_buddy.app_monitor import (
    ActivityEvent,
    IDEFileHandler,
    ProjectActivityMonitor,
)


def test_should_ignore_large_file(tmp_path: t.Any, monkeypatch: t.Any) -> None:
    mon = ProjectActivityMonitor(project_paths=[str(tmp_path)])
    handler = IDEFileHandler(mon)

    # Lower size threshold for the test (new shape Phase 3a:
    # settings.filesystem_extraction.<field>).
    handler.monitor._settings.filesystem_extraction.max_file_size_bytes = 100

    big = tmp_path / "big.py"
    big.write_bytes(b"x" * 101)
    assert handler.should_ignore(str(big)) is True


def test_thresholds_with_critical_and_noncritical(tmp_path: t.Any) -> None:
    mon = ProjectActivityMonitor(project_paths=[str(tmp_path)])
    handler = IDEFileHandler(mon)

    # Non-critical file name with relevance 0.8 should be filtered (<0.9)
    event = ActivityEvent(
        timestamp="2025-01-01T00:00:00",
        event_type="file_change",
        application="ide",
        details={"file_name": "utils.py"},
        relevance_score=0.8,
    )
    assert handler._passes_threshold(event) is False

    # Critical file name with relevance 0.8 should pass
    event2 = ActivityEvent(
        timestamp="2025-01-01T00:00:00",
        event_type="file_change",
        application="ide",
        details={"file_name": "auth_middleware.py"},
        relevance_score=0.8,
    )
    assert handler._passes_threshold(event2) is True
