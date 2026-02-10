# Session-Buddy Operational Modes Guide

## Overview

Session-Buddy supports two operational modes to accommodate different use cases:

- **Lite Mode**: Zero-dependency, in-memory mode for testing and CI/CD
- **Standard Mode**: Full-featured production mode with persistent storage

## Quick Start

### Lite Mode (Fastest Startup)

```bash
# Using CLI parameter
session-buddy --mode=lite start

# Using environment variable
SESSION_BUDDY_MODE=lite session-buddy start

# Using startup script
./scripts/dev-start.sh lite
```

**Characteristics:**

- ⚡ In-memory database (`:memory:`)
- 📦 No external dependencies
- ⏱️ Fast startup (< 2 seconds)
- ⚠️ No data persistence

### Standard Mode (Default)

```bash
# Default mode
session-buddy start

# Explicit standard mode
session-buddy --mode=standard start

# Using environment variable
SESSION_BUDDY_MODE=standard session-buddy start

# Using startup script
./scripts/dev-start.sh standard
```

**Characteristics:**

- 💾 Persistent database (`~/.claude/data/reflection.duckdb`)
- 📦 Full feature set
- 🧠 Semantic search enabled
- 🌐 Multi-project coordination

## Mode Comparison

| Feature | Lite Mode | Standard Mode |
|---------|-----------|---------------|
| **Setup Time** | < 2 min | ~ 5 min |
| **Services** | 1 (Session-Buddy) | 1 (Session-Buddy) |
| **Database** | `:memory:` (in-memory) | `~/.claude/data/reflection.duckdb` (file) |
| **Storage** | In-memory | File-based |
| **Persistence** | No (ephemeral) | Yes (persistent) |
| **Embeddings** | Disabled | Enabled (ONNX) |
| **Multi-Project** | Disabled | Enabled |
| **Token Optimization** | Disabled | Enabled |
| **Auto-Checkpoint** | Disabled | Enabled |
| **Faceted Search** | Disabled | Enabled |
| **Search Suggestions** | Disabled | Enabled |
| **Auto-Store** | Disabled | Enabled |
| **Crackerjack** | Disabled | Enabled |
| **Git Integration** | Disabled | Enabled |
| **Ideal For** | Testing, CI/CD | Development, Production |

## Use Cases

### Lite Mode

**Best for:**

- ✅ Quick testing and experimentation
- ✅ CI/CD pipelines
- ✅ Performance testing
- ✅ Temporary sessions
- ✅ Feature development without persistence

**Not recommended for:**

- ❌ Long-term development
- ❌ Production deployments
- ❌ Sessions requiring persistence
- ❌ Cross-project coordination

### Standard Mode

**Best for:**

- ✅ Daily development
- ✅ Production deployments
- ✅ Persistent data storage
- ✅ Cross-project coordination
- ✅ Semantic search
- ✅ Knowledge base building

**Not recommended for:**

- ❌ Quick testing (startup overhead)
- ❌ CI/CD (unnecessary persistence)

## Configuration Files

Mode-specific configuration files are located in `settings/`:

### Lite Mode Configuration

**File:** `settings/lite.yaml`

```yaml
mode: "lite"
database_path: ":memory:"
storage:
  default_backend: "memory"
enable_semantic_search: false
enable_multi_project: false
# ... minimal configuration
```

### Standard Mode Configuration

**File:** `settings/standard.yaml`

```yaml
mode: "standard"
database_path: "~/.claude/data/reflection.duckdb"
storage:
  default_backend: "file"
enable_semantic_search: true
enable_multi_project: true
# ... full configuration
```

### Base Configuration

**File:** `settings/session-buddy.yaml`

Contains default settings that apply to both modes. Mode-specific
settings override these defaults.

## Migration Guide

### From Lite to Standard

Lite mode data is ephemeral and cannot be migrated. However, you can
switch to standard mode at any time:

```bash
# Switch to standard mode
SESSION_BUDDY_MODE=standard session-buddy start

# Or using CLI
session-buddy --mode=standard start
```

All features will be enabled, and data will persist to disk.

### From Standard to Lite

**Warning:** Switching from standard to lite mode will result in data loss.
Standard mode data will not be available in lite mode.

```bash
# Switch to lite mode (ephemeral)
SESSION_BUDDY_MODE=lite session-buddy start

# Or using CLI
session-buddy --mode=lite start
```

### Exporting Data (Standard Mode)

Before switching to lite mode, you may want to export your data:

```bash
# Export reflections (example)
# TODO: Add export command

# Backup database
cp ~/.claude/data/reflection.duckdb ~/reflection_backup.duckdb
```

## Advanced Usage

### Programmatic Mode Selection

```python
from session_buddy.modes import get_mode, LiteMode, StandardMode

# Get mode from environment
mode = get_mode()  # Detects from SESSION_BUDDY_MODE

# Or specify explicitly
lite_mode = LiteMode()
standard_mode = StandardMode()

# Get configuration
config = lite_mode.get_config()
print(f"Database: {config.database_path}")
print(f"Storage: {config.storage_backend}")

# Validate environment
errors = standard_mode.validate_environment()
if errors:
    print(f"Validation errors: {errors}")

# Get startup message
message = lite_mode.get_startup_message()
print(message)
```

### Custom Mode Configuration

You can create custom mode configurations by extending the base classes:

```python
from session_buddy.modes.base import OperationMode, ModeConfig

class CustomMode(OperationMode):
    @property
    def name(self) -> str:
        return "custom"

    def get_config(self) -> ModeConfig:
        return ModeConfig(
            name="custom",
            database_path="~/.claude/data/custom.duckdb",
            storage_backend="file",
            enable_embeddings=True,
            enable_multi_project=False,
            # ... custom settings
        )
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SESSION_BUDDY_MODE` | Operational mode (lite, standard) | `standard` |
| `SESSION_BUDDY_DB_PATH` | Custom database path | (mode-dependent) |
| `SESSION_BUDDY_STORAGE_BACKEND` | Custom storage backend | (mode-dependent) |

## Troubleshooting

### Lite Mode Issues

**Problem:** Data not persisting across restarts

**Solution:** This is expected behavior in lite mode. Switch to standard
mode for persistent storage:

```bash
SESSION_BUDDY_MODE=standard session-buddy start
```

**Problem:** Semantic search not working

**Solution:** Lite mode disables embeddings for faster startup. Use
standard mode for semantic search:

```bash
SESSION_BUDDY_MODE=standard session-buddy start
```

### Standard Mode Issues

**Problem:** Slow startup time

**Solution:** Standard mode loads ONNX embeddings for semantic search.
This adds ~2-3 seconds to startup. Use lite mode if you don't need
semantic search:

```bash
SESSION_BUDDY_MODE=lite session-buddy start
```

**Problem:** Database connection errors

**Solution:** Ensure the data directory exists and is writable:

```bash
mkdir -p ~/.claude/data
chmod 755 ~/.claude/data
```

**Problem:** Permission errors

**Solution:** Check file permissions for the data directory:

```bash
ls -la ~/.claude/data
chmod 755 ~/.claude/data
```

### Mode Switching Issues

**Problem:** Mode not switching

**Solution:** Ensure the environment variable is set before starting:

```bash
export SESSION_BUDDY_MODE=lite
session-buddy start
```

Or use the CLI parameter:

```bash
session-buddy --mode=lite start
```

**Problem:** Configuration not loading

**Solution:** Check that mode-specific configuration files exist:

```bash
ls -la settings/lite.yaml
ls -la settings/standard.yaml
```

## Performance Comparison

### Startup Time

| Mode | Cold Start | Warm Start |
|------|------------|------------|
| Lite | ~1-2 seconds | ~0.5 seconds |
| Standard | ~3-5 seconds | ~1-2 seconds |

### Memory Usage

| Mode | Base Memory | With Embeddings |
|------|-------------|-----------------|
| Lite | ~50 MB | N/A |
| Standard | ~50 MB | ~200 MB |

### Database Size

| Mode | Initial Size | After 100 Sessions |
|------|--------------|---------------------|
| Lite | 0 MB | 0 MB (in-memory) |
| Standard | ~1 MB | ~10-50 MB |

## Best Practices

### Development Workflow

```bash
# 1. Use lite mode for quick testing
SESSION_BUDDY_MODE=lite session-buddy start

# 2. Test your feature

# 3. Switch to standard mode for full integration testing
SESSION_BUDDY_MODE=standard session-buddy start

# 4. Verify with persistent data
```

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
steps:
  - name: Start Session-Buddy (Lite Mode)
    run: |
      export SESSION_BUDDY_MODE=lite
      session-buddy start &
      sleep 5

  - name: Run Tests
    run: pytest

  - name: Stop Session-Buddy
    run: session-buddy stop
```

### Production Deployment

```bash
# Always use standard mode in production
export SESSION_BUDDY_MODE=standard

# Start with process manager
systemctl start session-buddy
# or
pm2 start session-buddy --name session-buddy
```

## FAQ

### Q: Can I run multiple instances in different modes?

A: Yes, but you'll need to use different ports and data directories:

```bash
SESSION_BUDDY_MODE=lite session-buddy start --port=8678
SESSION_BUDDY_MODE=standard session-buddy start --port=8679
```

### Q: How do I backup standard mode data?

A: Copy the database file:

```bash
cp ~/.claude/data/reflection.duckdb ~/backup.duckdb
```

### Q: Can I use lite mode with persistent storage?

A: Not directly. Lite mode is designed to be ephemeral. However, you
can create a custom mode with file-based storage but disabled embeddings:

```python
from session_buddy.modes.base import OperationMode, ModeConfig

class CustomMode(OperationMode):
    @property
    def name(self) -> str:
        return "custom"

    def get_config(self) -> ModeConfig:
        return ModeConfig(
            name="custom",
            database_path="~/.claude/data/custom.duckdb",
            storage_backend="file",
            enable_embeddings=False,  # Disable for fast startup
        )
```

### Q: Which mode should I use for development?

A: Use standard mode for daily development. The persistence and full
feature set are worth the slightly longer startup time. Use lite mode
only for quick testing or when you don't need persistence.

### Q: Can I change modes without restarting?

A: No, mode selection happens at startup. You must restart Session-Buddy
to change modes.

## Additional Resources

- [Session-Buddy README](../../README.md)
- [Configuration Guide](../user/CONFIGURATION.md)
- [Architecture Overview](../developer/ARCHITECTURE.md)
- [Feature Documentation](../features/)
