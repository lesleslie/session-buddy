"""Subagent lockfile marker MCP tool for Session-Buddy.

Exposes ``subagent_marker`` so external orchestrators (e.g., Mahavishnu's
``SessionBuddyPool.worker_execute``) can mark/clear the per-working-tree
``<working_dir>/.session-buddy/subagent.lock`` through the MCP server
instead of shelling out to the CLI.

The tool wraps the producer half of the lockfile contract that lives in
``session_buddy.checkpoint.subagent_detector.SubagentDetector.write``.
See ``docs/checkpoint/STASH_CLOBBER.md`` for the full cross-repo story.

Return-shape contract:

* ``subagent_marker`` -> ``{"success": bool, "lockfile_path": str, "action": str,
  "error": optional, "error_code": optional}``
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mcp_common.fastmcp import FastMCP

from ...checkpoint.subagent_detector import (
    LockfileSignalSource,
    SubagentDetector,
)

logger = logging.getLogger(__name__)

_MAX_PATH_LEN = 4096  # POSIX PATH_MAX is 4096 on Linux; macOS is 1024.

_VALID_ACTIONS = frozenset({"mark", "clear"})


def _is_safe_working_dir(working_dir: str) -> bool:
    """Validate the user-supplied working_dir at the MCP boundary.

    Defense in depth — the underlying ``SubagentDetector.write`` will also
    reject path traversal at the OS layer, but rejecting early keeps the
    error message tight and prevents an attacker from probing internal
    state via malformed paths.
    """
    if not working_dir or len(working_dir) >= _MAX_PATH_LEN:
        return False
    if not working_dir.startswith("/"):
        return False  # require absolute
    if ".." in Path(working_dir).parts:
        return False
    # Reject ASCII control chars (defense against shell-injection shenanigans
    # if a caller passes the result through a downstream subprocess).
    return not any(ord(c) < 0x20 for c in working_dir)


def register_subagent_marker_tools(mcp: FastMCP) -> None:
    """Register the subagent lockfile marker MCP tool.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool()
    async def subagent_marker(
        working_dir: str,
        action: str,
    ) -> str:
        """Mark or clear the subagent lockfile for ``working_dir``.

        Args:
            working_dir: Absolute path to the working tree whose lockfile
                should be mutated. The lockfile lives at
                ``<working_dir>/.session-buddy/subagent.lock``.
            action: Either ``"mark"`` (create the lockfile with
                auto-generated metadata) or ``"clear"`` (unlink it).

        Returns:
            JSON string with ``success``, ``lockfile_path``, and ``action``
            on success or ``error`` / ``error_code`` on failure.
        """
        if not _is_safe_working_dir(working_dir):
            return json.dumps(
                {
                    "success": False,
                    "error": f"Invalid working_dir: {working_dir!r}",
                    "error_code": "invalid_working_dir",
                    "action": action,
                }
            )
        if action not in _VALID_ACTIONS:
            return json.dumps(
                {
                    "success": False,
                    "error": (
                        f"action must be one of {sorted(_VALID_ACTIONS)!r}, "
                        f"got {action!r}"
                    ),
                    "error_code": "invalid_action",
                    "action": action,
                }
            )

        try:
            wd = Path(working_dir)
            if not wd.is_dir():
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Not a directory: {working_dir}",
                        "error_code": "not_a_directory",
                        "action": action,
                    }
                )
            lock = wd / ".session-buddy" / "subagent.lock"
            detector = SubagentDetector(wd, LockfileSignalSource(lock))
            detector.write(active=(action == "mark"))
            return json.dumps(
                {
                    "success": True,
                    "lockfile_path": str(lock),
                    "action": action,
                }
            )
        except Exception as exc:
            # ``SubagentDetector.write`` already swallows OSError per the
            # fail-open contract, so any exception here is a programming
            # error (e.g., the working_dir became invalid mid-call). Log
            # and surface a structured error rather than raising past
            # the MCP boundary.
            logger.exception("subagent_marker failed")
            return json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "error_code": "marker_exception",
                    "action": action,
                }
            )

    logger.info("Subagent marker tool registered successfully")


__all__ = ["register_subagent_marker_tools"]
