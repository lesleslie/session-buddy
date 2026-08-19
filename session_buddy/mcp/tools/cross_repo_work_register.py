"""Register store_cross_repo_work on a FastMCP server.

Composition:
  - @require_auth(optional=False) — session-buddy's local auth wrapper;
    requires a valid token kwarg.
  - @mcp_server.tool(name="store_cross_repo_work") — FastMCP registration.

The client-visible name is "mcp__session-buddy__store_cross_repo_work"
(the client prefix is added by FastMCP).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_common.fastmcp import FastMCP

from session_buddy.core.checkpoint.manifest_resolver import resolve_manifest_path
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.mcp.auth import require_auth
from session_buddy.mcp.tools.cross_repo_work import (
    CrossRepoStoreResult,
    StoreCrossRepoWorkRequest,
    store_cross_repo_work,
)
from session_buddy.utils.database_tools import require_reflection_database


def register_cross_repo_work_tools(mcp_server: FastMCP) -> None:
    """Register store_cross_repo_work on the given FastMCP server instance.

    The merge primitive is module-level (stateless); the DuckDB connection
    is acquired per-call via require_reflection_database().conn.
    """
    merge_primitive = MergePrimitive()

    @require_auth(optional=False)
    @mcp_server.tool(name="store_cross_repo_work")
    async def _store_cross_repo_work(
        request: StoreCrossRepoWorkRequest,
        token: str | None = None,  # populated by FastMCP auth context
    ) -> CrossRepoStoreResult:
        ecosystem_path = resolve_manifest_path()
        adapter = await require_reflection_database()
        conn = adapter.conn
        return await store_cross_repo_work(
            request=request,
            merge_primitive=merge_primitive,
            conn=conn,
            ecosystem_path=ecosystem_path,
        )
