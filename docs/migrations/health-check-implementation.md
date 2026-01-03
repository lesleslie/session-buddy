# Migration: Health Check Implementation

Note: This document describes a planned HTTP health/metrics layer. The current Session Buddy server does not expose HTTP endpoints; use exec/import checks or build a wrapper if needed.

## Overview

Add production-ready health checks to your MCP stack using mcp_common's health check system. This is an optional HTTP layer for wrappers or custom servers.

**Priority**: ⚡ **HIGH** - Critical for production deployments

## Prerequisites

- `mcp-common>=2.0.0` installed
- FastMCP server running
- Python 3.13+

## Benefits

✅ **Production Monitoring**: Real-time health status of all components (when exposed via a wrapper)

✅ **Early Problem Detection**: Identify issues before they cause failures

✅ **Standardized Format**: ComponentHealth pattern works across all MCP servers

✅ **Latency Tracking**: Performance diagnostics built-in

✅ **Actionable Metadata**: Rich context for debugging

✅ **Integration Ready**: Works with monitoring tools (Prometheus, DataDog, etc.)

## Current vs. New Pattern

### Before (No Health Checks)

```text
# No health monitoring - issues discovered through failures


@mcp.tool()
async def status():
    return {"status": "running"}  # Not very useful!
```

### After (Comprehensive Health Checks)

```text
from mcp_common.health import ComponentHealth, HealthStatus
from mcp_common.http_health import check_http_client_health


@mcp.tool()
async def health_check():
    """Comprehensive health check."""

    components = await asyncio.gather(
        check_python_environment_health(),
        check_database_health(),
        check_http_client_health(),
        check_file_system_health(),
    )

    return {
        "status": "healthy"
        if all(c.status == HealthStatus.HEALTHY for c in components)
        else "degraded",
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
```

## Migration Steps

### Step 1: Install/Update mcp-common

```bash
# Using uv (recommended)
uv add "mcp-common>=2.0.0"

# Using pip
pip install "mcp-common>=2.0.0"
```

### Step 2: Create Component Health Checks

Create health check module for your server:

```python
# health_checks.py
from __future__ import annotations

import time
import typing as t

from mcp_common.health import ComponentHealth, HealthStatus


async def check_python_environment_health() -> ComponentHealth:
    """Check Python runtime health."""
    import sys
    import platform

    python_version = sys.version_info

    if python_version < (3, 13):
        return ComponentHealth(
            name="python_env",
            status=HealthStatus.DEGRADED,
            message=f"Python {python_version.major}.{python_version.minor} (3.13+ recommended)",
            metadata={
                "python_version": f"{python_version.major}.{python_version.minor}.{python_version.micro}",
                "platform": platform.system(),
            },
        )

    return ComponentHealth(
        name="python_env",
        status=HealthStatus.HEALTHY,
        message=f"Python {python_version.major}.{python_version.minor}.{python_version.micro}",
        metadata={
            "python_version": f"{python_version.major}.{python_version.minor}.{python_version.micro}",
            "platform": platform.system(),
        },
    )


async def check_database_health() -> ComponentHealth:
    """Check database connection health."""
    start_time = time.perf_counter()

    try:
        from my_server.database import get_database

        db = await get_database()
        result = await db.ping()
        latency_ms = (time.perf_counter() - start_time) * 1000

        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database operational",
            latency_ms=latency_ms,
            metadata={
                "connections": result.get("connections", 0),
                "version": result.get("version", "unknown"),
            },
        )

    except Exception as e:
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database error: {e}",
            metadata={"error": str(e), "error_type": type(e).__name__},
        )


async def check_file_system_health() -> ComponentHealth:
    """Check file system accessibility."""
    start_time = time.perf_counter()

    from pathlib import Path
    import os

    app_dir = Path.home() / ".my-app"
    required_dirs = [
        app_dir / "logs",
        app_dir / "data",
        app_dir / "temp",
    ]

    issues = []
    for directory in required_dirs:
        if not directory.exists():
            issues.append(f"Missing: {directory.name}")
        elif not os.access(directory, os.W_OK):
            issues.append(f"Not writable: {directory.name}")

    latency_ms = (time.perf_counter() - start_time) * 1000

    if issues:
        return ComponentHealth(
            name="file_system",
            status=HealthStatus.DEGRADED,
            message=f"File system issues: {', '.join(issues)}",
            latency_ms=latency_ms,
            metadata={"issues": issues},
        )

    return ComponentHealth(
        name="file_system",
        status=HealthStatus.HEALTHY,
        message="File system accessible",
        latency_ms=latency_ms,
    )


async def get_all_health_checks() -> list[ComponentHealth]:
    """Execute all health checks concurrently."""
    import asyncio

    checks = await asyncio.gather(
        check_python_environment_health(),
        check_database_health(),
        check_file_system_health(),
        return_exceptions=True,
    )

    # Convert exceptions to UNHEALTHY ComponentHealth
    results = []
    for check in checks:
        if isinstance(check, Exception):
            results.append(
                ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check crashed: {check}",
                    metadata={"error": str(check)},
                )
            )
        else:
            results.append(check)

    return results
```

### Step 3: Add HTTP Client Health Check

If using HTTPClientAdapter:

```text
# In health_checks.py, add:
from mcp_common.http_health import check_http_client_health, check_http_connectivity


async def check_http_health() -> list[ComponentHealth]:
    """Check HTTP client and connectivity."""
    return await asyncio.gather(
        check_http_client_health(),
        check_http_connectivity(test_url="https://api.example.com/health"),
    )
```

### Step 4: Register MCP Health Check Tool

```text
# server.py
from fastmcp import FastMCP
from my_server.health_checks import get_all_health_checks

mcp = FastMCP("my-server")


@mcp.tool()
async def health_check() -> dict[str, t.Any]:
    """Comprehensive server health check.

    Returns health status for all server components including:
    - Python environment
    - Database connections
    - HTTP client
    - File system
    """

    components = await get_all_health_checks()

    # Determine overall status (worst component status)
    statuses = [c.status for c in components]
    if HealthStatus.UNHEALTHY in statuses:
        overall_status = "unhealthy"
    elif HealthStatus.DEGRADED in statuses:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
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
```

### Step 5: Add Health Check Endpoint (HTTP Servers)

For HTTP-based health check endpoints:

```python
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


async def http_health_check(request):
    """HTTP health check endpoint."""
    components = await get_all_health_checks()

    # Determine status code based on health
    statuses = [c.status for c in components]
    if HealthStatus.UNHEALTHY in statuses:
        status_code = 503  # Service Unavailable
    elif HealthStatus.DEGRADED in statuses:
        status_code = 200  # OK but with warnings
    else:
        status_code = 200  # OK

    return JSONResponse(
        {
            "status": "healthy" if status_code == 200 else "unhealthy",
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                }
                for c in components
            ],
        },
        status_code=status_code,
    )


app = Starlette(
    routes=[
        Route("/health", http_health_check),
    ]
)
```

### Step 6: Add Health Check UI (Optional)

Use ServerPanels for terminal UI:

```python
from mcp_common.ui import ServerPanels
from my_server.health_checks import get_all_health_checks


async def display_health_status():
    """Display health status with Rich UI."""
    components = await get_all_health_checks()
    ServerPanels.status(components)


# Call at startup or on demand
asyncio.run(display_health_status())
```

### Step 7: Add Monitoring Integration (Optional)

Export metrics for Prometheus:

```python
from prometheus_client import Gauge, generate_latest

# Create Prometheus metrics
health_status = Gauge("server_health_status", "Component health status", ["component"])
health_latency = Gauge(
    "server_health_latency_ms", "Health check latency", ["component"]
)


async def export_health_metrics():
    """Export health metrics for Prometheus."""
    components = await get_all_health_checks()

    for component in components:
        # Map status to numeric value (1=healthy, 0.5=degraded, 0=unhealthy)
        status_value = {
            HealthStatus.HEALTHY: 1.0,
            HealthStatus.DEGRADED: 0.5,
            HealthStatus.UNHEALTHY: 0.0,
        }[component.status]

        health_status.labels(component=component.name).set(status_value)

        if component.latency_ms is not None:
            health_latency.labels(component=component.name).set(component.latency_ms)


# Expose metrics endpoint
@app.route("/metrics")
async def metrics_endpoint(request):
    return Response(generate_latest(), media_type="text/plain")
```

## Validation

### Test 1: Basic Health Check

```python
import asyncio
from my_server.health_checks import get_all_health_checks


async def test_health_check():
    components = await get_all_health_checks()

    print("Health Check Results:")
    for component in components:
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌",
        }[component.status.value]

        print(f"{status_emoji} {component.name}: {component.message}")
        if component.latency_ms:
            print(f"   Latency: {component.latency_ms:.2f}ms")
        if component.metadata:
            print(f"   Metadata: {component.metadata}")


asyncio.run(test_health_check())
```

### Test 2: MCP Tool Integration

```bash
# Test via MCP client
echo '{"tool": "health_check", "arguments": {}}' | my-server
```

### Test 3: HTTP Endpoint (if applicable)

```bash
# Test HTTP health endpoint
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "healthy",
#   "components": [
#     {"name": "python_env", "status": "healthy", "message": "Python 3.13.7"},
#     {"name": "database", "status": "healthy", "message": "Database operational"},
#     {"name": "file_system", "status": "healthy", "message": "File system accessible"}
#   ]
# }
```

### Test 4: Monitoring Integration

```bash
# Test Prometheus metrics (if implemented)
curl http://localhost:8000/metrics

# Expected output includes:
# server_health_status{component="database"} 1.0
# server_health_latency_ms{component="database"} 5.2
```

## Rollback Procedure

Health checks are additive and safe to rollback:

### Step 1: Remove Health Check Tool

Comment out or remove the health_check tool:

```text
# @mcp.tool()
# async def health_check():
#     ...
```

### Step 2: Remove Health Check Module

Delete or rename `health_checks.py`:

```bash
mv health_checks.py health_checks.py.bak
```

### Step 3: Remove UI Dependencies (if added)

If you added Rich UI panels:

```bash
# Remove from dependencies
uv remove rich
```

## Common Issues

### Issue 1: Import Error for ComponentHealth

**Symptom**:

```
ImportError: cannot import name 'ComponentHealth' from 'mcp_common'
```

**Solution**:

```bash
# Ensure mcp-common 2.0+ is installed
uv add "mcp-common>=2.0.0"

# Verify import
python -c "from mcp_common.health import ComponentHealth; print('✅ Import successful')"
```

### Issue 2: Health Check Hangs

**Symptom**:

Health check never completes or times out.

**Solution**:

Add timeout to individual health checks:

```python
async def check_with_timeout(check_func, timeout_seconds=5.0):
    """Wrap health check with timeout."""
    try:
        return await asyncio.wait_for(check_func(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return ComponentHealth(
            name=check_func.__name__,
            status=HealthStatus.UNHEALTHY,
            message=f"Health check timed out after {timeout_seconds}s",
        )
```

### Issue 3: Health Check Crashes Server

**Symptom**:

Health check raises unhandled exception that crashes server.

**Solution**:

Always catch exceptions in health checks:

```python
async def safe_health_check(check_func):
    """Wrap health check to prevent crashes."""
    try:
        return await check_func()
    except Exception as e:
        return ComponentHealth(
            name=check_func.__name__,
            status=HealthStatus.UNHEALTHY,
            message=f"Health check crashed: {e}",
            metadata={"error": str(e), "error_type": type(e).__name__},
        )
```

### Issue 4: Slow Health Checks

**Symptom**:

Health check endpoint takes >1 second to respond.

**Solution**:

Run checks concurrently with `asyncio.gather()`:

```text
# ✅ Good: Concurrent execution (fast)
components = await asyncio.gather(
    check_1(),
    check_2(),
    check_3(),
)

# ❌ Bad: Sequential execution (slow)
components = [
    await check_1(),
    await check_2(),
    await check_3(),
]
```

## Best Practices

### 1. Measure Latency

```text
# ✅ Good: Always measure latency
start_time = time.perf_counter()
# ... perform check ...
latency_ms = (time.perf_counter() - start_time) * 1000
```

### 2. Provide Actionable Metadata

```python
# ✅ Good: Detailed metadata
return ComponentHealth(
    name="database",
    status=HealthStatus.DEGRADED,
    message="High connection count",
    metadata={
        "active_connections": 95,
        "max_connections": 100,
        "recommendation": "Scale database or optimize queries",
    },
)
```

### 3. Use Meaningful Status Levels

- **HEALTHY**: Everything is normal, no action needed
- **DEGRADED**: Functional but issues detected, monitor closely
- **UNHEALTHY**: Not operational, immediate attention required

### 4. Run Checks Concurrently

```python
# ✅ Good: Parallel execution
components = await asyncio.gather(
    check_python_environment_health(),
    check_database_health(),
    check_file_system_health(),
)
```

### 5. Handle Errors Gracefully

```text
# ✅ Good: Never let exceptions propagate
try:
    # Check logic
    return ComponentHealth(status=HealthStatus.HEALTHY)
except Exception as e:
    return ComponentHealth(
        status=HealthStatus.UNHEALTHY,
        message=f"Check failed: {e}",
        metadata={"error": str(e)}
    )
```

### 6. Cache Health Check Results (Optional)

For high-traffic servers:

```python
from functools import lru_cache
from datetime import datetime, timedelta

_health_cache = None
_health_cache_time = None


async def get_cached_health_checks(ttl_seconds=30):
    """Get health checks with caching."""
    global _health_cache, _health_cache_time

    now = datetime.now()

    if _health_cache and _health_cache_time:
        age = (now - _health_cache_time).total_seconds()
        if age < ttl_seconds:
            return _health_cache

    # Cache expired, run checks
    _health_cache = await get_all_health_checks()
    _health_cache_time = now

    return _health_cache
```

## Health Check Patterns

### Pattern 1: Simple Binary Check

```python
async def check_service_health() -> ComponentHealth:
    """Simple up/down check."""
    try:
        await service.ping()
        return ComponentHealth(
            name="service", status=HealthStatus.HEALTHY, message="Service responding"
        )
    except Exception as e:
        return ComponentHealth(
            name="service",
            status=HealthStatus.UNHEALTHY,
            message=f"Service not responding: {e}",
        )
```

### Pattern 2: Threshold-Based Check

```python
async def check_memory_health() -> ComponentHealth:
    """Memory usage with thresholds."""
    import psutil

    memory = psutil.virtual_memory()
    usage_percent = memory.percent

    if usage_percent > 90:
        status = HealthStatus.UNHEALTHY
        message = f"Critical memory usage: {usage_percent}%"
    elif usage_percent > 75:
        status = HealthStatus.DEGRADED
        message = f"High memory usage: {usage_percent}%"
    else:
        status = HealthStatus.HEALTHY
        message = f"Memory usage normal: {usage_percent}%"

    return ComponentHealth(
        name="memory",
        status=status,
        message=message,
        metadata={
            "usage_percent": usage_percent,
            "available_mb": memory.available / 1024 / 1024,
            "total_mb": memory.total / 1024 / 1024,
        },
    )
```

### Pattern 3: Connectivity Check

```python
async def check_api_connectivity() -> ComponentHealth:
    """Check external API connectivity."""
    from mcp_common.http_health import check_http_connectivity

    return await check_http_connectivity(
        test_url="https://api.example.com/health", timeout_ms=3000
    )
```

## Additional Resources

- [ComponentHealth API Reference](../reference/API_REFERENCE.md)
- [ARCHITECTURE.md - Health Check Architecture](../developer/ARCHITECTURE.md)
- [HTTPClientAdapter Health Checks](../reference/API_REFERENCE.md)
- [Prometheus Integration Guide](https://prometheus.io/docs/guides/go-application/)

______________________________________________________________________

**Need help?** Open an issue on GitHub with the `health-checks` label.

**Example implementations?** Check `session_buddy/health_checks.py` for reference.
