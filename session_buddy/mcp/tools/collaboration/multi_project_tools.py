"""Multi-project coordination MCP tools.

Wraps :class:`MultiProjectCoordinator` from
:mod:`session_buddy.multi_project_coordinator` as MCP tools for
cross-project session groups, dependency tracking, and cross-project
search.

Closes the gap identified in
``docs/feature-tracking/TOOL_REGISTRATION_GAPS.md`` (2026-09-09).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from session_buddy.utils.error_management import _get_logger
from session_buddy.utils.messages import ToolMessages

if TYPE_CHECKING:
    from mcp_common.fastmcp import FastMCP

    from session_buddy.multi_project_coordinator import (
        MultiProjectCoordinator,
        ProjectGroup,
        ProjectDependency,
        SessionLink,
    )


# ---------------------------------------------------------------------------
# Lazy coordinator factory
# ---------------------------------------------------------------------------
#
# MultiProjectCoordinator needs a ReflectionDatabaseProtocol. We resolve
# the live reflection DB on first tool invocation so registration at
# startup never blocks on database I/O and tests can swap the factory.
# ---------------------------------------------------------------------------


_coordinator: MultiProjectCoordinator | None = None


def _set_coordinator_for_testing(coordinator: MultiProjectCoordinator | None) -> None:
    """Inject a coordinator for tests. ``None`` resets the cache."""
    global _coordinator
    _coordinator = coordinator


async def _get_coordinator() -> MultiProjectCoordinator:
    """Return the cached coordinator, building one on first use."""
    global _coordinator
    if _coordinator is not None:
        return _coordinator
    from session_buddy.reflection_tools import get_reflection_database

    db = await get_reflection_database()
    # ty: ignore[invalid-argument-type] -- DB adapter conforms to the protocol at runtime
    _coordinator = _build_coordinator(db)
    return _coordinator


def _build_coordinator(db: Any) -> MultiProjectCoordinator:
    """Construct a coordinator; isolated to keep imports tight at module load."""
    from session_buddy.multi_project_coordinator import MultiProjectCoordinator

    return MultiProjectCoordinator(db)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


COORDINATOR_NOT_AVAILABLE_MSG = (
    "Multi-project coordinator not available. Ensure the reflection "
    "database is initialized."
)

VALID_DEPENDENCY_TYPES = {"uses", "extends", "references", "shares_code"}
VALID_SESSION_LINK_TYPES = {"related", "continuation", "reference", "dependency"}


# ---------------------------------------------------------------------------
# Input length bounds — enforce at the MCP boundary so we never store
# unbounded text. These are deliberately tight; callers needing more
# can split their payload.
# ---------------------------------------------------------------------------


MAX_NAME_CHARS = 200
MAX_DESCRIPTION_CHARS = 1000
MAX_PROJECT_ID_CHARS = 100
MAX_QUERY_CHARS = 500
MAX_DEPENDENCY_DESC_CHARS = 500
MAX_SESSION_ID_CHARS = 100
MAX_PROJECTS_PER_GROUP = 50
MAX_LIMIT = 100
MIN_LIMIT = 1


def _check_len(value: str, *, max_len: int, field_name: str) -> str | None:
    """Return an error envelope if ``value`` exceeds ``max_len``."""
    if len(value) > max_len:
        return (
            f"❌ {field_name} exceeds maximum length of {max_len} chars "
            f"(got {len(value)})"
        )
    return None


def _check_list_len(
    values: list[str], *, max_items: int, max_chars: int, field_name: str
) -> str | None:
    """Return an error envelope if a list exceeds size or any item exceeds chars."""
    if len(values) > max_items:
        return (
            f"❌ {field_name} exceeds maximum {max_items} items "
            f"(got {len(values)})"
        )
    for i, v in enumerate(values):
        if len(v) > max_chars:
            return (
                f"❌ {field_name}[{i}] exceeds maximum {max_chars} chars "
                f"(got {len(v)})"
            )
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dump_json(value: Any) -> str:
    """Serialize ``value`` to JSON, falling back to ``str`` for unsupported types."""
    if hasattr(value, "model_dump"):
        return value.model_dump_json()  # type: ignore[attr-defined]
    return json.dumps(value, default=str)


def _dump_list(items: list[Any]) -> str:
    """Serialize a list of model instances or dicts to JSON."""
    return json.dumps(
        [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in items
        ],
        default=str,
    )


async def _with_coordinator(
    operation_name: str, operation: Any
) -> str:
    """Resolve the coordinator, run ``operation(coordinator)``, and return its result."""
    try:
        coordinator = await _get_coordinator()
        return await operation(coordinator)
    except RuntimeError as exc:
        return f"❌ {exc!s}"
    except Exception as exc:  # noqa: BLE001 - MCP tool envelope must return a structured error string on any backend/runtime failure (network, redis, etc.)
        _get_logger().exception(f"Error in {operation_name}: {exc}")
        return ToolMessages.operation_failed(operation_name, exc)


# ---------------------------------------------------------------------------
# Operation implementations
# ---------------------------------------------------------------------------


async def _create_project_group_op(
    coordinator: MultiProjectCoordinator,
    name: str,
    projects: list[str],
    description: str,
) -> str:
    """Create a project group and return its JSON representation."""
    group = await coordinator.create_project_group(
        name=name,
        projects=projects,
        description=description,
    )
    return _dump_json(group)


async def _add_project_dependency_op(
    coordinator: MultiProjectCoordinator,
    source_project: str,
    target_project: str,
    dependency_type: str,
    description: str,
) -> str:
    """Add a dependency edge and return its JSON representation."""
    dependency = await coordinator.add_project_dependency(
        source_project=source_project,
        target_project=target_project,
        dependency_type=dependency_type,  # type: ignore[arg-type]
        description=description,
    )
    return _dump_json(dependency)


async def _link_sessions_op(
    coordinator: MultiProjectCoordinator,
    source_session_id: str,
    target_session_id: str,
    link_type: str,
    context: str,
) -> str:
    """Link two sessions and return the link JSON."""
    link = await coordinator.link_sessions(
        source_session_id=source_session_id,
        target_session_id=target_session_id,
        link_type=link_type,  # type: ignore[arg-type]
        context=context,
    )
    return _dump_json(link)


async def _list_project_groups_op(
    coordinator: MultiProjectCoordinator,
    project: str | None,
) -> str:
    """List project groups, optionally filtered by member project."""
    groups = await coordinator.get_project_groups(project=project)
    return _dump_list(groups)


async def _get_project_dependencies_op(
    coordinator: MultiProjectCoordinator,
    project: str,
    direction: str,
) -> str:
    """Return dependency edges for ``project`` in the requested direction."""
    deps = await coordinator.get_project_dependencies(
        project=project,
        direction=direction,
    )
    return _dump_list(deps)


async def _get_session_links_op(
    coordinator: MultiProjectCoordinator,
    session_id: str,
) -> str:
    """Return all session links involving ``session_id``."""
    links = await coordinator.get_session_links(session_id=session_id)
    return _dump_list(links)


async def _find_related_conversations_op(
    coordinator: MultiProjectCoordinator,
    current_project: str,
    query: str,
    limit: int,
) -> str:
    """Search conversations across the dependency graph rooted at ``current_project``."""
    results = await coordinator.find_related_conversations(
        current_project=current_project,
        query=query,
        limit=limit,
    )
    return json.dumps(results, default=str)


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register_multi_project_tools(mcp: FastMCP) -> None:
    """Register cross-project coordination MCP tools.

    Wraps :class:`MultiProjectCoordinator` to expose project groups,
    dependency tracking, session linking, and cross-project search
    over MCP.

    The coordinator is built lazily on first tool invocation so that
    registration at startup never blocks on reflection-database I/O.
    Tests can inject a coordinator via
    :func:`_set_coordinator_for_testing`.
    """

    @mcp.tool()
    async def create_project_group(
        name: str,
        projects: list[str],
        description: str = "",
    ) -> str:
        """Create a new cross-project coordination group.

        Args:
            name: Human-readable group name (1-200 chars).
            projects: At least one project identifier to include.
            description: Optional group description (max 1000 chars).

        Returns:
            JSON string with the created ``ProjectGroup`` record.
        """
        err = _check_len(name, max_len=MAX_NAME_CHARS, field_name="name")
        if err:
            return err
        err = _check_len(
            description,
            max_len=MAX_DESCRIPTION_CHARS,
            field_name="description",
        )
        if err:
            return err
        err = _check_list_len(
            projects,
            max_items=MAX_PROJECTS_PER_GROUP,
            max_chars=MAX_PROJECT_ID_CHARS,
            field_name="projects",
        )
        if err:
            return err

        async def op(coordinator: MultiProjectCoordinator) -> str:
            return await _create_project_group_op(
                coordinator, name, projects, description
            )

        return await _with_coordinator("Create project group", op)

    @mcp.tool()
    async def add_project_dependency(
        source_project: str,
        target_project: str,
        dependency_type: str = "uses",
        description: str = "",
    ) -> str:
        """Add a dependency edge between two projects.

        Args:
            source_project: The project that depends on ``target_project``.
            target_project: The depended-upon project.
            dependency_type: One of ``"uses"``, ``"extends"``,
                ``"references"``, ``"shares_code"``.
            description: Optional free-text description.

        Returns:
            JSON string with the created ``ProjectDependency`` record.
        """
        if dependency_type not in VALID_DEPENDENCY_TYPES:
            return (
                f"❌ Invalid dependency_type: {dependency_type!r}. "
                f"Must be one of {sorted(VALID_DEPENDENCY_TYPES)}."
            )
        err = _check_len(
            source_project,
            max_len=MAX_PROJECT_ID_CHARS,
            field_name="source_project",
        )
        if err:
            return err
        err = _check_len(
            target_project,
            max_len=MAX_PROJECT_ID_CHARS,
            field_name="target_project",
        )
        if err:
            return err
        err = _check_len(
            description,
            max_len=MAX_DEPENDENCY_DESC_CHARS,
            field_name="description",
        )
        if err:
            return err

        async def op(coordinator: MultiProjectCoordinator) -> str:
            return await _add_project_dependency_op(
                coordinator,
                source_project,
                target_project,
                dependency_type,
                description,
            )

        return await _with_coordinator("Add project dependency", op)

    @mcp.tool()
    async def link_sessions(
        source_session_id: str,
        target_session_id: str,
        link_type: str = "related",
        context: str = "",
    ) -> str:
        """Link two sessions across projects.

        Args:
            source_session_id: The originating session id.
            target_session_id: The session being linked to.
            link_type: One of ``"related"``, ``"continuation"``,
                ``"reference"``, ``"dependency"``.
            context: Optional context describing the link.

        Returns:
            JSON string with the created ``SessionLink`` record.
        """
        if link_type not in VALID_SESSION_LINK_TYPES:
            return (
                f"❌ Invalid link_type: {link_type!r}. "
                f"Must be one of {sorted(VALID_SESSION_LINK_TYPES)}."
            )
        err = _check_len(
            source_session_id,
            max_len=MAX_SESSION_ID_CHARS,
            field_name="source_session_id",
        )
        if err:
            return err
        err = _check_len(
            target_session_id,
            max_len=MAX_SESSION_ID_CHARS,
            field_name="target_session_id",
        )
        if err:
            return err
        err = _check_len(
            context,
            max_len=MAX_DESCRIPTION_CHARS,
            field_name="context",
        )
        if err:
            return err

        async def op(coordinator: MultiProjectCoordinator) -> str:
            return await _link_sessions_op(
                coordinator,
                source_session_id,
                target_session_id,
                link_type,
                context,
            )

        return await _with_coordinator("Link sessions", op)

    @mcp.tool()
    async def list_project_groups(
        project: str | None = None,
    ) -> str:
        """List known project groups, optionally filtered by member project.

        Args:
            project: If provided, restrict to groups that contain this project.

        Returns:
            JSON string with an array of ``ProjectGroup`` records.
        """
        if project is not None:
            err = _check_len(
                project,
                max_len=MAX_PROJECT_ID_CHARS,
                field_name="project",
            )
            if err:
                return err

        async def op(coordinator: MultiProjectCoordinator) -> str:
            return await _list_project_groups_op(coordinator, project)

        return await _with_coordinator("List project groups", op)

    @mcp.tool()
    async def get_project_dependencies(
        project: str,
        direction: str = "both",
    ) -> str:
        """List dependency edges for a project.

        Args:
            project: Project identifier to query.
            direction: ``"outbound"``, ``"inbound"``, or ``"both"``.

        Returns:
            JSON string with an array of ``ProjectDependency`` records.
        """
        if direction not in {"outbound", "inbound", "both"}:
            return (
                f"❌ Invalid direction: {direction!r}. "
                "Must be one of 'outbound', 'inbound', 'both'."
            )
        err = _check_len(
            project,
            max_len=MAX_PROJECT_ID_CHARS,
            field_name="project",
        )
        if err:
            return err

        async def op(coordinator: MultiProjectCoordinator) -> str:
            return await _get_project_dependencies_op(
                coordinator, project, direction
            )

        return await _with_coordinator("Get project dependencies", op)

    @mcp.tool()
    async def find_related_conversations(
        current_project: str,
        query: str,
        limit: int = 10,
    ) -> str:
        """Search conversations across projects related to ``current_project``.

        Args:
            current_project: Anchor project for the dependency-graph search.
            query: Free-text query.
            limit: Maximum results to return (default 10).

        Returns:
            JSON string with ranked conversation hits (each annotated
            with ``source_project`` and ``is_current_project``).
        """
        err = _check_len(
            current_project,
            max_len=MAX_PROJECT_ID_CHARS,
            field_name="current_project",
        )
        if err:
            return err
        err = _check_len(query, max_len=MAX_QUERY_CHARS, field_name="query")
        if err:
            return err
        limit = max(MIN_LIMIT, min(limit, MAX_LIMIT))

        async def op(coordinator: MultiProjectCoordinator) -> str:
            return await _find_related_conversations_op(
                coordinator, current_project, query, limit
            )

        return await _with_coordinator("Find related conversations", op)
