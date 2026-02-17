# Serverless Mode Refactoring Plan

**Date:** 2025-10-28
**Status:** 🚧 In Progress
**Goal:** Replace custom storage backends with ACB cache adapters

______________________________________________________________________

## Problem Statement

`serverless_mode.py` (945 lines) currently implements custom storage backends:

- `RedisStorage` (224 lines) - Duplicate Redis implementation
- `S3Storage` (264 lines) - Custom S3 implementation not in ACB
- `LocalFileStorage` (141 lines) - Custom file-based storage

**Issues:**

1. **Duplicate Infrastructure**: Reimplements Redis/storage that ACB already provides
1. **Limited Options**: Only Redis, S3, and local file - ACB offers more
1. **Maintenance Burden**: Custom code to maintain vs ACB's battle-tested adapters
1. **Missing Features**: No connection pooling, health checks, SSL/TLS support

______________________________________________________________________

## Solution: Use ACB Cache Adapters

### Why ACB Cache (Not Storage) Adapters?

**ACB Storage Adapters** (`file`, `s3`, `azure`, `gcs`):

- Designed for blob/file storage
- Interface: `read_file()`, `write_file()`, `list_files()`
- ❌ Not suitable for SessionState KV storage

**ACB Cache Adapters** (`redis`, `memory`):

- Designed for KV stores with TTL support
- Interface: `get(key)`, `set(key, value, ttl)`, `delete(key)`, `exists(key)`
- ✅ Perfect fit for serverless session management

### Available ACB Cache Adapters

1. **Redis Cache** (`/Users/les/Projects/acb/acb/adapters/cache/redis.py`)

   - Uses `aiocache[redis]` + `coredis` for advanced features
   - Connection pooling, cluster support, health checks
   - SSL/TLS support with certificate validation
   - Automatic reconnection on failures
   - Tracking cache for debugging

1. **Memory Cache** (`/Users/les/Projects/acb/acb/adapters/cache/memory.py`)

   - In-memory cache for testing/development
   - Same interface as Redis for drop-in replacement
   - No external dependencies

### Key Features We Get From ACB

```python
class CacheBase(BaseCache):
    """ACB cache adapter base class."""

    async def get(
        self,
        key: str,
        default: t.Any = None,
        namespace: str | None = None,
    ) -> t.Any:
        """Get cache value with namespace support."""

    async def set(
        self,
        key: str,
        value: t.Any,
        ttl: int | None = None,
        namespace: str | None = None,
    ) -> None:
        """Set cache value with TTL."""

    async def delete(self, key: str, namespace: str | None = None) -> bool:
        """Delete cache key."""

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
```

**Built-in Features:**

- `MsgPackSerializer` with brotli compression (efficient storage)
- `CacheBaseSettings` with SSL/TLS configuration
- `CleanupMixin` for proper resource cleanup
- `Inject[Config]` dependency injection integration
- Health check monitoring (if needed)

______________________________________________________________________

## Refactoring Architecture

### Current Architecture (Problematic)

```python
# session_buddy/serverless_mode.py


class SessionStorage(ABC):
    """Abstract base class - CUSTOM INTERFACE."""

    @abstractmethod
    async def store_session(
        self,
        session_state: SessionState,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Store session state with optional TTL."""

    @abstractmethod
    async def retrieve_session(self, session_id: str) -> SessionState | None:
        """Retrieve session state by ID."""


# 629 lines of duplicate Redis/S3/file implementation
```

### New Architecture (ACB-Based)

```python
# session_buddy/serverless_mode.py

from acb.adapters.cache import CacheBase  # Import ACB base
from acb.depends import depends


class SessionStorage(ABC):
    """Abstract base class - UNCHANGED INTERFACE."""

    @abstractmethod
    async def store_session(
        self,
        session_state: SessionState,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Store session state with optional TTL."""

    @abstractmethod
    async def retrieve_session(self, session_id: str) -> SessionState | None:
        """Retrieve session state by ID."""


class ACBCacheStorage(SessionStorage):
    """Adapter that wraps ACB cache to implement SessionStorage interface.

    Supports both Redis and Memory cache via ACB dependency injection.
    """

    def __init__(self, cache: CacheBase, namespace: str = "session"):
        self.cache = cache
        self.namespace = namespace

    async def store_session(
        self,
        session_state: SessionState,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Store session using ACB cache adapter."""
        try:
            key = f"{self.namespace}:{session_state.session_id}"
            # SessionState is Pydantic - use model_dump() for serialization
            data = session_state.model_dump(mode="json")
            await self.cache.set(key, data, ttl=ttl_seconds)
            return True
        except Exception as e:
            logger.error(f"Failed to store session: {e}")
            return False

    async def retrieve_session(self, session_id: str) -> SessionState | None:
        """Retrieve session using ACB cache adapter."""
        try:
            key = f"{self.namespace}:{session_id}"
            data = await self.cache.get(key)
            if data:
                return SessionState(**data)
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve session: {e}")
            return None

    async def delete_session(self, session_id: str) -> bool:
        """Delete session using ACB cache adapter."""
        key = f"{self.namespace}:{session_id}"
        return await self.cache.delete(key)

    async def list_sessions(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[SessionState]:
        """List sessions - requires scan support from cache adapter."""
        # Note: This may require additional implementation in ACB cache
        # For now, track session IDs in a separate key
        raise NotImplementedError("List sessions requires index support")


# Dependency injection factory
@depends.inject
def create_session_storage(
    cache: CacheBase = depends(),  # ACB provides Redis or Memory
    namespace: str = "session",
) -> SessionStorage:
    """Factory function to create SessionStorage using ACB cache."""
    return ACBCacheStorage(cache, namespace)
```

**Benefits:**

- 629 lines of custom code eliminated (87% reduction)
- ACB handles Redis connection pooling, SSL, reconnection
- Drop-in replacement: `RedisStorage` → `ACBCacheStorage(redis_cache)`
- Same for memory: `LocalFileStorage` → `ACBCacheStorage(memory_cache)`

______________________________________________________________________

## Migration Steps

### Phase 1: Create ACB Adapter Wrapper (Today)

1. ✅ **Research ACB cache interface** (DONE)

1. ⏳ **Create `ACBCacheStorage` class** in serverless_mode.py

   - Implement `store_session()`, `retrieve_session()`, `delete_session()`
   - Add proper error handling and logging
   - Handle SessionState Pydantic serialization

1. ⏳ **Add factory function** for dependency injection

   - `create_session_storage()` using `@depends.inject`
   - Configure namespace for multi-tenant support

1. ⏳ **Keep legacy backends temporarily** for gradual migration

   - Mark `RedisStorage`, `S3Storage`, `LocalFileStorage` as deprecated
   - Add deprecation warnings

### Phase 2: Update ServerlessSessionManager (Today)

1. ⏳ **Add ACB storage option** to `ServerlessSessionManager`

```text
   class ServerlessSessionManager:
       def __init__(
           self,
           storage_type: Literal["redis", "s3", "local", "acb"] = "acb",
           storage_config: dict[str, Any] | None = None,
       ):
           if storage_type == "acb":
               # Use ACB cache via dependency injection
               self.storage = create_session_storage()
           elif storage_type == "redis":
               # Legacy path (deprecated)
               self.storage = RedisStorage(**storage_config)
           # ...
```

1. ⏳ **Update configuration** to prefer ACB by default

   - Change default `storage_type="acb"`
   - Add configuration for ACB cache settings

### Phase 3: Update Tests (Today)

1. ⏳ **Update serverless_mode tests** to use ACB cache

   - Replace RedisStorage mocks with ACB cache mocks
   - Test both Redis and Memory cache adapters
   - Verify SessionState serialization/deserialization

1. ⏳ **Add integration tests** with real ACB cache

   - Test Redis cache adapter integration
   - Test Memory cache adapter for testing
   - Verify TTL expiration behavior

### Phase 4: Remove Legacy Backends (Later)

1. ⏳ **Remove deprecated classes** (600+ lines)

   - Delete `RedisStorage`, `S3Storage`, `LocalFileStorage`
   - Update imports and documentation

1. ⏳ **Update documentation**

   - Explain ACB cache configuration
   - Add examples for Redis and Memory cache

______________________________________________________________________

## Configuration Changes

### Before (Custom Backends)

```python
# .mcp.json or config
{
    "serverless": {
        "storage_type": "redis",
        "storage_config": {
            "host": "localhost",
            "port": 6379,
            "password": "secret",
            "db": 0,
        },
    }
}
```

### After (ACB Cache)

```python
# .mcp.json or config - ACB cache configuration
{
    "acb": {
        "cache": {
            "provider": "redis",  # or "memory" for testing
            "host": "localhost",
            "port": 6379,
            "password": "secret",
            "db": 0,
            "default_ttl": 86400,  # 24 hours
            "ssl_enabled": true,
            "ssl_cert_path": "/path/to/cert.pem",
        }
    }
}
```

**Advantages:**

- Unified configuration across all ACB components
- SSL/TLS support automatically available
- Connection pooling configured centrally
- Health checks and monitoring built-in

______________________________________________________________________

## Testing Strategy

### Unit Tests

1. **Test ACBCacheStorage adapter**

   ```text
   @pytest.mark.asyncio
   async def test_acb_cache_storage_store_session(mock_cache):
       storage = ACBCacheStorage(mock_cache)
       session = SessionState(session_id="test-123", ...)

       result = await storage.store_session(session, ttl_seconds=3600)

       assert result is True
       mock_cache.set.assert_called_once()
   ```

1. **Test SessionState serialization**

   - Verify Pydantic `model_dump()` works correctly
   - Test deserialization from cache data

1. **Test error handling**

   - Cache unavailable scenarios
   - Serialization failures
   - TTL edge cases

### Integration Tests

1. **Test with real ACB Redis cache**

   ```text
   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_redis_cache_integration():
       from acb.adapters.cache import redis

       cache = redis.Cache()  # Uses ACB config
       storage = ACBCacheStorage(cache)

       session = SessionState(session_id="test-123", ...)
       await storage.store_session(session, ttl_seconds=60)

       retrieved = await storage.retrieve_session("test-123")
       assert retrieved.session_id == "test-123"
   ```

1. **Test with ACB Memory cache** (for CI/CD)

```text
   @pytest.mark.asyncio
   async def test_memory_cache_integration():
       from acb.adapters.cache import memory

       cache = memory.Cache()
       storage = ACBCacheStorage(cache)
       # ... same tests as Redis
```

______________________________________________________________________

## Rollout Plan

### Week 5 Day 3 (Today)

1. **Morning**: Create ACB adapter wrapper and update ServerlessSessionManager
1. **Afternoon**: Update tests and verify everything passes

### Week 5 Day 4+

1. Add deprecation warnings to legacy backends
1. Update documentation with ACB cache examples
1. Monitor for any issues

### Week 6 (Later)

1. Remove legacy backends entirely
1. Final documentation cleanup

______________________________________________________________________

## Risk Mitigation

### Potential Issues

1. **ACB cache dependencies not installed**

   - Solution: Add `aiocache[redis]` and `coredis` to pyproject.toml
   - Fallback: Memory cache works without Redis

1. **SessionState serialization issues**

   - Solution: Use Pydantic `model_dump(mode="json")` for clean JSON
   - Test: Comprehensive serialization tests

1. **Configuration migration**

   - Solution: Support both old and new config during transition
   - Deprecation: Warn users about old config format

1. **Performance differences**

   - Solution: ACB uses msgpack + brotli compression (likely faster)
   - Monitoring: Add performance tests to verify

### Rollback Plan

If issues arise:

1. Keep legacy backends during Phase 1-3
1. Make ACB opt-in via `storage_type="acb"`
1. Default to Redis/S3/local if ACB fails

______________________________________________________________________

## Expected Benefits

### Code Quality

- **-629 lines** of custom code eliminated (87% reduction)
- **-300 lines** of Redis implementation (replaced by ACB)
- **-264 lines** of S3 implementation (use ACB storage if needed later)
- **-141 lines** of file storage (replaced by ACB memory cache)

### Features Gained

- ✅ Connection pooling (automatic with ACB Redis)
- ✅ SSL/TLS support (via ACB configuration)
- ✅ Health checks (built into ACB adapters)
- ✅ Automatic reconnection (ACB handles this)
- ✅ Namespace support (multi-tenant isolation)
- ✅ MsgPack + Brotli compression (efficient storage)

### Maintainability

- ✅ Battle-tested ACB adapters (used in production)
- ✅ Single source of truth for cache configuration
- ✅ Easier to add new cache backends (ACB does the work)
- ✅ Consistent error handling and logging

______________________________________________________________________

## Success Criteria

1. ✅ All existing serverless_mode tests pass with ACB adapter
1. ✅ New tests cover ACB cache integration
1. ✅ Performance equal or better than custom backends
1. ✅ Documentation updated with ACB examples
1. ✅ Zero regressions in serverless functionality

______________________________________________________________________

**Status:** Ready to implement
**Next Step:** Create `ACBCacheStorage` adapter class
**Estimated Time:** 2-3 hours for complete Phase 1-3

______________________________________________________________________

**Created:** 2025-10-28
**Author:** Claude Code + Les
**Project:** session-buddy
**Phase:** Week 5 Day 3 - Serverless Mode Refactoring
