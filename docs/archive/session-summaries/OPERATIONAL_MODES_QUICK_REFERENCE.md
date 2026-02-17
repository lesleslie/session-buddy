# Session-Buddy Operational Modes - Quick Reference

## TL;DR

```bash
# Lite mode (fast, no persistence)
session-buddy --mode=lite start

# Standard mode (default, persistent)
session-buddy start

# Using startup script
./scripts/dev-start.sh lite
./scripts/dev-start.sh standard
```

## Mode Comparison

| Feature | Lite Mode | Standard Mode |
|---------|-----------|---------------|
| **Startup Time** | < 2 sec | ~ 3-5 sec |
| **Database** | `:memory:` | `~/.claude/data/reflection.duckdb` |
| **Persistence** | ❌ No | ✅ Yes |
| **Embeddings** | ❌ Disabled | ✅ Enabled |
| **Best For** | Testing, CI/CD | Development, Production |

## Quick Start

### Lite Mode
```bash
# Start in lite mode
SESSION_BUDDY_MODE=lite session-buddy start

# Or using CLI
session-buddy --mode=lite start

# Or using script
./scripts/dev-start.sh lite
```

### Standard Mode
```bash
# Start in standard mode (default)
session-buddy start

# Or explicitly
session-buddy --mode=standard start

# Or using script
./scripts/dev-start.sh standard
```

## Configuration Files

- **Lite**: `settings/lite.yaml`
- **Standard**: `settings/standard.yaml`
- **Base**: `settings/session-buddy.yaml`

## Environment Variables

```bash
export SESSION_BUDDY_MODE=lite      # Lite mode
export SESSION_BUDDY_MODE=standard  # Standard mode
```

## Use Cases

### Use Lite Mode When:
- ✅ Quick testing
- ✅ CI/CD pipelines
- ✅ Temporary sessions
- ✅ No data persistence needed

### Use Standard Mode When:
- ✅ Daily development
- ✅ Production deployments
- ✅ Persistent data needed
- ✅ Full feature set needed

## Troubleshooting

### Data not persisting?
You're in lite mode. Switch to standard:
```bash
SESSION_BUDDY_MODE=standard session-buddy start
```

### Slow startup?
Standard mode loads embeddings. Use lite for faster startup:
```bash
SESSION_BUDDY_MODE=lite session-buddy start
```

### Semantic search not working?
Lite mode disables embeddings. Use standard mode:
```bash
SESSION_BUDDY_MODE=standard session-buddy start
```

## Documentation

- **Full Guide**: [docs/guides/operational-modes.md](docs/guides/operational-modes.md)
- **Implementation**: [SESSION_BUDDY_LITE_MODE_PROGRESS.md](SESSION_BUDDY_LITE_MODE_PROGRESS.md)
- **Plan**: [SESSION_BUDDY_LITE_MODE_PLAN.md](SESSION_BUDDY_LITE_MODE_PLAN.md)

## Examples

### Development Workflow
```bash
# 1. Quick test in lite mode
./scripts/dev-start.sh lite

# 2. Test feature

# 3. Switch to standard for full testing
./scripts/dev-start.sh standard

# 4. Verify with persistent data
```

### CI/CD Pipeline
```yaml
steps:
  - name: Start Session-Buddy
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
# Always use standard mode
export SESSION_BUDDY_MODE=standard
systemctl start session-buddy
```

## Programmatic Usage

```python
from session_buddy.modes import get_mode, LiteMode, StandardMode

# Get mode from environment
mode = get_mode()

# Or specify explicitly
lite = LiteMode()
standard = StandardMode()

# Get configuration
config = lite.get_config()
print(f"Database: {config.database_path}")
print(f"Storage: {config.storage_backend}")

# Validate environment
errors = standard.validate_environment()
if errors:
    print(f"Errors: {errors}")

# Get startup message
print(lite.get_startup_message())
```

## Feature Flags

### Lite Mode (Disabled Features)
- Semantic search (embeddings)
- Multi-project coordination
- Token optimization
- Auto-checkpoint
- Faceted search
- Search suggestions
- Auto-store reflections
- Crackerjack integration
- Git integration

### Standard Mode (Enabled Features)
- All features enabled
- Persistent database
- Semantic search
- Multi-project coordination
- Full integration support

## Performance

### Lite Mode
- Startup: ~1-2 seconds
- Memory: ~50 MB
- Database: 0 MB (in-memory)

### Standard Mode
- Startup: ~3-5 seconds
- Memory: ~50-200 MB (with embeddings)
- Database: ~1-50 MB (file-based)

## Migration

### Lite → Standard
```bash
# Switch to standard mode
SESSION_BUDDY_MODE=standard session-buddy start
```

### Standard → Lite (⚠️ Data Loss)
```bash
# Switch to lite mode (data will be lost)
SESSION_BUDDY_MODE=lite session-buddy start
```

## FAQ

**Q: Can I run multiple instances?**
A: Yes, but use different ports:
```bash
session-buddy --port=8678 --mode=lite start
session-buddy --port=8679 --mode=standard start
```

**Q: How do I backup data?**
A: Copy the database file (standard mode only):
```bash
cp ~/.claude/data/reflection.duckdb ~/backup.duckdb
```

**Q: Which mode should I use?**
A: Use standard for development, lite for testing.

**Q: Can I change modes without restarting?**
A: No, mode is set at startup. Restart to change modes.

## Support

- **Issues**: https://github.com/lesleslie/session-buddy/issues
- **Docs**: https://github.com/lesleslie/session-buddy/tree/main/docs
- **Guides**: https://github.com/lesleslie/session-buddy/tree/main/docs/guides

---

**Last Updated**: February 9, 2026
**Version**: 0.13.0+
