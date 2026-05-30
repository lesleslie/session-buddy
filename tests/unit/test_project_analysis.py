from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_UTILS_PACKAGE = types.ModuleType("session_buddy.utils")
_UTILS_PACKAGE.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("session_buddy.utils", _UTILS_PACKAGE)

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "project_analysis.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.project_analysis", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.project_analysis", _MODULE)
_SPEC.loader.exec_module(_MODULE)

analyze_project_context = _MODULE.analyze_project_context


@pytest.mark.asyncio
async def test_analyze_project_context_detects_project_features(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("readme")
    (tmp_path / "requirements.txt").write_text("pytest\n")
    (tmp_path / "uv.lock").write_text("")
    (tmp_path / ".mcp.json").write_text("{}")

    result = await analyze_project_context(tmp_path)

    assert result == {
        "python_project": True,
        "git_repo": True,
        "has_tests": True,
        "has_docs": True,
        "has_requirements": True,
        "has_uv_lock": True,
        "has_mcp_config": True,
    }


@pytest.mark.asyncio
async def test_analyze_project_context_missing_directory(tmp_path: Path) -> None:
    result = await analyze_project_context(tmp_path / "missing")

    assert result == {
        "python_project": False,
        "git_repo": False,
        "has_tests": False,
        "has_docs": False,
        "has_requirements": False,
        "has_uv_lock": False,
        "has_mcp_config": False,
    }


@pytest.mark.asyncio
async def test_analyze_project_context_os_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == tmp_path:
            raise OSError("boom")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    result = await analyze_project_context(tmp_path)

    assert result == {
        "python_project": False,
        "git_repo": False,
        "has_tests": False,
        "has_docs": False,
        "has_requirements": False,
        "has_uv_lock": False,
        "has_mcp_config": False,
    }
