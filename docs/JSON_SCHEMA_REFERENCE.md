# JSON Schema Reference Guide

This guide provides comprehensive reference documentation for JSON Schema export and validation in the Session-Buddy event models.

## Table of Contents

- [Overview](#overview)
- [Schema Versioning](#schema-versioning)
- [Event Model Schemas](#event-model-schemas)
- [JSON Schema Format](#json-schema-format)
- [Validation Examples](#validation-examples)
- [Schema Evolution](#schema-evolution)
- [API Reference](#api-reference)

## Overview

All event models in Session-Buddy support JSON Schema export and validation:

- **SessionStartEvent**: Emitted when an admin shell starts
- **SessionEndEvent**: Emitted when an admin shell exits
- **SessionStartResult**: Result of session start tracking
- **SessionEndResult**: Result of session end tracking
- **ErrorResponse**: Standardized error responses
- **UserInfo**: User information component
- **EnvironmentInfo**: Environment information component

### Quick Start

```python
from session_buddy.mcp.event_models import SessionStartEvent
from session_buddy.mcp.schemas import get_all_schemas

# Get JSON Schema for a model
schema = SessionStartEvent.json_schema()
print(schema["$schema"])  # https://json-schema.org/draft/2020-12/schema

# Get all schemas
all_schemas = get_all_schemas()

# Validate JSON data
event = SessionStartEvent.validate_json('{"event_version": "1.0", ...}')
```

## Schema Versioning

### Current Version

- **Version**: 1.0
- **Schema Draft**: JSON Schema 2020-12
- **Compatibility**: Exact version matching only

### Version Format

All schemas include version metadata:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "event_version": "1.0",
  "title": "SessionStartEvent"
}
```

### Backward Compatibility Strategy

**Current Policy (v1.0)**: Exact version matching required

**Future Policy (planned for v2.0+)**:

- Additive changes only (new optional fields)
- No breaking changes to existing fields
- Semantic versioning (MAJOR.MINOR.PATCH)
- Minor version updates for additive changes
- Major version updates for breaking changes

## Event Model Schemas

### SessionStartEvent

```json
{
  "type": "object",
  "properties": {
    "event_version": {
      "type": "string",
      "description": "Event format version (currently '1.0')"
    },
    "event_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique event identifier (UUID v4 string)"
    },
    "event_type": {
      "type": "string",
      "const": "session_start",
      "description": "Event type discriminator"
    },
    "component_name": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9_-]+$",
      "description": "Component name (e.g., 'mahavishnu', 'session-buddy')"
    },
    "shell_type": {
      "type": "string",
      "description": "Shell class name (e.g., 'MahavishnuShell')"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp in UTC"
    },
    "pid": {
      "type": "integer",
      "minimum": 1,
      "maximum": 4194304,
      "description": "Process ID (1-4194304)"
    },
    "user": {
      "$ref": "#/$defs/UserInfo"
    },
    "hostname": {
      "type": "string",
      "description": "System hostname"
    },
    "environment": {
      "$ref": "#/$defs/EnvironmentInfo"
    },
    "metadata": {
      "type": "object",
      "additionalProperties": true,
      "default": {},
      "description": "Optional additional metadata"
    }
  },
  "required": [
    "event_version",
    "event_id",
    "component_name",
    "shell_type",
    "timestamp",
    "pid",
    "user",
    "hostname",
    "environment"
  ],
  "$defs": {
    "UserInfo": {
      "type": "object",
      "properties": {
        "username": {
          "type": "string",
          "maxLength": 100,
          "description": "System username (truncated to 100 characters)"
        },
        "home": {
          "type": "string",
          "maxLength": 500,
          "description": "User home directory path (truncated to 500 characters)"
        }
      },
      "required": ["username", "home"]
    },
    "EnvironmentInfo": {
      "type": "object",
      "properties": {
        "python_version": {
          "type": "string",
          "description": "Python interpreter version"
        },
        "platform": {
          "type": "string",
          "description": "Operating system and platform identifier"
        },
        "cwd": {
          "type": "string",
          "maxLength": 500,
          "description": "Current working directory (truncated to 500 characters)"
        }
      },
      "required": ["python_version", "platform", "cwd"]
    }
  }
}
```

### SessionEndEvent

```json
{
  "type": "object",
  "properties": {
    "event_type": {
      "type": "string",
      "const": "session_end",
      "description": "Event type discriminator"
    },
    "session_id": {
      "type": "string",
      "description": "Session ID from SessionStartEvent response"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp in UTC"
    },
    "metadata": {
      "type": "object",
      "additionalProperties": true,
      "default": {},
      "description": "Optional additional metadata"
    }
  },
  "required": ["session_id", "timestamp"]
}
```

### UserInfo

```json
{
  "type": "object",
  "properties": {
    "username": {
      "type": "string",
      "maxLength": 100,
      "description": "System username (truncated to 100 characters)"
    },
    "home": {
      "type": "string",
      "maxLength": 500,
      "description": "User home directory path (truncated to 500 characters)"
    }
  },
  "required": ["username", "home"]
}
```

### EnvironmentInfo

```json
{
  "type": "object",
  "properties": {
    "python_version": {
      "type": "string",
      "description": "Python interpreter version"
    },
    "platform": {
      "type": "string",
      "description": "Operating system and platform identifier"
    },
    "cwd": {
      "type": "string",
      "maxLength": 500,
      "description": "Current working directory (truncated to 500 characters)"
    }
  },
  "required": ["python_version", "platform", "cwd"]
}
```

## JSON Schema Format

### Schema Metadata

All exported schemas include the following metadata:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "event_version": "1.0",
  "title": "ModelName"
}
```

### Field Descriptions

- **event_version**: Schema version identifier
- **title**: Model class name
- **$schema**: JSON Schema meta-schema reference

### Validation Rules

1. **Type Validation**: All fields have explicit type constraints
1. **Format Validation**: UUID, ISO 8601 timestamps
1. **Pattern Validation**: Component names must match `^[a-zA-Z0-9_-]+$`
1. **Range Validation**: PID must be 1-4194304
1. **Length Validation**: String fields have maxLength constraints

## Validation Examples

### Validate JSON String

```python
from session_buddy.mcp.event_models import SessionStartEvent

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
    "cwd": "/home/john/projects/mahavishnu"
  }
}
"""

event = SessionStartEvent.validate_json(json_str)
print(event.event_id)
```

### Validate JSON Dictionary

```python
from session_buddy.mcp.event_models import SessionEndEvent

json_dict = {
    "session_id": "sess_abc123",
    "timestamp": "2026-02-06T13:45:67.890Z",
    "metadata": {"exit_reason": "user_exit"}
}

event = SessionEndEvent.validate_json(json_dict)
print(event.session_id)
```

### Safe Validation with Error Handling

```python
from session_buddy.mcp.event_models import SessionStartEvent

invalid_json = '{"event_version": "2.0", ...}'  # Wrong version

event, error = SessionStartEvent.validate_json_safe(invalid_json)
if error:
    print(f"Validation failed: {error}")
else:
    print(f"Valid event: {event.event_id}")
```

### Using Schema Registry

```python
from session_buddy.mcp.schemas import (
    get_all_schemas,
    get_schema,
    validate_event_json,
)

# Get all schemas
schemas = get_all_schemas()

# Get specific schema
schema = get_schema("SessionStartEvent")

# Validate using registry
event = validate_event_json("SessionStartEvent", json_data)
```

### Export Schemas to File

```python
from session_buddy.mcp.schemas import export_schemas_to_file

# Export as JSON
export_schemas_to_file("event_schemas.json")

# Export as YAML (requires pyyaml)
export_schemas_to_file("event_schemas.yaml", format="yaml")
```

## Schema Evolution

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-06 | Initial schema version |

### Evolution Guidelines

**Additive Changes (Minor Version Update)**:

- Add new optional fields
- Add new validation rules that don't break existing valid data
- Extend metadata schemas

**Breaking Changes (Major Version Update)**:

- Remove or rename fields
- Change field types
- Make required fields optional
- Tighten validation constraints

### Migration Strategy

When upgrading to a new schema version:

1. **Update event_version field** in emitted events
1. **Update validation logic** in Session-Buddy
1. **Support multiple versions** during transition period
1. **Provide migration tools** for old data

Example:

```python
def validate_event_with_version(json_data: dict) -> bool:
    """Validate event with version-aware logic."""
    version = json_data.get("event_version", "1.0")

    if version == "1.0":
        return validate_v1_event(json_data)
    elif version == "2.0":
        return validate_v2_event(json_data)
    else:
        raise ValueError(f"Unsupported version: {version}")
```

## API Reference

### Model Methods

#### `json_schema()`

Get JSON Schema for the model.

```python
@classmethod
def json_schema(cls) -> dict[str, Any]:
    """Get JSON Schema for this model."""
    schema = cls.model_json_schema()
    schema["$schema"] = JSON_SCHEMA_DRAFT
    schema["event_version"] = SCHEMA_VERSION
    return schema
```

**Returns**: JSON Schema dictionary

#### `validate_json()`

Validate JSON data and return model instance.

```python
@classmethod
def validate_json(cls, json_data: str | dict[str, Any]) -> JsonSchemaMixin:
    """Validate JSON data and return model instance."""
```

**Parameters**:

- `json_data`: JSON string or dictionary

**Returns**: Validated model instance

**Raises**: `ValidationError` if data is invalid

#### `validate_json_safe()`

Validate JSON data with error handling.

```python
@classmethod
def validate_json_safe(
    cls,
    json_data: str | dict[str, Any],
) -> tuple[JsonSchemaMixin | None, ValidationError | None]:
    """Validate JSON data with error handling."""
```

**Parameters**:

- `json_data`: JSON string or dictionary

**Returns**: Tuple of (model_instance, error)

### Schema Registry Functions

#### `get_all_schemas()`

Get all event model schemas.

```python
def get_all_schemas() -> dict[str, dict[str, Any]]:
    """Get JSON schemas for all event models."""
```

**Returns**: Dictionary mapping model names to schemas

#### `get_schema(model_name)`

Get schema for a specific model.

```python
def get_schema(model_name: str) -> dict[str, Any]:
    """Get JSON Schema for a specific model."""
```

**Parameters**:

- `model_name`: Name of the model

**Returns**: JSON Schema dictionary

**Raises**: `ValueError` if model not found

#### `validate_event_json()`

Validate JSON against a model schema.

```python
def validate_event_json(
    model_name: str,
    json_data: str | dict[str, Any],
) -> Any:
    """Validate JSON data against an event model schema."""
```

**Parameters**:

- `model_name`: Name of the model
- `json_data`: JSON string or dictionary

**Returns**: Validated model instance

#### `export_schemas_to_file()`

Export all schemas to a file.

```python
def export_schemas_to_file(
    output_path: str | Path,
    format: Literal["json", "yaml"] = "json",
) -> None:
    """Export all schemas to a file."""
```

**Parameters**:

- `output_path`: Path to output file
- `format`: Output format ("json" or "yaml")

**Raises**: `ValueError` if format not supported

## Best Practices

### 1. Always Validate Input

```python
# Good
event = SessionStartEvent.validate_json(json_data)

# Bad - no validation
event = SessionStartEvent(**json_data)
```

### 2. Use Safe Validation for User Input

```python
event, error = SessionStartEvent.validate_json_safe(user_input)
if error:
    logger.error(f"Invalid event: {error}")
    return error_response()
```

### 3. Check Schema Version

```python
from session_buddy.mcp.schemas import validate_event_version

try:
    validate_event_version(event.event_version)
except ValueError as e:
    logger.error(f"Unsupported version: {e}")
    return error_response()
```

### 4. Export Schemas for Documentation

```python
# Generate schema documentation
from session_buddy.mcp.schemas import export_schemas_to_file

export_schemas_to_file("docs/event_schemas.json")
```

### 5. Handle Validation Errors Gracefully

```python
from pydantic import ValidationError

try:
    event = SessionStartEvent.validate_json(json_data)
except ValidationError as e:
    logger.error(f"Validation error: {e.json()}")
    return {
        "status": "error",
        "message": "Invalid event data",
        "details": e.errors()
    }
```

## Testing

### Test JSON Schema Export

```python
def test_json_schema_export():
    """Test that all models can export JSON schemas."""
    from session_buddy.mcp.event_models import (
        SessionStartEvent,
        SessionEndEvent,
        UserInfo,
    )

    schemas = {
        "SessionStartEvent": SessionStartEvent.json_schema(),
        "SessionEndEvent": SessionEndEvent.json_schema(),
        "UserInfo": UserInfo.json_schema(),
    }

    for name, schema in schemas.items():
        assert "$schema" in schema
        assert "event_version" in schema
        assert schema["event_version"] == "1.0"
```

### Test Validation

```python
def test_validate_json():
    """Test JSON validation."""
    from session_buddy.mcp.event_models import SessionStartEvent

    valid_json = {
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

    event = SessionStartEvent.validate_json(valid_json)
    assert event.event_version == "1.0"
```

### Test Version Compatibility

```python
def test_version_compatibility():
    """Test schema version validation."""
    from session_buddy.mcp.schemas import validate_event_version

    # Valid version
    validate_event_version("1.0")  # OK

    # Invalid version
    with pytest.raises(ValueError):
        validate_event_version("2.0")
```

## Troubleshooting

### Common Errors

**ValidationError: Unsupported event version**

```python
# Solution: Check event version
event_version = event_data.get("event_version")
if event_version != "1.0":
    raise ValueError(f"Only version 1.0 supported, got {event_version}")
```

**ValidationError: Invalid UUID v4 format**

```python
# Solution: Validate UUID format
import uuid
try:
    uuid.UUID(event_data["event_id"], version=4)
except ValueError:
    raise ValueError("event_id must be a valid UUID v4")
```

**ValidationError: Invalid ISO 8601 timestamp**

```python
# Solution: Ensure timestamp includes time component
timestamp = event_data["timestamp"]
if "T" not in timestamp:
    raise ValueError("Timestamp must include time component (ISO 8601)")
```

## Additional Resources

- [JSON Schema Specification](https://json-schema.org/specification)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Session-Buddy MCP Tools](../MCP_TOOLS_SPECIFICATION.md)
- [Event Models Source](../session_buddy/mcp/event_models.py)
