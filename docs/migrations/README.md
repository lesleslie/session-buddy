# Migration Guides

Step-by-step guides for migrating between versions and adopting new patterns in session-buddy.

## Available Migration Guides

### Core Migrations

1. **[HTTP Client Adapter](http-client-adapter.md)** - Migrate from aiohttp to mcp_common HTTPClientAdapter (11x performance improvement)
1. **[Health Check Implementation](health-check-implementation.md)** - Add production-ready health checks to your server

## Migration Strategy

### 1. Assess Current State

Before migrating, assess your current implementation:

```bash
# Check current version
python -c "import session_buddy; print(session_buddy.__version__)"

# Review active features
python -c "from session_buddy.health_checks import get_all_health_checks; import asyncio; asyncio.run(get_all_health_checks())"
```

### 2. Plan Migration

1. **Read the relevant migration guide(s)**
1. **Identify affected code** in your project
1. **Create a backup** or feature branch
1. **Follow the step-by-step instructions**
1. **Test thoroughly** before deploying

### 3. Testing After Migration

Run comprehensive test suite after each migration:

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/unit/ -v
pytest tests/integration/ -v

# Check code quality
crackerjack lint
crackerjack typecheck
```

### 4. Rollback Plan

Each migration guide includes:

- **Prerequisites**: What you need before starting
- **Step-by-step instructions**: Clear migration path
- **Validation steps**: How to verify success
- **Rollback procedure**: How to revert if needed
- **Common issues**: Troubleshooting guide

## Migration Priority

**High Priority** (Production Impact):

- ✅ [Health Check Implementation](health-check-implementation.md) - Essential for production monitoring
- ✅ [HTTP Client Adapter](http-client-adapter.md) - Significant performance improvement

## Version Compatibility

| Migration Guide | Minimum Version | Target Version | Breaking Changes |
|----------------|----------------|----------------|------------------|
| HTTP Client Adapter | 1.x | 2.0+ | ✅ Yes - New adapter pattern |
| Health Checks | Any | 2.0+ | ❌ No - Additive only |

## Getting Help

If you encounter issues during migration:

1. **Check the troubleshooting section** in the specific migration guide
1. **Review the ARCHITECTURE.md** for detailed implementation patterns
1. **Check API_REFERENCE.md** for updated API signatures
1. **Open an issue** on GitHub with migration details

## Contributing Migration Guides

To add a new migration guide:

1. Create `docs/migrations/your-migration-name.md`
1. Follow the [migration guide template](#migration-guide-template)
1. Add entry to this README
1. Submit pull request

### Migration Guide Template

```markdown
# Migration: [Title]

## Overview

Brief description of what's being migrated and why.

## Prerequisites

- Current version requirements
- Dependencies needed
- Backup recommendations

## Benefits

- Benefit 1
- Benefit 2
- Benefit 3

## Migration Steps

### Step 1: [First Step]

Detailed instructions...

### Step 2: [Second Step]

More instructions...

## Validation

How to verify the migration succeeded.

## Rollback Procedure

How to revert changes if needed.

## Common Issues

### Issue 1

**Symptom**: ...
**Solution**: ...

### Issue 2

**Symptom**: ...
**Solution**: ...
```

______________________________________________________________________

**Need help?** Check [ARCHITECTURE.md](../developer/ARCHITECTURE.md) and [API_REFERENCE.md](../reference/API_REFERENCE.md) for detailed technical information.
