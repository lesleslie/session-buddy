from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


_COMPACTION_PATH = (
    Path(__file__).resolve().parents[2]
    / "session_buddy"
    / "utils"
    / "quality"
    / "compaction.py"
)
_COMPACTION_SPEC = importlib.util.spec_from_file_location(
    "session_buddy.utils.quality.compaction",
    _COMPACTION_PATH,
)
assert _COMPACTION_SPEC is not None and _COMPACTION_SPEC.loader is not None
_COMPACTION_MODULE = importlib.util.module_from_spec(_COMPACTION_SPEC)
sys.modules[_COMPACTION_SPEC.name] = _COMPACTION_MODULE
_COMPACTION_SPEC.loader.exec_module(_COMPACTION_MODULE)


def test_reason_helpers() -> None:
    get_default_compaction_reason = _COMPACTION_MODULE.get_default_compaction_reason
    get_fallback_compaction_reason = _COMPACTION_MODULE.get_fallback_compaction_reason

    assert "manageable" in get_default_compaction_reason().lower()
    assert "precaution" in get_fallback_compaction_reason().lower()


def test_count_significant_files_ignores_hidden_and_limits(tmp_path: Path) -> None:
    count_significant_files = _COMPACTION_MODULE.count_significant_files

    (tmp_path / ".hidden.py").write_text("print('hidden')")
    for index in range(3):
        (tmp_path / f"file_{index}.py").write_text("print('ok')")
    (tmp_path / "notes.txt").write_text("ignore")

    assert count_significant_files(tmp_path) == 3


def test_count_significant_files_stops_after_threshold(tmp_path: Path) -> None:
    count_significant_files = _COMPACTION_MODULE.count_significant_files

    for index in range(60):
        (tmp_path / f"file_{index}.py").write_text("print('ok')")

    assert count_significant_files(tmp_path) == 51


def test_check_git_activity_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    compaction = _COMPACTION_MODULE

    assert compaction.check_git_activity(tmp_path) is None

    (tmp_path / ".git").mkdir()

    def fake_run(cmd, **kwargs):
        if cmd[1] == "log":
            return SimpleNamespace(returncode=0, stdout="a\nb\nc\n")
        if cmd[1] == "status":
            return SimpleNamespace(returncode=0, stdout=" M one.py\n M two.py\n")
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(compaction.subprocess, "run", fake_run)

    assert compaction.check_git_activity(tmp_path) == (3, 2)

    def failing_status_run(cmd, **kwargs):
        if cmd[1] == "log":
            return SimpleNamespace(returncode=1, stdout="")
        if cmd[1] == "status":
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(compaction.subprocess, "run", failing_status_run)
    assert compaction.check_git_activity(tmp_path) == (0, 0)

    def failing_run(*args, **kwargs):
        raise compaction.subprocess.TimeoutExpired(cmd="git", timeout=5)

    monkeypatch.setattr(compaction.subprocess, "run", failing_run)
    assert compaction.check_git_activity(tmp_path) is None


def test_compaction_heuristics() -> None:
    evaluate_git_activity_heuristic = _COMPACTION_MODULE.evaluate_git_activity_heuristic
    evaluate_large_project_heuristic = _COMPACTION_MODULE.evaluate_large_project_heuristic
    evaluate_python_project_heuristic = _COMPACTION_MODULE.evaluate_python_project_heuristic

    assert evaluate_large_project_heuristic(51) == (
        True,
        "Large codebase with 50+ source files detected - context compaction recommended",
    )
    assert evaluate_large_project_heuristic(50) == (False, "")

    assert evaluate_git_activity_heuristic((3, 1)) == (
        True,
        "High development activity (3 commits in 24h) - compaction recommended",
    )
    assert evaluate_git_activity_heuristic((1, 10)) == (
        True,
        "Many modified files (10) detected - context optimization beneficial",
    )
    assert evaluate_git_activity_heuristic(None) == (False, "")

    project = Path("/tmp/compaction-python-project")
    assert evaluate_python_project_heuristic(project) == (False, "")


def test_evaluate_python_project_heuristic(tmp_path: Path) -> None:
    evaluate_python_project_heuristic = _COMPACTION_MODULE.evaluate_python_project_heuristic

    assert evaluate_python_project_heuristic(tmp_path) == (False, "")

    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
    assert evaluate_python_project_heuristic(tmp_path) == (
        True,
        "Python project with tests detected - compaction may improve focus",
    )
