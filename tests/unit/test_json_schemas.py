"""Tests for JSON Schema export and validation.

This module tests JSON Schema export, validation, and schema registry
functionality for all event models.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from session_buddy.mcp.event_models import (
    SessionStartEvent,
    SessionEndEvent,
    SessionStartResult,
    SessionEndResult,
    ErrorResponse,
    UserInfo,
    EnvironmentInfo,
)
from session_buddy.mcp.schemas import (
    get_all_schemas,
    get_schema,
    get_schema_version,
    validate_event_json,
    list_event_models,
    export_schemas_to_file,
    check_schema_compatibility,
    validate_event_version,
    get_schema_changelog,
)


class TestJsonSchemaMixin:
    """Tests for JsonSchemaMixin class methods."""

    def test_session_start_event_json_schema(self):
        """Test SessionStartEvent.json_schema() returns valid schema."""
        schema = SessionStartEvent.json_schema()

        # Check schema metadata
        assert "$schema" in schema
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "event_version" in schema
        assert schema["event_version"] == "1.0"
        assert schema["title"] == "SessionStartEvent"

        # Check schema structure
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_session_end_event_json_schema(self):
        """Test SessionEndEvent.json_schema() returns valid schema."""
        schema = SessionEndEvent.json_schema()

        assert "$schema" in schema
        assert schema["event_version"] == "1.0"
        assert schema["type"] == "object"

    def test_user_info_json_schema(self):
        """Test UserInfo.json_schema() returns valid schema."""
        schema = UserInfo.json_schema()

        assert "$schema" in schema
        assert schema["event_version"] == "1.0"
        assert "username" in schema["properties"]
        assert "home" in schema["properties"]

    def test_environment_info_json_schema(self):
        """Test EnvironmentInfo.json_schema() returns valid schema."""
        schema = EnvironmentInfo.json_schema()

        assert "$schema" in schema
        assert schema["event_version"] == "1.0"
        assert "python_version" in schema["properties"]
        assert "platform" in schema["properties"]
        assert "cwd" in schema["properties"]

    def test_result_models_json_schema(self):
        """Test result models export JSON schemas."""
        # SessionStartResult
        schema = SessionStartResult.json_schema()
        assert "$schema" in schema
        assert schema["event_version"] == "1.0"

        # SessionEndResult
        schema = SessionEndResult.json_schema()
        assert "$schema" in schema
        assert schema["event_version"] == "1.0"

        # ErrorResponse
        schema = ErrorResponse.json_schema()
        assert "$schema" in schema
        assert schema["event_version"] == "1.0"


class TestJsonValidation:
    """Tests for JSON validation functionality."""

    def test_validate_json_string(self):
        """Test validate_json() with JSON string."""
        json_str = """
        {
            "event_version": "1.0",
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "component_name": "mahavishnu",
            "shell_type": "MahavishnuShell",
            "timestamp": "2026-02-06T12:34:56.789Z",
            "pid": 12345,
            "user": {
                "username": "john",
                "home": "/home/john"
            },
            "hostname": "server01",
            "environment": {
                "python_version": "3.13.0",
                "platform": "Linux-6.5.0-x86_64",
                "cwd": "/home/john/projects"
            }
        }
        """

        event = SessionStartEvent.validate_json(json_str)
        assert isinstance(event, SessionStartEvent)
        assert event.component_name == "mahavishnu"
        assert event.event_version == "1.0"

    def test_validate_json_dict(self):
        """Test validate_json() with dictionary."""
        json_dict = {
            "session_id": "sess_abc123",
            "timestamp": "2026-02-06T13:45:67.890Z",
            "metadata": {"exit_reason": "user_exit"}
        }

        event = SessionEndEvent.validate_json(json_dict)
        assert isinstance(event, SessionEndEvent)
        assert event.session_id == "sess_abc123"

    def test_validate_json_invalid_data(self):
        """Test validate_json() raises ValidationError for invalid data."""
        invalid_json = {
            "event_version": "2.0",  # Invalid version
            "component_name": "mahavishnu",
        }

        with pytest.raises(ValidationError):
            SessionStartEvent.validate_json(invalid_json)

    def test_validate_json_safe_success(self):
        """Test validate_json_safe() returns event on success."""
        json_dict = {
            "session_id": "sess_abc123",
            "timestamp": "2026-02-06T13:45:67.890Z"
        }

        event, error = SessionEndEvent.validate_json_safe(json_dict)
        assert error is None
        assert isinstance(event, SessionEndEvent)

    def test_validate_json_safe_failure(self):
        """Test validate_json_safe() returns error on failure."""
        invalid_json = {"event_version": "2.0"}

        event, error = SessionStartEvent.validate_json_safe(invalid_json)
        assert event is None
        assert isinstance(error, ValidationError)

    def test_validate_user_info(self):
        """Test UserInfo validation."""
        json_dict = {
            "username": "john",
            "home": "/home/john"
        }

        user = UserInfo.validate_json(json_dict)
        assert user.username == "john"
        assert user.home == "/home/john"

    def test_validate_environment_info(self):
        """Test EnvironmentInfo validation."""
        json_dict = {
            "python_version": "3.13.0",
            "platform": "Linux-6.5.0-x86_64",
            "cwd": "/home/john/projects"
        }

        env = EnvironmentInfo.validate_json(json_dict)
        assert env.python_version == "3.13.0"
        assert env.cwd == "/home/john/projects"


class TestSchemaRegistry:
    """Tests for SchemaRegistry functionality."""

    def test_get_all_schemas(self):
        """Test get_all_schemas() returns all model schemas."""
        schemas = get_all_schemas()

        assert isinstance(schemas, dict)
        assert "SessionStartEvent" in schemas
        assert "SessionEndEvent" in schemas
        assert "UserInfo" in schemas
        assert "EnvironmentInfo" in schemas
        assert "SessionStartResult" in schemas
        assert "SessionEndResult" in schemas
        assert "ErrorResponse" in schemas

        # Check each schema has metadata
        for name, schema in schemas.items():
            assert "$schema" in schema
            assert "event_version" in schema
            assert schema["event_version"] == "1.0"

    def test_get_schema_specific_model(self):
        """Test get_schema() returns specific model schema."""
        schema = get_schema("SessionStartEvent")

        assert isinstance(schema, dict)
        assert schema["title"] == "SessionStartEvent"
        assert "$schema" in schema
        assert schema["event_version"] == "1.0"

    def test_get_schema_unknown_model(self):
        """Test get_schema() raises ValueError for unknown model."""
        with pytest.raises(ValueError, match="Unknown model"):
            get_schema("UnknownModel")

    def test_get_schema_version(self):
        """Test get_schema_version() returns current version."""
        version = get_schema_version()
        assert version == "1.0"

    def test_list_event_models(self):
        """Test list_event_models() returns all model names."""
        models = list_event_models()

        assert isinstance(models, list)
        assert "SessionStartEvent" in models
        assert "SessionEndEvent" in models
        assert "UserInfo" in models
        assert "EnvironmentInfo" in models

    def test_validate_event_json_via_registry(self):
        """Test validate_event_json() via schema registry."""
        json_dict = {
            "event_version": "1.0",
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "component_name": "mahavishnu",
            "shell_type": "MahavishnuShell",
            "timestamp": "2026-02-06T12:34:56.789Z",
            "pid": 12345,
            "user": {"username": "john", "home": "/home/john"},
            "hostname": "server01",
            "environment": {
                "python_version": "3.13.0",
                "platform": "Linux-6.5.0-x86_64",
                "cwd": "/home/john/projects"
            }
        }

        event = validate_event_json("SessionStartEvent", json_dict)
        assert isinstance(event, SessionStartEvent)

    def test_validate_event_json_unknown_model(self):
        """Test validate_event_json() raises ValueError for unknown model."""
        with pytest.raises(ValueError, match="Unknown model"):
            validate_event_json("UnknownModel", {})

    def test_export_schemas_to_json(self, tmp_path: Path):
        """Test export_schemas_to_file() with JSON format."""
        output_file = tmp_path / "schemas.json"

        export_schemas_to_file(output_file, format="json")

        assert output_file.exists()

        # Verify JSON is valid
        with output_file.open("r") as f:
            schemas = json.load(f)

        assert "SessionStartEvent" in schemas
        assert schemas["SessionStartEvent"]["event_version"] == "1.0"

    def test_export_schemas_to_yaml_unavailable(self, tmp_path: Path):
        """Test export_schemas_to_file() raises error without PyYAML."""
        output_file = tmp_path / "schemas.yaml"

        # This should raise ValueError if PyYAML is not installed
        try:
            import yaml  # noqa: F401
            pytest.skip("PyYAML is installed")
        except ImportError:
            with pytest.raises(ValueError, match="PyYAML"):
                export_schemas_to_file(output_file, format="yaml")

    def test_export_schemas_unsupported_format(self, tmp_path: Path):
        """Test export_schemas_to_file() raises error for unsupported format."""
        output_file = tmp_path / "schemas.txt"

        with pytest.raises(ValueError, match="Unsupported format"):
            export_schemas_to_file(output_file, format="txt")


class TestSchemaVersioning:
    """Tests for schema versioning and compatibility."""

    def test_check_schema_compatibility_valid(self):
        """Test check_schema_compatibility() with valid version."""
        compatible = check_schema_compatibility("1.0")
        assert compatible is True

    def test_check_schema_compatibility_invalid(self):
        """Test check_schema_compatibility() with invalid version."""
        compatible = check_schema_compatibility("2.0")
        assert compatible is False

    def test_validate_event_version_valid(self):
        """Test validate_event_version() with valid version."""
        # Should not raise
        validate_event_version("1.0")

    def test_validate_event_version_invalid(self):
        """Test validate_event_version() raises error for invalid version."""
        with pytest.raises(ValueError, match="Unsupported event version"):
            validate_event_version("2.0")

    def test_get_schema_changelog(self):
        """Test get_schema_changelog() returns version history."""
        changelog = get_schema_changelog()

        assert isinstance(changelog, dict)
        assert "1.0" in changelog
        assert "Initial schema version" in changelog["1.0"]


class TestSchemaStructure:
    """Tests for JSON Schema structure and content."""

    def test_session_start_event_required_fields(self):
        """Test SessionStartEvent schema has required fields."""
        schema = SessionStartEvent.json_schema()
        required = schema["required"]

        assert "event_version" in required
        assert "event_id" in required
        assert "component_name" in required
        assert "shell_type" in required
        assert "timestamp" in required
        assert "pid" in required
        assert "user" in required
        assert "hostname" in required
        assert "environment" in required

    def test_session_start_event_field_constraints(self):
        """Test SessionStartEvent schema field constraints."""
        schema = SessionStartEvent.json_schema()
        properties = schema["properties"]

        # Check PID constraints
        pid_props = properties["pid"]
        assert pid_props["type"] == "integer"
        assert pid_props["minimum"] == 1
        assert pid_props["maximum"] == 4194304

        # Check component_name pattern
        component_name_props = properties["component_name"]
        assert "pattern" in component_name_props
        assert component_name_props["pattern"] == "^[a-zA-Z0-9_-]+$"

    def test_user_info_constraints(self):
        """Test UserInfo schema field constraints."""
        schema = UserInfo.json_schema()
        properties = schema["properties"]

        # Check maxLength constraints
        assert properties["username"]["maxLength"] == 100
        assert properties["home"]["maxLength"] == 500

    def test_environment_info_constraints(self):
        """Test EnvironmentInfo schema field constraints."""
        schema = EnvironmentInfo.json_schema()
        properties = schema["properties"]

        # Check cwd maxLength
        assert properties["cwd"]["maxLength"] == 500


class TestSchemaExportFunctions:
    """Tests for schema export functions."""

    def test_get_session_start_event_schema(self):
        """Test get_session_start_event_schema() function."""
        from session_buddy.mcp.event_models import get_session_start_event_schema

        schema = get_session_start_event_schema()
        assert "$schema" in schema
        assert schema["event_version"] == "1.0"

    def test_get_session_end_event_schema(self):
        """Test get_session_end_event_schema() function."""
        from session_buddy.mcp.event_models import get_session_end_event_schema

        schema = get_session_end_event_schema()
        assert "$schema" in schema
        assert schema["event_version"] == "1.0"

    def test_get_session_start_result_schema(self):
        """Test get_session_start_result_schema() function."""
        from session_buddy.mcp.event_models import get_session_start_result_schema

        schema = get_session_start_result_schema()
        assert "$schema" in schema
        assert schema["event_version"] == "1.0"

    def test_get_session_end_result_schema(self):
        """Test get_session_end_result_schema() function."""
        from session_buddy.mcp.event_models import get_session_end_result_schema

        schema = get_session_end_result_schema()
        assert "$schema" in schema
        assert schema["event_version"] == "1.0"
