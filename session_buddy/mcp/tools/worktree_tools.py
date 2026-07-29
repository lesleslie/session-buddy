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
    create_worktree as _create_worktree,
)
from ...utils.git_worktrees import (
    is_git_repository,
)
from ...utils.git_worktrees import (
    list_worktrees as _list_worktrees,
)
from ...utils.git_worktrees import (
    remove_worktree as _remove_worktree,
)

logger = logging.getLogger(__name__)

# Branch names can include alphanumeric, dash, underscore, slash (for
# remote-style refs) and dot (for semver tags). Reject path-traversal and
# any leading ``-`` so the value can't be parsed as a CLI flag by git.
import re as _re_branch

_BRANCH_PATTERN = _re_branch.compile(r"^[a-zA-Z0-9_/.-]+$")
_MAX_BRANCH_LEN = 100
_MAX_PATH_LEN = 500


def _is_valid_branch(branch: str) -> bool:
    if not branch or len(branch) >= _MAX_BRANCH_LEN:
        return False
    if branch.startswith("-"):  # defense against CLI flag injection
        return False
    if ".." in branch:
        return False
    return bool(_BRANCH_PATTERN.match(branch))


def _is_safe_worktree_path(worktree_path: str) -> bool:
    if not worktree_path or len(worktree_path) >= _MAX_PATH_LEN:
        return False
    if not worktree_path.startswith("/"):
        return False  # require absolute
    if ".." in worktree_path:
        return False
    # Defense against CLI flag injection: reject any path whose basename
    # starts with ``-`` (e.g., ``/tmp/-rf``).
    basename = worktree_path.rstrip("/").rsplit("/", 1)[-1]
    if basename.startswith("-"):
        return False
    # Reject any ASCII control character (NUL, TAB, newline, etc.) — these
    # either have special meaning to shells/filesystems or can mask
    # downstream argument-injection attempts.
    return not any(ord(c) < 0x20 for c in worktree_path)


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
            logger.exception("list_worktrees failed")
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
        # Validate user-supplied inputs at the MCP boundary so a malicious
        # caller cannot smuggle CLI flags or path-traversal sequences.
        if not _is_valid_branch(branch):
            return json.dumps(
                {
                    "success": False,
                    "error": "Invalid branch name",
                    "error_code": "invalid_branch",
                }
            )
        if not _is_safe_worktree_path(worktree_path):
            return json.dumps(
                {
                    "success": False,
                    "error": "Invalid worktree path",
                    "error_code": "invalid_worktree_path",
                }
            )

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
            logger.exception("create_worktree failed")
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
        # Validate user-supplied inputs at the MCP boundary
        if not _is_safe_worktree_path(worktree_path):
            return json.dumps(
                {
                    "success": False,
                    "error": "Invalid worktree path",
                    "error_code": "invalid_worktree_path",
                    "force_required": True,
                    "safety_check": "invalid_input",
                }
            )

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
            logger.exception("remove_worktree failed")
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
