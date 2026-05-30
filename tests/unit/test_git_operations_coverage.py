from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest


def _load_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repo_root = Path(__file__).resolve().parents[2]

session_buddy_pkg = sys.modules.setdefault("session_buddy", types.ModuleType("session_buddy"))
session_buddy_pkg.__path__ = [str(repo_root / "session_buddy")]  # type: ignore[attr-defined]

utils_pkg = sys.modules.setdefault("session_buddy.utils", types.ModuleType("session_buddy.utils"))
utils_pkg.__path__ = [str(repo_root / "session_buddy" / "utils")]  # type: ignore[attr-defined]

git_worktrees = _load_module(
    "session_buddy.utils.git_worktrees",
    repo_root / "session_buddy" / "utils" / "git_worktrees.py",
)
setattr(utils_pkg, "git_worktrees", git_worktrees)

git_operations = _load_module(
    "session_buddy.utils.git_operations",
    repo_root / "session_buddy" / "utils" / "git_operations.py",
)
setattr(utils_pkg, "git_operations", git_operations)


class DummyResult:
    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr


def test_parse_and_format_untracked_files() -> None:
    staged, untracked = git_operations._parse_git_status(
        [
            "A  staged.txt",
            "M  modified.txt",
            "D  deleted.txt",
            "?? untracked.txt",
            "?? another.txt",
        ]
    )

    assert staged == ["staged.txt", "modified.txt", "deleted.txt"]
    assert untracked == ["untracked.txt", "another.txt"]
    assert git_operations._format_untracked_files([]) == ["✅ No untracked files"]

    formatted = git_operations._format_untracked_files([f"file{i}.txt" for i in range(12)])
    assert formatted[0] == "📁 Untracked Files:"
    assert formatted[-1] == "   ... and 2 more files"


def test_run_git_command_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    output: list[str] = []

    monkeypatch.setattr(
        git_operations.subprocess,
        "run",
        lambda *args, **kwargs: DummyResult(returncode=0),
    )
    assert git_operations._run_git_command(["git", "status"], Path.cwd(), output) is True

    monkeypatch.setattr(
        git_operations.subprocess,
        "run",
        lambda *args, **kwargs: DummyResult(returncode=1, stderr="boom"),
    )
    assert git_operations._run_git_command(["git", "status"], Path.cwd(), output) is False
    assert any("status failed: boom" in line for line in output)


def test_stage_and_commit_files_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output: list[str] = []

    monkeypatch.setattr(git_operations, "_stage_files", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        git_operations,
        "_commit_staged_changes",
        lambda *args, **kwargs: (True, ["committed"]),
    )

    ok, lines = git_operations._stage_and_commit_files(tmp_path, "msg", ["a.txt"])
    assert ok is True
    assert lines == ["committed"]

    monkeypatch.setattr(git_operations, "_stage_files", lambda *args, **kwargs: False)
    ok, lines = git_operations._stage_and_commit_files(tmp_path, "msg", ["a.txt"])
    assert ok is False
    assert lines == []

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(git_operations, "_stage_files", boom)
    ok, lines = git_operations._stage_and_commit_files(tmp_path, "msg", ["a.txt"])
    assert ok is False
    assert any("Git operation error" in line for line in lines)


def test_stage_files_and_commit_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output: list[str] = []
    calls: list[list[str]] = []

    def fake_run(command: list[str], current_dir: Path, output_lines: list[str]) -> bool:
        calls.append(command)
        return True

    monkeypatch.setattr(git_operations, "_run_git_command", fake_run)

    assert git_operations._stage_files(tmp_path, ["one.txt", "two.txt"], output) is True
    assert calls == [["git", "add", "one.txt"], ["git", "add", "two.txt"]]

    calls.clear()
    assert git_operations._stage_files(tmp_path, None, output) is True
    assert calls == [["git", "add", "-A"]]

    monkeypatch.setattr(git_operations, "_run_git_command", lambda *args, **kwargs: False)
    output.clear()
    assert git_operations._stage_files(tmp_path, None, output) is False
    assert "Failed to stage changes" in output[-1]

    monkeypatch.setattr(git_operations, "_run_git_command", lambda *args, **kwargs: True)
    ok, lines = git_operations._commit_staged_changes(tmp_path, "msg", output)
    assert ok is True
    assert any("Committed changes: msg" in line for line in lines)

    monkeypatch.setattr(git_operations, "_run_git_command", lambda *args, **kwargs: False)
    ok, lines = git_operations._commit_staged_changes(tmp_path, "msg", output)
    assert ok is False
    assert any("Commit failed" in line for line in lines)


def test_optimize_git_repository_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        git_operations.subprocess,
        "run",
        lambda *args, **kwargs: DummyResult(returncode=0),
    )
    result = git_operations._optimize_git_repository(tmp_path)
    assert result == [
        "🗑️ Git garbage collection completed",
        "🌿 Pruned remote tracking branches",
    ]

    calls: list[list[str]] = []

    def fake_run(command: list[str], cwd: Path, capture_output: bool, text: bool, check: bool) -> DummyResult:
        calls.append(command)
        if command == ["git", "gc", "--auto"]:
            return DummyResult(returncode=1, stderr="gc failed")
        return DummyResult(returncode=1, stderr="prune failed")

    monkeypatch.setattr(git_operations.subprocess, "run", fake_run)
    result = git_operations._optimize_git_repository(tmp_path)
    assert result == [
        "⚠️ Git gc failed: gc failed",
        "ℹ️ Remote pruning skipped (no remote or access issues)",
    ]
    assert calls == [["git", "gc", "--auto"], ["git", "remote", "prune", "origin"]]

    def boom(*args, **kwargs) -> DummyResult:
        raise RuntimeError("boom")

    monkeypatch.setattr(git_operations.subprocess, "run", boom)
    result = git_operations._optimize_git_repository(tmp_path)
    assert result == ["⚠️ Git optimization error: boom"]
