"""Git worktree MCP tools for Session-Buddy.

Exposes ``list_worktrees`` / ``create_worktree`` / ``remove_worktree`` so
external orchestrators (e.g., Mahavishnu ``SessionBuddyWorktreeProvider``)
can manage git worktrees through Session-Buddy's MCP server instead of
calling git directly.

Return-shape contract (matches what Mahavishnu's ``WorktreeCoordinator``
expects via ``coordinator.list_worktrees`` / ``coordinator.remove_worktree``):

* ``list_worktrees`` -> ``{"success": bool, "worktrees": [{"path", "branch",
  "head"}, ...], "error": optional}``
* ``create_worktree`` -> ``{"success": bool, "head", "branch",
  "worktree_path", "error": optional, "error_code": optional}``
* ``remove_worktree`` -> ``{"success": bool, "force", "force_reason",
  "force_required": bool, "safety_check": "uncommitted_changes" |
  "dependency_block" | None, "backup_path": optional, "error": optional,
  "error_code": optional}``
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp_common.fastmcp import FastMCP

from ...utils.git_worktrees import (
    is_git_repository,
    list_worktrees as _list_worktrees,
    create_worktree as _create_worktree,
    remove_worktree as _remove_worktree,
)

logger = logging.getLogger(__name__)


def _serialize_worktrees(worktrees: list[Any]) -> list[dict[str, Any]]:
    """Convert WorktreeInfo dataclasses to JSON-safe dicts."""
    return [
        {
            "path": str(wt.path),
            "branch": wt.branch,
            "head": wt.head,
            "is_bare": wt.is_bare,
            "is_detached": wt.is_detached,
            "is_main_worktree": wt.is_main_worktree,
            "locked": wt.locked,
            "prunable": wt.prunable,
        }
        for wt in worktrees
    ]


def register_worktree_tools(mcp: FastMCP) -> None:
    """Register git worktree management tools.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool()
    async def list_worktrees(repository_path: str) -> str:
        """List git worktrees in the given repository.

        Args:
            repository_path: Absolute or repo-relative path to a git repository.

        Returns:
            JSON string ``{"success": bool, "worktrees": [...], ...}``. Each
            entry has ``path``, ``branch``, ``head``, and metadata flags.
        """
        try:
            repo = Path(repository_path)
            if not is_git_repository(repo):
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Not a git repository: {repository_path}",
                        "error_code": "not_git_repository",
                        "worktrees": [],
                    }
                )
            worktrees = _list_worktrees(repo)
            return json.dumps(
                {
                    "success": True,
                    "repository_path": str(repo),
                    "count": len(worktrees),
                    "worktrees": _serialize_worktrees(worktrees),
                }
            )
        except Exception as exc:
            logger.error("list_worktrees failed: %s", exc)
            return json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "error_code": "list_failed",
                    "worktrees": [],
                }
            )

    @mcp.tool()
    async def create_worktree(
        repository_path: str,
        worktree_path: str,
        branch: str,
        create_branch: bool = False,
    ) -> str:
        """Create a new git worktree.

        Args:
            repository_path: Path to the git repository.
            worktree_path: Absolute path where the new worktree should be created.
            branch: Branch name to check out (or to create when ``create_branch``).
            create_branch: If True, create ``branch`` first (equivalent to
                ``git worktree add -b <branch> <path>``).

        Returns:
            JSON string with ``success``, ``head``, ``branch``, ``worktree_path``
            on success or ``error``/``error_code`` on failure.
        """
        try:
            repo = Path(repository_path)
            ok, info = _create_worktree(
                repository_path=repo,
                worktree_path=worktree_path,
                branch=branch,
                create_branch=create_branch,
            )
            payload: dict[str, Any] = {"success": ok}
            payload.update(info)
            return json.dumps(payload)
        except Exception as exc:
            logger.error("create_worktree failed: %s", exc)
            return json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "error_code": "create_exception",
                }
            )

    @mcp.tool()
    async def remove_worktree(
        repository_path: str,
        worktree_path: str,
        force: bool = False,
        force_reason: str | None = None,
    ) -> str:
        """Remove a git worktree, with optional force + reason.

        Args:
            repository_path: Path to the git repository.
            worktree_path: Absolute path of the worktree to remove.
            force: If True, pass ``--force`` to ``git worktree remove``.
            force_reason: Required when ``force=True``; preserved in the
                returned ``force_reason`` for audit logging.

        Returns:
            JSON string with ``success``, ``force_required``, ``safety_check``,
            and ``error`` fields. When ``success=False`` and ``force_required=True``,
            the caller should re-invoke with ``force=True`` (and ``force_reason``).
        """
        try:
            repo = Path(repository_path)
            ok, info = _remove_worktree(
                repository_path=repo,
                worktree_path=worktree_path,
                force=force,
                force_reason=force_reason,
            )
            payload: dict[str, Any] = {"success": ok}
            payload.update(info)
            return json.dumps(payload)
        except Exception as exc:
            logger.error("remove_worktree failed: %s", exc)
            return json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "error_code": "remove_exception",
                    "force_required": True,
                    "safety_check": "exception",
                }
            )

    logger.info("Git worktree tools registered successfully")


__all__ = ["register_worktree_tools"]
