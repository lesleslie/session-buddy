"""Project analysis utilities.

This module provides project structure and context analysis functions.
Extracted to break circular dependencies between server_core and quality_engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


async def analyze_project_context(project_dir: Path) -> dict[str, bool]:
    """Analyze project structure and context with enhanced error handling.

    Args:
        project_dir: Path to the project directory to analyze

    Returns:
        Dictionary with boolean flags for various project characteristics:
        - python_project: Has pyproject.toml
        - git_repo: Has .git directory
        - has_tests: Has test files or directories
        - has_docs: Has README.md or docs directory
        - has_requirements: Has requirements.txt
        - has_uv_lock: Has uv.lock file
        - has_mcp_config: Has .mcp.json file

    """
    try:
        # Ensure project_dir exists and is accessible
        if not project_dir.exists():
            return {
                "python_project": False,
                "git_repo": False,
                "has_tests": False,
                "has_docs": False,
                "has_requirements": False,
                "has_uv_lock": False,
                "has_mcp_config": False,
            }

        return {
            "python_project": (project_dir / "pyproject.toml").exists(),
            "git_repo": (project_dir / ".git").exists(),
            "has_tests": any(project_dir.glob("test*"))
            or any(project_dir.glob("**/test*")),
            "has_docs": (project_dir / "README.md").exists()
            or any(project_dir.glob("docs/**")),
            "has_requirements": (project_dir / "requirements.txt").exists(),
            "has_uv_lock": (project_dir / "uv.lock").exists(),
            "has_mcp_config": (project_dir / ".mcp.json").exists(),
        }
    except OSError, PermissionError:
        # Return safe defaults on error
        return {
            "python_project": False,
            "git_repo": False,
            "has_tests": False,
            "has_docs": False,
            "has_requirements": False,
            "has_uv_lock": False,
            "has_mcp_config": False,
        }
