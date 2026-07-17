---
status: complete
role: canonical
date: 2026-07-16
last_reviewed: 2026-07-16
superseded_by: null
blocks_on: []
topic: mcp-design
---

# mcp_common API Reference

Complete Python API reference for the `mcp_common` package - the ACB-native foundation library for MCP servers.

## Installation

```bash
pip install mcp-common  # or via uv: uv add mcp-common
```

## Package Overview

`mcp_common` provides production-ready patterns for building MCP servers:

- **HTTP Client Adapter**: High-performance async HTTP client with connection pooling
- **Health Checks**: Production monitoring with ComponentHealth pattern
- **Configuration Management**: Type-safe settings with validation
- **UI Components**: Rich terminal UI panels for server information
- **Exception Hierarchy**: Structured error handling for MCP servers

**Version**: 2.0.0 (ACB-native)

______________________________________________________________________

## HTTP Client Adapter

### HTTPClientAdapter

High-performance async HTTP client built on httpx with ACB adapter lifecycle management.

**Import:**

```text
from mcp_common.adapters.http import HTTPClientAdapter
from acb.depends import depends
```

**Performance:**

- 11x faster than aiohttp for repeated requests
- Connection pool reuse reduces latency
- Automatic retry with exponential backoff

#### Getting the Adapter

```text
# Via ACB dependency injection (recommended)
from acb.depends import depends
from mcp_common.adapters.http.client import HTTPClientAdapter

http_adapter = depends.get_sync(HTTPClientAdapter)

# Direct instantiation (not recommended - breaks singleton pattern)
http_adapter = HTTPClientAdapter()
```

#### Making Requests

```text
# Using context manager (recommended)
async with http_adapter as client:
    response = await client.get("https://api.example.com/data")
    data = response.json()

# Direct client creation
client = await http_adapter._create_client()
response = await client.get("https://api.example.com/data")
await client.aclose()
```

#### Methods

##### `_create_client() -> httpx.AsyncClient`

Creates configured async HTTP client.

**Returns**: Configured `httpx.AsyncClient` instance

**Example:**

```text
client = await http_adapter._create_client()
try:
    response = await client.get("https://api.example.com/endpoint")
finally:
    await client.aclose()
```

##### `async __aenter__() -> httpx.AsyncClient`

Context manager entry - creates and returns HTTP client.

**Returns**: Configured `httpx.AsyncClient` instance

##### `async __aexit__(...) -> None`

Context manager exit - closes HTTP client connections.

##### `_cleanup_resources() -> None`

Cleanup method called during graceful shutdown to release connection pools.

**Example:**

```python
async def cleanup():
    http_adapter = depends.get_sync(HTTPClientAdapter)
    if http_adapter and hasattr(http_adapter, "_cleanup_resources"):
        await http_adapter._cleanup_resources()
```

______________________________________________________________________

### HTTPClientSettings

Configuration settings for HTTPClientAdapter.

**Import:**

```python
from mcp_common.adapters.http import HTTPClientSettings
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_connections` | `int` | `100` | Maximum concurrent connections |
| `max_keepalive_connections` | `int` | `20` | Maximum keep-alive connections |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `retry_attempts` | `int` | `3` | Number of retry attempts |
| `retry_backoff` | `float` | `0.1` | Exponential backoff base (seconds) |
| `follow_redirects` | `bool` | `True` | Follow HTTP redirects |
| `verify_ssl` | `bool` | `True` | Verify SSL certificates |

#### Example Configuration

```python
from mcp_common.adapters.http import HTTPClientSettings, HTTPClientAdapter
from acb.depends import depends

# Create custom settings
settings = HTTPClientSettings(
    max_connections=200,
    max_keepalive_connections=50,
    timeout=60.0,
    retry_attempts=5,
    retry_backoff=0.5,
)

# Register with DI container
http_adapter = HTTPClientAdapter(settings=settings)
depends.set(HTTPClientAdapter, http_adapter)
```

______________________________________________________________________

## Health Checks

Production-ready health check system for monitoring MCP server components.

### HealthStatus

Enumeration of component health states.

**Import:**

```python
from mcp_common.health import HealthStatus
```

#### Values

| Status | Description | Use Case |
|--------|-------------|----------|
| `HEALTHY` | Component fully operational | Normal operation, all systems green |
| `DEGRADED` | Component functional but issues detected | Performance issues, warnings, non-critical errors |
| `UNHEALTHY` | Component not operational | Critical failures, service unavailable |

#### Example

```python
from mcp_common.health import HealthStatus, ComponentHealth


def check_service() -> ComponentHealth:
    try:
        # Check service health
        if service.is_ready():
            return ComponentHealth(
                name="my_service",
                status=HealthStatus.HEALTHY,
                message="Service operational",
            )
    except Exception as e:
        return ComponentHealth(
            name="my_service",
            status=HealthStatus.UNHEALTHY,
            message=f"Service failed: {e}",
        )
```

______________________________________________________________________

### ComponentHealth

Health check result for a single component.

**Import:**

```python
from mcp_common.health import ComponentHealth
from dataclasses import dataclass
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Component identifier (e.g., "database", "http_client") |
| `status` | `HealthStatus` | Current health status (HEALTHY/DEGRADED/UNHEALTHY) |
| `message` | `str` | Human-readable status description |
| `latency_ms` | `float \| None` | Optional latency measurement in milliseconds |
| `metadata` | `dict[str, Any]` | Additional context (counts, versions, errors) |

#### Constructor

```text
ComponentHealth(
    name: str,
    status: HealthStatus,
    message: str,
    latency_ms: float | None = None,
    metadata: dict[str, Any] = field(default_factory=dict),
)
```

#### Example: Database Health Check

```python
import time
from mcp_common.health import ComponentHealth, HealthStatus


async def check_database_health() -> ComponentHealth:
    """Check database connection health."""
    start_time = time.perf_counter()

    try:
        # Perform database health check
        result = await database.ping()
        latency_ms = (time.perf_counter() - start_time) * 1000

        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database operational",
            latency_ms=latency_ms,
            metadata={
                "connections": result["active_connections"],
                "version": result["version"],
                "uptime_hours": result["uptime"] / 3600,
            },
        )

    except DatabaseError as e:
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database error: {e}",
            metadata={"error": str(e), "error_type": type(e).__name__},
        )
```

#### Example: HTTP Client Health Check

```text
from mcp_common.health import ComponentHealth, HealthStatus


async def check_http_health(test_url: str = None) -> ComponentHealth:
    """Check HTTP client health with optional connectivity test."""
    start_time = time.perf_counter()

    try:
        from acb.depends import depends
        from mcp_common.adapters.http.client import HTTPClientAdapter

        http_client = depends.get_sync(HTTPClientAdapter)

        if test_url:
            # Perform connectivity test
            async with http_client as client:
                response = await client.get(test_url)
                latency_ms = (time.perf_counter() - start_time) * 1000

                if response.status_code >= 400:
                    return ComponentHealth(
                        name="http_client",
                        status=HealthStatus.DEGRADED,
                        message=f"HTTP {response.status_code}",
                        latency_ms=latency_ms,
                        metadata={
                            "status_code": response.status_code,
                            "test_url": test_url,
                        },
                    )

                return ComponentHealth(
                    name="http_client",
                    status=HealthStatus.HEALTHY,
                    message="HTTP client operational",
                    latency_ms=latency_ms,
                    metadata={"test_url": test_url},
                )

        return ComponentHealth(
            name="http_client",
            status=HealthStatus.HEALTHY,
            message="HTTP client initialized",
        )

    except Exception as e:
        return ComponentHealth(
            name="http_client",
            status=HealthStatus.UNHEALTHY,
            message=f"Failed to initialize: {e}",
            metadata={"error": str(e)},
        )
```

______________________________________________________________________

### HealthCheckResponse

Aggregated health check response for multiple components.

**Import:**

```python
from mcp_common.health import HealthCheckResponse
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `status` | `HealthStatus` | Overall system status (worst component status) |
| `components` | `list[ComponentHealth]` | Individual component health results |
| `timestamp` | `datetime` | When health check was performed |

#### Constructor

```text
HealthCheckResponse(
    status: HealthStatus,
    components: list[ComponentHealth],
    timestamp: datetime = field(default_factory=datetime.now),
)
```

#### Example: Aggregated Health Check

```python
from datetime import datetime
from mcp_common.health import HealthCheckResponse, HealthStatus, ComponentHealth


async def system_health_check() -> HealthCheckResponse:
    """Perform system-wide health check."""

    # Run all component health checks concurrently
    component_checks = await asyncio.gather(
        check_database_health(),
        check_http_client_health(),
        check_file_system_health(),
        check_dependencies_health(),
        return_exceptions=True,
    )

    # Convert exceptions to UNHEALTHY ComponentHealth
    components = []
    for check in component_checks:
        if isinstance(check, Exception):
            components.append(
                ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check crashed: {check}",
                    metadata={"error": str(check)},
                )
            )
        else:
            components.append(check)

    # Determine overall status (worst component status)
    statuses = [c.status for c in components]
    if HealthStatus.UNHEALTHY in statuses:
        overall_status = HealthStatus.UNHEALTHY
    elif HealthStatus.DEGRADED in statuses:
        overall_status = HealthStatus.DEGRADED
    else:
        overall_status = HealthStatus.HEALTHY

    return HealthCheckResponse(
        status=overall_status, components=components, timestamp=datetime.now()
    )
```

______________________________________________________________________

### check_http_client_health()

Check HTTP client adapter health with optional connectivity test.

**Import:**

```python
from mcp_common.http_health import check_http_client_health
```

#### Signature

```text
async def check_http_client_health(
    http_client: HTTPClientAdapter | None = None,
    test_url: str | None = None,
    timeout_ms: float = 5000,
) -> ComponentHealth:
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `http_client` | `HTTPClientAdapter \| None` | `None` | HTTP client to check (uses DI if None) |
| `test_url` | `str \| None` | `None` | Optional URL for connectivity test |
| `timeout_ms` | `float` | `5000` | Latency threshold for DEGRADED status |

#### Returns

`ComponentHealth` with:

- **HEALTHY**: Client initialized and responsive
- **DEGRADED**: High latency or HTTP errors
- **UNHEALTHY**: Initialization failed or connectivity test failed

#### Examples

##### Basic Initialization Check

```python
from mcp_common.http_health import check_http_client_health

result = await check_http_client_health()
print(f"HTTP Client: {result.status.value}")  # HEALTHY
```

##### With Connectivity Test

```python
result = await check_http_client_health(
    test_url="https://api.example.com/health", timeout_ms=3000
)

if result.status == HealthStatus.HEALTHY:
    print(f"✅ HTTP client operational ({result.latency_ms:.0f}ms)")
elif result.status == HealthStatus.DEGRADED:
    print(f"⚠️ HTTP client degraded: {result.message}")
else:
    print(f"❌ HTTP client unhealthy: {result.message}")
```

##### With Custom HTTP Client

```python
from mcp_common.adapters.http import HTTPClientAdapter, HTTPClientSettings

# Create custom HTTP client
settings = HTTPClientSettings(max_connections=50, timeout=15.0)
http_client = HTTPClientAdapter(settings=settings)

# Check health
result = await check_http_client_health(http_client=http_client)
```

______________________________________________________________________

### check_http_connectivity()

Perform HTTP connectivity test to verify network access.

**Import:**

```python
from mcp_common.http_health import check_http_connectivity
```

#### Signature

```text
async def check_http_connectivity(
    test_url: str = "https://www.google.com",
    timeout_ms: float = 5000,
    http_client: HTTPClientAdapter | None = None,
) -> ComponentHealth:
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `test_url` | `str` | `"https://www.google.com"` | URL to test connectivity |
| `timeout_ms` | `float` | `5000` | Latency threshold for DEGRADED status |
| `http_client` | `HTTPClientAdapter \| None` | `None` | HTTP client to use (uses DI if None) |

#### Returns

`ComponentHealth` with:

- **HEALTHY**: Successful HTTP connection within threshold
- **DEGRADED**: Connection succeeded but high latency
- **UNHEALTHY**: Connection failed or timeout

#### Examples

##### Basic Connectivity Test

```python
from mcp_common.http_health import check_http_connectivity

result = await check_http_connectivity()

if result.status == HealthStatus.HEALTHY:
    print(f"✅ Internet connectivity operational ({result.latency_ms:.0f}ms)")
```

##### Custom Test URL

```python
# Test connectivity to specific service
result = await check_http_connectivity(
    test_url="https://api.myservice.com/health", timeout_ms=2000
)

print(f"Service connectivity: {result.status.value}")
print(f"Latency: {result.latency_ms:.2f}ms")
print(f"Metadata: {result.metadata}")
```

##### Combined Health Check

```python
async def full_network_health() -> list[ComponentHealth]:
    """Check both HTTP client and connectivity."""
    return await asyncio.gather(
        check_http_client_health(),
        check_http_connectivity(test_url="https://api.example.com"),
    )


checks = await full_network_health()
for check in checks:
    print(f"{check.name}: {check.status.value} - {check.message}")
```

______________________________________________________________________

## Configuration Management

Type-safe configuration with YAML and environment variable support.

### MCPBaseSettings

Base settings class for MCP servers with ACB integration.

**Import:**

```python
from mcp_common.config import MCPBaseSettings
```

#### Features

- **YAML Configuration**: Load from `config.yaml` or `config.yml`
- **Environment Variables**: Override YAML with env vars
- **Type Validation**: Automatic Pydantic validation
- **ACB Integration**: Uses ACB Settings resolution

#### Example

```python
from mcp_common.config import MCPBaseSettings
from pydantic import Field


class MyServerSettings(MCPBaseSettings):
    """Custom MCP server settings."""

    # Server configuration
    server_name: str = Field(default="my-mcp-server", description="Server name")
    server_port: int = Field(default=8000, ge=1, le=65535)

    # API configuration
    api_key: str = Field(..., description="Required API key")
    api_endpoint: str = Field(default="https://api.example.com")

    # Feature flags
    enable_caching: bool = Field(default=True)
    cache_ttl_seconds: int = Field(default=300, ge=0)

    class Config:
        env_prefix = "MY_SERVER_"  # Environment variable prefix


# Usage
settings = MyServerSettings()
print(f"Server: {settings.server_name}")
print(f"Port: {settings.server_port}")
print(f"API Key: {'*' * 8}")  # Never log API keys!
```

#### Configuration Priority

1. **Environment Variables** (highest priority): `MY_SERVER_API_KEY=xyz`
1. **YAML Files**: `config.yaml` or `config.yml`
1. **Default Values** (lowest priority): Field defaults

#### Example YAML Configuration

```yaml
# config.yaml
server_name: my-production-server
server_port: 443
api_endpoint: https://api.production.com
enable_caching: true
cache_ttl_seconds: 600
```

______________________________________________________________________

### ValidationMixin

Mixin providing validation utilities for settings classes.

**Import:**

```python
from mcp_common.config import ValidationMixin
```

#### Methods

##### `validate_api_key(api_key: str, name: str = "API_KEY") -> str`

Validate API key format and length.

**Parameters:**

- `api_key` (`str`): API key to validate
- `name` (`str`): Key name for error messages (default: "API_KEY")

**Returns**: Validated API key (stripped)

**Raises:**

- `APIKeyMissingError`: If key is None or empty
- `APIKeyFormatError`: If key contains invalid characters
- `APIKeyLengthError`: If key length is invalid

**Example:**

```python
from mcp_common.config import MCPBaseSettings, ValidationMixin
from pydantic import Field, field_validator


class MyServerSettings(MCPBaseSettings, ValidationMixin):
    """Server settings with API key validation."""

    api_key: str = Field(..., description="API key for authentication")

    @field_validator("api_key")
    @classmethod
    def validate_api_key_field(cls, v: str) -> str:
        """Validate API key format and length."""
        return cls.validate_api_key(v, name="API_KEY")


# Usage
try:
    settings = MyServerSettings(api_key="sk-1234567890abcdef")
except APIKeyFormatError as e:
    print(f"Invalid API key: {e}")
```

______________________________________________________________________

## UI Components

Rich terminal UI components for MCP servers.

### ServerPanels

Rich panels for displaying server information with styled output.

**Import:**

```python
from mcp_common.ui import ServerPanels
```

#### Methods

##### `welcome(server_name: str, features: list[str]) -> None`

Display welcome panel with server features.

**Parameters:**

- `server_name` (`str`): Name of the MCP server
- `features` (`list[str]`): List of server features/capabilities

**Example:**

```text
from mcp_common.ui import ServerPanels

ServerPanels.welcome(
    server_name="My MCP Server",
    features=[
        "📊 Health Monitoring",
        "🔄 Session Management",
        "🔍 Semantic Search",
        "🔐 Secure Authentication",
    ],
)
```

**Output:**

```
╭─────────── My MCP Server ───────────╮
│                                     │
│ Features:                           │
│  📊 Health Monitoring              │
│  🔄 Session Management             │
│  🔍 Semantic Search                │
│  🔐 Secure Authentication          │
│                                     │
╰─────────────────────────────────────╯
```

##### `status(components: list[ComponentHealth]) -> None`

Display health status panel for multiple components.

**Parameters:**

- `components` (`list[ComponentHealth]`): List of component health checks

**Example:**

```text
from mcp_common.ui import ServerPanels
from mcp_common.health import ComponentHealth, HealthStatus

components = [
    ComponentHealth(
        "database", HealthStatus.HEALTHY, "DuckDB operational", latency_ms=5.2
    ),
    ComponentHealth(
        "http_client", HealthStatus.HEALTHY, "HTTP client ready", latency_ms=12.1
    ),
    ComponentHealth(
        "cache", HealthStatus.DEGRADED, "High memory usage", metadata={"usage": "85%"}
    ),
]

ServerPanels.status(components)
```

**Output:**

```
╭─────────── System Health ───────────╮
│                                     │
│ ✅ database: DuckDB operational    │
│    Latency: 5.2ms                  │
│                                     │
│ ✅ http_client: HTTP client ready  │
│    Latency: 12.1ms                 │
│                                     │
│ ⚠️  cache: High memory usage       │
│    usage: 85%                      │
│                                     │
╰─────────────────────────────────────╯
```

______________________________________________________________________

## Exception Hierarchy

Structured exception hierarchy for MCP server error handling.

### Base Exception

#### MCPServerError

Base exception for all MCP server errors.

**Import:**

```python
from mcp_common.exceptions import MCPServerError
```

**Usage:**

```python
try:
    # MCP server operation
    pass
except MCPServerError as e:
    print(f"MCP server error: {e}")
    # Handle any MCP-related error
```

______________________________________________________________________

### Configuration Exceptions

#### ServerConfigurationError

Raised when server configuration is invalid.

**Import:**

```python
from mcp_common.exceptions import ServerConfigurationError
```

**Example:**

```python
from mcp_common.exceptions import ServerConfigurationError


def validate_config(config: dict) -> None:
    if "api_key" not in config:
        raise ServerConfigurationError("Missing required 'api_key' in configuration")

    if config["max_connections"] < 1:
        raise ServerConfigurationError("max_connections must be >= 1")
```

______________________________________________________________________

#### ServerInitializationError

Raised when server fails to initialize.

**Import:**

```python
from mcp_common.exceptions import ServerInitializationError
```

**Example:**

```python
from mcp_common.exceptions import ServerInitializationError


async def initialize_server():
    try:
        # Initialize components
        await database.connect()
        await http_client.initialize()
    except Exception as e:
        raise ServerInitializationError(f"Server initialization failed: {e}") from e
```

______________________________________________________________________

### Dependency Exceptions

#### DependencyMissingError

Raised when required dependency is not installed.

**Import:**

```python
from mcp_common.exceptions import DependencyMissingError
```

**Example:**

```python
from mcp_common.exceptions import DependencyMissingError

try:
    import onnxruntime
except ImportError as e:
    raise DependencyMissingError(
        "onnxruntime is required for embedding generation. "
        "Install with: pip install onnxruntime"
    ) from e
```

______________________________________________________________________

### Credential Validation Exceptions

#### CredentialValidationError

Base exception for credential validation failures.

**Import:**

```python
from mcp_common.exceptions import CredentialValidationError
```

**Example:**

```python
from mcp_common.exceptions import CredentialValidationError


def validate_credentials(username: str, password: str) -> None:
    if not username or not password:
        raise CredentialValidationError("Username and password are required")

    if len(password) < 8:
        raise CredentialValidationError("Password must be at least 8 characters")
```

______________________________________________________________________

#### APIKeyMissingError

Raised when required API key is missing.

**Import:**

```python
from mcp_common.exceptions import APIKeyMissingError
```

**Example:**

```python
from mcp_common.exceptions import APIKeyMissingError


def get_api_key(key_name: str) -> str:
    key = os.environ.get(key_name)
    if not key:
        raise APIKeyMissingError(f"{key_name} environment variable not set")
    return key
```

______________________________________________________________________

#### APIKeyFormatError

Raised when API key format is invalid.

**Import:**

```python
from mcp_common.exceptions import APIKeyFormatError
```

**Example:**

```python
from mcp_common.exceptions import APIKeyFormatError
import re


def validate_api_key_format(key: str, key_name: str = "API_KEY") -> str:
    # Check for invalid characters
    if not re.match(r"^[A-Za-z0-9_-]+$", key):
        raise APIKeyFormatError(
            f"{key_name} contains invalid characters. "
            f"Only alphanumeric, underscore, and dash allowed."
        )
    return key
```

______________________________________________________________________

#### APIKeyLengthError

Raised when API key length is invalid.

**Import:**

```python
from mcp_common.exceptions import APIKeyLengthError
```

**Example:**

```python
from mcp_common.exceptions import APIKeyLengthError


def validate_api_key_length(key: str, key_name: str = "API_KEY") -> str:
    if len(key) < 16:
        raise APIKeyLengthError(
            f"{key_name} must be at least 16 characters (got {len(key)})"
        )

    if len(key) > 256:
        raise APIKeyLengthError(
            f"{key_name} exceeds maximum length of 256 characters (got {len(key)})"
        )

    return key
```

______________________________________________________________________

## Complete Usage Example

Here's a complete example showing how to use mcp_common to build a production-ready MCP server:

```python
"""Example MCP server using mcp_common foundation."""

from __future__ import annotations

import asyncio
import typing as t
from dataclasses import dataclass

from acb.depends import depends
from fastmcp import FastMCP
from pydantic import Field, field_validator

from mcp_common import (
    HTTPClientAdapter,
    HTTPClientSettings,
    MCPBaseSettings,
    ServerPanels,
    ValidationMixin,
)
from mcp_common.exceptions import (
    APIKeyMissingError,
    DependencyMissingError,
    ServerInitializationError,
)
from mcp_common.health import ComponentHealth, HealthStatus
from mcp_common.http_health import check_http_client_health, check_http_connectivity


# 1. Define server settings with validation
class MyServerSettings(MCPBaseSettings, ValidationMixin):
    """My MCP server configuration."""

    server_name: str = Field(default="my-mcp-server", description="Server name")
    api_key: str = Field(..., description="Required API key for external service")
    api_endpoint: str = Field(default="https://api.example.com")
    enable_health_checks: bool = Field(default=True)

    @field_validator("api_key")
    @classmethod
    def validate_api_key_field(cls, v: str) -> str:
        """Validate API key format."""
        return cls.validate_api_key(v, name="MY_API_KEY")

    class Config:
        env_prefix = "MY_SERVER_"


# 2. Initialize server and adapters
mcp = FastMCP("my-mcp-server")
settings = MyServerSettings()

# Setup HTTP client adapter with custom settings
http_settings = HTTPClientSettings(
    max_connections=50,
    timeout=30.0,
    retry_attempts=3,
)
http_adapter = HTTPClientAdapter(settings=http_settings)
depends.set(HTTPClientAdapter, http_adapter)


# 3. Implement health checks
async def check_external_api_health() -> ComponentHealth:
    """Check external API connectivity."""
    try:
        async with http_adapter as client:
            response = await client.get(f"{settings.api_endpoint}/health")

            if response.status_code == 200:
                return ComponentHealth(
                    name="external_api",
                    status=HealthStatus.HEALTHY,
                    message="API operational",
                    metadata={"endpoint": settings.api_endpoint},
                )
            else:
                return ComponentHealth(
                    name="external_api",
                    status=HealthStatus.DEGRADED,
                    message=f"HTTP {response.status_code}",
                    metadata={"status_code": response.status_code},
                )

    except Exception as e:
        return ComponentHealth(
            name="external_api",
            status=HealthStatus.UNHEALTHY,
            message=f"API unreachable: {e}",
            metadata={"error": str(e)},
        )


# 4. Register MCP tools
@mcp.tool()
async def health_check() -> dict[str, t.Any]:
    """System health check."""

    if not settings.enable_health_checks:
        return {
            "status": "disabled",
            "message": "Health checks disabled in configuration",
        }

    # Run all health checks concurrently
    checks = await asyncio.gather(
        check_http_client_health(),
        check_http_connectivity(),
        check_external_api_health(),
        return_exceptions=True,
    )

    # Convert to ComponentHealth list
    components = []
    for check in checks:
        if isinstance(check, Exception):
            components.append(
                ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {check}",
                )
            )
        else:
            components.append(check)

    # Display health status
    ServerPanels.status(components)

    # Determine overall status
    statuses = [c.status for c in components]
    if HealthStatus.UNHEALTHY in statuses:
        overall = "unhealthy"
    elif HealthStatus.DEGRADED in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "components": [
            {
                "name": c.name,
                "status": c.status.value,
                "message": c.message,
                "latency_ms": c.latency_ms,
                "metadata": c.metadata,
            }
            for c in components
        ],
    }


@mcp.tool()
async def fetch_data(query: str) -> dict[str, t.Any]:
    """Fetch data from external API."""

    try:
        async with http_adapter as client:
            response = await client.get(
                f"{settings.api_endpoint}/data",
                params={"q": query},
                headers={"Authorization": f"Bearer {settings.api_key}"},
            )
            response.raise_for_status()

            return {
                "success": True,
                "data": response.json(),
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# 5. Server startup
async def startup():
    """Initialize server components."""

    try:
        # Display welcome panel
        ServerPanels.welcome(
            server_name=settings.server_name,
            features=[
                "🌐 HTTP Client with Connection Pooling",
                "🏥 Production Health Checks",
                "🔐 Secure API Authentication",
                "⚙️  Type-Safe Configuration",
            ],
        )

        # Initialize components
        print("✅ Server initialized successfully")

    except Exception as e:
        raise ServerInitializationError(f"Failed to initialize server: {e}") from e


# Run server
if __name__ == "__main__":
    asyncio.run(startup())
    mcp.run()
```

______________________________________________________________________

## Best Practices

### 1. Use ACB Dependency Injection

```text
# ✅ Good: Use DI container
from acb.depends import depends

http_adapter = depends.get_sync(HTTPClientAdapter)

# ❌ Bad: Direct instantiation
http_adapter = HTTPClientAdapter()
```

### 2. Always Measure Health Check Latency

```text
# ✅ Good: Include latency measurement
start_time = time.perf_counter()
# ... perform check ...
latency_ms = (time.perf_counter() - start_time) * 1000

return ComponentHealth(
    name="service",
    status=HealthStatus.HEALTHY,
    message="Operational",
    latency_ms=latency_ms,
)
```

### 3. Provide Actionable Metadata

```text
# ✅ Good: Detailed metadata
return ComponentHealth(
    name="database",
    status=HealthStatus.DEGRADED,
    message="High connection count",
    metadata={
        "active_connections": 95,
        "max_connections": 100,
        "recommendation": "Consider scaling database or optimizing queries",
    },
)
```

### 4. Use Context Managers for HTTP Clients

```text
# ✅ Good: Automatic cleanup
async with http_adapter as client:
    response = await client.get(url)

# ❌ Bad: Manual cleanup
client = await http_adapter._create_client()
response = await client.get(url)
await client.aclose()
```

### 5. Handle Errors Gracefully

```python
# ✅ Good: Never let health checks raise exceptions
async def check_service() -> ComponentHealth:
    try:
        # Check logic
        return ComponentHealth(status=HealthStatus.HEALTHY)
    except Exception as e:
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Check failed: {e}",
            metadata={"error": str(e)},
        )
```

______________________________________________________________________

## Related Documentation

- [ARCHITECTURE.md](../developer/ARCHITECTURE.md) - Complete architecture guide including ACB integration
- [MCP_SCHEMA_REFERENCE.md](MCP_SCHEMA_REFERENCE.md) - MCP tool schemas for AI agents
- [mcp-common GitHub Repository](https://github.com/lesleslie/mcp-common) - Source code and examples

______________________________________________________________________

**Version**: 2.0.0 (ACB-native)
**Last Updated**: Phase 10.2 (Production Hardening)
