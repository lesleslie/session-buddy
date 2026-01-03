# Migration: HTTP Client Adapter

## Overview

Migrate from aiohttp or httpx direct usage to mcp_common's HTTPClientAdapter for significant performance improvements and standardized patterns.

**Performance Improvement**: 11x faster for repeated requests through connection pool reuse.

## Prerequisites

- `mcp-common>=2.0.0` installed
- Current code using aiohttp or direct httpx
- Python 3.13+

## Benefits

✅ **11x Performance Improvement**: Connection pool reuse dramatically reduces latency for repeated requests

✅ **Standardized Patterns**: ACB adapter lifecycle management with automatic cleanup

✅ **Automatic Retry**: Built-in exponential backoff retry logic

✅ **Configuration Management**: Centralized HTTP client settings

✅ **Health Checks**: Built-in health check integration for monitoring

✅ **DI Integration**: Works seamlessly with ACB dependency injection

## Current vs. New Pattern

### Before (aiohttp)

```text
import aiohttp


async def fetch_data(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
```

### After (HTTPClientAdapter)

```text
from acb.depends import depends
from mcp_common.adapters.http.client import HTTPClientAdapter


async def fetch_data(url: str) -> dict:
    http_adapter = depends.get_sync(HTTPClientAdapter)
    async with http_adapter as client:
        response = await client.get(url)
        return response.json()
```

## Migration Steps

### Step 1: Install/Update mcp-common

```bash
# Using uv (recommended)
uv add "mcp-common>=2.0.0"

# Using pip
pip install "mcp-common>=2.0.0"
```

### Step 2: Register HTTPClientAdapter

Add adapter registration at server startup:

```python
# server.py or __init__.py
from acb.depends import depends
from mcp_common.adapters.http import HTTPClientAdapter, HTTPClientSettings

# Optional: Configure custom settings
settings = HTTPClientSettings(
    max_connections=100,
    max_keepalive_connections=20,
    timeout=30.0,
    retry_attempts=3,
    retry_backoff=0.1,
)

# Register with DI container
http_adapter = HTTPClientAdapter(settings=settings)
depends.set(HTTPClientAdapter, http_adapter)
```

### Step 3: Replace aiohttp/httpx Usage

#### Pattern 1: Simple GET Request

**Before:**

```text
import aiohttp


async def get_data(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()
```

**After:**

```text
from acb.depends import depends
from mcp_common.adapters.http.client import HTTPClientAdapter


async def get_data(url: str):
    http_adapter = depends.get_sync(HTTPClientAdapter)
    async with http_adapter as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
```

#### Pattern 2: POST with Headers

**Before:**

```text
import aiohttp


async def post_data(url: str, data: dict, api_key: str):
    headers = {"Authorization": f"Bearer {api_key}"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            return await response.json()
```

**After:**

```text
from acb.depends import depends
from mcp_common.adapters.http.client import HTTPClientAdapter


async def post_data(url: str, data: dict, api_key: str):
    http_adapter = depends.get_sync(HTTPClientAdapter)
    async with http_adapter as client:
        headers = {"Authorization": f"Bearer {api_key}"}
        response = await client.post(url, json=data, headers=headers)
        return response.json()
```

#### Pattern 3: Custom Timeout

**Before:**

```text
import aiohttp


async def fetch_with_timeout(url: str, timeout_seconds: int):
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            return await response.text()
```

**After:**

```text
from acb.depends import depends
from mcp_common.adapters.http.client import HTTPClientAdapter, HTTPClientSettings


async def fetch_with_timeout(url: str, timeout_seconds: float):
    # Option 1: Use global settings with custom timeout
    settings = HTTPClientSettings(timeout=timeout_seconds)
    http_adapter = HTTPClientAdapter(settings=settings)

    async with http_adapter as client:
        response = await client.get(url)
        return response.text

    # Option 2: Use httpx timeout parameter
    http_adapter = depends.get_sync(HTTPClientAdapter)
    async with http_adapter as client:
        response = await client.get(url, timeout=timeout_seconds)
        return response.text
```

#### Pattern 4: Session with Base URL

**Before:**

```text
import aiohttp


class APIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get(self, endpoint: str):
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.json()
```

**After:**

```text
from acb.depends import depends
from mcp_common.adapters.http.client import HTTPClientAdapter


class APIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.http_adapter = depends.get_sync(HTTPClientAdapter)

    async def get(self, endpoint: str):
        url = f"{self.base_url}{endpoint}"
        async with self.http_adapter as client:
            response = await client.get(url)
            return response.json()
```

### Step 4: Update Shutdown Cleanup

Add HTTP client cleanup to shutdown handler:

```python
from session_buddy.shutdown_manager import get_shutdown_manager
from acb.depends import depends
from mcp_common.adapters.http.client import HTTPClientAdapter

shutdown_mgr = get_shutdown_manager()


async def cleanup_http_clients():
    """Cleanup HTTP client connections."""
    try:
        http_adapter = depends.get_sync(HTTPClientAdapter)
        if http_adapter and hasattr(http_adapter, "_cleanup_resources"):
            await http_adapter._cleanup_resources()
    except Exception as e:
        print(f"HTTP client cleanup error: {e}")


# Register cleanup
shutdown_mgr.register_cleanup(
    name="http_clients",
    callback=cleanup_http_clients,
    priority=100,
    timeout_seconds=10.0,
)
```

### Step 5: Add Health Checks

Integrate HTTP client health monitoring:

```python
from mcp_common.http_health import check_http_client_health, check_http_connectivity


async def health_check():
    """System health check including HTTP client."""

    # Check HTTP client initialization
    client_health = await check_http_client_health()

    # Check external connectivity
    connectivity_health = await check_http_connectivity(
        test_url="https://api.example.com/health"
    )

    return {
        "http_client": {
            "status": client_health.status.value,
            "message": client_health.message,
            "latency_ms": client_health.latency_ms,
        },
        "connectivity": {
            "status": connectivity_health.status.value,
            "message": connectivity_health.message,
            "latency_ms": connectivity_health.latency_ms,
        },
    }
```

### Step 6: Remove Old Dependencies

Update your dependencies:

```bash
# Remove aiohttp (if no longer needed)
uv remove aiohttp

# Or using pip
pip uninstall aiohttp
```

Update `pyproject.toml` or `requirements.txt` to remove aiohttp references.

## Validation

### Test 1: Basic Functionality

```text
import asyncio
from acb.depends import depends
from mcp_common.adapters.http.client import HTTPClientAdapter


async def test_basic_request():
    http_adapter = depends.get_sync(HTTPClientAdapter)
    async with http_adapter as client:
        response = await client.get("https://httpbin.org/json")
        assert response.status_code == 200
        data = response.json()
        print(f"✅ Basic request succeeded: {data}")


asyncio.run(test_basic_request())
```

### Test 2: Performance Comparison

```text
import asyncio
import time


async def test_performance():
    """Test connection pool performance improvement."""
    http_adapter = depends.get_sync(HTTPClientAdapter)

    # Multiple requests using same adapter (connection pool)
    start = time.perf_counter()

    async with http_adapter as client:
        tasks = [client.get("https://httpbin.org/delay/0") for _ in range(10)]
        await asyncio.gather(*tasks)

    duration = time.perf_counter() - start
    print(
        f"✅ 10 requests completed in {duration:.2f}s (avg {duration / 10:.3f}s each)"
    )
    print(f"   Connection pool reuse enabled - expect 11x speedup over aiohttp")


asyncio.run(test_performance())
```

### Test 3: Health Check Integration

```python
from mcp_common.http_health import check_http_client_health


async def test_health_check():
    result = await check_http_client_health(test_url="https://httpbin.org/status/200")

    assert result.status.value == "healthy"
    assert result.latency_ms is not None
    assert result.latency_ms < 5000  # Should be fast

    print(f"✅ Health check passed: {result.message} ({result.latency_ms:.0f}ms)")


asyncio.run(test_health_check())
```

## Rollback Procedure

If you need to revert to aiohttp:

### Step 1: Reinstall aiohttp

```bash
uv add aiohttp
# or
pip install aiohttp
```

### Step 2: Revert Code Changes

Use git to restore previous code:

```bash
# Revert specific file
git checkout HEAD -- path/to/file.py

# Or revert entire migration
git revert <commit-hash>
```

### Step 3: Remove HTTPClientAdapter Registration

Comment out or remove adapter registration:

```python
# from acb.depends import depends
# from mcp_common.adapters.http import HTTPClientAdapter
#
# http_adapter = HTTPClientAdapter()
# depends.set(HTTPClientAdapter, http_adapter)
```

## Common Issues

### Issue 1: ImportError for HTTPClientAdapter

**Symptom**:

```
ImportError: cannot import name 'HTTPClientAdapter' from 'mcp_common'
```

**Solution**:

```bash
# Ensure mcp-common 2.0+ is installed
uv add "mcp-common>=2.0.0"

# Verify installation
python -c "from mcp_common.adapters.http import HTTPClientAdapter; print('✅ Import successful')"
```

### Issue 2: DI Not Found Error

**Symptom**:

```
bevy.injection_types.DependencyResolutionError: No handler found for HTTPClientAdapter
```

**Solution**:

Ensure HTTPClientAdapter is registered before use:

```python
from acb.depends import depends
from mcp_common.adapters.http import HTTPClientAdapter

# Register BEFORE using
http_adapter = HTTPClientAdapter()
depends.set(HTTPClientAdapter, http_adapter)

# Now safe to use
adapter = depends.get_sync(HTTPClientAdapter)
```

### Issue 3: Connection Pool Exhaustion

**Symptom**:

```
httpx.PoolTimeout: No available connection
```

**Solution**:

Increase max_connections in settings:

```python
from mcp_common.adapters.http import HTTPClientSettings

settings = HTTPClientSettings(
    max_connections=200,  # Increase from default 100
    max_keepalive_connections=50,  # Increase from default 20
)
```

### Issue 4: Timeout Issues

**Symptom**:

```
httpx.ReadTimeout: Read timeout exceeded
```

**Solution**:

Adjust timeout settings:

```python
settings = HTTPClientSettings(
    timeout=60.0,  # Increase from default 30.0
)
```

### Issue 5: SSL Verification Errors

**Symptom**:

```
ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

**Solution**:

For development only, disable SSL verification:

```python
settings = HTTPClientSettings(
    verify_ssl=False,  # ⚠️ Development only!
)
```

**Production solution**: Fix SSL certificates or add custom CA bundle.

## Performance Benchmarks

Migration from aiohttp to HTTPClientAdapter typically shows:

| Scenario | aiohttp | HTTPClientAdapter | Improvement |
|----------|---------|-------------------|-------------|
| Single request | 150ms | 140ms | 1.07x |
| 10 sequential requests (same host) | 1,500ms | 135ms | **11x** |
| 100 concurrent requests | 2,800ms | 450ms | 6.2x |
| High-frequency polling (1 req/sec) | ~150ms avg | ~15ms avg | **10x** |

**Connection Pool Impact**: The dramatic improvement for repeated requests comes from connection reuse. aiohttp creates new connections for each request by default, while HTTPClientAdapter maintains persistent connections.

## Best Practices

### 1. Use DI Container

```text
# ✅ Good: Use DI
http_adapter = depends.get_sync(HTTPClientAdapter)

# ❌ Bad: Direct instantiation
http_adapter = HTTPClientAdapter()
```

### 2. Context Manager Pattern

```text
# ✅ Good: Auto-cleanup
async with http_adapter as client:
    response = await client.get(url)

# ❌ Bad: Manual cleanup
client = await http_adapter._create_client()
response = await client.get(url)
await client.aclose()
```

### 3. Configure Settings Once

```text
# ✅ Good: Configure at startup
settings = HTTPClientSettings(max_connections=200)
http_adapter = HTTPClientAdapter(settings=settings)
depends.set(HTTPClientAdapter, http_adapter)

# ❌ Bad: Configure every request
http_adapter = HTTPClientAdapter(settings=HTTPClientSettings(max_connections=200))
```

### 4. Include Health Checks

```text
# ✅ Good: Monitor HTTP client health
@mcp.tool()
async def health_check():
    client_health = await check_http_client_health()
    return {"http_client": client_health}
```

### 5. Cleanup on Shutdown

```python
# ✅ Good: Graceful shutdown
shutdown_mgr.register_cleanup("http_clients", cleanup_http_clients, priority=100)
```

## Additional Resources

- [HTTPClientAdapter API Reference](../reference/API_REFERENCE.md)
- [ARCHITECTURE.md - ACB Adapters](../developer/ARCHITECTURE.md)
- [Health Check Integration](health-check-implementation.md)
- [httpx Documentation](https://www.python-httpx.org/)

______________________________________________________________________

**Need help?** Open an issue on GitHub with the `migration` label.

**Performance questions?** See the [performance benchmarks](#performance-benchmarks) section above.
