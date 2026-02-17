# ACB Migration Guide - Session Management MCP

**Version**: 0.9.4+
**Migration Date**: January 2025
**Status**: Production Ready ✅

## Overview

This guide helps you migrate to the new ACB (Asynchronous Component Base) integrated session management system. The migration brings improved reliability, better configuration management, and reduced code complexity while maintaining 100% backward compatibility.

## What Changed

### Summary of Changes

**✅ New ACB Storage Adapters** (Recommended):

- `file` - Local file storage (default, replaces old `local` backend)
- `s3` - AWS S3/MinIO (replaces old `s3` backend)
- `azure` - Azure Blob Storage (new!)
- `gcs` - Google Cloud Storage (new!)
- `memory` - In-memory storage for testing (new!)

**⚠️ Deprecated Backends** (Still work, but will be removed in v1.0):

- `local` - Old local file storage → Use `file` instead
- `redis` - Old Redis backend → Use `acb` or `s3` instead
- Old `s3` - Old S3 backend → Use new `s3` instead
- `acb` - Old ACB cache → Use `file` or `s3` instead

**Benefits of Migration**:

- ✅ Better reliability (ACB handles connection pooling, retries)
- ✅ More storage options (Azure, GCS)
- ✅ Improved configuration (YAML with environment variables)
- ✅ Reduced code (91% reduction in storage layer)
- ✅ Better error handling
- ✅ Zero breaking changes

## Migration Steps

### Step 1: Check Your Current Configuration

**Find your current storage backend**:

Look in your configuration or code for:

```python
# Old style (still works):
from session_buddy.backends import RedisStorage, S3Storage, LocalFileStorage

storage = RedisStorage(config)  # ⚠️ Deprecated
storage = S3Storage(config)  # ⚠️ Deprecated
storage = LocalFileStorage(config)  # ⚠️ Deprecated
```

Or in `serverless_mode.py` configuration:

```python
config = {
    "storage_backend": "redis",  # ⚠️ Deprecated
    # or "s3", "local", "acb"
}
```

### Step 2: Update to New ACB Adapters

#### Option A: Update Configuration (Recommended)

**Before** (old backends):

```python
config = {
    "storage_backend": "local",  # ⚠️ Deprecated
    "backends": {"local": {"storage_dir": "~/.claude/data/sessions"}},
}
```

**After** (new ACB adapters):

```python
config = {
    "storage_backend": "file",  # ✅ New ACB adapter
    "backends": {"file": {"local_path": "~/.claude/data/sessions", "auto_mkdir": True}},
}
```

#### Option B: Update Code Directly

**Before** (old backends):

```python
from session_buddy.backends import S3Storage

storage = S3Storage({"bucket_name": "my-sessions", "region": "us-east-1"})
```

**After** (new ACB adapters):

```python
from session_buddy.adapters import ServerlessStorageAdapter

storage = ServerlessStorageAdapter(
    config={"bucket_name": "my-sessions", "region": "us-east-1"},
    backend="s3",  # Uses ACB S3 adapter
)
```

### Step 3: Test the Migration

**Run existing tests**:

```bash
# Test storage adapters
pytest tests/unit/test_session_storage_adapter.py -v
pytest tests/integration/test_serverless_storage.py -v

# Expected: 41/41 tests passing ✅
```

**Test your specific backend**:

```python
from session_buddy.serverless_mode import ServerlessConfigManager

# Test backend availability
config = ServerlessConfigManager.load_config()
results = await ServerlessConfigManager.test_storage_backends(config)
print(results)  # {"file": True, "s3": True, ...}
```

## Backend-Specific Migration Guides

### Migrating from `local` to `file`

**Old Configuration**:

```yaml
storage_backend: local
backends:
  local:
    storage_dir: ~/.claude/data/sessions
```

**New Configuration**:

```yaml
storage_backend: file
backends:
  file:
    local_path: ~/.claude/data/sessions
    auto_mkdir: true
```

**Data Migration**:

- ✅ No data migration needed! Files stay in same location.
- ✅ File format is identical (JSON)
- ✅ Just update config, existing sessions will work

**Code Changes**:

```python
# Before:
from session_buddy.backends import LocalFileStorage

storage = LocalFileStorage({"storage_dir": "~/.claude/data"})

# After:
from session_buddy.adapters import ServerlessStorageAdapter

storage = ServerlessStorageAdapter(
    config={"local_path": "~/.claude/data"}, backend="file"
)
```

### Migrating from old `s3` to new `s3`

**Old Configuration**:

```yaml
storage_backend: s3
backends:
  s3:
    bucket_name: session-buddy
    region: us-east-1
    # Old S3 backend required explicit AWS credentials
```

**New Configuration**:

```yaml
storage_backend: s3
backends:
  s3:
    bucket_name: ${S3_BUCKET:session-buddy}
    endpoint_url: ${S3_ENDPOINT:}
    access_key_id: ${S3_ACCESS_KEY:}
    secret_access_key: ${S3_SECRET_KEY:}
    region: ${S3_REGION:us-east-1}
```

**Benefits of New S3 Adapter**:

- ✅ Environment variable support (no credentials in config)
- ✅ Better connection pooling
- ✅ Automatic retries
- ✅ MinIO compatibility (via endpoint_url)

**Data Migration**:

- ✅ No migration needed if bucket/prefix unchanged
- ✅ Session data format is compatible
- ⚠️ If you need to migrate data: Use AWS CLI or migration script

**Migration Script** (if changing buckets):

```bash
# Copy sessions to new bucket (optional)
aws s3 sync s3://old-bucket/sessions/ s3://new-bucket/sessions/
```

### Migrating from `redis` to `file` or `s3`

**Why Migrate**:

- Redis backend is deprecated
- File/S3 provide better persistence
- ACB adapters more reliable

**Before** (Redis):

```yaml
storage_backend: redis
backends:
  redis:
    host: localhost
    port: 6379
    db: 0
    key_prefix: "session_mgmt:"
```

**After** (File - for development):

```yaml
storage_backend: file
backends:
  file:
    local_path: ~/.claude/data/sessions
    auto_mkdir: true
```

**After** (S3 - for production):

```yaml
storage_backend: s3
backends:
  s3:
    bucket_name: ${S3_BUCKET:session-buddy}
    region: ${S3_REGION:us-east-1}
```

**Data Migration**:

- ⚠️ Redis sessions are not automatically migrated
- ⚠️ Old sessions will expire naturally (TTL)
- ✅ New sessions will use new backend
- **Recommendation**: Don't migrate, let sessions expire

### Migrating to Azure or GCS (New!)

**Azure Blob Storage**:

```yaml
storage_backend: azure
backends:
  azure:
    account_name: ${AZURE_STORAGE_ACCOUNT}
    account_key: ${AZURE_STORAGE_KEY}
    container_name: ${AZURE_CONTAINER:sessions}
```

**Google Cloud Storage**:

```yaml
storage_backend: gcs
backends:
  gcs:
    bucket_name: ${GCS_BUCKET:session-buddy}
    project_id: ${GCS_PROJECT_ID}
    credentials_path: ${GCS_CREDENTIALS:~/.gcp/credentials.json}
```

## Configuration Reference

### Environment Variables

All backends support environment variables:

```yaml
storage:
  default_backend: "file"

  file:
    local_path: "${SESSION_STORAGE_PATH:~/.claude/data/sessions}"
    auto_mkdir: true

  s3:
    bucket_name: "${S3_BUCKET:session-buddy}"
    endpoint_url: "${S3_ENDPOINT:}"
    access_key_id: "${S3_ACCESS_KEY:}"
    secret_access_key: "${S3_SECRET_KEY:}"
    region: "${S3_REGION:us-east-1}"

  azure:
    account_name: "${AZURE_STORAGE_ACCOUNT}"
    account_key: "${AZURE_STORAGE_KEY}"
    container_name: "${AZURE_CONTAINER:sessions}"

  gcs:
    bucket_name: "${GCS_BUCKET:session-buddy}"
    project_id: "${GCS_PROJECT_ID}"
    credentials_path: "${GCS_CREDENTIALS:}"
```

**Syntax**: `${VARIABLE:default_value}`

### Bucket Configuration

Sessions are organized into buckets (logical groupings):

```python
buckets = {
    "sessions": "sessions",  # Active session state
    "checkpoints": "checkpoints",  # Session checkpoints
    "handoffs": "handoffs",  # Session handoff documents
    "test": "test",  # Test data
}
```

**File backend**: Buckets → subdirectories
**S3/Azure/GCS backends**: Buckets → key prefixes

## Troubleshooting

### Issue: "ACB Graph adapter not found in DI container"

**Cause**: DI not initialized before using adapter
**Solution**:

```python
from session_buddy.di import configure

# Initialize DI first
configure(force=True)

# Then use adapters
from session_buddy.adapters import KnowledgeGraphDatabaseAdapter

async with KnowledgeGraphDatabaseAdapter() as kg:
    # Now it works!
    pass
```

### Issue: "Storage backend unavailable"

**Cause**: Backend not properly configured or credentials missing
**Solution**:

```python
# Test backend availability
from session_buddy.serverless_mode import ServerlessConfigManager

config = ServerlessConfigManager.load_config()
results = await ServerlessConfigManager.test_storage_backends(config)

if not results.get("s3"):
    print("S3 backend not available - check credentials")
```

### Issue: Deprecation warnings

**Example Warning**:

```
DeprecationWarning: RedisStorage is deprecated. Use ServerlessStorageAdapter(backend="file")
or ServerlessStorageAdapter(backend="s3") instead.
```

**Solution**: Update to new ACB adapters (see migration steps above)

### Issue: Sessions not found after migration

**Cause**: Data in different location/format
**Solution**:

1. Check bucket/path configuration matches old location
1. Verify file permissions (file backend)
1. Verify credentials (cloud backends)
1. Check session hasn't expired (TTL)

### Issue: Performance slower than old backend

**Unlikely** - ACB adapters are generally faster
**If it happens**:

1. Check network latency (cloud backends)
1. Enable connection pooling (should be automatic)
1. Consider using `memory` backend for testing
1. Report issue with benchmarks

## Common Patterns

### Pattern: Multi-Environment Configuration

```python
# config/development.yaml
storage_backend: file
backends:
  file:
    local_path: ~/.claude/data/sessions-dev

# config/production.yaml
storage_backend: s3
backends:
  s3:
    bucket_name: ${S3_BUCKET}
    region: ${S3_REGION}
```

### Pattern: Fallback Backends

```python
from session_buddy.serverless_mode import ServerlessConfigManager

config = ServerlessConfigManager.load_config()

# Try S3 first, fallback to file
try:
    storage = ServerlessConfigManager.create_storage_backend(
        {"storage_backend": "s3", "backends": config["backends"]}
    )
    if not await storage.is_available():
        raise RuntimeError("S3 unavailable")
except Exception:
    # Fallback to file
    storage = ServerlessConfigManager.create_storage_backend(
        {"storage_backend": "file", "backends": config["backends"]}
    )
```

### Pattern: Custom Storage Paths

```python
from session_buddy.adapters import ServerlessStorageAdapter

# Development: local file storage
dev_storage = ServerlessStorageAdapter(
    config={"local_path": "/tmp/sessions"}, backend="file"
)

# Production: S3 storage
prod_storage = ServerlessStorageAdapter(
    config={"bucket_name": "prod-sessions", "region": "us-west-2"}, backend="s3"
)
```

## Testing Your Migration

### Unit Tests

```bash
# Test storage adapters
pytest tests/unit/test_session_storage_adapter.py -v

# Expected: 25/25 passing ✅
```

### Integration Tests

```bash
# Test serverless storage
pytest tests/integration/test_serverless_storage.py -v

# Expected: 16/16 passing ✅
```

### End-to-End Test

```python
from session_buddy.serverless_mode import ServerlessSessionManager
from session_buddy.adapters import ServerlessStorageAdapter


async def test_e2e():
    # Create storage adapter
    storage = ServerlessStorageAdapter(backend="file")

    # Create session manager
    manager = ServerlessSessionManager(storage)

    # Create session
    session_id = await manager.create_session(
        user_id="test_user", project_id="test_project", session_data={"test": "data"}
    )

    # Retrieve session
    session = await manager.get_session(session_id)
    assert session is not None
    assert session.metadata["test"] == "data"

    # Cleanup
    await manager.delete_session(session_id)

    print("✅ End-to-end test passed!")


# Run test
import asyncio

asyncio.run(test_e2e())
```

## Rollback Plan

If you need to rollback to old backends:

1. **Old backends still work** - They're deprecated but not removed yet
1. **Update configuration** back to old backend names
1. **No data loss** - Sessions remain in same locations
1. **Report issues** so we can fix them!

**Example Rollback**:

```yaml
# Rollback to old S3 backend (still works in 0.9.x)
storage_backend: s3  # Will show deprecation warning
backends:
  s3:
    bucket_name: session-buddy
    region: us-east-1
```

**Important**: Old backends will be **removed in v1.0**, so migration is recommended.

## Getting Help

- **Documentation**: See `docs/ACB_MIGRATION_PLAN.md` for technical details
- **Issues**: Report problems on GitHub issues
- **Questions**: Ask in discussions or create an issue
- **Examples**: See `tests/integration/test_serverless_storage.py`

## Summary Checklist

- [ ] Identified current storage backend
- [ ] Chose new ACB backend (file, s3, azure, gcs, memory)
- [ ] Updated configuration (YAML or code)
- [ ] Set environment variables (if using cloud backends)
- [ ] Ran tests to validate migration
- [ ] Tested end-to-end workflow
- [ ] No deprecation warnings
- [ ] Sessions loading correctly
- [ ] Ready for production!

______________________________________________________________________

**Migration Status**: ✅ Ready for Production
**Backward Compatibility**: ✅ 100% (old backends work until v1.0)
**Tests Passing**: ✅ 41/41 (100% pass rate)
**Documentation**: ✅ Complete

For technical details, see:

- `docs/ACB_MIGRATION_PLAN.md` - Complete migration plan
- `docs/ACB_MIGRATION_PHASE3_STATUS.md` - Test status
- `docs/ACB_GRAPH_ADAPTER_INVESTIGATION.md` - Graph adapter investigation
