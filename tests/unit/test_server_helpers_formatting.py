from __future__ import annotations

from types import SimpleNamespace

from session_buddy.utils import session_formatters as sh


def test_format_metrics_summary() -> None:
    s = sh._format_metrics_summary(
        {"duration_minutes": 42, "success_rate": 88.88, "total_checkpoints": 3}
    )
    assert "Duration: 42min" in s
    assert "Success rate" in s
    assert "Checkpoints: 3" in s


def test_format_worktree_status_and_basic_info() -> None:
    wt = {"locked": True, "prunable": False, "exists": True, "has_session": True}
    status = sh._format_worktree_status(wt)
    assert "locked" in status
    assert "has session" in status

    info = sh._format_basic_worktree_info(
        {
            "branch": "main",
            "path": "/repo/path",
            "has_session": True,
            "is_detached": False,
        },
        SimpleNamespace(name="project"),
    )
    joined = "\n".join(info)
    assert "Repository: project" in joined
    assert "Current worktree: main" in joined
