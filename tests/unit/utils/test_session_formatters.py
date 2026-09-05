"""Unit tests for session_buddy.utils.session_formatters.

Covers the non-trivial display formatters and session-setup helpers
extracted from server.py. All 40 functions in this module are
underscore-prefixed (private); per the brief, only non-trivial helpers
are tested.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from session_buddy.utils.session_formatters import (
    TOKEN_OPTIMIZER_AVAILABLE,
    CONFIG_AVAILABLE,
    CRACKERJACK_INTEGRATION_AVAILABLE,
    _add_basic_tools_info,
    _add_configuration_info,
    _add_crackerjack_integration_info,
    _add_current_session_context,
    _add_feature_status_info,
    _add_final_summary,
    _add_permissions_and_tools_summary,
    _add_permissions_info,
    _add_session_health_insights,
    _format_advanced_search_results,
    _format_basic_worktree_info,
    _format_common_patterns_section,
    _format_current_worktree_info,
    _format_detached_head_warning,
    _format_git_worktree_header,
    _format_interruption_statistics,
    _format_metrics_summary,
    _format_no_reminders_message,
    _format_other_branches_info,
    _format_project_activity_section,
    _setup_claude_directory,
    _setup_session_management,
    _setup_uv_dependencies,
    _format_project_insights,
    _format_project_maturity_section,
    _format_reminder_basic_info,
    _format_reminders_header,
    _format_session_info,
    _format_session_summary,
    _format_single_reminder,
    _format_single_worktree,
    _format_snapshot_statistics,
    _format_worktree_count_info,
    _format_worktree_list_header,
    _format_worktree_status,
    _format_worktree_status_display,
    _format_worktree_suggestions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def main_worktree() -> SimpleNamespace:
    return SimpleNamespace(
        is_main_worktree=True,
        branch="main",
        path=Path("/repo"),
        is_detached=False,
    )


@pytest.fixture()
def linked_worktree() -> SimpleNamespace:
    return SimpleNamespace(
        is_main_worktree=False,
        branch="feature-x",
        path=Path("/repo-feature"),
        is_detached=False,
    )


@pytest.fixture()
def detached_worktree() -> SimpleNamespace:
    return SimpleNamespace(
        is_main_worktree=False,
        branch="HEAD",
        path=Path("/repo-detached"),
        is_detached=True,
    )


@pytest.fixture()
def stub_permissions() -> Any:
    class StubPermissions:
        def get_permission_status(self) -> dict[str, Any]:
            return {
                "trusted_operations_count": 0,
                "trusted_operations": [],
            }

    return StubPermissions()


@pytest.fixture()
def stub_permissions_with_ops() -> Any:
    class StubPermissionsWithOps:
        def get_permission_status(self) -> dict[str, Any]:
            return {
                "trusted_operations_count": 2,
                "trusted_operations": ["git_commit"],
            }

    return StubPermissionsWithOps()


# ---------------------------------------------------------------------------
# Session metrics
# ---------------------------------------------------------------------------


class TestMetricsSummary:
    def test_full_metrics(self) -> None:
        out = _format_metrics_summary(
            {
                "duration_minutes": 42,
                "success_rate": 92.5,
                "total_checkpoints": 7,
            },
        )
        assert "Duration: 42min" in out
        assert "Success rate: 92.5%" in out
        assert "Checkpoints: 7" in out

    def test_missing_fields_default_to_zero(self) -> None:
        out = _format_metrics_summary({})
        assert "Duration: 0min" in out
        assert "Success rate: 0.0%" in out
        assert "Checkpoints: 0" in out

    def test_string_output(self) -> None:
        out = _format_metrics_summary(
            {"duration_minutes": 1, "success_rate": 1.0, "total_checkpoints": 1},
        )
        assert isinstance(out, str)


# ---------------------------------------------------------------------------
# Project maturity
# ---------------------------------------------------------------------------


class TestProjectMaturity:
    def test_format_includes_score(self) -> None:
        [line] = _format_project_maturity_section(75, 100)
        assert "75/100" in line
        assert "Project maturity" in line


# ---------------------------------------------------------------------------
# Git worktree header
# ---------------------------------------------------------------------------


class TestGitWorktreeHeader:
    def test_header_starts_with_newline(self) -> None:
        assert _format_git_worktree_header().startswith("\n")


# ---------------------------------------------------------------------------
# Current worktree info
# ---------------------------------------------------------------------------


class TestCurrentWorktreeInfo:
    def test_main_branch_label(self, main_worktree: SimpleNamespace) -> None:
        [line] = _format_current_worktree_info(main_worktree)
        assert "Main repository" in line
        assert "'main'" in line

    def test_linked_worktree_includes_path(
        self,
        linked_worktree: SimpleNamespace,
    ) -> None:
        lines = _format_current_worktree_info(linked_worktree)
        joined = "\n".join(lines)
        assert "Worktree" in joined
        assert "/repo-feature" in joined


# ---------------------------------------------------------------------------
# Worktree count and other branches
# ---------------------------------------------------------------------------


class TestWorktreeCountInfo:
    def test_single_worktree_omits_count(self) -> None:
        assert _format_worktree_count_info([]) == []

    def test_multiple_worktrees_reports_count(self) -> None:
        wts = [
            SimpleNamespace(path="/a", branch="a"),
            SimpleNamespace(path="/b", branch="b"),
        ]
        out = _format_worktree_count_info(wts)
        assert len(out) == 1
        assert "Total worktrees: 2" in out[0]


class TestOtherBranchesInfo:
    def test_no_other_branches(self, main_worktree: SimpleNamespace) -> None:
        assert _format_other_branches_info([], main_worktree) == []

    def test_three_or_fewer_branches_no_truncation(
        self,
        main_worktree: SimpleNamespace,
    ) -> None:
        wts = [SimpleNamespace(path=main_worktree.path, branch="main")]
        wts.extend(
            SimpleNamespace(path=f"/p{i}", branch=f"b{i}") for i in range(3)
        )
        out = _format_other_branches_info(wts, main_worktree)
        joined = "\n".join(out)
        assert "b0, b1, b2" in joined
        assert "more" not in joined

    def test_more_than_three_branches_truncated(
        self,
        main_worktree: SimpleNamespace,
    ) -> None:
        wts = [SimpleNamespace(path=main_worktree.path, branch="main")]
        wts.extend(SimpleNamespace(path=f"/p{i}", branch=f"b{i}") for i in range(5))
        out = _format_other_branches_info(wts, main_worktree)
        joined = "\n".join(out)
        assert "more" in joined
        assert "2 more" in joined


# ---------------------------------------------------------------------------
# Worktree suggestions
# ---------------------------------------------------------------------------


class TestWorktreeSuggestions:
    def test_singular_suggests_create(self) -> None:
        [line] = _format_worktree_suggestions([])
        assert "create parallel worktrees" in line

    def test_plural_suggests_list(self) -> None:
        wts = [
            SimpleNamespace(path="/a", branch="a"),
            SimpleNamespace(path="/b", branch="b"),
        ]
        [line] = _format_worktree_suggestions(wts)
        assert "git_worktree_list" in line


# ---------------------------------------------------------------------------
# Detached HEAD warning
# ---------------------------------------------------------------------------


class TestDetachedHeadWarning:
    def test_no_warning_when_attached(self, main_worktree: SimpleNamespace) -> None:
        assert _format_detached_head_warning(main_worktree) == []

    def test_warning_when_detached(self, detached_worktree: SimpleNamespace) -> None:
        [line] = _format_detached_head_warning(detached_worktree)
        assert "Detached HEAD" in line


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------


class TestNoRemindersMessage:
    def test_with_project_id(self) -> None:
        lines = _format_no_reminders_message("alice", "myproj")
        joined = "\n".join(lines)
        assert "alice" in joined
        assert "myproj" in joined

    def test_without_project_id_omits_line(self) -> None:
        lines = _format_no_reminders_message("alice", None)
        joined = "\n".join(lines)
        assert "Project:" not in joined
        assert "alice" in joined


class TestRemindersHeader:
    def test_header_count_and_user(self) -> None:
        lines = _format_reminders_header(
            [{"id": 1, "title": "x"}, {"id": 2, "title": "y"}],
            "bob",
            "proj1",
        )
        joined = "\n".join(lines)
        assert "Found 2 pending reminders" in joined
        assert "bob" in joined
        assert "proj1" in joined
        assert "=" * 50 in joined

    def test_header_without_project(self) -> None:
        lines = _format_reminders_header([], "bob", None)
        joined = "\n".join(lines)
        assert "Project:" not in joined
        assert "Found 0 pending reminders" in joined


class TestSingleReminder:
    def test_basic_fields(self) -> None:
        lines = _format_single_reminder({"id": "abc", "title": "do thing"}, 3)
        joined = "\n".join(lines)
        assert "#3" in joined
        assert "abc" in joined
        assert "do thing" in joined


class TestReminderBasicInfo:
    def test_overdue_marker(self) -> None:
        lines = _format_reminder_basic_info({"id": "z", "title": "late"}, 1)
        joined = "\n".join(lines)
        assert "OVERDUE" in joined
        assert "#1" in joined


# ---------------------------------------------------------------------------
# Project insights & activity
# ---------------------------------------------------------------------------


class TestProjectInsights:
    def test_includes_count_and_window(self) -> None:
        out = _format_project_insights({"a": 1, "b": 2}, 30)
        assert "30 days" in out
        assert "2 items" in out

    def test_empty_dict(self) -> None:
        out = _format_project_insights({}, 7)
        assert "7 days" in out
        assert "0 items" in out


class TestProjectActivitySection:
    def test_per_project_line(self) -> None:
        out = _format_project_activity_section(
            {
                "alpha": {"conversation_count": 3, "last_activity": "2026-09-04"},
                "beta": {"conversation_count": 5},
            },
        )
        joined = "\n".join(out)
        assert "alpha" in joined
        assert "beta" in joined
        assert "3 conversations" in joined
        assert "5 conversations" in joined
        assert "Unknown" in joined


class TestCommonPatternsSection:
    def test_top_5_limiting(self) -> None:
        patterns = [
            {"pattern": f"P{i}", "projects": ["x"], "frequency": i}
            for i in range(8)
        ]
        out = _format_common_patterns_section(patterns)
        joined = "\n".join(out)
        for i in range(5):
            assert f"P{i}" in joined
        for i in range(5, 8):
            assert f"P{i}" not in joined

    def test_joins_projects(self) -> None:
        out = _format_common_patterns_section(
            [
                {
                    "pattern": "refactor",
                    "projects": ["a", "b"],
                    "frequency": 4,
                },
            ],
        )
        joined = "\n".join(out)
        assert "a, b" in joined
        assert "refactor" in joined


class TestAdvancedSearchResults:
    def test_includes_count(self) -> None:
        out = _format_advanced_search_results([1, 2, 3])
        assert "3 found" in out

    def test_zero_results(self) -> None:
        out = _format_advanced_search_results([])
        assert "0 found" in out


# ---------------------------------------------------------------------------
# Worktree status / list / single
# ---------------------------------------------------------------------------


class TestWorktreeStatus:
    def test_normal_default(self) -> None:
        assert (
            _format_worktree_status(
                {
                    "locked": False,
                    "prunable": False,
                    "exists": True,
                    "has_session": False,
                },
            )
            == "✓ normal"
        )

    def test_locked_marker(self) -> None:
        out = _format_worktree_status(
            {
                "locked": True,
                "prunable": False,
                "exists": True,
                "has_session": False,
            },
        )
        assert "locked" in out

    def test_all_flags(self) -> None:
        out = _format_worktree_status(
            {
                "locked": True,
                "prunable": True,
                "exists": False,
                "has_session": True,
            },
        )
        for marker in ("locked", "prunable", "missing", "has session"):
            assert marker in out


class TestWorktreeListHeader:
    def test_header_fields(self) -> None:
        out = _format_worktree_list_header(3, "myrepo", "main")
        joined = "\n".join(out)
        assert "3 total" in joined
        assert "myrepo" in joined
        assert "main" in joined


class TestSingleWorktree:
    def test_branch_and_path(self) -> None:
        wt = {
            "branch": "feat",
            "path": "/tmp/feat",
            "locked": False,
            "prunable": False,
            "exists": True,
            "has_session": False,
        }
        out = _format_single_worktree(wt)
        joined = "\n".join(out)
        assert "feat" in joined
        assert "/tmp/feat" in joined
        assert "Status:" not in joined

    def test_status_line_when_not_normal(self) -> None:
        wt = {
            "branch": "feat",
            "path": "/tmp/feat",
            "locked": True,
            "prunable": False,
            "exists": True,
            "has_session": False,
        }
        out = _format_single_worktree(wt)
        assert any("Status:" in line and "locked" in line for line in out)


# ---------------------------------------------------------------------------
# Session summary / worktree status display
# ---------------------------------------------------------------------------


class TestSessionSummary:
    def test_includes_totals_and_branches(self) -> None:
        result = {
            "total_worktrees": 3,
            "session_summary": {
                "active_sessions": 2,
                "unique_branches": 3,
                "branches": ["main", "feat", "fix"],
            },
        }
        out = _format_session_summary(result)
        joined = "\n".join(out)
        assert "Total worktrees: 3" in joined
        assert "Active sessions: 2" in joined
        assert "main, feat, fix" in joined


class TestWorktreeStatusDisplay:
    def test_basic_and_session(self) -> None:
        status_info = {
            "branch": "main",
            "path": "/repo",
            "has_session": True,
            "is_detached": False,
            "session_info": {"id": "abc", "status": "active"},
        }
        out = _format_worktree_status_display(status_info, Path("/repo"))
        assert "main" in out
        assert "/repo" in out
        assert "Session Information" in out
        assert "abc" in out

    def test_without_session_info(self) -> None:
        status_info = {
            "branch": "main",
            "path": "/repo",
            "has_session": False,
            "is_detached": False,
        }
        out = _format_worktree_status_display(status_info, Path("/repo"))
        assert "main" in out
        assert "Session Information" not in out


class TestBasicWorktreeInfo:
    def test_each_field(self) -> None:
        info = {
            "branch": "main",
            "path": "/p",
            "has_session": True,
            "is_detached": True,
        }
        out = _format_basic_worktree_info(info, Path("/p"))
        joined = "\n".join(out)
        assert "main" in joined
        assert "/p" in joined
        assert "Yes" in joined


class TestSessionInfo:
    def test_none_returns_empty(self) -> None:
        assert _format_session_info(None) == []

    def test_empty_dict_treated_as_missing(self) -> None:
        assert _format_session_info({}) == []

    def test_partial_dict(self) -> None:
        out = _format_session_info({"id": "abc"})
        joined = "\n".join(out)
        assert "abc" in joined
        assert "unknown" in joined

    def test_full(self) -> None:
        out = _format_session_info({"id": "abc", "status": "paused"})
        joined = "\n".join(out)
        assert "abc" in joined
        assert "paused" in joined


# ---------------------------------------------------------------------------
# Interruption / snapshot statistics
# ---------------------------------------------------------------------------


class TestInterruptionStatistics:
    def test_empty(self) -> None:
        out = _format_interruption_statistics([])
        assert len(out) == 1
        assert "No recent interruptions" in out[0]

    def test_caps_at_five(self) -> None:
        items = [{"type": "x", "timestamp": f"t{i}"} for i in range(10)]
        out = _format_interruption_statistics(items)
        joined = "\n".join(out)
        assert "10 interruptions" in joined
        numbered = [
            line
            for line in out
            if line.startswith("  ") and line.strip()[:2].rstrip(".").isdigit()
        ]
        assert len(numbered) == 5

    def test_missing_fields_default(self) -> None:
        out = _format_interruption_statistics([{}])
        joined = "\n".join(out)
        assert "unknown" in joined
        assert "N/A" in joined


class TestSnapshotStatistics:
    def test_empty(self) -> None:
        out = _format_snapshot_statistics([])
        assert "No snapshots available" in out[0]

    def test_caps_at_five(self) -> None:
        items = [{"type": "x", "timestamp": f"t{i}"} for i in range(8)]
        out = _format_snapshot_statistics(items)
        joined = "\n".join(out)
        assert "8 snapshots" in joined
        numbered = [
            line
            for line in out
            if line.startswith("  ") and line.strip()[:2].rstrip(".").isdigit()
        ]
        assert len(numbered) == 5


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


class TestSetupClaudeDirectory:
    def test_appends_phase_announcement(self) -> None:
        output: list[str] = []
        result = _setup_claude_directory(output)
        assert any("Phase 1" in line for line in output)
        assert result["status"] == "success"


class TestSetupUvDependencies:
    def test_appends_phase_announcement(self) -> None:
        output: list[str] = []
        _setup_uv_dependencies(output, Path("/tmp"))
        assert any("Phase 2" in line for line in output)


class TestSetupSessionManagement:
    def test_appends_phase_and_tools(self) -> None:
        output: list[str] = []
        _setup_session_management(output)
        joined = "\n".join(output)
        assert "Phase 3" in joined
        assert "Session management" in joined


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------


class TestFinalSummary:
    def test_appends_banner_and_project_name(self) -> None:
        output: list[str] = []
        _add_final_summary(output, "myproj", 80, {}, {})
        joined = "\n".join(output)
        assert "MYPROJ" in joined
        assert "SESSION INITIALIZATION COMPLETE" in joined
        assert "=" * 60 in joined


# ---------------------------------------------------------------------------
# Session health insights
# ---------------------------------------------------------------------------


class TestSessionHealthInsights:
    @pytest.mark.parametrize(
        ("score", "expected_fragment"),
        [
            (95, "Excellent"),
            (80, "Excellent"),
            (79, "Good"),
            (60, "Good"),
            (59, "requires attention"),
            (0, "requires attention"),
        ],
    )
    def test_thresholds(self, score: float, expected_fragment: str) -> None:
        insights: list[str] = []
        _add_session_health_insights(insights, score)
        assert any(expected_fragment in line for line in insights)


# ---------------------------------------------------------------------------
# Current session context
# ---------------------------------------------------------------------------


class TestCurrentSessionContext:
    def test_appends_keyword_when_session_buddy_dir_present(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (tmp_path / "session_buddy").mkdir()
        monkeypatch.setenv("PWD", str(tmp_path))
        summary: dict[str, list[str]] = {"key_topics": []}
        _add_current_session_context(summary)
        assert any("session-mgmt-mcp" in topic for topic in summary["key_topics"])

    def test_does_not_append_when_dir_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PWD", str(tmp_path))
        summary: dict[str, list[str]] = {"key_topics": []}
        _add_current_session_context(summary)
        assert summary["key_topics"] == []


# ---------------------------------------------------------------------------
# Permissions info
# ---------------------------------------------------------------------------


class TestPermissionsAndToolsSummary:
    def test_with_permissions_manager(self, stub_permissions: Any) -> None:
        output: list[str] = []
        _add_permissions_and_tools_summary(output, "proj", stub_permissions)
        joined = "\n".join(output)
        assert "Trusted operations: 0" in joined

    def test_without_permissions_manager(self) -> None:
        output: list[str] = []
        _add_permissions_and_tools_summary(output, "proj", None)
        joined = "\n".join(output)
        assert "Permissions manager not available" in joined


class TestPermissionsInfo:
    def test_with_manager_no_trusted_ops(self, stub_permissions: Any) -> None:
        output: list[str] = []
        _add_permissions_info(output, stub_permissions)
        joined = "\n".join(output)
        assert "Trusted operations: 0" in joined
        assert "No trusted operations yet" in joined

    def test_with_manager_has_trusted_ops(
        self,
        stub_permissions_with_ops: Any,
    ) -> None:
        output: list[str] = []
        _add_permissions_info(output, stub_permissions_with_ops)
        joined = "\n".join(output)
        assert "Git Commit" in joined

    def test_without_manager(self) -> None:
        output: list[str] = []
        _add_permissions_info(output, None)
        joined = "\n".join(output)
        assert "Permissions manager not available" in joined


# ---------------------------------------------------------------------------
# Tools / feature / config / crackerjack info
# ---------------------------------------------------------------------------


class TestBasicToolsInfo:
    def test_lists_mcp_tools(self) -> None:
        output: list[str] = []
        _add_basic_tools_info(output)
        joined = "\n".join(output)
        assert "Available MCP Tools" in joined
        for tool in ("init", "checkpoint", "end", "status", "permissions"):
            assert tool in joined
        for worktree_tool in (
            "git_worktree_list",
            "git_worktree_add",
            "git_worktree_remove",
            "git_worktree_status",
            "git_worktree_prune",
        ):
            assert worktree_tool in joined


class TestFeatureStatusInfo:
    def test_emits_token_optimizer_section_iff_available(self) -> None:
        output: list[str] = []
        _add_feature_status_info(output)
        joined = "\n".join(output)
        if TOKEN_OPTIMIZER_AVAILABLE:
            assert "Token Optimization" in joined
            assert "get_cached_chunk" in joined
        else:
            assert "Token Optimization" not in joined


class TestConfigurationInfo:
    def test_config_section_iff_available(self) -> None:
        output: list[str] = []
        _add_configuration_info(output)
        joined = "\n".join(output)
        if CONFIG_AVAILABLE:
            assert "Configuration" in joined
        else:
            assert "Configuration" not in joined


class TestCrackerjackIntegrationInfo:
    def test_section_iff_available(self) -> None:
        output: list[str] = []
        _add_crackerjack_integration_info(output)
        joined = "\n".join(output)
        if CRACKERJACK_INTEGRATION_AVAILABLE:
            assert "Crackerjack" in joined
        else:
            assert "Crackerjack Integration" not in joined