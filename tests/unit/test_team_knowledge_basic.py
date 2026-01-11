"""Tests for team_knowledge module."""

import pytest
from session_buddy.team_knowledge import (
    AccessLevel,
    Team,
    TeamReflection,
    TeamUser,
    UserRole,
)


def test_user_role_enum():
    """Test UserRole enum values."""
    assert UserRole.VIEWER.value == "viewer"
    assert UserRole.CONTRIBUTOR.value == "contributor"
    assert UserRole.MODERATOR.value == "moderator"
    assert UserRole.ADMIN.value == "admin"


def test_access_level_enum():
    """Test AccessLevel enum values."""
    assert AccessLevel.PRIVATE.value == "private"
    assert AccessLevel.TEAM.value == "team"
    assert AccessLevel.PROJECT.value == "project"
    assert AccessLevel.PUBLIC.value == "public"


def test_team_user_dataclass():
    """Test TeamUser dataclass."""
    from datetime import datetime
    user = TeamUser(
        user_id="user123",
        username="testuser",
        email="test@example.com",
        role=UserRole.CONTRIBUTOR,
        teams=["team123"],
        created_at=datetime.now(),
        last_active=datetime.now(),
        permissions={"read": True, "write": False}
    )

    assert user.user_id == "user123"
    assert user.username == "testuser"
    assert user.role == UserRole.CONTRIBUTOR
    assert user.email == "test@example.com"
    assert user.teams == ["team123"]
    assert user.permissions == {"read": True, "write": False}


def test_team_reflection_dataclass():
    """Test TeamReflection dataclass."""
    from datetime import datetime
    reflection = TeamReflection(
        id="ref123",
        content="Test reflection content",
        author_id="user123",
        team_id="team123",
        project_id="proj123",
        access_level=AccessLevel.TEAM,
        tags=["test", "example"],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        votes=0,
        viewers=set(),
        editors=set()
    )

    assert reflection.id == "ref123"
    assert reflection.content == "Test reflection content"
    assert reflection.author_id == "user123"
    assert reflection.team_id == "team123"
    assert reflection.project_id == "proj123"
    assert reflection.access_level == AccessLevel.TEAM
    assert reflection.tags == ["test", "example"]


def test_team_dataclass():
    """Test Team dataclass."""
    from datetime import datetime
    team = Team(
        team_id="team123",
        name="Test Team",
        description="A test team",
        owner_id="owner123",
        members={"user123", "user456"},
        projects={"project1", "project2"},
        created_at=datetime.now(),
        settings={"setting1": "value1"}
    )

    assert team.team_id == "team123"
    assert team.name == "Test Team"
    assert team.description == "A test team"
    assert team.owner_id == "owner123"
    assert "user123" in team.members
    assert "project1" in team.projects
    assert team.settings == {"setting1": "value1"}
