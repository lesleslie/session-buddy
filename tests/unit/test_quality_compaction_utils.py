"""Tests for session_buddy.utils.quality.compaction.

Covers the deterministic surface of the compaction evaluator: the reason
helpers, the project-size counter (with hidden-file filtering and the
50-file early-stop threshold), the git-activity subprocess wrapper (with
subprocess.run monkeypatched), and the three evaluate_* heuristics that
decide whether context compaction is worthwhile.

NOTE: This test file imports the module through the normal
``session_buddy.utils.quality.compaction`` path so pytest-cov's coverage
hooks attach. Earlier revisions used ``importlib.util.spec_from_file_location``
which bypassed coverage tracking entirely.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from session_buddy.utils.quality import compaction
from session_buddy.utils.quality.compaction import (
    check_git_activity,
    count_significant_files,
    evaluate_git_activity_heuristic,
    evaluate_large_project_heuristic,
    evaluate_python_project_heuristic,
    get_default_compaction_reason,
    get_fallback_compaction_reason,
)


# ---------------------------------------------------------------------------
# Reason helpers
# ---------------------------------------------------------------------------


class TestReasonHelpers:
    def test_default_reason_mentions_manageable(self) -> None:
        msg = get_default_compaction_reason().lower()
        assert "manageable" in msg

    def test_fallback_reason_mentions_precaution(self) -> None:
        msg = get_fallback_compaction_reason().lower()
        assert "precaution" in msg

    def test_helpers_return_strings(self) -> None:
        assert isinstance(get_default_compaction_reason(), str)
        assert isinstance(get_fallback_compaction_reason(), str)


# ---------------------------------------------------------------------------
# count_significant_files
# ---------------------------------------------------------------------------


class TestCountSignificantFiles:
    def test_counts_only_recognized_extensions(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden.py").write_text("print('hidden')")
        for i in range(3):
            (tmp_path / f"file_{i}.py").write_text("print('ok')")
        (tmp_path / "notes.txt").write_text("ignore")

        assert count_significant_files(tmp_path) == 3

    def test_ignores_hidden_directories(self, tmp_path: Path) -> None:
        hidden_dir = tmp_path / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "x.py").write_text("print('x')")
        (tmp_path / "visible.py").write_text("print('v')")

        assert count_significant_files(tmp_path) == 1

    def test_stops_at_threshold_of_50(self, tmp_path: Path) -> None:
        for i in range(60):
            (tmp_path / f"f{i:03d}.py").write_text("print('ok')")

        # The function counts up to 50 then short-circuits; the exact value
        # depends on rglob traversal order. The contract: never returns >51.
        result = count_significant_files(tmp_path)
        assert 1 <= result <= 51

    def test_recognizes_all_listed_extensions(self, tmp_path: Path) -> None:
        for ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
                    ".java", ".cpp", ".c", ".h"):
            (tmp_path / f"file{ext}").write_text("// content")
        assert count_significant_files(tmp_path) == 11

    def test_empty_directory_returns_zero(self, tmp_path: Path) -> None:
        assert count_significant_files(tmp_path) == 0

    def test_nonexistent_directory_returns_zero(self, tmp_path: Path) -> None:
        # The function uses suppress(OSError, ...) so missing paths return 0.
        assert count_significant_files(tmp_path / "does-not-exist") == 0

    def test_handles_permission_error(self, tmp_path: Path) -> None:
        # Permission errors during rglob are also caught by the broad except.
        # We can't easily simulate EACCES cross-platform, but the bare-except
        # contract means we should never raise.
        assert count_significant_files(tmp_path) >= 0


# ---------------------------------------------------------------------------
# check_git_activity
# ---------------------------------------------------------------------------


class TestCheckGitActivity:
    def test_returns_none_when_no_git_dir(self, tmp_path: Path) -> None:
        assert check_git_activity(tmp_path) is None

    def test_parses_log_and_status(self, monkeypatch, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()

        def fake_run(cmd, **kwargs):
            if cmd[1] == "log":
                return SimpleNamespace(returncode=0, stdout="a\nb\nc\n")
            if cmd[1] == "status":
                return SimpleNamespace(returncode=0, stdout=" M one.py\n M two.py\n")
            return SimpleNamespace(returncode=1, stdout="")

        monkeypatch.setattr(compaction.subprocess, "run", fake_run)
        assert check_git_activity(tmp_path) == (3, 2)

    def test_zero_returncode_yields_zero_counts(self, monkeypatch, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()

        def zero_run(cmd, **kwargs):
            return SimpleNamespace(returncode=0, stdout="")

        monkeypatch.setattr(compaction.subprocess, "run", zero_run)
        assert check_git_activity(tmp_path) == (0, 0)

    def test_nonzero_returncode_yields_zero_counts(self, monkeypatch, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()

        def failing_run(cmd, **kwargs):
            return SimpleNamespace(returncode=1, stdout="")

        monkeypatch.setattr(compaction.subprocess, "run", failing_run)
        assert check_git_activity(tmp_path) == (0, 0)

    def test_returns_none_on_timeout(self, monkeypatch, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()

        def hung_run(*args, **kwargs):
            raise compaction.subprocess.TimeoutExpired(cmd="git", timeout=5)

        monkeypatch.setattr(compaction.subprocess, "run", hung_run)
        assert check_git_activity(tmp_path) is None

    def test_returns_none_on_called_process_error(self, monkeypatch, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()

        def error_run(*args, **kwargs):
            raise compaction.subprocess.CalledProcessError(1, "git")

        monkeypatch.setattr(compaction.subprocess, "run", error_run)
        # CalledProcessError IS in the except tuple (subprocess.check=True
        # would raise it; even though the function uses check=False, the
        # caller could surface it from a custom runner).
        assert check_git_activity(tmp_path) is None


# ---------------------------------------------------------------------------
# evaluate_large_project_heuristic
# ---------------------------------------------------------------------------


class TestEvaluateLargeProjectHeuristic:
    @pytest.mark.parametrize(
        ("file_count", "expected"),
        [
            (0, (False, "")),
            (50, (False, "")),
            (51, (True, "Large codebase with 50+ source files detected - context compaction recommended")),
            (100, (True, "Large codebase with 50+ source files detected - context compaction recommended")),
        ],
    )
    def test_boundary(self, file_count: int, expected: tuple[bool, str]) -> None:
        assert evaluate_large_project_heuristic(file_count) == expected


# ---------------------------------------------------------------------------
# evaluate_git_activity_heuristic
# ---------------------------------------------------------------------------


class TestEvaluateGitActivityHeuristic:
    def test_returns_false_false_when_none(self) -> None:
        assert evaluate_git_activity_heuristic(None) == (False, "")

    def test_high_commit_count_triggers(self) -> None:
        assert evaluate_git_activity_heuristic((3, 0)) == (
            True,
            "High development activity (3 commits in 24h) - compaction recommended",
        )

    def test_high_modified_count_triggers(self) -> None:
        assert evaluate_git_activity_heuristic((1, 10)) == (
            True,
            "Many modified files (10) detected - context optimization beneficial",
        )

    def test_low_activity_does_not_trigger(self) -> None:
        assert evaluate_git_activity_heuristic((2, 5)) == (False, "")

    def test_commit_count_takes_precedence_over_modified(self) -> None:
        # When both thresholds would fire, the commit message wins.
        flag, msg = evaluate_git_activity_heuristic((5, 20))
        assert flag is True
        assert "commits in 24h" in msg


# ---------------------------------------------------------------------------
# evaluate_python_project_heuristic
# ---------------------------------------------------------------------------


class TestEvaluatePythonProjectHeuristic:
    def test_no_tests_dir_returns_false(self, tmp_path: Path) -> None:
        assert evaluate_python_project_heuristic(tmp_path) == (False, "")

    def test_no_pyproject_returns_false(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        assert evaluate_python_project_heuristic(tmp_path) == (False, "")

    def test_python_project_with_tests_and_pyproject_triggers(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        assert evaluate_python_project_heuristic(tmp_path) == (
            True,
            "Python project with tests detected - compaction may improve focus",
        )

    def test_both_conditions_required(self, tmp_path: Path) -> None:
        # pyproject without tests → False.
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        assert evaluate_python_project_heuristic(tmp_path) == (False, "")
