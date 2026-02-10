# Akosha Cloud Sync - User Guide

Complete guide for configuring and using Session-Buddy's Akosha cloud synchronization feature.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)

______________________________________________________________________

## Overview

Akosha sync automatically uploads your Session-Buddy memories to cloud storage or HTTP endpoints, providing:

- **Automatic Backup**: Memories uploaded on session end
- **Cloud Storage**: Fast, reliable uploads to S3/R2
- **HTTP Fallback**: Direct upload when cloud unavailable
- **Compression**: 65% size reduction with gzip
- **Deduplication**: Skips unchanged uploads

### Sync Methods

1. **Cloud Sync** (Primary)

   - Uploads to S3-compatible storage (Cloudflare R2, AWS S3, MinIO)
   - Fast, reliable, scalable
   - Recommended for production

1. **HTTP Sync** (Fallback)

   - Direct POST to Akosha server
   - For development/testing
   - Requires Akosha running locally

______________________________________________________________________

## Quick Start

### 1. Install Dependencies

```bash
# Install Session-Buddy with Oneiric support
uv sync --group dev

# Verify Oneiric installation
python -c "from oneiric.adapters.storage.s3 import S3StorageAdapter; print('✅ Oneiric installed')"
```

### 2. Configure Cloud Storage

Edit `~/.claude/settings/session-buddy.yaml`:

```yaml
# Cloud Storage Configuration
akosha_cloud_bucket: "session-buddy-memories"  # Your bucket name
akosha_cloud_endpoint: "https://<account>.r2.cloudflarestorage.com"
akosha_cloud_region: "auto"
akosha_system_id: "macbook-pro-username"  # Optional (defaults to hostname)

# Behavior
akosha_upload_on_session_end: true  # Auto-upload on session end
akosha_enable_fallback: true  # Allow cloud → HTTP fallback
akosha_force_method: "auto"  # auto, cloud, or http

# Performance
akosha_upload_timeout_seconds: 300  # 5 minutes
akosha_max_retries: 3
akosha_retry_backoff_seconds: 2.0

# Features
akosha_enable_compression: true  # Gzip compression (65% reduction)
akosha_enable_deduplication: true  # Skip unchanged uploads
akosha_chunk_size_mb: 5  # Upload chunk size
```

### 3. Verify Configuration

```bash
# Check Akosha sync status
python -c "
from session_buddy.mcp.tools.memory.akosha_tools import akosha_sync_status
result = await akosha_sync_status()
print(result)
"
```

Expected output:

```json
{
  "cloud_configured": true,
  "system_id": "macbook-pro-username",
  "should_use_cloud": true,
  "should_use_http": true,
  "force_method": "auto",
  "enable_fallback": true,
  "upload_on_session_end": true,
  "configuration": {
    "cloud_bucket": "session-buddy-memories",
    ...
  }
}
```

### 4. Test Manual Sync

```bash
# Trigger manual sync
python -c "
from session_buddy.mcp.tools.memory.akosha_tools import sync_to_akosha
result = await sync_to_akosha(method='auto')
print(result)
"
```

______________________________________________________________________

## Configuration

### Environment Variables

You can also configure via environment variables (highest priority):

```bash
export SESSION_BUDDY_AKOSHA_CLOUD_BUCKET="session-buddy-memories"
export SESSION_BUDDY_AKOSHA_CLOUD_ENDPOINT="https://<account>.r2.cloudflarestorage.com"
export SESSION_BUDDY_AKOSHA_SYSTEM_ID="macbook-pro-username"
```

### Configuration Priority

Settings are loaded in this order (highest to lowest):

1. Environment variables (`SESSION_BUDDY_AKOSHA_*`)
1. `settings/local.yaml` (local overrides, gitignored)
1. `settings/session-buddy.yaml` (base configuration)
1. Default values

### Field Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `akosha_cloud_bucket` | string | `""` | S3/R2 bucket name (empty = disabled) |
| `akosha_cloud_endpoint` | string | `""` | S3/R2 endpoint URL |
| `akosha_cloud_region` | string | `"auto"` | Storage region |
| `akosha_system_id` | string | `""` | System identifier (hostname if empty) |
| `akosha_upload_on_session_end` | bool | `true` | Auto-upload on session end |
| `akosha_enable_fallback` | bool | `true` | Allow cloud → HTTP fallback |
| `akosha_force_method` | string | `"auto"` | Force method: auto/cloud/http |
| `akosha_upload_timeout_seconds` | int | `300` | Upload timeout (seconds) |
| `akosha_max_retries` | int | `3` | Maximum retry attempts |
| `akosha_retry_backoff_seconds` | float | `2.0` | Base delay for exponential backoff |
| `akosha_enable_compression` | bool | `true` | Gzip compression (65% reduction) |
| `akosha_enable_deduplication` | bool | `true` | Skip unchanged uploads |
| `akosha_chunk_size_mb` | int | `5` | Upload chunk size (MB) |

______________________________________________________________________

## Usage

### Automatic Upload

When `akosha_upload_on_session_end: true`, memories upload automatically on session end:

```
Session ends
    ↓
Cleanup completes
    ↓
Background upload starts (non-blocking)
    ↓
✅ Upload completes in background
```

**Note**: Session end completes immediately; upload continues in background.

### Manual Upload

Trigger upload manually using MCP tool:

```python
# Via Claude Code
await sync_to_akosha()

# Force specific method
await sync_to_akosha(method="cloud")  # Cloud only
await sync_to_akosha(method="http")   # HTTP only
```

### Check Sync Status

```python
await akosha_sync_status()
```

Returns:

```json
{
  "cloud_configured": true,
  "system_id": "macbook-pro-les",
  "should_use_cloud": true,
  "should_use_http": true,
  "force_method": "auto",
  "enable_fallback": true,
  "upload_on_session_end": true,
  "configuration": { ... }
}
```

______________________________________________________________________

## Troubleshooting

### Issue: "Oneiric S3 adapter not available"

**Solution**: Install Oneiric package

```bash
uv pip install oneiric
```

### Issue: "Cloud sync failed: Authentication failed"

**Solution**: Verify credentials

```bash
# For AWS S3
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"

# For Cloudflare R2
export AWS_ACCESS_KEY_ID="your-r2-access-key"
export AWS_SECRET_ACCESS_KEY="your-r2-secret-key"
```

### Issue: "Akosha HTTP endpoint unreachable"

**Solution**: Start Akosha server

```bash
cd /path/to/akosha
python -m akosha.mcp.server
```

Verify Akosha is running:

```bash
curl http://localhost:8682/status
```

### Issue: "Upload timed out"

**Solution**: Increase timeout

```yaml
akosha_upload_timeout_seconds: 600  # 10 minutes
```

### Issue: "Slow uploads"

**Solution**: Enable compression and increase chunk size

```yaml
akosha_enable_compression: true
akosha_chunk_size_mb: 10  # Larger chunks = faster
```

### Issue: "Circular import error"

**Solution**: Ensure no circular imports in custom code

The Akosha sync modules use lazy imports to avoid circular dependencies. If you're extending the sync system, use the same pattern:

```python
# ❌ Wrong: Causes circular import
from session_buddy.mcp.server import mcp

# ✅ Correct: Lazy import
def register_tools(mcp_instance):
    mcp_instance.tool()(my_tool)
```

______________________________________________________________________

## Advanced Configuration

### Cloudflare R2 Setup

1. **Create R2 Bucket**:

   ```bash
   # Via wrangler CLI
   wrangler r2 bucket create session-buddy-memories
   ```

1. **Get API Token**:

   - Go to Cloudflare Dashboard → R2 → Overview → Manage R2 API Tokens
   - Create token with `Edit` permissions

1. **Configure Session-Buddy**:

   ```yaml
   akosha_cloud_bucket: "session-buddy-memories"
   akosha_cloud_endpoint: "https://<account-id>.r2.cloudflarestorage.com"
   ```

1. **Set Credentials**:

   ```bash
   export AWS_ACCESS_KEY_ID="your-r2-token-id"
   export AWS_SECRET_ACCESS_KEY="your-r2-token-secret"
   ```

### AWS S3 Setup

1. **Create S3 Bucket**:

   ```bash
   aws s3 mb s3://session-buddy-memories --region us-east-1
   ```

1. **Create IAM User**:

   - Policy: `AmazonS3FullAccess` (or scoped to specific bucket)
   - Generate access keys

1. **Configure Session-Buddy**:

   ```yaml
   akosha_cloud_bucket: "session-buddy-memories"
   akosha_cloud_endpoint: "https://s3.us-east-1.amazonaws.com"
   akosha_cloud_region: "us-east-1"
   ```

### MinIO Setup (Local Development)

1. **Start MinIO**:

   ```bash
   docker run -p 9000:9000 -p 9001:9001 \
     -e "MINIO_ROOT_USER=minioadmin" \
     -e "MINIO_ROOT_PASSWORD=minioadmin" \
     minio/minio server /data --console-address ":9001"
   ```

1. **Create Bucket**:

   ```bash
   mc alias set local http://localhost:9000 minioadmin minioadmin
   mc mb local/session-buddy-memories
   ```

1. **Configure Session-Buddy**:

   ```yaml
   akosha_cloud_bucket: "session-buddy-memories"
   akosha_cloud_endpoint: "http://localhost:9000"
   ```

### Development Mode (HTTP Only)

For development without cloud storage:

```yaml
akosha_cloud_bucket: ""  # Empty to disable cloud
akosha_enable_fallback: true  # Allow HTTP fallback
akosha_force_method: "auto"  # Will use HTTP
```

Or force HTTP explicitly:

```yaml
akosha_force_method: "http"
```

______________________________________________________________________

## Performance Tuning

### Upload Speed

**Faster Uploads** (larger chunks, compression):

```yaml
akosha_chunk_size_mb: 10  # 10MB chunks (fewer requests)
akosha_enable_compression: true  # 65% less data to transfer
```

**Slower but More Reliable** (smaller chunks):

```yaml
akosha_chunk_size_mb: 1  # 1MB chunks (more progress tracking)
```

### Retry Behavior

**Aggressive Retries** (slow connections):

```yaml
akosha_max_retries: 5
akosha_retry_backoff_seconds: 1.0
```

**Conservative Retries** (fast connections):

```yaml
akosha_max_retries: 2
akosha_retry_backoff_seconds: 3.0
```

### Memory Usage

**Low Memory** (smaller chunks):

```yaml
akosha_chunk_size_mb: 1  # ~1MB per chunk in memory
```

**Higher Throughput** (larger chunks):

```yaml
akosha_chunk_size_mb: 10  # ~10MB per chunk in memory
```

______________________________________________________________________

## Security Best Practices

### Credentials

1. **Never commit credentials** to git
1. **Use environment variables** for sensitive data
1. **Restrict bucket access** to specific IAM users
1. **Enable bucket encryption** (SSE-S3 or SSE-KMS)
1. **Use HTTPS endpoints** only

### IAM Policy Example

Minimal policy for Session-Buddy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::session-buddy-memories",
        "arn:aws:s3:::session-buddy-memories/*"
      ]
    }
  ]
}
```

______________________________________________________________________

## Monitoring and Logging

### Enable Debug Logging

```yaml
# In settings/session-buddy.yaml
enable_debug_mode: true
log_level: "DEBUG"
```

### Sync Logs

Logs include:

- Upload progress (files, bytes, duration)
- Retry attempts and backoff delays
- Fallback from cloud to HTTP
- Error details and stack traces

View logs:

```bash
tail -f ~/.claude/logs/session-buddy.log | grep -i akosha
```

______________________________________________________________________

## API Reference

### MCP Tools

#### `sync_to_akosha()`

Manually trigger memory synchronization.

```python
await sync_to_akosha(
    method: Literal["auto", "cloud", "http"] = "auto",
    enable_fallback: bool = True,
) -> dict[str, Any]
```

**Returns**:

```json
{
  "method": "cloud",
  "success": true,
  "files_uploaded": ["systems/mac/uploads/123/reflection.duckdb"],
  "bytes_transferred": 42000000,
  "duration_seconds": 45.2,
  "upload_id": "20250208_143052_mac",
  "error": null
}
```

#### `akosha_sync_status()`

Get current configuration and status.

```python
await akosha_sync_status() -> dict[str, Any]
```

**Returns**:

```json
{
  "cloud_configured": true,
  "system_id": "macbook-pro-les",
  "should_use_cloud": true,
  "should_use_http": true,
  "force_method": "auto",
  "enable_fallback": true,
  "upload_on_session_end": true,
  "configuration": { ... }
}
```

______________________________________________________________________

## Next Steps

- **Testing**: Run integration tests to verify setup
- **Monitoring**: Configure Prometheus metrics for sync performance
- **Automation**: Set up lifecycle policies for old uploads
- **Documentation**: Document your specific setup for team

For technical details, see [API Reference](API_REFERENCE.md) or [Developer Guide](DEVELOPER.md).
