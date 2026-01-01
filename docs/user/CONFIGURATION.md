# Session Buddy - Configuration Reference

Complete configuration guide for the Session Management MCP server with advanced setup options.

## Overview

The Session Management MCP server is designed to work with minimal configuration, but provides extensive customization options for advanced users and enterprise deployments.

## Configuration Files

### Primary Configuration

#### `.mcp.json` - MCP Server Configuration

Location: Project root or `~/.config/claude/` directory

#### `settings/session-buddy.yaml` - Base Settings

Committed defaults live in `settings/session-buddy.yaml`. Create `settings/local.yaml` for machine-specific overrides (gitignored). Environment variables use the `SESSION_BUDDY_` prefix and map to fields in `session_buddy/settings.py`.

```json
{
  "mcpServers": {
    "session-buddy": {
      "command": "python",
      "args": ["-m", "session_buddy.server"],
      "cwd": "/absolute/path/to/session-buddy",
      "env": {
        "PYTHONPATH": "/absolute/path/to/session-buddy",
        "SESSION_BUDDY_LOG_LEVEL": "INFO",
        "SESSION_BUDDY_DATA_DIR": "/custom/data/path",
        "SESSION_BUDDY_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
        "SESSION_BUDDY_EMBEDDING_CACHE_SIZE": "1000"
      }
    }
  }
}
```

#### Alternative: uvx Installation

```json
{
  "mcpServers": {
    "session-buddy": {
      "command": "uvx",
      "args": ["session-buddy"],
      "env": {
        "SESSION_BUDDY_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

## Environment Variables

### Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_BUDDY_DATA_DIR` | `~/.claude/data/` | Directory for database storage |
| `SESSION_BUDDY_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `SESSION_BUDDY_LOG_DIR` | `~/.claude/logs/` | Directory for log files |

### Memory System Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_BUDDY_ENABLE_SEMANTIC_SEARCH` | `true` | Toggle semantic search with embeddings |
| `SESSION_BUDDY_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | ONNX model for embeddings |
| `SESSION_BUDDY_EMBEDDING_CACHE_SIZE` | `1000` | Number of cached embeddings |

### Performance Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_BUDDY_DATABASE_CONNECTION_TIMEOUT` | `30` | Database connection timeout (seconds) |
| `SESSION_BUDDY_DATABASE_QUERY_TIMEOUT` | `120` | Database query timeout (seconds) |
| `SESSION_BUDDY_MAX_SEARCH_RESULTS` | `100` | Maximum search results per query |
| `SESSION_BUDDY_DEFAULT_MAX_TOKENS` | `4000` | Default max tokens for responses |
| `SESSION_BUDDY_DEFAULT_CHUNK_SIZE` | `2000` | Chunk size for response splitting |

### Security Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_BUDDY_ENABLE_PERMISSION_SYSTEM` | `true` | Toggle permission system |
| `SESSION_BUDDY_DEFAULT_TRUSTED_OPERATIONS` | `["git_commit", "uv_sync", "file_operations"]` | JSON array of trusted operations |
| `SESSION_BUDDY_ENABLE_RATE_LIMITING` | `true` | Toggle rate limiting |
| `SESSION_BUDDY_MAX_REQUESTS_PER_MINUTE` | `100` | Requests per minute limit |
| `SESSION_BUDDY_MAX_QUERY_LENGTH` | `10000` | Maximum search query length |
| `SESSION_BUDDY_MAX_CONTENT_LENGTH` | `1000000` | Maximum content size in bytes |

## Advanced Configuration

### Custom Data Directory Structure

```bash
# Custom data directory setup
export SESSION_BUDDY_DATA_DIR="/opt/session-buddy/data"
mkdir -p "$SESSION_BUDDY_DATA_DIR"/{db,cache,temp}
chmod 750 "$SESSION_BUDDY_DATA_DIR"
```

### Embedding Model Configuration

Use `SESSION_BUDDY_EMBEDDING_MODEL` to switch models and `SESSION_BUDDY_ENABLE_SEMANTIC_SEARCH` to disable embeddings entirely.

## Production Configuration

### Docker Deployment

```dockerfile
FROM python:3.13-slim

ENV SESSION_BUDDY_DATA_DIR=/data/session-buddy
ENV SESSION_BUDDY_LOG_LEVEL=INFO
ENV SESSION_BUDDY_EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV SESSION_BUDDY_EMBEDDING_CACHE_SIZE=1000

VOLUME ["/data/session-buddy"]

COPY . /app
WORKDIR /app
RUN uv sync

ENTRYPOINT ["python", "-m", "session_buddy.server"]
```

### Kubernetes Configuration

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: session-buddy-config
data:
  SESSION_BUDDY_LOG_LEVEL: "INFO"
  SESSION_BUDDY_EMBEDDING_MODEL: "all-MiniLM-L6-v2"
  SESSION_BUDDY_EMBEDDING_CACHE_SIZE: "1000"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: session-buddy
spec:
  replicas: 2
  selector:
    matchLabels:
      app: session-buddy
  template:
    spec:
      containers:
      - name: session-buddy
        image: session-buddy:latest
        envFrom:
        - configMapRef:
            name: session-buddy-config
        volumeMounts:
        - name: data-volume
          mountPath: /data/session-buddy
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
```

### Load Balancing Configuration

```nginx
upstream session_buddy_backend {
    server localhost:8000;
    server localhost:8001;
    server localhost:8002;
}

server {
    listen 80;
    server_name session-buddy.example.com;

    location / {
        proxy_pass http://session_buddy_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Multi-Environment Setup

### Development Environment

```bash
# .env.development
SESSION_BUDDY_LOG_LEVEL=DEBUG
SESSION_BUDDY_EMBEDDING_CACHE_SIZE=100
SESSION_BUDDY_ENABLE_RATE_LIMITING=false
```

### Staging Environment

```bash
# .env.staging
SESSION_BUDDY_LOG_LEVEL=INFO
SESSION_BUDDY_EMBEDDING_CACHE_SIZE=500
SESSION_BUDDY_DEFAULT_TRUSTED_OPERATIONS='["uv_sync", "git_commit"]'
```

### Production Environment

```bash
# .env.production
SESSION_BUDDY_LOG_LEVEL=WARNING
SESSION_BUDDY_EMBEDDING_CACHE_SIZE=2000
SESSION_BUDDY_MAX_REQUESTS_PER_MINUTE=50
```

## Troubleshooting Configuration

### Debug Mode

```bash
# Enable comprehensive debugging
export SESSION_BUDDY_LOG_LEVEL=DEBUG
export SESSION_BUDDY_ENABLE_DEBUG_MODE=true
python -m session_buddy.server --debug
```

### Data Import/Export

```json
{
  "migration": {
    "import_format": "json",
    "export_format": "json",
    "batch_size": 1000,
    "validate_imports": true
  }
}
```

## Configuration Validation

### Validation Script

```text
#!/usr/bin/env python3
"""Validate Session Management MCP configuration."""

import json
import os
from pathlib import Path


def validate_config():
    """Validate all configuration settings."""

    # Check required paths
    data_dir = Path(os.getenv("SESSION_BUDDY_DATA_DIR", "~/.claude/data")).expanduser()
    assert data_dir.exists(), f"Data directory missing: {data_dir}"

    # Check MCP configuration
    mcp_config_path = Path(".mcp.json")
    if mcp_config_path.exists():
        with open(mcp_config_path) as f:
            config = json.load(f)

        assert "session-buddy" in config.get("mcpServers", {}), (
            "session-buddy server not configured"
        )

    # Check embedding model availability
    try:
        import onnxruntime
        import transformers

        print("✅ Embedding dependencies available")
    except ImportError:
        print("⚠️ Embedding dependencies missing - text search fallback will be used")

    print("✅ Configuration validation passed")


if __name__ == "__main__":
    validate_config()
```

## Best Practices

### Configuration Management

1. **Use Environment Variables**: Keep sensitive data out of config files
1. **Version Control**: Track configuration changes in git
1. **Environment-Specific**: Use different configs for dev/staging/prod
1. **Documentation**: Document all custom configuration changes
1. **Validation**: Test configuration changes in staging first

### Security Best Practices

1. **Encrypt Sensitive Data**: Use tools like sops or Vault
1. **Rotate Keys**: Regular API key and certificate rotation
1. **Principle of Least Privilege**: Minimal permissions by default
1. **Audit Logs**: Enable comprehensive logging for security events
1. **Network Security**: Use firewalls and VPNs for production

### Performance Optimization

1. **Resource Limits**: Set appropriate memory and CPU limits
1. **Connection Pooling**: Configure database connection pooling
1. **Caching**: Enable embedding caching for better performance
1. **Monitoring**: Track performance metrics and set alerts
1. **Scaling**: Plan for horizontal scaling in high-load scenarios

______________________________________________________________________

**Next Steps**: See [ARCHITECTURE.md](../developer/ARCHITECTURE.md) for detailed system architecture and [DEPLOYMENT.md](DEPLOYMENT.md) for deployment strategies.
