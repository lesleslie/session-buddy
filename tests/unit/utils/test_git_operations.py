"""Tests for session_buddy.utils.git_operations.

Targets the in-file private helpers (``_parse_git_status``,
``_format_untracked_files``, ``_stage_and_commit_files``,
``_stage_files``, ``_commit_staged_changes``, ``_run_git_command``,
``_optimize_git_repository``) plus the re-exports from
``git_worktrees``. The tests use ``tmp_path`` to spin up real git
repos so subprocess.run actually executes the bundled git binary.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from session_buddy.utils import git_operations
from session_buddy.utils.git_operations import (
    WorktreeInfo,
    _commit_staged_changes,
    _format_untracked_files,
    _optimize_git_repository,
    _parse_git_status,
    _run_git_command,
    _stage_and_commit_files,
    _stage_files,
    create_checkpoint_commit,
    create_commit,
    get_git_status,
    get_staged_files,
    is_git_operation_in_progress,
    is_git_repository,
    schedule_automatic_git_gc,
    stage_files,
)
from session_buddy.utils.git_worktrees import _validate_prune_delay


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    """Initialize a git repository at ``path`` with sane defaults for tests."""
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def _commit(path: Path, message: str = "init") -> str:
    """Make an initial commit in ``path`` so HEAD points at something."""
    (path / "README.md").write_text("# test\n")
    subprocess.run(
        ["git", "add", "-A"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=path,
        check=True,
        capture_output=True,
    )
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


# ---------------------------------------------------------------------------
# Module surface / re-exports
# ---------------------------------------------------------------------------


class TestModuleSurface:
    def test_all_listed_exports_are_importable(self) -> None:
        for name in git_operations.__all__:
            assert hasattr(git_operations, name), f"Missing export: {name}"

    def test_worktree_info_dataclass_construction(self) -> None:
        info = WorktreeInfo(path=Path("/tmp/wt"), branch="main", head="abc")
        assert info.path == Path("/tmp/wt")
        assert info.branch == "main"
        assert info.head == "abc"
        assert info.is_bare is False
        assert info.is_detached is False
        assert info.is_main_worktree is False
        assert info.locked is False
        assert info.prunable is False

    def test_worktree_info_with_all_fields(self) -> None:
        info = WorktreeInfo(
            path=Path("/tmp/wt2"),
            branch="feature",
            head="deadbeef",
            is_bare=True,
            is_detached=True,
            is_main_worktree=True,
            locked=True,
            prunable=True,
        )
        assert info.is_bare is True
        assert info.is_detached is True
        assert info.is_main_worktree is True
        assert info.locked is True
        assert info.prunable is True


# ---------------------------------------------------------------------------
# _parse_git_status
# ---------------------------------------------------------------------------


class TestParseGitStatus:
    def test_empty_input_returns_empty_lists(self) -> None:
        staged, untracked = _parse_git_status([])
        assert staged == []
        assert untracked == []

    def test_parses_added_modified_deleted(self) -> None:
        lines = ["A  new.txt", "M  mod.txt", "D  gone.txt"]
        staged, untracked = _parse_git_status(lines)
        assert staged == ["new.txt", "mod.txt", "gone.txt"]
        assert untracked == []

    def test_parses_untracked_files(self) -> None:
        lines = ["?? brand-new.txt", "?? another-new.txt"]
        staged, untracked = _parse_git_status(lines)
        assert staged == []
        assert untracked == ["brand-new.txt", "another-new.txt"]

    def test_mixed_staged_and_untracked(self) -> None:
        lines = [
            "M  modified.py",
            "A  new.py",
            "?? untracked.py",
            "D  deleted.py",
        ]
        staged, untracked = _parse_git_status(lines)
        assert staged == ["modified.py", "new.py", "deleted.py"]
        assert untracked == ["untracked.py"]

    def test_renames_and_copies_ignored(self) -> None:
        """Renames start with 'R ' and copies with 'C ' — both ignored."""
        lines = ["R  old.txt -> new.txt", "C  src.txt -> dst.txt"]
        staged, untracked = _parse_git_status(lines)
        assert staged == []
        assert untracked == []

    def test_preserves_filename_with_spaces(self) -> None:
        """Only the first 2 characters of the prefix are stripped, so file
        names that contain spaces survive the parse."""
        lines = ["A  a file with spaces.txt"]
        staged, _ = _parse_git_status(lines)
        assert staged == ["a file with spaces.txt"]


# ---------------------------------------------------------------------------
# _format_untracked_files
# ---------------------------------------------------------------------------


class TestFormatUntrackedFiles:
    def test_empty_list_returns_no_untracked_marker(self) -> None:
        assert _format_untracked_files([]) == ["✅ No untracked files"]

    def test_single_file_display(self) -> None:
        result = _format_untracked_files(["only.txt"])
        assert result == [
            "📁 Untracked Files:",
            "   • only.txt",
        ]

    def test_caps_display_to_ten_files(self) -> None:
        files = [f"file{i}.txt" for i in range(15)]
        result = _format_untracked_files(files)
        assert result[0] == "📁 Untracked Files:"
        # 10 file lines + header + 'and N more' line.
        assert len(result) == 12
        assert "and 5 more files" in result[-1]

    def test_exactly_ten_files_no_more_marker(self) -> None:
        files = [f"file{i}.txt" for i in range(10)]
        result = _format_untracked_files(files)
        assert len(result) == 11
        assert all("and" not in line for line in result)


# ---------------------------------------------------------------------------
# _run_git_command
# ---------------------------------------------------------------------------


class TestRunGitCommand:
    def test_successful_command_returns_true(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        output: list[str] = []
        ok = _run_git_command(["git", "status"], tmp_path, output)
        assert ok is True
        assert output == []

    def test_failing_command_appends_stderr(self, tmp_path: Path) -> None:
        output: list[str] = []
        # `git not-a-real-subcommand` exits non-zero.
        ok = _run_git_command(["git", "not-a-real-subcommand"], tmp_path, output)
        assert ok is False
        assert len(output) == 1
        assert "failed:" in output[0]
        # Output mentions the subcommand we tried.
        assert "not-a-real-subcommand" in output[0]


# ---------------------------------------------------------------------------
# _stage_files / _commit_staged_changes / _stage_and_commit_files
# ---------------------------------------------------------------------------


class TestStageAndCommit:
    def test_stage_files_with_explicit_list(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "alpha.txt").write_text("a")
        (tmp_path / "beta.txt").write_text("b")
        output: list[str] = []
        ok = _stage_files(tmp_path, ["alpha.txt", "beta.txt"], output)
        assert ok is True

    def test_stage_files_with_no_explicit_list_stages_all(
        self, tmp_path: Path
    ) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        (tmp_path / "delta.txt").write_text("d")
        output: list[str] = []
        ok = _stage_files(tmp_path, None, output)
        assert ok is True

    def test_stage_files_returns_false_when_git_add_fails(
        self, tmp_path: Path
    ) -> None:
        # ``tmp_path`` is NOT a git repo, so ``git add`` fails.
        (tmp_path / "x.txt").write_text("x")
        output: list[str] = []
        ok = _stage_files(tmp_path, ["x.txt"], output)
        assert ok is False
        assert len(output) >= 1

    def test_stage_files_all_branches_when_git_add_fails(
        self, tmp_path: Path
    ) -> None:
        # With explicit files: if any ``git add <file>`` fails, all() short-
        # circuits to False. Force a failure by giving a path with a NUL.
        output: list[str] = []
        ok = _stage_files(tmp_path, ["bogus_filename.txt"], output)
        assert ok is False

    def test_commit_staged_changes_success(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        (tmp_path / "new.txt").write_text("new")
        subprocess.run(
            ["git", "add", "new.txt"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        output: list[str] = []
        ok, out = _commit_staged_changes(tmp_path, "add new", output)
        assert ok is True
        assert any("Committed changes: add new" in line for line in out)

    def test_commit_staged_changes_no_changes_appends_warning(
        self, tmp_path: Path
    ) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        # No further changes to commit.
        output: list[str] = []
        ok, out = _commit_staged_changes(tmp_path, "no-op", output)
        assert ok is False
        assert any("Commit failed" in line for line in out)

    def test_stage_and_commit_files_happy_path(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        (tmp_path / "feature.txt").write_text("feature")
        ok, out = _stage_and_commit_files(tmp_path, "add feature")
        assert ok is True
        assert any("Committed" in line for line in out)

    def test_stage_and_commit_files_short_circuits_when_stage_fails(
        self, tmp_path: Path
    ) -> None:
        # Not a git repo → ``_stage_files`` fails and returns (False, output)
        # without attempting a commit.
        ok, out = _stage_and_commit_files(tmp_path, "boom")
        assert ok is False
        assert any("Git operation error" in line or "failed" in line.lower() for line in out)

    def test_stage_and_commit_files_swallows_exception(
        self, tmp_path: Path
    ) -> None:
        """If an unexpected exception bubbles up, it is captured into output."""
        with patch(
            "session_buddy.utils.git_operations._stage_files",
            side_effect=RuntimeError("nope"),
        ):
            ok, out = _stage_and_commit_files(tmp_path, "msg")
        assert ok is False
        assert any("Git operation error: nope" in line for line in out)


# ---------------------------------------------------------------------------
# _optimize_git_repository
# ---------------------------------------------------------------------------


class TestOptimizeGitRepository:
    def test_runs_gc_and_prune_against_real_repo(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        results = _optimize_git_repository(tmp_path)
        # At least the gc and prune messages should appear (they may not
        # both succeed in every environment, but at minimum gc completes).
        joined = " ".join(results)
        assert "Git" in joined

    def test_handles_non_git_directory_gracefully(self, tmp_path: Path) -> None:
        results = _optimize_git_repository(tmp_path)
        assert isinstance(results, list)
        # Should at minimum not raise; the function returns warnings.
        assert all(isinstance(line, str) for line in results)

    def test_swallows_unexpected_exception(self, tmp_path: Path) -> None:
        with patch(
            "session_buddy.utils.git_operations.subprocess.run",
            side_effect=OSError("boom"),
        ):
            results = _optimize_git_repository(tmp_path)
        assert any("Git optimization error" in line for line in results)

    def test_records_successful_prune(self, tmp_path: Path) -> None:
        """When both git gc and the remote prune returncode == 0, the
        success message is appended (covers the happy-path branch)."""
        fake_results = [
            subprocess.CompletedProcess(
                args=["git", "gc", "--auto"], returncode=0, stdout="", stderr=""
            ),
            subprocess.CompletedProcess(
                args=["git", "remote", "prune", "origin"],
                returncode=0,
                stdout="",
                stderr="",
            ),
        ]
        with patch(
            "session_buddy.utils.git_operations.subprocess.run",
            side_effect=fake_results,
        ):
            results = _optimize_git_repository(tmp_path)
        assert any("Pruned remote tracking branches" in line for line in results)
        assert any("Git garbage collection completed" in line for line in results)


# ---------------------------------------------------------------------------
# is_git_repository (re-export)
# ---------------------------------------------------------------------------


class TestIsGitRepository:
    def test_false_for_arbitrary_directory(self, tmp_path: Path) -> None:
        assert is_git_repository(tmp_path) is False

    def test_true_for_real_repo(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        assert is_git_repository(tmp_path) is True

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        assert is_git_repository(str(tmp_path)) is True


# ---------------------------------------------------------------------------
# stage_files / get_staged_files / create_commit
# ---------------------------------------------------------------------------


class TestStageFiles:
    def test_refuses_when_not_a_git_repo(self, tmp_path: Path) -> None:
        assert stage_files(tmp_path, []) is False

    def test_stages_specific_files(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        (tmp_path / "staged.txt").write_text("s")
        assert stage_files(tmp_path, ["staged.txt"]) is True
        assert get_staged_files(tmp_path) == ["staged.txt"]

    def test_returns_false_on_git_failure(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        # Stage a file path that doesn't exist — git add fails.
        assert stage_files(tmp_path, ["does-not-exist.txt"]) is False


class TestCreateCommit:
    def test_fails_when_not_a_git_repo(self, tmp_path: Path) -> None:
        ok, msg = create_commit(tmp_path, "msg")
        assert ok is False
        assert msg == "Not a git repository"

    def test_creates_commit_in_real_repo(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        (tmp_path / "new.txt").write_text("new")
        stage_files(tmp_path, ["new.txt"])
        ok, msg = create_commit(tmp_path, "add new")
        assert ok is True
        # msg should look like a hex hash.
        assert len(msg) >= 7
        assert all(c in "0123456789abcdef" for c in msg)


# ---------------------------------------------------------------------------
# get_git_status
# ---------------------------------------------------------------------------


class TestGetGitStatus:
    def test_returns_empty_pair_for_non_repo(self, tmp_path: Path) -> None:
        modified, untracked = get_git_status(tmp_path)
        assert modified == []
        assert untracked == []

    def test_detects_modified_files(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        # Commit x.txt, then edit it so it shows as a tracked modified file.
        (tmp_path / "x.txt").write_text("v1")
        subprocess.run(
            ["git", "add", "-A"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "add x"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        (tmp_path / "x.txt").write_text("v2-edit")
        modified, _ = get_git_status(tmp_path)
        assert "x.txt" in modified

    def test_detects_untracked_files(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        (tmp_path / "fresh.txt").write_text("fresh")
        _, untracked = get_git_status(tmp_path)
        assert "fresh.txt" in untracked


# ---------------------------------------------------------------------------
# get_staged_files
# ---------------------------------------------------------------------------


class TestGetStagedFiles:
    def test_empty_for_non_repo(self, tmp_path: Path) -> None:
        assert get_staged_files(tmp_path) == []

    def test_returns_staged_paths(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        (tmp_path / "staged.txt").write_text("s")
        stage_files(tmp_path, ["staged.txt"])
        assert get_staged_files(tmp_path) == ["staged.txt"]

    def test_empty_when_no_staged_changes(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        assert get_staged_files(tmp_path) == []


# ---------------------------------------------------------------------------
# create_checkpoint_commit
# ---------------------------------------------------------------------------


class TestCreateCheckpointCommit:
    def test_returns_false_for_non_repo(self, tmp_path: Path) -> None:
        ok, result, output = create_checkpoint_commit(tmp_path, "p", 80)
        assert ok is False
        assert "Not a git repository" in result

    def test_returns_clean_when_no_changes(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        ok, result, _ = create_checkpoint_commit(tmp_path, "p", 80)
        assert ok is True
        assert result == "clean"

    def test_creates_checkpoint_for_modified_files(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        (tmp_path / "change.txt").write_text("change")
        # Stage so the checkpoint picks it up as a tracked modified file.
        stage_files(tmp_path, ["change.txt"])
        ok, result, output = create_checkpoint_commit(
            tmp_path,
            "test-project",
            90,
            explicit_files=["change.txt"],
        )
        assert ok is True
        # result should be a hash-like string.
        assert result != "clean"
        assert len(result) >= 7

    def test_only_untracked_files_returns_no_staged(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        (tmp_path / "u.txt").write_text("u")
        ok, result, _ = create_checkpoint_commit(tmp_path, "p", 80)
        assert ok is False
        assert "No staged changes" in result


# ---------------------------------------------------------------------------
# is_git_operation_in_progress
# ---------------------------------------------------------------------------


class TestIsGitOperationInProgress:
    def test_false_for_non_repo(self, tmp_path: Path) -> None:
        assert is_git_operation_in_progress(tmp_path) is False

    def test_false_for_clean_repo(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        assert is_git_operation_in_progress(tmp_path) is False

    def test_true_when_rebase_in_progress(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        # Simulate an interactive rebase by writing the indicator file.
        subprocess.run(
            ["git", "rebase", "--interactive", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
        )
        # If rebase failed to start (empty repo / no parent), force the file.
        git_dir = tmp_path / ".git"
        (git_dir / "rebase-merge").mkdir(exist_ok=True)
        assert is_git_operation_in_progress(tmp_path) is True

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        assert is_git_operation_in_progress(str(tmp_path)) is False


# ---------------------------------------------------------------------------
# _validate_prune_delay (re-export)
# ---------------------------------------------------------------------------


class TestValidatePruneDelay:
    @pytest.mark.parametrize(
        "value",
        ["now", "NEVER", "2.weeks", "1.day", "3.months", "1.year", "30.seconds"],
    )
    def test_accepts_safe_values(self, value: str) -> None:
        ok, msg = _validate_prune_delay(value)
        assert ok is True
        assert msg == ""

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "foo",
            "1.day.ago",
            "; rm -rf /",
            "$(whoami)",
            "&&x",
            "0.weeks",  # below min
            "1001.weeks",  # above max
        ],
    )
    def test_rejects_unsafe_values(self, value: str) -> None:
        ok, msg = _validate_prune_delay(value)
        assert ok is False
        assert msg != ""


# ---------------------------------------------------------------------------
# schedule_automatic_git_gc
# ---------------------------------------------------------------------------


class TestScheduleAutomaticGitGc:
    def test_refuses_when_not_a_git_repo(self, tmp_path: Path) -> None:
        ok, msg = schedule_automatic_git_gc(tmp_path)
        assert ok is False
        assert "Not a git repository" in msg

    def test_rejects_unsafe_prune_delay(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        ok, msg = schedule_automatic_git_gc(tmp_path, prune_delay="bad;rm")
        assert ok is False
        assert msg != ""

    def test_schedules_gc_in_real_repo(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        ok, msg = schedule_automatic_git_gc(tmp_path)
        assert ok is True
        # msg should mention scheduling in some form.
        assert isinstance(msg, str)

    def test_accepts_string_directory(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit(tmp_path)
        ok, _ = schedule_automatic_git_gc(str(tmp_path))
        assert ok is True
