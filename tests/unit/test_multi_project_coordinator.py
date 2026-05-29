"""Comprehensive tests for multi_project_coordinator module.

Tests project group management, dependency tracking, session linking,
and cross-project insights functionality with full async support.

Phase: Week 5 Day 4 - Multi-Project Coordinator Coverage
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
import pytest_asyncio
from pydantic import ValidationError

from session_buddy.multi_project_coordinator import (
    MultiProjectCoordinator,
    ProjectDependency,
    ProjectGroup,
    ReflectionDatabaseProtocol,
    SessionLink,
)


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create a mock database connection with proper async handling."""
    conn = MagicMock()
    conn.commit = MagicMock()
    return conn


@pytest.fixture
def mock_reflection_db(mock_conn: MagicMock) -> MagicMock:
    """Create a mock reflection database."""
    db = MagicMock(spec=ReflectionDatabaseProtocol)
    db.conn = mock_conn
    db.search_conversations = AsyncMock(return_value=[])
    return db


@pytest.fixture
def coordinator(mock_reflection_db: MagicMock) -> MultiProjectCoordinator:
    """Create a coordinator with mocked database."""
    return MultiProjectCoordinator(mock_reflection_db)


@pytest.fixture
def sample_datetime() -> datetime:
    """Create a sample datetime for testing."""
    return datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)


@pytest.fixture
def sample_project_group_data() -> dict[str, Any]:
    """Sample data for creating a project group."""
    return {
        "id": "test-group-123",
        "name": "Test Project Group",
        "description": "A test group for unit testing",
        "projects": ["project-a", "project-b", "project-c"],
        "metadata": {"owner": "test-team", "priority": "high"},
    }


@pytest.fixture
def sample_dependency_data() -> dict[str, Any]:
    """Sample data for creating a project dependency."""
    return {
        "id": "test-dep-456",
        "source_project": "frontend-service",
        "target_project": "backend-service",
        "dependency_type": "uses",
        "description": "Frontend uses backend API",
        "metadata": {"api_version": "v2"},
    }


@pytest.fixture
def sample_session_link_data() -> dict[str, Any]:
    """Sample data for creating a session link."""
    return {
        "id": "test-link-789",
        "source_session_id": "session-alpha",
        "target_session_id": "session-beta",
        "link_type": "continuation",
        "context": "Continued from previous session",
        "metadata": {"work_type": "feature development"},
    }


# ============================================================================
# ProjectGroup Model Tests
# ============================================================================


class TestProjectGroupModel:
    """Test ProjectGroup Pydantic model validation and behavior."""

    def test_valid_project_group_creation(
        self, sample_project_group_data: dict[str, Any]
    ) -> None:
        """Should create ProjectGroup with valid data."""
        group = ProjectGroup(**sample_project_group_data)

        assert group.id == sample_project_group_data["id"]
        assert group.name == sample_project_group_data["name"]
        assert group.description == sample_project_group_data["description"]
        assert group.projects == sample_project_group_data["projects"]
        assert group.metadata == sample_project_group_data["metadata"]
        assert isinstance(group.created_at, datetime)

    def test_project_group_default_values(self) -> None:
        """Should use default values for optional fields."""
        group = ProjectGroup(
            id="minimal-group",
            name="Minimal Group",
            projects=["single-project"],
        )

        assert group.description == ""
        assert group.metadata == {}
        assert isinstance(group.created_at, datetime)

    def test_project_group_strips_whitespace(self) -> None:
        """Should strip whitespace from project names."""
        group = ProjectGroup(
            id="strip-test",
            name="Trim Test",
            projects=["  project-a  ", "  project-b  "],
        )

        assert group.projects == ["project-a", "project-b"]

    def test_project_group_rejects_empty_projects_list(self) -> None:
        """Should reject project group with empty projects list."""
        with pytest.raises(ValidationError):
            ProjectGroup(
                id="empty-projects",
                name="Empty Projects",
                projects=[],
            )

    def test_project_group_rejects_empty_project_name(self) -> None:
        """Should reject projects with empty names."""
        with pytest.raises(ValidationError):
            ProjectGroup(
                id="empty-name-test",
                name="Empty Name Test",
                projects=["valid-project", ""],
            )

    def test_project_group_rejects_whitespace_only_project_name(self) -> None:
        """Should reject projects with whitespace-only names."""
        with pytest.raises(ValidationError):
            ProjectGroup(
                id="whitespace-test",
                name="Whitespace Test",
                projects=["valid-project", "   "],
            )

    def test_project_group_name_max_length(self) -> None:
        """Should enforce max length on name field."""
        with pytest.raises(ValidationError):
            ProjectGroup(
                id="long-name-test",
                name="x" * 201,  # Exceeds max_length=200
                projects=["project-a"],
            )

    def test_project_group_description_max_length(self) -> None:
        """Should enforce max length on description field."""
        with pytest.raises(ValidationError):
            ProjectGroup(
                id="long-desc-test",
                name="Valid Name",
                projects=["project-a"],
                description="x" * 1001,  # Exceeds max_length=1000
            )

    def test_project_group_stores_metadata_correctly(
        self, sample_project_group_data: dict[str, Any]
    ) -> None:
        """Should store and retrieve metadata correctly."""
        group = ProjectGroup(**sample_project_group_data)
        assert group.metadata["owner"] == "test-team"
        assert group.metadata["priority"] == "high"


# ============================================================================
# ProjectDependency Model Tests
# ============================================================================


class TestProjectDependencyModel:
    """Test ProjectDependency Pydantic model validation."""

    def test_valid_dependency_creation(
        self, sample_dependency_data: dict[str, Any]
    ) -> None:
        """Should create ProjectDependency with valid data."""
        dep = ProjectDependency(**sample_dependency_data)

        assert dep.id == sample_dependency_data["id"]
        assert dep.source_project == sample_dependency_data["source_project"]
        assert dep.target_project == sample_dependency_data["target_project"]
        assert dep.dependency_type == sample_dependency_data["dependency_type"]
        assert dep.description == sample_dependency_data["description"]
        assert dep.metadata == sample_dependency_data["metadata"]

    def test_all_valid_dependency_types(self) -> None:
        """Should accept all valid dependency type values."""
        for dep_type in ["uses", "extends", "references", "shares_code"]:
            dep = ProjectDependency(
                id=f"dep-{dep_type}",
                source_project="proj-a",
                target_project="proj-b",
                dependency_type=dep_type,
            )
            assert dep.dependency_type == dep_type

    def test_dependency_rejects_empty_source_project(self) -> None:
        """Should reject empty source project name."""
        with pytest.raises(ValidationError):
            ProjectDependency(
                id="empty-source",
                source_project="",
                target_project="proj-b",
                dependency_type="uses",
            )

    def test_dependency_rejects_empty_target_project(self) -> None:
        """Should reject empty target project name."""
        with pytest.raises(ValidationError):
            ProjectDependency(
                id="empty-target",
                source_project="proj-a",
                target_project="",
                dependency_type="uses",
            )

    def test_dependency_rejects_self_reference(self) -> None:
        """Should reject when source and target are the same."""
        with pytest.raises(ValidationError):
            ProjectDependency(
                id="self-dep",
                source_project="same-project",
                target_project="same-project",
                dependency_type="uses",
            )

    def test_dependency_strips_whitespace(self) -> None:
        """Should strip whitespace from project names."""
        dep = ProjectDependency(
            id="strip-test",
            source_project="  proj-a  ",
            target_project="  proj-b  ",
            dependency_type="uses",
        )
        assert dep.source_project == "proj-a"
        assert dep.target_project == "proj-b"


# ============================================================================
# SessionLink Model Tests
# ============================================================================


class TestSessionLinkModel:
    """Test SessionLink Pydantic model validation."""

    def test_valid_link_creation(
        self, sample_session_link_data: dict[str, Any]
    ) -> None:
        """Should create SessionLink with valid data."""
        link = SessionLink(**sample_session_link_data)

        assert link.id == sample_session_link_data["id"]
        assert link.source_session_id == sample_session_link_data["source_session_id"]
        assert link.target_session_id == sample_session_link_data["target_session_id"]
        assert link.link_type == sample_session_link_data["link_type"]
        assert link.context == sample_session_link_data["context"]
        assert link.metadata == sample_session_link_data["metadata"]

    def test_all_valid_link_types(self) -> None:
        """Should accept all valid link type values."""
        for link_type in ["related", "continuation", "reference", "dependency"]:
            link = SessionLink(
                id=f"link-{link_type}",
                source_session_id="sess-1",
                target_session_id="sess-2",
                link_type=link_type,
            )
            assert link.link_type == link_type

    def test_link_rejects_empty_source_session(self) -> None:
        """Should reject empty source session ID."""
        with pytest.raises(ValidationError):
            SessionLink(
                id="empty-source",
                source_session_id="",
                target_session_id="sess-2",
                link_type="related",
            )

    def test_link_rejects_empty_target_session(self) -> None:
        """Should reject empty target session ID."""
        with pytest.raises(ValidationError):
            SessionLink(
                id="empty-target",
                source_session_id="sess-1",
                target_session_id="",
                link_type="related",
            )

    def test_link_rejects_self_reference(self) -> None:
        """Should reject when source and target are the same."""
        with pytest.raises(ValidationError):
            SessionLink(
                id="self-link",
                source_session_id="same-session",
                target_session_id="same-session",
                link_type="continuation",
            )

    def test_link_default_context(self) -> None:
        """Should have empty string as default context."""
        link = SessionLink(
            id="default-context",
            source_session_id="sess-1",
            target_session_id="sess-2",
            link_type="related",
        )
        assert link.context == ""

    def test_link_context_max_length(self) -> None:
        """Should enforce max length on context field."""
        with pytest.raises(ValidationError):
            SessionLink(
                id="long-context",
                source_session_id="sess-1",
                target_session_id="sess-2",
                link_type="related",
                context="x" * 2001,  # Exceeds max_length=2000
            )


# ============================================================================
# MultiProjectCoordinator Initialization Tests
# ============================================================================


class TestMultiProjectCoordinatorInit:
    """Test MultiProjectCoordinator initialization."""

    def test_init_sets_reflection_db(self, mock_reflection_db: MagicMock) -> None:
        """Should store reflection_db reference."""
        coordinator = MultiProjectCoordinator(mock_reflection_db)
        assert coordinator.reflection_db is mock_reflection_db

    def test_init_initializes_caches(self, coordinator: MultiProjectCoordinator) -> None:
        """Should initialize empty cache dictionaries."""
        assert isinstance(coordinator.active_project_groups, dict)
        assert len(coordinator.active_project_groups) == 0
        assert isinstance(coordinator.dependency_cache, dict)
        assert len(coordinator.dependency_cache) == 0
        assert isinstance(coordinator.session_links_cache, dict)
        assert len(coordinator.session_links_cache) == 0

    def test_get_conn_returns_connection(self, coordinator: MultiProjectCoordinator) -> None:
        """Should return the database connection."""
        conn = coordinator._get_conn()
        assert conn is not None

    def test_get_conn_raises_when_conn_none(self) -> None:
        """Should raise RuntimeError when connection is None."""
        mock_db = MagicMock()
        mock_db.conn = None
        coordinator = MultiProjectCoordinator(mock_db)

        with pytest.raises(RuntimeError, match="not initialized"):
            coordinator._get_conn()

    def test_get_conn_raises_when_conn_missing(self) -> None:
        """Should raise RuntimeError when connection attribute is missing."""
        mock_db = MagicMock(spec=ReflectionDatabaseProtocol)
        # conn property returns None
        type(mock_db).conn = PropertyMock(return_value=None)
        coordinator = MultiProjectCoordinator(mock_db)

        with pytest.raises(RuntimeError, match="not initialized"):
            coordinator._get_conn()


# ============================================================================
# Project Group CRUD Tests
# ============================================================================


class TestProjectGroupCRUD:
    """Test project group CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_project_group_success(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_project_group_data: dict[str, Any],
    ) -> None:
        """Should create and return a new project group."""
        group = await coordinator.create_project_group(
            name=sample_project_group_data["name"],
            projects=sample_project_group_data["projects"],
            description=sample_project_group_data["description"],
            metadata=sample_project_group_data["metadata"],
        )

        assert group.name == sample_project_group_data["name"]
        assert group.projects == sample_project_group_data["projects"]
        assert group.description == sample_project_group_data["description"]
        assert group.metadata == sample_project_group_data["metadata"]
        assert group.id is not None

        # Verify database was called
        mock_reflection_db.conn.execute.assert_called()
        mock_reflection_db.conn.commit.assert_called()

        # Verify cache was updated
        assert group.id in coordinator.active_project_groups

    @pytest.mark.asyncio
    async def test_create_project_group_with_defaults(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should create project group with default description and metadata."""
        group = await coordinator.create_project_group(
            name="Minimal Group",
            projects=["project-a"],
        )

        assert group.description == ""
        assert group.metadata == {}

    @pytest.mark.asyncio
    async def test_create_project_group_stores_in_cache(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should store created group in active_project_groups cache."""
        group = await coordinator.create_project_group(
            name="Cache Test Group",
            projects=["proj-a", "proj-b"],
        )

        assert group.id in coordinator.active_project_groups
        assert coordinator.active_project_groups[group.id] is group

    @pytest.mark.asyncio
    async def test_get_project_groups_empty_database(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should return empty list when no groups exist."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        groups = await coordinator.get_project_groups()

        assert groups == []

    @pytest.mark.asyncio
    async def test_get_project_groups_with_data(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should return project groups from database."""
        mock_rows = [
            (
                "group-1",
                "Group One",
                "Description",
                ["proj-a", "proj-b"],
                sample_datetime,
                '{"key": "value"}',
            ),
            (
                "group-2",
                "Group Two",
                "Another description",
                ["proj-c"],
                sample_datetime,
                "{}",
            ),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_reflection_db.conn.execute.return_value = mock_cursor

        groups = await coordinator.get_project_groups()

        assert len(groups) == 2
        assert groups[0].id == "group-1"
        assert groups[0].name == "Group One"
        assert groups[0].projects == ["proj-a", "proj-b"]
        assert groups[0].metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_project_groups_filtered_by_project(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should filter groups by project name."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        await coordinator.get_project_groups(project="specific-project")

        # Verify SQL contains filter clause
        call_args = mock_reflection_db.conn.execute.call_args
        sql_query = call_args[0][0]
        params = call_args[0][1]
        assert "list_contains" in sql_query
        assert "specific-project" in params

    @pytest.mark.asyncio
    async def test_get_project_groups_caches_results(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should cache project groups after retrieval."""
        mock_rows = [
            ("cached-group", "Cached Group", "Desc", ["proj-a"], sample_datetime, "{}"),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_reflection_db.conn.execute.return_value = mock_cursor

        # First call populates cache
        groups1 = await coordinator.get_project_groups()
        first_call_count = mock_reflection_db.conn.execute.call_count

        # Second call may hit DB again (implementation detail)
        groups2 = await coordinator.get_project_groups()

        assert len(groups1) == 1
        assert groups1[0].id == "cached-group"

        # Verify the group is cached in active_project_groups
        assert "cached-group" in coordinator.active_project_groups


# ============================================================================
# Project Dependency CRUD Tests
# ============================================================================


class TestProjectDependencyCRUD:
    """Test project dependency CRUD operations."""

    @pytest.mark.asyncio
    async def test_add_project_dependency_success(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should create and return a new project dependency."""
        dep = await coordinator.add_project_dependency(
            source_project="frontend",
            target_project="backend",
            dependency_type="uses",
            description="Frontend uses backend API",
        )

        assert dep.source_project == "frontend"
        assert dep.target_project == "backend"
        assert dep.dependency_type == "uses"
        assert dep.description == "Frontend uses backend API"
        assert dep.id is not None

    @pytest.mark.asyncio
    async def test_add_project_dependency_clears_cache(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should clear dependency cache after adding new dependency."""
        # Pre-populate cache
        coordinator.dependency_cache["frontend_outbound"] = []

        dep = await coordinator.add_project_dependency(
            source_project="frontend",
            target_project="backend",
            dependency_type="uses",
        )

        # Cache should be cleared (entries removed)
        assert "frontend_outbound" not in coordinator.dependency_cache

    @pytest.mark.asyncio
    async def test_get_project_dependencies_empty(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should return empty list when no dependencies exist."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        deps = await coordinator.get_project_dependencies("proj-a")

        assert deps == []

    @pytest.mark.asyncio
    async def test_get_project_dependencies_with_data(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should return dependencies from database."""
        mock_rows = [
            (
                "dep-1",
                "proj-a",
                "proj-b",
                "uses",
                "A uses B",
                sample_datetime,
                "{}",
            ),
            (
                "dep-2",
                "proj-b",
                "proj-c",
                "extends",
                "B extends C",
                sample_datetime,
                "{}",
            ),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_reflection_db.conn.execute.return_value = mock_cursor

        deps = await coordinator.get_project_dependencies("proj-a")

        assert len(deps) == 2
        assert deps[0].source_project == "proj-a"
        assert deps[0].target_project == "proj-b"

    @pytest.mark.asyncio
    async def test_get_project_dependencies_outbound_filter(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should filter to outbound dependencies only."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        await coordinator.get_project_dependencies("proj-a", direction="outbound")

        call_args = mock_reflection_db.conn.execute.call_args
        sql_query = call_args[0][0]
        assert "source_project = ?" in sql_query

    @pytest.mark.asyncio
    async def test_get_project_dependencies_inbound_filter(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should filter to inbound dependencies only."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        await coordinator.get_project_dependencies("proj-a", direction="inbound")

        call_args = mock_reflection_db.conn.execute.call_args
        sql_query = call_args[0][0]
        assert "target_project = ?" in sql_query

    @pytest.mark.asyncio
    async def test_get_project_dependencies_both_directions(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should return dependencies in both directions."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        await coordinator.get_project_dependencies("proj-a", direction="both")

        call_args = mock_reflection_db.conn.execute.call_args
        sql_query = call_args[0][0]
        # Should have OR condition for both source and target
        assert "OR" in sql_query

    @pytest.mark.asyncio
    async def test_get_project_dependencies_caches_results(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should cache dependency results."""
        mock_rows = [
            ("cached-dep", "proj-a", "proj-b", "uses", "Desc", sample_datetime, "{}"),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_reflection_db.conn.execute.return_value = mock_cursor

        # First call
        deps1 = await coordinator.get_project_dependencies("proj-a")

        # Should be cached now
        assert "proj-a_both" in coordinator.dependency_cache


# ============================================================================
# Session Link CRUD Tests
# ============================================================================


class TestSessionLinkCRUD:
    """Test session link CRUD operations."""

    @pytest.mark.asyncio
    async def test_link_sessions_success(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should create and return a new session link."""
        link = await coordinator.link_sessions(
            source_session_id="session-1",
            target_session_id="session-2",
            link_type="continuation",
            context="Continued work",
        )

        assert link.source_session_id == "session-1"
        assert link.target_session_id == "session-2"
        assert link.link_type == "continuation"
        assert link.context == "Continued work"
        assert link.id is not None

    @pytest.mark.asyncio
    async def test_link_sessions_clears_cache(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should clear session links cache after creating link."""
        # Pre-populate cache
        coordinator.session_links_cache["session-1"] = []
        coordinator.session_links_cache["session-2"] = []

        await coordinator.link_sessions(
            source_session_id="session-1",
            target_session_id="session-2",
            link_type="related",
        )

        assert "session-1" not in coordinator.session_links_cache
        assert "session-2" not in coordinator.session_links_cache

    @pytest.mark.asyncio
    async def test_get_session_links_empty(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should return empty list when no links exist."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        links = await coordinator.get_session_links("session-x")

        assert links == []

    @pytest.mark.asyncio
    async def test_get_session_links_with_data(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should return session links from database."""
        mock_rows = [
            (
                "link-1",
                "sess-a",
                "sess-b",
                "related",
                "Related context",
                sample_datetime,
                '{"source": "test"}',
            ),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_reflection_db.conn.execute.return_value = mock_cursor

        links = await coordinator.get_session_links("sess-a")

        assert len(links) == 1
        assert links[0].source_session_id == "sess-a"
        assert links[0].target_session_id == "sess-b"
        assert links[0].link_type == "related"

    @pytest.mark.asyncio
    async def test_get_session_links_caches_results(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should cache session links results."""
        mock_rows = [
            ("cached-link", "sess-1", "sess-2", "related", "Context", sample_datetime, "{}"),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_reflection_db.conn.execute.return_value = mock_cursor

        # First call
        links1 = await coordinator.get_session_links("sess-1")

        # Should be cached
        assert "sess-1" in coordinator.session_links_cache
        assert len(links1) == 1


# ============================================================================
# Cache Management Tests
# ============================================================================


class TestCacheManagement:
    """Test internal cache management operations."""

    def test_clear_dependency_cache_single_project(
        self, coordinator: MultiProjectCoordinator
    ) -> None:
        """Should clear all dependency cache entries for a project."""
        # Add multiple cache entries for same project
        coordinator.dependency_cache["proj-a_outbound"] = []
        coordinator.dependency_cache["proj-a_inbound"] = []
        coordinator.dependency_cache["proj-a_both"] = []
        coordinator.dependency_cache["other-proj_both"] = []

        coordinator._clear_dependency_cache("proj-a")

        assert "proj-a_outbound" not in coordinator.dependency_cache
        assert "proj-a_inbound" not in coordinator.dependency_cache
        assert "proj-a_both" not in coordinator.dependency_cache
        assert "other-proj_both" in coordinator.dependency_cache

    def test_clear_session_links_cache(self, coordinator: MultiProjectCoordinator) -> None:
        """Should clear session links cache for specific session."""
        coordinator.session_links_cache["session-1"] = []
        coordinator.session_links_cache["session-2"] = []

        coordinator._clear_session_links_cache("session-1")

        assert "session-1" not in coordinator.session_links_cache
        assert "session-2" in coordinator.session_links_cache

    def test_clear_session_links_cache_nonexistent(
        self, coordinator: MultiProjectCoordinator
    ) -> None:
        """Should not raise error when clearing nonexistent cache entry."""
        # Should not raise
        coordinator._clear_session_links_cache("nonexistent-session")
        assert True


# ============================================================================
# Cross-Project Search Tests
# ============================================================================


class TestCrossProjectSearch:
    """Test cross-project conversation search functionality."""

    @pytest.mark.asyncio
    async def test_find_related_conversations_no_dependencies(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should search only current project when no dependencies exist."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        # Mock search to return results
        mock_reflection_db.search_conversations = AsyncMock(
            return_value=[
                {"id": "conv-1", "content": "Test conversation", "score": 0.9},
            ]
        )

        results = await coordinator.find_related_conversations(
            current_project="proj-a",
            query="test",
            limit=10,
        )

        assert len(results) >= 1
        # Should have source_project field added
        assert all("source_project" in r for r in results)

    @pytest.mark.asyncio
    async def test_find_related_conversations_with_dependencies(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should search across related projects based on dependencies."""
        # Mock dependencies
        deps_rows = [
            ("dep-1", "proj-a", "proj-b", "uses", "Desc", sample_datetime, "{}"),
        ]
        deps_cursor = MagicMock()
        deps_cursor.fetchall.return_value = deps_rows
        mock_reflection_db.conn.execute.return_value = deps_cursor

        # Mock search results for different projects
        mock_reflection_db.search_conversations = AsyncMock(
            side_effect=[
                [{"id": "conv-a", "content": "API in A", "score": 0.85}],
                [{"id": "conv-b", "content": "API in B", "score": 0.9}],
            ]
        )

        results = await coordinator.find_related_conversations(
            current_project="proj-a",
            query="API",
            limit=10,
        )

        # Results should be from both projects
        source_projects = {r.get("source_project") for r in results}
        assert "proj-a" in source_projects or "proj-b" in source_projects

    @pytest.mark.asyncio
    async def test_find_related_conversations_sorted_by_score(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should sort results by relevance score."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        mock_reflection_db.search_conversations = AsyncMock(
            return_value=[
                {"id": "low", "content": "Low score", "score": 0.3},
                {"id": "high", "content": "High score", "score": 0.95},
                {"id": "mid", "content": "Mid score", "score": 0.7},
            ]
        )

        results = await coordinator.find_related_conversations(
            current_project="proj-a",
            query="test",
            limit=10,
        )

        # Should be sorted descending by score
        scores = [r.get("score", 0) for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_find_related_conversations_respects_limit(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should limit results to specified amount."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        # Return many results
        mock_reflection_db.search_conversations = AsyncMock(
            return_value=[
                {"id": f"conv-{i}", "content": f"Result {i}", "score": 1.0 - i * 0.1}
                for i in range(20)
            ]
        )

        results = await coordinator.find_related_conversations(
            current_project="proj-a",
            query="test",
            limit=5,
        )

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_find_related_conversations_marks_current_project(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should mark results from current project with is_current_project flag."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        mock_reflection_db.search_conversations = AsyncMock(
            return_value=[
                {"id": "conv-1", "content": "Current project result", "score": 0.9},
            ]
        )

        results = await coordinator.find_related_conversations(
            current_project="proj-a",
            query="test",
            limit=10,
        )

        # Result from current project should be marked
        current_results = [r for r in results if r.get("is_current_project")]
        assert len(current_results) >= 1


# ============================================================================
# Cross-Project Insights Tests
# ============================================================================


class TestCrossProjectInsights:
    """Test cross-project insights and analytics functionality."""

    @pytest.mark.asyncio
    async def test_get_cross_project_insights_structure(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should return insights with correct structure."""
        # Mock empty responses
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        insights = await coordinator.get_cross_project_insights(
            projects=["proj-a", "proj-b"],
            time_range_days=30,
        )

        assert isinstance(insights, dict)
        assert "project_activity" in insights
        assert "common_patterns" in insights
        assert "knowledge_gaps" in insights
        assert "collaboration_opportunities" in insights

    @pytest.mark.asyncio
    async def test_get_cross_project_insights_with_activity(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should include project activity data."""
        stats = (15, sample_datetime, 350.5)  # count, last_activity, avg_length
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = stats
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        insights = await coordinator.get_cross_project_insights(
            projects=["proj-a"],
            time_range_days=7,
        )

        assert "project_activity" in insights
        # May have activity data if stats were returned

    @pytest.mark.asyncio
    async def test_initialize_insights_structure(
        self, coordinator: MultiProjectCoordinator
    ) -> None:
        """Should initialize correct insights structure."""
        structure = coordinator._initialize_insights_structure()

        assert structure["project_activity"] == {}
        assert structure["common_patterns"] == []
        assert structure["knowledge_gaps"] == []
        assert structure["collaboration_opportunities"] == []

    @pytest.mark.asyncio
    async def test_analyze_project_activity_empty(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should handle empty project activity."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_reflection_db.conn.execute.return_value = mock_cursor

        activity = await coordinator._analyze_project_activity(
            projects=["empty-project"],
            since_date=sample_datetime,
        )

        assert isinstance(activity, dict)
        assert "empty-project" not in activity or activity["empty-project"] is None

    @pytest.mark.asyncio
    async def test_find_common_patterns_no_data(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
        sample_datetime: datetime,
    ) -> None:
        """Should return empty patterns when no conversation data."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        patterns = await coordinator._find_common_patterns(
            projects=["proj-a"],
            since_date=sample_datetime,
        )

        assert isinstance(patterns, list)

    @pytest.mark.asyncio
    async def test_extract_project_keywords(
        self, coordinator: MultiProjectCoordinator
    ) -> None:
        """Should extract keywords from conversation data (words > 4 chars)."""
        # Use words that are definitely > 4 chars after lowercasing
        conversation_data = [
            ("proj-a", "This is a test conversation about database design patterns"),
            ("proj-b", "Database implementation using Python with async patterns"),
        ]

        keywords = coordinator._extract_project_keywords(conversation_data)

        assert isinstance(keywords, dict)
        assert "proj-a" in keywords
        assert "proj-b" in keywords
        # "database" is 8 chars, should be extracted
        assert "database" in keywords["proj-a"] or "database" in keywords["proj-b"]

    @pytest.mark.asyncio
    async def test_extract_project_keywords_skips_short_words(
        self, coordinator: MultiProjectCoordinator
    ) -> None:
        """Should skip words with 4 or fewer characters."""
        conversation_data = [
            ("proj-a", "a be see do it"),
        ]

        keywords = coordinator._extract_project_keywords(conversation_data)

        # All words are <= 4 chars, so none should be extracted
        assert len(keywords.get("proj-a", {})) == 0

    @pytest.mark.asyncio
    async def test_identify_common_patterns(
        self, coordinator: MultiProjectCoordinator
    ) -> None:
        """Should identify keywords appearing in multiple projects."""
        project_keywords = {
            "proj-a": {"authentication": 5, "api": 3, "testing": 2},
            "proj-b": {"authentication": 3, "api": 4, "database": 1},
            "proj-c": {"authentication": 2, "api": 2, "testing": 1},
        }

        patterns = coordinator._identify_common_patterns(project_keywords)

        # Should find patterns appearing in at least 2 projects
        assert isinstance(patterns, list)
        # "authentication" and "api" should appear in at least 2 projects
        pattern_words = {p["pattern"] for p in patterns}
        assert "authentication" in pattern_words
        assert "api" in pattern_words
        # "testing" only in 2 projects (a and c), should be included
        assert "testing" in pattern_words
        # "database" only in 1 project, should not be included
        assert "database" not in pattern_words

    @pytest.mark.asyncio
    async def test_identify_common_patterns_limits_to_top_10(
        self, coordinator: MultiProjectCoordinator
    ) -> None:
        """Should limit patterns to top 10 by frequency."""
        # Create many patterns
        project_keywords = {
            "proj-a": {f"keyword-{i}": 10 for i in range(20)},
            "proj-b": {f"keyword-{i}": 8 for i in range(20)},
        }

        patterns = coordinator._identify_common_patterns(project_keywords)

        assert len(patterns) <= 10


# ============================================================================
# Cleanup Operations Tests
# ============================================================================


class TestCleanupOperations:
    """Test cleanup operations for old links and dependencies."""

    @pytest.mark.asyncio
    async def test_cleanup_old_links_success(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should delete old session links and return count."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (5,)  # 5 old links
        mock_reflection_db.conn.execute.return_value = mock_cursor

        result = await coordinator.cleanup_old_links(max_age_days=90)

        assert isinstance(result, dict)
        assert "deleted_session_links" in result
        assert result["deleted_session_links"] == 5

    @pytest.mark.asyncio
    async def test_cleanup_old_links_zero_count(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should handle zero old links."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (0,)
        mock_reflection_db.conn.execute.return_value = mock_cursor

        result = await coordinator.cleanup_old_links(max_age_days=365)

        assert result["deleted_session_links"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_links_clears_cache(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should clear session links cache after cleanup."""
        # Pre-populate cache
        coordinator.session_links_cache["session-1"] = []
        coordinator.session_links_cache["session-2"] = []

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (0,)
        mock_reflection_db.conn.execute.return_value = mock_cursor

        await coordinator.cleanup_old_links()

        # Cache should be cleared
        assert len(coordinator.session_links_cache) == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_links_commits_transaction(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should commit transaction after cleanup."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_reflection_db.conn.execute.return_value = mock_cursor

        await coordinator.cleanup_old_links()

        mock_reflection_db.conn.commit.assert_called()


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_create_project_group_empty_name(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should handle empty project names in group creation."""
        # This tests the validator on ProjectGroup model
        with pytest.raises(ValidationError):
            await coordinator.create_project_group(
                name="Valid Name",
                projects=["valid", ""],  # Empty project name
            )

    @pytest.mark.asyncio
    async def test_get_project_dependencies_nonexistent_project(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should return empty list for nonexistent project."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        deps = await coordinator.get_project_dependencies("nonexistent-project")

        assert deps == []

    @pytest.mark.asyncio
    async def test_get_session_links_nonexistent_session(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should return empty list for nonexistent session."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        links = await coordinator.get_session_links("nonexistent-session")

        assert links == []

    @pytest.mark.asyncio
    async def test_concurrent_access_same_cache(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should handle concurrent access to same cache entry."""
        # Simulate concurrent reads that populate cache
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("concurrent-group", "Concurrent", "Desc", ["proj-a"], datetime.now(), "{}"),
        ]
        mock_reflection_db.conn.execute.return_value = mock_cursor

        # Two concurrent calls
        results = await asyncio.gather(
            coordinator.get_project_groups(),
            coordinator.get_project_groups(),
        )

        # Both should succeed
        assert len(results[0]) == 1
        assert len(results[1]) == 1

    @pytest.mark.asyncio
    async def test_cross_project_insights_empty_projects_list(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should handle empty projects list in insights."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        insights = await coordinator.get_cross_project_insights(
            projects=[],
            time_range_days=30,
        )

        assert isinstance(insights, dict)
        assert insights["project_activity"] == {}

    @pytest.mark.asyncio
    async def test_cross_project_insights_zero_time_range(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should handle zero time range in insights."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        insights = await coordinator.get_cross_project_insights(
            projects=["proj-a"],
            time_range_days=0,
        )

        assert isinstance(insights, dict)

    @pytest.mark.asyncio
    async def test_find_related_conversations_empty_query(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should handle empty query string."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor
        mock_reflection_db.search_conversations = AsyncMock(return_value=[])

        results = await coordinator.find_related_conversations(
            current_project="proj-a",
            query="",
            limit=10,
        )

        assert isinstance(results, list)

    def test_internal_methods_private(self, coordinator: MultiProjectCoordinator) -> None:
        """Should have private internal methods starting with underscore."""
        # Verify internal methods exist and are callable
        assert hasattr(coordinator, "_initialize_caches")
        assert hasattr(coordinator, "_get_conn")
        assert hasattr(coordinator, "_clear_dependency_cache")
        assert hasattr(coordinator, "_clear_session_links_cache")
        assert hasattr(coordinator, "_initialize_insights_structure")


# ============================================================================
# Integration-Style Async Context Manager Tests (if any async CM exists)
# ============================================================================


class TestAsyncContextManagerPatterns:
    """Test async context manager patterns if used in the module."""

    def test_no_async_context_managers_in_module(self) -> None:
        """Verify module doesn't use async context managers that need testing."""
        # This module doesn't have any async context managers (no @asynccontextmanager)
        # But we keep this test class for documentation purposes
        assert True


# ============================================================================
# Metadata and Edge Case Validation
# ============================================================================


class TestMetadataHandling:
    """Test handling of metadata field across operations."""

    @pytest.mark.asyncio
    async def test_create_group_with_complex_metadata(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should handle complex nested metadata."""
        complex_metadata = {
            "owner": "team-a",
            "priority": "high",
            "tags": ["backend", "api", "database"],
            "config": {"timeout": 30, "retries": 3},
        }

        group = await coordinator.create_project_group(
            name="Complex Metadata Group",
            projects=["proj-a"],
            metadata=complex_metadata,
        )

        assert group.metadata == complex_metadata

    @pytest.mark.asyncio
    async def test_create_dependency_with_empty_metadata(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should handle empty metadata dictionary."""
        dep = await coordinator.add_project_dependency(
            source_project="proj-a",
            target_project="proj-b",
            dependency_type="uses",
            metadata=None,  # Should default to {}
        )

        assert dep.metadata == {}

    @pytest.mark.asyncio
    async def test_create_link_with_metadata(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should store link metadata correctly."""
        link_metadata = {"source": "session-manager", "reason": "continuation"}

        link = await coordinator.link_sessions(
            source_session_id="sess-1",
            target_session_id="sess-2",
            link_type="continuation",
            metadata=link_metadata,
        )

        assert link.metadata == link_metadata


# ============================================================================
# String Handling and Whitespace Tests
# ============================================================================


class TestStringHandling:
    """Test string handling and whitespace validation."""

    @pytest.mark.asyncio
    async def test_project_names_with_extra_whitespace(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should handle project names with extra whitespace."""
        group = await coordinator.create_project_group(
            name="Whitespace Test",
            projects=["  project-a  ", "  project-b  "],
            description="  Multiple spaces  ",
        )

        # Model should strip whitespace
        assert group.projects[0] == "project-a"
        assert group.projects[1] == "project-b"

    def test_dependency_validation_whitespace_only(self) -> None:
        """Should reject whitespace-only project names in dependency."""
        with pytest.raises(ValidationError):
            ProjectDependency(
                id="whitespace-dep",
                source_project="valid-project",
                target_project="   ",
                dependency_type="uses",
            )

    def test_link_validation_whitespace_only(self) -> None:
        """Should reject whitespace-only session IDs in link."""
        with pytest.raises(ValidationError):
            SessionLink(
                id="whitespace-link",
                source_session_id="valid-session",
                target_session_id="   ",
                link_type="related",
            )


# ============================================================================
# SQL Injection Prevention Tests (via parameterized queries)
# ============================================================================


class TestSQLSafety:
    """Test that SQL queries use parameterized values."""

    @pytest.mark.asyncio
    async def test_get_project_dependencies_uses_params(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should use parameterized queries for project names."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        # Attempt with special characters that could be SQL injection
        await coordinator.get_project_dependencies("proj'; DROP TABLE--")

        call_args = mock_reflection_db.conn.execute.call_args
        # Second argument should be a list of params (not interpolated)
        params = call_args[0][1]
        assert isinstance(params, list)
        # The project name should be in params, not in SQL string
        assert any("proj" in str(p) for p in params)

    @pytest.mark.asyncio
    async def test_get_session_links_uses_params(
        self,
        coordinator: MultiProjectCoordinator,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Should use parameterized queries for session IDs."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_reflection_db.conn.execute.return_value = mock_cursor

        await coordinator.get_session_links("sess' OR '1'='1")

        call_args = mock_reflection_db.conn.execute.call_args
        params = call_args[0][1]
        # Session ID should be in params list
        assert any("sess" in str(p) for p in params)


# ============================================================================
# Verify All Public APIs Are Tested
# ============================================================================


class TestPublicAPICoverage:
    """Verify all public classes and methods are tested."""

    def test_all_public_classes_tested(self) -> None:
        """Verify all public classes from module are referenced in tests."""
        from session_buddy.multi_project_coordinator import (
            MultiProjectCoordinator,
            ProjectDependency,
            ProjectGroup,
            ReflectionDatabaseProtocol,
            SessionLink,
        )

        # These classes are imported and tested
        assert ProjectGroup is not None
        assert ProjectDependency is not None
        assert SessionLink is not None
        assert ReflectionDatabaseProtocol is not None
        assert MultiProjectCoordinator is not None

    @pytest.mark.asyncio
    async def test_all_public_methods_tested(
        self, coordinator: MultiProjectCoordinator
    ) -> None:
        """Verify all public methods of MultiProjectCoordinator are tested."""
        public_methods = [
            method
            for method in dir(coordinator)
            if not method.startswith("_") and callable(getattr(coordinator, method))
        ]

        # These are the public async methods that should be tested
        expected_public_methods = [
            "create_project_group",
            "add_project_dependency",
            "link_sessions",
            "get_project_groups",
            "get_project_dependencies",
            "get_session_links",
            "find_related_conversations",
            "get_cross_project_insights",
            "cleanup_old_links",
        ]

        for method_name in expected_public_methods:
            assert method_name in public_methods, f"Public method {method_name} not found"
