from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from session_buddy.utils import session_formatters as sh


def test_worktree_formatters_cover_primary_branches() -> None:
    current = SimpleNamespace(
        is_main_worktree=True,
        branch="main",
        path="/repo",
        is_detached=False,
    )
    secondary = SimpleNamespace(
        is_main_worktree=False,
        branch="feature/branch",
        path="/repo/feature",
        is_detached=True,
    )
    worktrees = [
        current,
        SimpleNamespace(branch="one", path="/repo/one"),
        SimpleNamespace(branch="two", path="/repo/two"),
        SimpleNamespace(branch="three", path="/repo/three"),
        SimpleNamespace(branch="four", path="/repo/four"),
    ]

    assert "Current: Main repository" in "\n".join(
        sh._format_current_worktree_info(current)
    )
    assert "Worktree on 'feature/branch'" in "\n".join(
        sh._format_current_worktree_info(secondary)
    )
    assert sh._format_worktree_count_info(worktrees) == ["   t Total worktrees: 5"]
    assert sh._format_worktree_count_info([current]) == []
    assert "Other branches: one, two, three" in "\n".join(
        sh._format_other_branches_info(worktrees, current)
    )
    assert "and 1 more" in "\n".join(
        sh._format_other_branches_info(worktrees, current)
    )
    assert sh._format_other_branches_info([current], current) == []
    assert sh._format_worktree_suggestions(worktrees) == [
        "   t Use 'git_worktree_list' to see all worktrees",
    ]
    assert sh._format_worktree_suggestions([current]) == [
        "   t Use 'git_worktree_add <branch> <path>' to create parallel worktrees",
    ]
    assert sh._format_detached_head_warning(secondary) == [
        "   w Detached HEAD - consider checking out a branch",
    ]
    assert sh._format_detached_head_warning(current) == []
    assert sh._format_project_maturity_section(7, 10) == [
        "\nu Project maturity: 7/10"
    ]
    assert sh._format_git_worktree_header() == "\nr Git Worktree Information:"


def test_reminder_and_status_formatters_cover_lists() -> None:
    reminders = [
        {"id": "r1", "title": "First"},
        {"id": "r2", "title": "Second"},
    ]
    status_info = {
        "branch": "main",
        "path": "/repo",
        "has_session": True,
        "is_detached": False,
        "session_info": {"id": "session-1", "status": "active"},
    }

    assert "No pending reminders found" in "\n".join(
        sh._format_no_reminders_message("alice", "project-1")
    )
    assert "User: alice" in "\n".join(
        sh._format_no_reminders_message("alice", None)
    )
    assert sh._format_reminders_header(reminders, "alice", "project-1")[0].startswith(
        "⏰ Found 2 pending reminders"
    )
    assert sh._format_reminders_list(reminders, "alice", "project-1")[0].startswith(
        "⏰ Found 2 pending reminders"
    )
    assert sh._format_single_reminder(reminders[0], 1) == [
        "\n#1",
        "🆔 ID: r1",
        "📝 Title: First",
    ]
    assert sh._format_reminder_basic_info(reminders[1], 2)[0] == "\n🔥 #2 OVERDUE"
    assert "Session Information" in "\n".join(sh._format_session_info(status_info["session_info"]))
    assert sh._format_session_info(None) == []
    assert "Session Information" in sh._format_worktree_status_display(
        status_info,
        Path("/repo"),
    )
    assert "Session Information" not in sh._format_worktree_status_display(
        {
            "branch": "main",
            "path": "/repo",
            "has_session": False,
            "is_detached": False,
            "session_info": None,
        },
        Path("/repo"),
    )
    assert "Project insights over 7 days: 2 items" == sh._format_project_insights(
        {"a": 1, "b": 2},
        7,
    )


def test_statistics_and_summary_sections_cover_truncation() -> None:
    interruptions = [{"type": "pause", "timestamp": "t1"}] * 6
    snapshots = [{"type": "checkpoint", "timestamp": "t2"}] * 6
    project_activity = {
        "alpha": {"conversation_count": 4, "last_activity": "now"},
    }
    common_patterns = [
        {"pattern": f"pattern-{i}", "projects": [f"project-{i}"], "frequency": i}
        for i in range(1, 7)
    ]
    result = {
        "session_summary": {
            "active_sessions": 2,
            "unique_branches": 3,
            "branches": ["main", "feature", "fix"],
        },
        "total_worktrees": 4,
    }

    assert sh._format_interruption_statistics([]) == [
        "📊 **Interruption Patterns**: No recent interruptions",
    ]
    assert sh._format_interruption_statistics(interruptions)[0] == (
        "📊 **Interruption Patterns**: 6 interruptions"
    )
    assert sh._format_snapshot_statistics([]) == [
        "💾 **Context Snapshots**: No snapshots available",
    ]
    assert sh._format_snapshot_statistics(snapshots)[0] == (
        "💾 **Context Snapshots**: 6 snapshots"
    )
    assert "Project Activity" in "\n".join(
        sh._format_project_activity_section(project_activity)
    )
    assert "Common Patterns" in "\n".join(
        sh._format_common_patterns_section(common_patterns)
    )
    assert "pattern-5" in "\n".join(sh._format_common_patterns_section(common_patterns))
    assert "Advanced Search Results" in sh._format_advanced_search_results([1, 2, 3])
    assert sh._format_worktree_status(
        {"locked": False, "prunable": False, "exists": True, "has_session": False}
    ) == "✓ normal"
    assert "Multi-Worktree Summary" in "\n".join(sh._format_session_summary(result))


def test_feature_and_setup_helpers_respect_flags_and_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output: list[str] = []
    monkeypatch.setattr(sh, "TOKEN_OPTIMIZER_AVAILABLE", True)
    monkeypatch.setattr(sh, "CONFIG_AVAILABLE", True)
    monkeypatch.setattr(sh, "CRACKERJACK_INTEGRATION_AVAILABLE", True)

    sh._add_feature_status_info(output)
    sh._add_configuration_info(output)
    sh._add_crackerjack_integration_info(output)

    assert any("Token Optimization" in line for line in output)
    assert any("Configuration" in line for line in output)
    assert any("Crackerjack Integration" in line for line in output)

    summary = {"key_topics": []}
    monkeypatch.setenv("PWD", str(tmp_path))
    (tmp_path / "session_buddy").mkdir()
    sh._add_current_session_context(summary)
    assert "session-mgmt-mcp development" in summary["key_topics"]

    insights: list[str] = []
    sh._add_session_health_insights(insights, 90)
    sh._add_session_health_insights(insights, 70)
    sh._add_session_health_insights(insights, 20)
    assert insights == [
        "Excellent session progress with optimal workflow patterns",
        "Good session progress with minor optimization opportunities",
        "Session requires attention - potential workflow improvements needed",
    ]

    permissions_manager = SimpleNamespace(
        get_permission_status=lambda: {
            "trusted_operations_count": 2,
            "trusted_operations": ["git_commit", "uv_sync"],
        }
    )
    permissions_output: list[str] = []
    sh._add_permissions_and_tools_summary(
        permissions_output,
        "project",
        permissions_manager=permissions_manager,
    )
    sh._add_permissions_info(permissions_output, permissions_manager)
    assert any("Trusted operations: 2" in line for line in permissions_output)
    assert any("Git Commit" in line for line in permissions_output)
    assert any("Uv Sync" in line for line in permissions_output)

    no_permissions: list[str] = []
    sh._add_permissions_and_tools_summary(no_permissions, "project", None)
    sh._add_permissions_info(no_permissions, None)
    assert any("Permissions manager not available" in line for line in no_permissions)

    empty_trusted: list[str] = []
    sh._add_permissions_info(
        empty_trusted,
        SimpleNamespace(
            get_permission_status=lambda: {
                "trusted_operations_count": 0,
                "trusted_operations": [],
            }
        ),
    )
    assert any("No trusted operations yet" in line for line in empty_trusted)


def test_setup_and_list_helpers_cover_remaining_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output: list[str] = []
    monkeypatch.setattr(
        sh.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )

    claude_result = sh._setup_claude_directory(output)
    sh._setup_uv_dependencies(output, tmp_path)
    sh._handle_uv_operations(output, tmp_path, uv_trusted=True)
    sh._run_uv_sync_and_compile(output, tmp_path)
    sh._setup_session_management(output)
    sh._add_final_summary(
        output,
        "project",
        88,
        {"context": "value"},
        claude_result,
    )
    sh._add_basic_tools_info(output)

    assert claude_result == {"status": "success", "directories_created": []}
    assert any("Claude directory setup" in line for line in output)
    assert any("UV dependency management" in line for line in output)
    assert any("UV sync completed successfully" in line for line in output)
    assert any("Session management" in line for line in output)
    assert any("PROJECT SESSION INITIALIZATION COMPLETE" in line for line in output)
    assert any("Available MCP Tools" in line for line in output)

    failing_output: list[str] = []
    monkeypatch.setattr(
        sh.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    sh._run_uv_sync_and_compile(failing_output, tmp_path)
    assert failing_output == []

    assert sh._format_worktree_list_header(3, "repo", "main") == [
        "🌿 **Git Worktrees** (3 total)\\n",
        "📂 Repository: repo",
        "🎯 Current: main\\n",
    ]
    assert "locked" in sh._format_single_worktree(
        {
            "branch": "feature",
            "path": "/repo/feature",
            "locked": True,
            "prunable": True,
            "exists": False,
            "has_session": True,
        }
    )[-1]
    assert sh._format_single_worktree(
        {
            "branch": "main",
            "path": "/repo/main",
            "locked": False,
            "prunable": False,
            "exists": True,
            "has_session": False,
        }
    ) == ["• main", "  Path: /repo/main"]
    assert "locked" in sh._format_worktree_status(
        {"locked": True, "prunable": True, "exists": False, "has_session": True}
    )


def test_feature_flag_helpers_cover_disabled_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sh, "TOKEN_OPTIMIZER_AVAILABLE", False)
    monkeypatch.setattr(sh, "CONFIG_AVAILABLE", False)
    monkeypatch.setattr(sh, "CRACKERJACK_INTEGRATION_AVAILABLE", False)

    output: list[str] = []
    sh._add_feature_status_info(output)
    sh._add_configuration_info(output)
    sh._add_crackerjack_integration_info(output)

    assert output == []
