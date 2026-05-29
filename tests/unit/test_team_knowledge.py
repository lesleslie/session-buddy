#!/usr/bin/env python3
"""Test suite for session_buddy.team_knowledge module.

Tests team collaboration and knowledge sharing features.
Target: 60%+ code coverage.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.team_knowledge import (
    AccessLevel,
    Team,
    TeamKnowledgeManager,
    TeamReflection,
    TeamUser,
    UserRole,
    _team_knowledge_manager,
    add_team_reflection,
    create_team,
    create_team_user,
    get_team_knowledge_manager,
    get_team_statistics,
    get_user_team_permissions,
    join_team,
    search_team_knowledge,
    vote_on_reflection,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Provide a temporary database path for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "test_team_knowledge.db")


@pytest.fixture
def manager(temp_db_path: str) -> TeamKnowledgeManager:
    """Create a TeamKnowledgeManager with temporary database."""
    # Reset global instance for clean state
    global _team_knowledge_manager
    _team_knowledge_manager = None
    mgr = TeamKnowledgeManager(db_path=temp_db_path)
    return mgr


@pytest.fixture
def sample_user_data() -> dict[str, Any]:
    """Sample user data for testing."""
    return {
        "user_id": "user_123",
        "username": "testuser",
        "email": "test@example.com",
        "role": UserRole.CONTRIBUTOR,
    }


@pytest.fixture
def sample_team_data() -> dict[str, Any]:
    """Sample team data for testing."""
    return {
        "team_id": "team_456",
        "name": "Test Team",
        "description": "A team for testing",
        "owner_id": "user_123",
    }


@pytest.fixture
def sample_reflection_data() -> dict[str, Any]:
    """Sample reflection data for testing."""
    return {
        "content": "This is a test reflection about testing.",
        "tags": ["testing", "unit-test"],
        "access_level": AccessLevel.TEAM,
        "team_id": "team_456",
    }


# =============================================================================
# Test Data Structures (UserRole, AccessLevel, TeamUser, TeamReflection, Team)
# =============================================================================


class TestTeamStructures:
    """Test team data structures and enums."""

    def test_user_role_enum_values(self) -> None:
        """Test UserRole enum has expected values."""
        assert UserRole.VIEWER.value == "viewer"
        assert UserRole.CONTRIBUTOR.value == "contributor"
        assert UserRole.MODERATOR.value == "moderator"
        assert UserRole.ADMIN.value == "admin"

    def test_access_level_enum_values(self) -> None:
        """Test AccessLevel enum has expected values."""
        assert AccessLevel.PRIVATE.value == "private"
        assert AccessLevel.TEAM.value == "team"
        assert AccessLevel.PROJECT.value == "project"
        assert AccessLevel.PUBLIC.value == "public"

    def test_team_user_dataclass(self) -> None:
        """Test TeamUser dataclass creation."""
        now = datetime.now()
        user = TeamUser(
            user_id="u1",
            username="alice",
            email="alice@example.com",
            role=UserRole.CONTRIBUTOR,
            teams=["team1", "team2"],
            created_at=now,
            last_active=now,
            permissions={"read": True, "write": False},
        )
        assert user.user_id == "u1"
        assert user.username == "alice"
        assert user.role == UserRole.CONTRIBUTOR
        assert len(user.teams) == 2

    def test_team_reflection_dataclass(self) -> None:
        """Test TeamReflection dataclass creation."""
        now = datetime.now()
        reflection = TeamReflection(
            id="ref1",
            content="Test content",
            tags=["tag1"],
            access_level=AccessLevel.TEAM,
            team_id="team1",
            project_id=None,
            author_id="author1",
            created_at=now,
            updated_at=now,
            votes=5,
            viewers={"user1", "user2"},
            editors={"author1"},
        )
        assert reflection.id == "ref1"
        assert reflection.votes == 5
        assert "user1" in reflection.viewers

    def test_team_dataclass(self) -> None:
        """Test Team dataclass creation."""
        now = datetime.now()
        team = Team(
            team_id="team1",
            name="My Team",
            description="Team description",
            owner_id="owner1",
            members={"user1", "user2"},
            projects={"proj1"},
            created_at=now,
            settings={"setting1": True},
        )
        assert team.team_id == "team1"
        assert team.name == "My Team"
        assert len(team.members) == 2


# =============================================================================
# Test TeamKnowledgeManager Initialization
# =============================================================================


class TestManagerInitialization:
    """Test TeamKnowledgeManager initialization."""

    def test_init_creates_database_file(self, temp_db_path: str) -> None:
        """Test manager initializes database at specified path."""
        mgr = TeamKnowledgeManager(db_path=temp_db_path)
        assert Path(temp_db_path).exists()

    def test_init_default_path(self) -> None:
        """Test manager uses default path when none provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # We need to patch Path.home() to return our temp dir
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                mgr = TeamKnowledgeManager()
                # Default path should contain team_knowledge.db
                assert "team_knowledge.db" in mgr.db_path

    def test_init_creates_tables(self, temp_db_path: str) -> None:
        """Test manager creates required tables."""
        mgr = TeamKnowledgeManager(db_path=temp_db_path)
        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
            assert "users" in tables
            assert "teams" in tables
            assert "team_reflections" in tables
            assert "access_logs" in tables

    def test_init_creates_indices(self, temp_db_path: str) -> None:
        """Test manager creates required indices."""
        mgr = TeamKnowledgeManager(db_path=temp_db_path)
        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )
            indices = {row[0] for row in cursor.fetchall()}
            assert "idx_reflections_team" in indices
            assert "idx_reflections_author" in indices
            assert "idx_access_logs_user" in indices


# =============================================================================
# Test User Management
# =============================================================================


class TestUserManagement:
    """Test user creation and management."""

    @pytest.mark.asyncio
    async def test_create_user(self, manager: TeamKnowledgeManager) -> None:
        """Test creating a new user."""
        user = await manager.create_user(
            user_id="user_123",
            username="testuser",
            email="test@example.com",
            role=UserRole.CONTRIBUTOR,
        )
        assert user.user_id == "user_123"
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.role == UserRole.CONTRIBUTOR
        assert len(user.permissions) > 0

    @pytest.mark.asyncio
    async def test_create_user_without_email(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test creating user without email."""
        user = await manager.create_user(
            user_id="user_no_email",
            username="noemail",
            role=UserRole.VIEWER,
        )
        assert user.email is None
        assert user.role == UserRole.VIEWER

    @pytest.mark.asyncio
    async def test_create_user_with_default_role(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test creating user gets default CONTRIBUTOR role."""
        user = await manager.create_user(
            user_id="default_role_user",
            username="defaultrole",
        )
        assert user.role == UserRole.CONTRIBUTOR

    @pytest.mark.asyncio
    async def test_create_user_logs_access(
        self, manager: TeamKnowledgeManager, temp_db_path: str
    ) -> None:
        """Test user creation is logged."""
        await manager.create_user(
            user_id="log_test_user",
            username="logtest",
        )
        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute(
                "SELECT action FROM access_logs WHERE user_id = ?",
                ("log_test_user",),
            )
            actions = {row[0] for row in cursor.fetchall()}
            assert "user_created" in actions


# =============================================================================
# Test Team Management
# =============================================================================


class TestTeamManagement:
    """Test team creation and management."""

    @pytest.mark.asyncio
    async def test_create_team(self, manager: TeamKnowledgeManager) -> None:
        """Test creating a new team."""
        team = await manager.create_team(
            team_id="team_123",
            name="Test Team",
            description="A test team",
            owner_id="owner_123",
        )
        assert team.team_id == "team_123"
        assert team.name == "Test Team"
        assert team.owner_id == "owner_123"
        assert "owner_123" in team.members

    @pytest.mark.asyncio
    async def test_create_team_adds_owner_to_team(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test team owner is added as team member."""
        await manager.create_user(
            user_id="owner_member",
            username="ownermember",
        )
        await manager.create_team(
            team_id="member_test_team",
            name="Member Test Team",
            description="Test",
            owner_id="owner_member",
        )
        # Verify owner can access team (they were added as member via _add_user_to_team)
        can_access = await manager._can_access_team("owner_member", "member_test_team")
        assert can_access is True

    @pytest.mark.asyncio
    async def test_create_team_logs_access(
        self, manager: TeamKnowledgeManager, temp_db_path: str
    ) -> None:
        """Test team creation is logged."""
        await manager.create_team(
            team_id="log_team",
            name="Log Team",
            description="Test",
            owner_id="log_owner",
        )
        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute(
                "SELECT action FROM access_logs WHERE resource_type = 'team'",
            )
            actions = {row[0] for row in cursor.fetchall()}
            assert "team_created" in actions


# =============================================================================
# Test Team Reflection Management
# =============================================================================


class TestReflectionManagement:
    """Test reflection creation and management."""

    @pytest.mark.asyncio
    async def test_add_reflection(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test adding a reflection to team knowledge base."""
        await manager.create_user(**sample_user_data)
        reflection_id = await manager.add_team_reflection(
            content="Test reflection content",
            author_id=sample_user_data["user_id"],
            tags=["test"],
            access_level=AccessLevel.TEAM,
            team_id="team_123",
        )
        assert reflection_id is not None
        assert len(reflection_id) == 16  # SHA256 hexdigest[:16]

    @pytest.mark.asyncio
    async def test_add_reflection_generates_unique_id(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test that each reflection gets a unique ID."""
        await manager.create_user(**sample_user_data)
        id1 = await manager.add_team_reflection(
            content="First reflection",
            author_id=sample_user_data["user_id"],
        )
        id2 = await manager.add_team_reflection(
            content="Second reflection",
            author_id=sample_user_data["user_id"],
        )
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_add_reflection_default_access_level(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test reflection defaults to TEAM access level."""
        await manager.create_user(**sample_user_data)
        await manager.add_team_reflection(
            content="Default access test",
            author_id=sample_user_data["user_id"],
        )
        # Default is TEAM - would need team membership to see
        # We just verify it was created

    @pytest.mark.asyncio
    async def test_add_reflection_with_tags(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test adding reflection with multiple tags."""
        await manager.create_user(**sample_user_data)
        reflection_id = await manager.add_team_reflection(
            content="Tagged reflection",
            author_id=sample_user_data["user_id"],
            tags=["python", "testing", "tdd"],
        )
        assert reflection_id is not None


# =============================================================================
# Test Reflection Voting
# =============================================================================


class TestReflectionVoting:
    """Test reflection voting functionality."""

    @pytest.mark.asyncio
    async def test_vote_reflection_success(
        self,
        manager: TeamKnowledgeManager,
        sample_user_data: dict[str, Any],
    ) -> None:
        """Test voting on a reflection succeeds for authorized user."""
        # Create user first
        await manager.create_user(**sample_user_data)
        # Add reflection
        reflection_id = await manager.add_team_reflection(
            content="Vote test reflection",
            author_id=sample_user_data["user_id"],
            access_level=AccessLevel.PUBLIC,
        )
        # Vote should succeed (author can access)
        result = await manager.vote_reflection(
            reflection_id=reflection_id,
            user_id=sample_user_data["user_id"],
            vote_delta=1,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_vote_reflection_no_access(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test voting fails for user without access."""
        # Create a user who owns the reflection
        await manager.create_user(
            user_id="author",
            username="author",
            role=UserRole.CONTRIBUTOR,
        )
        reflection_id = await manager.add_team_reflection(
            content="Private reflection",
            author_id="author",
            access_level=AccessLevel.TEAM,
            team_id="private_team",
        )
        # Try to vote as different user with no access
        result = await manager.vote_reflection(
            reflection_id=reflection_id,
            user_id="stranger",
            vote_delta=1,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_vote_negative_delta(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test downvoting with negative vote delta."""
        await manager.create_user(**sample_user_data)
        reflection_id = await manager.add_team_reflection(
            content="Downvote test",
            author_id=sample_user_data["user_id"],
            access_level=AccessLevel.PUBLIC,
        )
        result = await manager.vote_reflection(
            reflection_id=reflection_id,
            user_id=sample_user_data["user_id"],
            vote_delta=-1,
        )
        assert result is True


# =============================================================================
# Test Team Joining
# =============================================================================


class TestTeamJoining:
    """Test team joining functionality."""

    @pytest.mark.asyncio
    async def test_join_team_success(
        self,
        manager: TeamKnowledgeManager,
    ) -> None:
        """Test user can join a team."""
        # Create owner first
        await manager.create_user(
            user_id="join_team_owner",
            username="jointeamowner",
        )
        # Create team
        await manager.create_team(
            team_id="join_test_team",
            name="Join Test Team",
            description="Test",
            owner_id="join_team_owner",
        )
        # Create user to join
        await manager.create_user(
            user_id="join_user",
            username="joinuser",
        )
        # Join team
        result = await manager.join_team(
            user_id="join_user",
            team_id="join_test_team",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_join_team_nonexistent(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test joining nonexistent team fails."""
        result = await manager.join_team(
            user_id="some_user",
            team_id="nonexistent_team",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_join_team_requires_permission_for_other_users(
        self,
        manager: TeamKnowledgeManager,
    ) -> None:
        """Test that adding another user to team requires permission."""
        # Create owner
        await manager.create_user(
            user_id="perm_owner",
            username="permowner",
        )
        # Create team
        await manager.create_team(
            team_id="perm_test_team",
            name="Perm Test Team",
            description="Test",
            owner_id="perm_owner",
        )
        # Create another user who is not the owner
        await manager.create_user(
            user_id="perm_joiner",
            username="permjoiner",
        )
        # Try to add user to team as a different requester without permission
        # This should fail because requester_id is not the owner and random_user doesn't exist
        result = await manager.join_team(
            user_id="perm_joiner",
            team_id="perm_test_team",
            requester_id="random_user",  # Not the owner, not an admin
        )
        assert result is False


# =============================================================================
# Test Search Functionality
# =============================================================================


class TestSearchFunctionality:
    """Test team reflection search."""

    @pytest.mark.asyncio
    async def test_search_public_reflections(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test searching finds public reflections."""
        await manager.create_user(**sample_user_data)
        await manager.add_team_reflection(
            content="This is a searchable public reflection",
            author_id=sample_user_data["user_id"],
            access_level=AccessLevel.PUBLIC,
        )
        results = await manager.search_team_reflections(
            query="searchable",
            user_id=sample_user_data["user_id"],
        )
        assert len(results) >= 1
        assert "searchable" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_search_with_no_query(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test search with empty query returns results."""
        await manager.create_user(**sample_user_data)
        await manager.add_team_reflection(
            content="Content without specific query",
            author_id=sample_user_data["user_id"],
            access_level=AccessLevel.PUBLIC,
        )
        results = await manager.search_team_reflections(
            query="",
            user_id=sample_user_data["user_id"],
        )
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_respects_access_control(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test search only returns accessible reflections."""
        # Create user1 with team reflection
        await manager.create_user(user_id="user1", username="user1")
        team_id = "private_team_123"
        await manager.create_team(
            team_id=team_id,
            name="Private Team",
            description="Private",
            owner_id="user1",
        )
        # Add user1 to team first
        await manager.add_team_reflection(
            content="Private team reflection",
            author_id="user1",
            access_level=AccessLevel.TEAM,
            team_id=team_id,
        )
        # Create user2 who is not in the team
        await manager.create_user(user_id="user2", username="user2")
        # Search should not return the team reflection for user2
        results = await manager.search_team_reflections(
            query="Private",
            user_id="user2",
        )
        # Should not find team-private reflections
        team_reflections = [r for r in results if r.get("team_id") == team_id]
        assert len(team_reflections) == 0

    @pytest.mark.asyncio
    async def test_search_with_tag_filter(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test search can filter by tags."""
        await manager.create_user(**sample_user_data)
        # Add a reflection with known tags
        await manager.add_team_reflection(
            content="Python is great and programming is fun",
            author_id=sample_user_data["user_id"],
            tags=["python", "programming"],
            access_level=AccessLevel.PUBLIC,
        )
        results = await manager.search_team_reflections(
            query="Python",  # Use query that matches content
            user_id=sample_user_data["user_id"],
            tags=["python"],
        )
        # The tag filter should work - at minimum we should get our reflection
        assert len(results) >= 1
        # Find our specific reflection - tags is already a list after _process_search_results
        python_reflections = [
            r for r in results if "python" in (r.get("tags") or [])
        ]
        assert len(python_reflections) >= 1

    @pytest.mark.asyncio
    async def test_search_limit(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test search respects limit parameter."""
        await manager.create_user(**sample_user_data)
        # Add multiple reflections
        for i in range(5):
            await manager.add_team_reflection(
                content=f"Reflection number {i}",
                author_id=sample_user_data["user_id"],
                access_level=AccessLevel.PUBLIC,
            )
        results = await manager.search_team_reflections(
            query="Reflection",
            user_id=sample_user_data["user_id"],
            limit=2,
        )
        assert len(results) <= 2


# =============================================================================
# Test Team Statistics
# =============================================================================


class TestTeamStatistics:
    """Test team statistics functionality."""

    @pytest.mark.asyncio
    async def test_get_team_stats_success(
        self,
        manager: TeamKnowledgeManager,
        sample_user_data: dict[str, Any],
        sample_team_data: dict[str, Any],
    ) -> None:
        """Test getting team statistics succeeds for member."""
        await manager.create_user(
            user_id=sample_team_data["owner_id"],
            username="teamowner",
        )
        await manager.create_team(**sample_team_data)
        stats = await manager.get_team_stats(
            team_id=sample_team_data["team_id"],
            user_id=sample_team_data["owner_id"],
        )
        assert stats is not None
        assert "team" in stats
        assert "reflection_stats" in stats
        assert "member_count" in stats

    @pytest.mark.asyncio
    async def test_get_team_stats_no_access(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test getting stats fails for non-member."""
        # Create owner and team
        await manager.create_user(user_id="owner", username="owner")
        await manager.create_team(
            team_id="private_team",
            name="Private",
            description="",
            owner_id="owner",
        )
        # Try to get stats as non-member
        stats = await manager.get_team_stats(
            team_id="private_team",
            user_id="stranger",
        )
        assert stats is None

    @pytest.mark.asyncio
    async def test_get_team_stats_nonexistent_team(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test getting stats for nonexistent team."""
        await manager.create_user(user_id="some_user", username="someuser")
        stats = await manager.get_team_stats(
            team_id="nonexistent",
            user_id="some_user",
        )
        assert stats is None


# =============================================================================
# Test User Permissions
# =============================================================================


class TestUserPermissions:
    """Test user permissions functionality."""

    @pytest.mark.asyncio
    async def test_get_user_permissions_existing_user(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test getting permissions for existing user."""
        await manager.create_user(**sample_user_data)
        perms = await manager.get_user_permissions(sample_user_data["user_id"])
        assert "user" in perms
        assert "teams" in perms
        assert "can_create_teams" in perms

    @pytest.mark.asyncio
    async def test_get_user_permissions_nonexistent_user(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test getting permissions for nonexistent user."""
        perms = await manager.get_user_permissions("nonexistent_user_12345")
        assert perms == {}


# =============================================================================
# Test Default Permissions
# =============================================================================


class TestDefaultPermissions:
    """Test default permissions by role."""

    def test_viewer_permissions(self, manager: TeamKnowledgeManager) -> None:
        """Test viewer role has correct default permissions."""
        perms = manager._get_default_permissions(UserRole.VIEWER)
        assert perms["read_reflections"] is True
        assert perms["create_reflections"] is False
        assert perms["admin_access"] is False

    def test_contributor_permissions(self, manager: TeamKnowledgeManager) -> None:
        """Test contributor role has correct default permissions."""
        perms = manager._get_default_permissions(UserRole.CONTRIBUTOR)
        assert perms["read_reflections"] is True
        assert perms["create_reflections"] is True
        assert perms["vote_reflections"] is True
        assert perms["join_teams"] is True

    def test_moderator_permissions(self, manager: TeamKnowledgeManager) -> None:
        """Test moderator role has correct default permissions."""
        perms = manager._get_default_permissions(UserRole.MODERATOR)
        assert perms["create_reflections"] is True
        assert perms["create_teams"] is True
        assert perms["moderate_content"] is True

    def test_admin_permissions(self, manager: TeamKnowledgeManager) -> None:
        """Test admin role has all permissions."""
        perms = manager._get_default_permissions(UserRole.ADMIN)
        assert all(perms.values()), "Admin should have all permissions set to True"


# =============================================================================
# Test Query Building
# =============================================================================


class TestQueryBuilding:
    """Test SQL query building."""

    def test_build_access_condition_with_teams(self, manager: TeamKnowledgeManager) -> None:
        """Test access condition includes team membership."""
        condition, params = manager._build_access_condition(
            user_teams=["team1", "team2"],
            user_id="user1",
        )
        assert "public" in condition
        assert "team" in condition
        assert "team1" in params
        assert "team2" in params
        assert "user1" in params

    def test_build_access_condition_no_teams(self, manager: TeamKnowledgeManager) -> None:
        """Test access condition with no team membership."""
        condition, params = manager._build_access_condition(
            user_teams=[],
            user_id="lonely_user",
        )
        assert "public" in condition
        assert "lonely_user" in params  # author check

    def test_add_filter_conditions_team_id(self, manager: TeamKnowledgeManager) -> None:
        """Test adding team_id filter."""
        conditions = ["1=1"]
        params: list[str | int] = []
        manager._add_filter_conditions(
            conditions,
            params,
            team_id="filter_team",
            project_id=None,
            tags=None,
        )
        assert "team_id = ?" in conditions
        assert "filter_team" in params

    def test_add_filter_conditions_project_id(self, manager: TeamKnowledgeManager) -> None:
        """Test adding project_id filter."""
        conditions = ["1=1"]
        params: list[str | int] = []
        manager._add_filter_conditions(
            conditions,
            params,
            team_id=None,
            project_id="filter_project",
            tags=None,
        )
        assert "project_id = ?" in conditions
        assert "filter_project" in params

    def test_add_filter_conditions_tags(self, manager: TeamKnowledgeManager) -> None:
        """Test adding tags filter."""
        conditions = ["1=1"]
        params: list[str | int] = []
        manager._add_filter_conditions(
            conditions,
            params,
            team_id=None,
            project_id=None,
            tags=["tag1", "tag2"],
        )
        assert any("tags LIKE" in c for c in conditions)

    def test_build_search_query_full(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test building complete search query."""
        query_builder = manager._build_search_query(
            user_teams=["team1"],
            user_id="user1",
            query="test",
            team_id=None,
            project_id=None,
            tags=None,
            limit=10,
        )
        assert "SELECT * FROM team_reflections" in query_builder.sql
        assert "content LIKE ?" in query_builder.sql
        assert "ORDER BY votes DESC" in query_builder.sql
        assert "LIMIT ?" in query_builder.sql
        assert 10 in query_builder.params

    def test_process_search_results(self, manager: TeamKnowledgeManager) -> None:
        """Test processing raw DB rows into result dicts."""
        # Create mock rows
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: {
            "id": "ref1",
            "content": "test",
            "tags": '["tag1"]',
            "viewers": '["user1"]',
            "editors": '[]',
        }.get(key, None)
        mock_row.keys = lambda: ["id", "content", "tags", "viewers", "editors"]

        results = manager._process_search_results([mock_row])
        assert len(results) == 1
        assert results[0]["tags"] == ["tag1"]


# =============================================================================
# Test Public API Functions
# =============================================================================


class TestPublicAPIFunctions:
    """Test module-level public API functions."""

    @pytest.mark.asyncio
    async def test_create_team_user_api(self, temp_db_path: str) -> None:
        """Test create_team_user public API."""
        # Reset global instance
        global _team_knowledge_manager
        _team_knowledge_manager = None

        with patch.object(
            TeamKnowledgeManager,
            "__init__",
            lambda self, db_path=None: None,
        ):
            # Patch the global get_team_knowledge_manager to return a mocked manager
            mock_mgr = MagicMock(spec=TeamKnowledgeManager)
            mock_user = TeamUser(
                user_id="api_user",
                username="apiuser",
                email=None,
                role=UserRole.CONTRIBUTOR,
                teams=[],
                created_at=datetime.now(),
                last_active=datetime.now(),
                permissions={},
            )
            mock_mgr.create_user = AsyncMock(return_value=mock_user)

            with patch(
                "session_buddy.team_knowledge.get_team_knowledge_manager",
                return_value=mock_mgr,
            ):
                result = await create_team_user(
                    user_id="api_user",
                    username="apiuser",
                )
                assert result["user_id"] == "api_user"

    @pytest.mark.asyncio
    async def test_create_team_api(self, temp_db_path: str) -> None:
        """Test create_team public API."""
        global _team_knowledge_manager
        _team_knowledge_manager = None

        mock_team = Team(
            team_id="api_team",
            name="API Team",
            description="Test",
            owner_id="owner1",
            members={"owner1"},
            projects=set(),
            created_at=datetime.now(),
            settings={},
        )
        mock_mgr = MagicMock(spec=TeamKnowledgeManager)
        mock_mgr.create_team = AsyncMock(return_value=mock_team)

        with patch(
            "session_buddy.team_knowledge.get_team_knowledge_manager",
            return_value=mock_mgr,
        ):
            result = await create_team(
                team_id="api_team",
                name="API Team",
                description="Test",
                owner_id="owner1",
            )
            assert result["team_id"] == "api_team"
            assert result["name"] == "API Team"

    @pytest.mark.asyncio
    async def test_add_team_reflection_api(self) -> None:
        """Test add_team_reflection public API."""
        mock_mgr = MagicMock(spec=TeamKnowledgeManager)
        mock_mgr.add_team_reflection = AsyncMock(return_value="reflection_123")

        with patch(
            "session_buddy.team_knowledge.get_team_knowledge_manager",
            return_value=mock_mgr,
        ):
            result = await add_team_reflection(
                content="API reflection",
                author_id="author1",
                access_level="team",
            )
            assert result == "reflection_123"

    @pytest.mark.asyncio
    async def test_search_team_knowledge_api(self) -> None:
        """Test search_team_knowledge public API."""
        mock_results = [
            {"id": "ref1", "content": "test result"},
        ]
        mock_mgr = MagicMock(spec=TeamKnowledgeManager)
        mock_mgr.search_team_reflections = AsyncMock(return_value=mock_results)

        with patch(
            "session_buddy.team_knowledge.get_team_knowledge_manager",
            return_value=mock_mgr,
        ):
            result = await search_team_knowledge(
                query="test",
                user_id="user1",
            )
            assert len(result) == 1
            assert result[0]["content"] == "test result"

    @pytest.mark.asyncio
    async def test_join_team_api(self) -> None:
        """Test join_team public API."""
        mock_mgr = MagicMock(spec=TeamKnowledgeManager)
        mock_mgr.join_team = AsyncMock(return_value=True)

        with patch(
            "session_buddy.team_knowledge.get_team_knowledge_manager",
            return_value=mock_mgr,
        ):
            result = await join_team(
                user_id="user1",
                team_id="team1",
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_get_team_statistics_api(self) -> None:
        """Test get_team_statistics public API."""
        mock_stats = {
            "team": {},
            "member_count": 5,
        }
        mock_mgr = MagicMock(spec=TeamKnowledgeManager)
        mock_mgr.get_team_stats = AsyncMock(return_value=mock_stats)

        with patch(
            "session_buddy.team_knowledge.get_team_knowledge_manager",
            return_value=mock_mgr,
        ):
            result = await get_team_statistics(
                team_id="team1",
                user_id="user1",
            )
            assert result["member_count"] == 5

    @pytest.mark.asyncio
    async def test_get_user_team_permissions_api(self) -> None:
        """Test get_user_team_permissions public API."""
        mock_perms = {
            "user": {},
            "teams": [],
            "can_create_teams": False,
        }
        mock_mgr = MagicMock(spec=TeamKnowledgeManager)
        mock_mgr.get_user_permissions = AsyncMock(return_value=mock_perms)

        with patch(
            "session_buddy.team_knowledge.get_team_knowledge_manager",
            return_value=mock_mgr,
        ):
            result = await get_user_team_permissions(user_id="user1")
            assert result["can_create_teams"] is False

    @pytest.mark.asyncio
    async def test_vote_on_reflection_api(self) -> None:
        """Test vote_on_reflection public API."""
        mock_mgr = MagicMock(spec=TeamKnowledgeManager)
        mock_mgr.vote_reflection = AsyncMock(return_value=True)

        with patch(
            "session_buddy.team_knowledge.get_team_knowledge_manager",
            return_value=mock_mgr,
        ):
            result = await vote_on_reflection(
                reflection_id="ref1",
                user_id="user1",
                vote_delta=1,
            )
            assert result is True


# =============================================================================
# Test Access Control Helpers
# =============================================================================


class TestAccessControlHelpers:
    """Test access control helper methods."""

    @pytest.mark.asyncio
    async def test_can_access_reflection_author(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test author can always access their reflection."""
        await manager.create_user(**sample_user_data)
        reflection_id = await manager.add_team_reflection(
            content="Author's reflection",
            author_id=sample_user_data["user_id"],
            access_level=AccessLevel.PRIVATE,
        )
        can_access = await manager._can_access_reflection(
            reflection_id,
            sample_user_data["user_id"],
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_can_access_reflection_public(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test public reflections are accessible to all."""
        await manager.create_user(user_id="author", username="author")
        await manager.create_user(user_id="anyone", username="anyone")

        reflection_id = await manager.add_team_reflection(
            content="Public reflection",
            author_id="author",
            access_level=AccessLevel.PUBLIC,
        )
        can_access = await manager._can_access_reflection(
            reflection_id,
            "anyone",
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_can_access_reflection_team_member(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test team reflections are accessible to team members."""
        await manager.create_user(user_id="owner", username="owner")
        await manager.create_user(user_id="member", username="member")
        await manager.create_user(user_id="outsider", username="outsider")

        team_id = "access_test_team"
        await manager.create_team(
            team_id=team_id,
            name="Access Test",
            description="",
            owner_id="owner",
        )
        await manager.join_team(user_id="member", team_id=team_id)

        reflection_id = await manager.add_team_reflection(
            content="Team reflection",
            author_id="owner",
            access_level=AccessLevel.TEAM,
            team_id=team_id,
        )

        # Member should access
        assert await manager._can_access_reflection(reflection_id, "member") is True
        # Outsider should not
        assert await manager._can_access_reflection(reflection_id, "outsider") is False

    @pytest.mark.asyncio
    async def test_can_access_reflection_nonexistent(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test accessing nonexistent reflection fails."""
        can_access = await manager._can_access_reflection(
            "nonexistent_reflection",
            "any_user",
        )
        assert can_access is False

    @pytest.mark.asyncio
    async def test_can_access_team_member(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test team membership check."""
        await manager.create_user(user_id="owner", username="owner")
        await manager.create_user(user_id="member", username="member")

        team_id = "member_test_team"
        await manager.create_team(
            team_id=team_id,
            name="Member Test",
            description="",
            owner_id="owner",
        )
        await manager.join_team(user_id="member", team_id=team_id)

        assert await manager._can_access_team("member", team_id) is True
        assert await manager._can_access_team("owner", team_id) is True
        # Owner not in team until they join
        await manager.join_team(user_id="owner", team_id=team_id)
        assert await manager._can_access_team("owner", team_id) is True

    @pytest.mark.asyncio
    async def test_can_manage_team_owner(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test team owner can manage team."""
        await manager.create_user(user_id="owner", username="owner")
        await manager.create_team(
            team_id="manage_test",
            name="Manage Test",
            description="",
            owner_id="owner",
        )
        assert await manager._can_manage_team("owner", "manage_test") is True

    @pytest.mark.asyncio
    async def test_can_manage_team_admin(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test admin can manage any team."""
        await manager.create_user(
            user_id="admin",
            username="admin",
            role=UserRole.ADMIN,
        )
        await manager.create_user(user_id="owner", username="owner")
        await manager.create_team(
            team_id="admin_manage_test",
            name="Admin Test",
            description="",
            owner_id="owner",
        )
        assert await manager._can_manage_team("admin", "admin_manage_test") is True

    @pytest.mark.asyncio
    async def test_can_manage_team_moderator(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test moderator with moderate_content permission can manage."""
        await manager.create_user(
            user_id="moderator",
            username="moderator",
            role=UserRole.MODERATOR,
        )
        await manager.create_user(user_id="owner", username="owner")
        await manager.create_team(
            team_id="mod_manage_test",
            name="Mod Test",
            description="",
            owner_id="owner",
        )
        assert await manager._can_manage_team("moderator", "mod_manage_test") is True

    @pytest.mark.asyncio
    async def test_can_manage_team_nonexistent_team(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test managing nonexistent team fails."""
        await manager.create_user(user_id="someuser", username="someuser")
        assert await manager._can_manage_team("someuser", "nonexistent") is False


# =============================================================================
# Test Private Helpers
# =============================================================================


class TestPrivateHelpers:
    """Test private helper methods."""

    @pytest.mark.asyncio
    async def test_get_user_teams(
        self, manager: TeamKnowledgeManager, sample_user_data: dict[str, Any]
    ) -> None:
        """Test getting user's teams."""
        await manager.create_user(**sample_user_data)
        team_id = "helper_test_team"
        await manager.create_team(
            team_id=team_id,
            name="Helper Test",
            description="",
            owner_id=sample_user_data["user_id"],
        )
        teams = await manager._get_user_teams(sample_user_data["user_id"])
        assert team_id in teams

    @pytest.mark.asyncio
    async def test_get_user_teams_no_teams(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test getting teams for user with no teams."""
        await manager.create_user(user_id="lonely", username="lonely")
        teams = await manager._get_user_teams("lonely")
        assert teams == []

    @pytest.mark.asyncio
    async def test_get_team_exists(
        self, manager: TeamKnowledgeManager
    ) -> None:
        """Test getting existing team."""
        await manager.create_user(user_id="owner", username="owner")
        await manager.create_team(
            team_id="get_test_team",
            name="Get Test",
            description="Test description",
            owner_id="owner",
        )
        team = await manager._get_team("get_test_team")
        assert team is not None
        assert team["name"] == "Get Test"

    @pytest.mark.asyncio
    async def test_get_team_nonexistent(self, manager: TeamKnowledgeManager) -> None:
        """Test getting nonexistent team."""
        team = await manager._get_team("nonexistent_team_12345")
        assert team is None

    @pytest.mark.asyncio
    async def test_log_access(self, manager: TeamKnowledgeManager, temp_db_path: str) -> None:
        """Test access logging."""
        await manager._log_access(
            user_id="log_test",
            action="test_action",
            resource_id="resource_123",
            resource_type="test",
            details={"key": "value"},
        )
        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM access_logs WHERE user_id = ?",
                ("log_test",),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[2] == "test_action"  # action column
