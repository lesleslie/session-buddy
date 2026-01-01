"""Project context analysis for session management.

This module provides utilities for analyzing project structure, detecting
frameworks, and gathering project health indicators.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from session_buddy.utils.git_operations import is_git_repository

if TYPE_CHECKING:
    from pathlib import Path


def check_readme_exists(project_dir: Path) -> bool:
    """Check if README file exists."""
    return any(
        (project_dir / name).exists()
        for name in ("README.md", "README.rst", "README.txt", "readme.md")
    )


def check_venv_exists(project_dir: Path) -> bool:
    """Check if virtual environment exists."""
    return any(
        (project_dir / name).exists() for name in (".venv", "venv", ".env", "env")
    )


def check_tests_exist(project_dir: Path) -> bool:
    """Check if test directories exist."""
    return any((project_dir / name).exists() for name in ("tests", "test", "testing"))


def check_docs_exist(project_dir: Path) -> bool:
    """Check if documentation directories exist."""
    return any((project_dir / name).exists() for name in ("docs", "documentation"))


def check_ci_cd_exists(project_dir: Path) -> bool:
    """Check if CI/CD configuration exists."""
    return any(
        (project_dir / name).exists()
        for name in (".github", ".gitlab-ci.yml", ".travis.yml", "Jenkinsfile")
    )


def get_basic_project_indicators(project_dir: Path) -> dict[str, bool]:
    """Get basic project structure indicators."""
    return {
        "has_pyproject_toml": (project_dir / "pyproject.toml").exists(),
        "has_setup_py": (project_dir / "setup.py").exists(),
        "has_requirements_txt": (project_dir / "requirements.txt").exists(),
        "has_readme": check_readme_exists(project_dir),
        "has_git_repo": is_git_repository(project_dir),
        "has_venv": check_venv_exists(project_dir),
        "has_tests": check_tests_exist(project_dir),
        "has_src_structure": (project_dir / "src").exists(),
        "has_docs": check_docs_exist(project_dir),
        "has_ci_cd": check_ci_cd_exists(project_dir),
    }


def check_framework_imports(content: str, indicators: dict[str, bool]) -> None:
    """Check for framework imports in file content."""
    if "import fastapi" in content or "from fastapi" in content:
        indicators["uses_fastapi"] = True
    if "import django" in content or "from django" in content:
        indicators["uses_django"] = True
    if "import flask" in content or "from flask" in content:
        indicators["uses_flask"] = True


def detect_python_frameworks(
    python_files: list[Path], indicators: dict[str, bool]
) -> None:
    """Detect Python frameworks from file content."""
    for py_file in python_files[:10]:  # Sample first 10 files
        try:
            with py_file.open("r", encoding="utf-8") as f:
                content = f.read(1000)  # Read first 1000 chars
                check_framework_imports(content, indicators)
        except (UnicodeDecodeError, PermissionError):
            continue


def add_python_context_indicators(
    project_dir: Path, indicators: dict[str, bool]
) -> None:
    """Add Python-specific context indicators."""
    with suppress(Exception):
        python_files = list(project_dir.glob("**/*.py"))
        indicators["has_python_files"] = len(python_files) > 0
        detect_python_frameworks(python_files, indicators)


async def analyze_project_context(project_dir: Path) -> dict[str, bool]:
    """Analyze project directory for common indicators and patterns."""
    indicators = get_basic_project_indicators(project_dir)
    add_python_context_indicators(project_dir, indicators)
    return indicators
