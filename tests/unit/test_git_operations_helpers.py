from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest


def _load_git_operations_module():
    package_name = "session_buddy.utils"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = []  # type: ignore[attr-defined]
        sys.modules[package_name] = package

    git_worktrees = types.ModuleType("session_buddy.utils.git_worktrees")
    git_worktrees.WorktreeInfo = object  # type: ignore[attr-defined]
    git_worktrees._validate_prune_delay = lambda value: (True, "")  # type: ignore[attr-defined]
    git_worktrees.create_checkpoint_commit = lambda *args, **kwargs: (True, "hash", [])  # type: ignore[attr-defined]
    git_worktrees.create_commit = lambda *args, **kwargs: (True, "hash")  # type: ignore[attr-defined]
    git_worktrees.get_git_status = lambda *args, **kwargs: ([], [])  # type: ignore[attr-defined]
    git_worktrees.get_staged_files = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    git_worktrees.get_worktree_info = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    git_worktrees.is_git_operation_in_progress = lambda *args, **kwargs: False  # type: ignore[attr-defined]
    git_worktrees.is_git_repository = lambda *args, **kwargs: True  # type: ignore[attr-defined]
    git_worktrees.is_git_worktree = lambda *args, **kwargs: False  # type: ignore[attr-defined]
    git_worktrees.list_worktrees = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    git_worktrees.get_git_root = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    git_worktrees.schedule_automatic_git_gc = lambda *args, **kwargs: (True, "scheduled")  # type: ignore[attr-defined]
    git_worktrees.stage_files = lambda *args, **kwargs: True  # type: ignore[attr-defined]
    sys.modules["session_buddy.utils.git_worktrees"] = git_worktrees

    module_path = (
        Path(__file__).resolve().parents[2]
        / "session_buddy"
        / "utils"
        / "git_operations.py"
    )
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.git_operations",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


go = _load_git_operations_module()


def test_parse_and_format_helpers() -> None:
    staged, untracked = go._parse_git_status(
        ["A  tracked.txt", "M  modified.txt", "D  deleted.txt", "?? new.txt", "ignored"]
    )

    assert staged == ["tracked.txt", "modified.txt", "deleted.txt"]
    assert untracked == ["new.txt"]
    assert go._format_untracked_files([]) == ["✅ No untracked files"]
    assert go._format_untracked_files(["a", "b"]) == ["📁 Untracked Files:", "   • a", "   • b"]


def test_run_git_command_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class Result:
        def __init__(self, returncode: int, stderr: str = "") -> None:
            self.returncode = returncode
            self.stderr = stderr

    def fake_run(command, cwd=None, capture_output=False, text=False, check=False):
        if command[1:] == ["add", "-A"]:
            return Result(0)
        return Result(1, "boom")

    monkeypatch.setattr(go.subprocess, "run", fake_run)

    output: list[str] = []
    assert go._run_git_command(["git", "add", "-A"], tmp_path, output) is True
    assert go._run_git_command(["git", "commit", "-m", "msg"], tmp_path, output) is False
    assert output[-1] == "⚠️ commit -m failed: boom"


def test_stage_and_commit_files_covers_success_failure_and_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, cwd=None, capture_output=False, text=False, check=False):
        calls.append(command)
        if command == ["git", "add", "-A"]:
            return types.SimpleNamespace(returncode=0, stderr="")
        if command == ["git", "commit", "-m", "ok"]:
            return types.SimpleNamespace(returncode=0, stderr="")
        if command == ["git", "commit", "-m", "fail"]:
            return types.SimpleNamespace(returncode=1, stderr="no commit")
        if command == ["git", "add", "one.txt"]:
            return types.SimpleNamespace(returncode=0, stderr="")
        if command == ["git", "add", "two.txt"]:
            return types.SimpleNamespace(returncode=1, stderr="bad add")
        raise RuntimeError("unexpected")

    monkeypatch.setattr(go.subprocess, "run", fake_run)

    success, output = go._stage_and_commit_files(tmp_path, "ok")
    assert success is True
    assert "✅ Committed changes: ok" in output

    success, output = go._stage_and_commit_files(tmp_path, "fail")
    assert success is False
    assert "⚠️ Commit failed" in output

    success, output = go._stage_and_commit_files(tmp_path, "msg", ["one.txt", "two.txt"])
    assert success is False
    assert any("failed" in line for line in output)

    monkeypatch.setattr(
        go,
        "_stage_files",
        Mock(side_effect=RuntimeError("boom")),
    )
    success, output = go._stage_and_commit_files(tmp_path, "msg")
    assert success is False
    assert output[-1] == "❌ Git operation error: boom"


def test_optimize_git_repository_covers_all_outcomes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Result:
        def __init__(self, returncode: int, stderr: str = "") -> None:
            self.returncode = returncode
            self.stderr = stderr

    outputs = [
        Result(0),
        Result(0),
        Result(1, "prune failed"),
    ]

    def fake_run(*args, **kwargs):
        return outputs.pop(0)

    monkeypatch.setattr(go.subprocess, "run", fake_run)
    result = go._optimize_git_repository(tmp_path)
    assert "Git garbage collection completed" in result[0]
    assert "Pruned remote tracking branches" in result[1]

    outputs[:] = [Result(1, "gc failed"), Result(1, "prune failed")]
    result = go._optimize_git_repository(tmp_path)
    assert any("Git gc failed" in line for line in result)
    assert any("Remote pruning skipped" in line for line in result)

    def raising_run(*args, **kwargs):
        raise RuntimeError("explode")

    monkeypatch.setattr(go.subprocess, "run", raising_run)
    result = go._optimize_git_repository(tmp_path)
    assert result == ["⚠️ Git optimization error: explode"]
