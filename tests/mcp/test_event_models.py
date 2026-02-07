"""Tests for admin shell session event models in Session-Buddy.

This test suite validates the Pydantic models used for session lifecycle
event tracking received from admin shells via MCP.
"""

import pytest
from pydantic import ValidationError

from session_buddy.mcp.event_models import (
    EnvironmentInfo,
    ErrorResponse,
    SessionEndEvent,
    SessionEndResult,
    SessionStartEvent,
    SessionStartResult,
    UserInfo,
    get_session_end_event_schema,
    get_session_end_result_schema,
    get_session_start_event_schema,
    get_session_start_result_schema,
)


class TestUserInfo:
    """Test UserInfo model validation."""

    def test_valid_user_info(self):
        """Test creating valid UserInfo."""
        user = UserInfo(username="john", home="/home/john")
        assert user.username == "john"
        assert user.home == "/home/john"

    def test_whitespace_stripping(self):
        """Test that whitespace is stripped from user fields."""
        user = UserInfo(username="  john  ", home="  /home/john  ")
        assert user.username == "john"
        assert user.home == "/home/john"

    def test_username_max_length(self):
        """Test username max length validation (100 chars)."""
        long_username = "a" * 101
        with pytest.raises(ValidationError) as exc_info:
            UserInfo(username=long_username, home="/home/john")
        assert "at most 100 characters" in str(exc_info.value)

    def test_home_max_length(self):
        """Test home directory max length validation (500 chars)."""
        long_home = "/a" * 251  # 502 characters
        with pytest.raises(ValidationError) as exc_info:
            UserInfo(username="john", home=long_home)
        assert "at most 500 characters" in str(exc_info.value)


class TestEnvironmentInfo:
    """Test EnvironmentInfo model validation."""

    def test_valid_environment_info(self):
        """Test creating valid EnvironmentInfo."""
        env = EnvironmentInfo(
            python_version="3.13.0",
            platform="Linux-6.5.0-x86_64",
            cwd="/home/john/projects"
        )
        assert env.python_version == "3.13.0"
        assert env.platform == "Linux-6.5.0-x86_64"
        assert env.cwd == "/home/john/projects"

    def test_cwd_whitespace_stripping(self):
        """Test that whitespace is stripped from cwd."""
        env = EnvironmentInfo(
            python_version="3.13.0",
            platform="Linux",
            cwd="  /home/john/projects  "
        )
        assert env.cwd == "/home/john/projects"

    def test_cwd_max_length(self):
        """Test cwd max length validation (500 chars)."""
        long_cwd = "/a" * 251  # 502 characters
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentInfo(
                python_version="3.13.0",
                platform="Linux",
                cwd=long_cwd
            )
        assert "at most 500 characters" in str(exc_info.value)


class TestSessionStartEvent:
    """Test SessionStartEvent model validation."""

    @pytest.fixture
    def valid_user(self):
        """Fixture for valid UserInfo."""
        return UserInfo(username="john", home="/home/john")

    @pytest.fixture
    def valid_environment(self):
        """Fixture for valid EnvironmentInfo."""
        return EnvironmentInfo(
            python_version="3.13.0",
            platform="Linux-6.5.0-x86_64",
            cwd="/home/john/projects"
        )

    def test_valid_session_start_event(
        self, valid_user, valid_environment
    ):
        """Test creating valid SessionStartEvent."""
        event = SessionStartEvent(
            event_version="1.0",
            event_id="550e8400-e29b-41d4-a716-446655440000",
            component_name="mahavishnu",
            shell_type="MahavishnuShell",
            timestamp="2026-02-06T12:34:56.789Z",
            pid=12345,
            user=valid_user,
            hostname="server01",
            environment=valid_environment
        )
        assert event.event_version == "1.0"
        assert event.event_type == "session_start"
        assert event.component_name == "mahavishnu"
        assert event.shell_type == "MahavishnuShell"
        assert event.pid == 12345

    def test_uuid_validation(self, valid_user, valid_environment):
        """Test that invalid UUID is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SessionStartEvent(
                event_version="1.0",
                event_id="not-a-valid-uuid",
                component_name="mahavishnu",
                shell_type="MahavishnuShell",
                timestamp="2026-02-06T12:34:56.789Z",
                pid=12345,
                user=valid_user,
                hostname="server01",
                environment=valid_environment
            )
        assert "Invalid UUID v4 format" in str(exc_info.value)

    def test_version_validation(self, valid_user, valid_environment):
        """Test that unsupported version is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SessionStartEvent(
                event_version="2.0",
                event_id="550e8400-e29b-41d4-a716-446655440000",
                component_name="mahavishnu",
                shell_type="MahavishnuShell",
                timestamp="2026-02-06T12:34:56.789Z",
                pid=12345,
                user=valid_user,
                hostname="server01",
                environment=valid_environment
            )
        assert "Unsupported event version" in str(exc_info.value)

    def test_component_name_validation(self, valid_user, valid_environment):
        """Test that invalid component names are rejected."""
        invalid_names = [
            "invalid@component",
            "component with spaces",
            "component/with/slashes",
            "component.with.dots",
        ]

        for invalid_name in invalid_names:
            with pytest.raises(ValidationError) as exc_info:
                SessionStartEvent(
                    event_version="1.0",
                    event_id="550e8400-e29b-41d4-a716-446655440000",
                    component_name=invalid_name,
                    shell_type="MahavishnuShell",
                    timestamp="2026-02-06T12:34:56.789Z",
                    pid=12345,
                    user=valid_user,
                    hostname="server01",
                    environment=valid_environment
                )
            assert "Invalid component_name" in str(exc_info.value)

    def test_pid_range_validation(self, valid_user, valid_environment):
        """Test PID range validation (1-4194304)."""
        # Test PID too low
        with pytest.raises(ValidationError) as exc_info:
            SessionStartEvent(
                event_version="1.0",
                event_id="550e8400-e29b-41d4-a716-446655440000",
                component_name="mahavishnu",
                shell_type="MahavishnuShell",
                timestamp="2026-02-06T12:34:56.789Z",
                pid=0,
                user=valid_user,
                hostname="server01",
                environment=valid_environment
            )
        assert "greater than or equal to 1" in str(exc_info.value)

        # Test PID too high
        with pytest.raises(ValidationError) as exc_info:
            SessionStartEvent(
                event_version="1.0",
                event_id="550e8400-e29b-41d4-a716-446655440000",
                component_name="mahavishnu",
                shell_type="MahavishnuShell",
                timestamp="2026-02-06T12:34:56.789Z",
                pid=4194305,
                user=valid_user,
                hostname="server01",
                environment=valid_environment
            )
        assert "less than or equal to 4194304" in str(exc_info.value)


class TestSessionEndEvent:
    """Test SessionEndEvent model validation."""

    def test_valid_session_end_event(self):
        """Test creating valid SessionEndEvent."""
        event = SessionEndEvent(
            session_id="sess_abc123",
            timestamp="2026-02-06T13:45:00.000Z"
        )
        assert event.session_id == "sess_abc123"
        assert event.event_type == "session_end"

    def test_timestamp_validation(self):
        """Test that invalid timestamps are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SessionEndEvent(
                session_id="sess_abc123",
                timestamp="not-a-timestamp"
            )
        assert "Invalid ISO 8601 timestamp" in str(exc_info.value)


class TestSessionStartResult:
    """Test SessionStartResult model validation."""

    def test_valid_success_result(self):
        """Test creating valid success result."""
        result = SessionStartResult(
            session_id="sess_abc123",
            status="tracked"
        )
        assert result.session_id == "sess_abc123"
        assert result.status == "tracked"
        assert result.error is None

    def test_valid_error_result(self):
        """Test creating valid error result."""
        result = SessionStartResult(
            session_id=None,
            status="error",
            error="Database connection failed"
        )
        assert result.session_id is None
        assert result.status == "error"
        assert result.error == "Database connection failed"

    def test_status_validation(self):
        """Test that invalid status is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SessionStartResult(
                session_id="sess_abc123",
                status="invalid_status"
            )
        assert "Invalid status" in str(exc_info.value)

    def test_tracked_status_requires_session_id(self):
        """Test that 'tracked' status requires session_id."""
        with pytest.raises(ValidationError) as exc_info:
            SessionStartResult(
                session_id=None,
                status="tracked"
            )
        assert "session_id required when status is 'tracked'" in str(exc_info.value)

    def test_tracked_status_cannot_have_error(self):
        """Test that 'tracked' status cannot have error."""
        with pytest.raises(ValidationError) as exc_info:
            SessionStartResult(
                session_id="sess_abc123",
                status="tracked",
                error="Some error"
            )
        assert "error must be None when status is 'tracked'" in str(exc_info.value)

    def test_error_status_requires_error_message(self):
        """Test that 'error' status requires error message."""
        with pytest.raises(ValidationError) as exc_info:
            SessionStartResult(
                session_id=None,
                status="error"
            )
        assert "error message required when status is 'error'" in str(exc_info.value)

    def test_error_status_cannot_have_session_id(self):
        """Test that 'error' status cannot have session_id."""
        with pytest.raises(ValidationError) as exc_info:
            SessionStartResult(
                session_id="sess_abc123",
                status="error",
                error="Some error"
            )
        assert "session_id must be None when status is 'error'" in str(exc_info.value)


class TestSessionEndResult:
    """Test SessionEndResult model validation."""

    def test_valid_success_result(self):
        """Test creating valid success result."""
        result = SessionEndResult(
            session_id="sess_abc123",
            status="ended"
        )
        assert result.session_id == "sess_abc123"
        assert result.status == "ended"
        assert result.error is None

    def test_valid_not_found_result(self):
        """Test creating valid not_found result."""
        result = SessionEndResult(
            session_id="sess_abc123",
            status="not_found"
        )
        assert result.session_id == "sess_abc123"
        assert result.status == "not_found"

    def test_valid_error_result(self):
        """Test creating valid error result."""
        result = SessionEndResult(
            session_id="sess_abc123",
            status="error",
            error="Database update failed"
        )
        assert result.session_id == "sess_abc123"
        assert result.status == "error"
        assert result.error == "Database update failed"

    def test_status_validation(self):
        """Test that invalid status is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SessionEndResult(
                session_id="sess_abc123",
                status="invalid_status"
            )
        assert "Invalid status" in str(exc_info.value)

    def test_error_status_requires_error_message(self):
        """Test that 'error' status requires error message."""
        with pytest.raises(ValidationError) as exc_info:
            SessionEndResult(
                session_id="sess_abc123",
                status="error"
            )
        assert "error message required when status is 'error'" in str(exc_info.value)

    def test_success_status_cannot_have_error(self):
        """Test that success statuses cannot have error."""
        for status in ["ended", "not_found"]:
            with pytest.raises(ValidationError) as exc_info:
                SessionEndResult(
                    session_id="sess_abc123",
                    status=status,
                    error="Some error"
                )
            assert "error must be None when status is 'ended' or 'not_found'" in str(exc_info.value)


class TestErrorResponse:
    """Test ErrorResponse model validation."""

    def test_valid_error_response(self):
        """Test creating valid ErrorResponse."""
        error = ErrorResponse(
            error="Invalid session ID",
            detail="Session 'sess_invalid' not found in database"
        )
        assert error.error == "Invalid session ID"
        assert error.detail == "Session 'sess_invalid' not found in database"
        assert error.error_code is None

    def test_with_error_code(self):
        """Test ErrorResponse with error code."""
        error = ErrorResponse(
            error="Invalid session ID",
            detail="Session 'sess_invalid' not found in database",
            error_code="SESSION_NOT_FOUND"
        )
        assert error.error_code == "SESSION_NOT_FOUND"


class TestJsonSchema:
    """Test JSON Schema generation."""

    def test_session_start_event_schema(self):
        """Test SessionStartEvent JSON Schema generation."""
        schema = get_session_start_event_schema()
        assert schema["title"] == "SessionStartEvent"
        assert "properties" in schema
        assert "event_version" in schema["properties"]
        assert "event_id" in schema["properties"]
        assert "component_name" in schema["properties"]

    def test_session_end_event_schema(self):
        """Test SessionEndEvent JSON Schema generation."""
        schema = get_session_end_event_schema()
        assert schema["title"] == "SessionEndEvent"
        assert "properties" in schema
        assert "session_id" in schema["properties"]
        assert "timestamp" in schema["properties"]

    def test_session_start_result_schema(self):
        """Test SessionStartResult JSON Schema generation."""
        schema = get_session_start_result_schema()
        assert schema["title"] == "SessionStartResult"
        assert "properties" in schema
        assert "session_id" in schema["properties"]
        assert "status" in schema["properties"]

    def test_session_end_result_schema(self):
        """Test SessionEndResult JSON Schema generation."""
        schema = get_session_end_result_schema()
        assert schema["title"] == "SessionEndResult"
        assert "properties" in schema
        assert "session_id" in schema["properties"]
        assert "status" in schema["properties"]
