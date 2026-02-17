# Week 7 Planning - ACB DI Refactoring

**Status:** Planning Phase (Day 0)
**Date:** 2025-10-29
**Focus:** Architecture Improvement - Proper ACB Dependency Injection

______________________________________________________________________

## Executive Summary

Week 7 focuses on addressing the ACB specialist's critical finding (4/10 score) by migrating to proper ACB dependency injection patterns. This will resolve the 4 failing DI infrastructure tests and improve overall architecture quality.

### Goals

1. **Replace string-based DI keys** with type-based keys (ACB standard)
1. **Fix 4 failing DI infrastructure tests** (bevy type confusion)
1. **Improve architecture score** from 4/10 to 8/10+
1. **Maintain 98% test pass rate** throughout refactoring

______________________________________________________________________

## Problem Analysis

### Current Architecture Issues

**1. Mixed DI Key Types (Root Cause)**

The codebase currently mixes two incompatible DI key types:

```python
# String keys (causes bevy type confusion)
CLAUDE_DIR_KEY = "paths.claude_dir"  # ❌ String
LOGS_DIR_KEY = "paths.logs_dir"  # ❌ String

# Class keys (works correctly)
SessionLogger  # ✅ Type
ApplicationMonitor  # ✅ Type
```

**Problem:** Bevy's internal `issubclass()` check fails when passed a string:

```python
# This fails with TypeError
depends.get_sync("paths.claude_dir")  # bevy calls issubclass(str, Something)
```

**Error:** `TypeError: issubclass() arg 2 must be a class, a tuple of classes, or a union`

### 2. Failing Tests (4 total)

**File:** `tests/unit/test_instance_managers.py`

1. `test_get_app_monitor_registers_singleton`
1. `test_get_llm_manager_uses_di_cache`
1. `test_serverless_manager_uses_config`

**File:** `tests/unit/test_di_container.py` (if applicable)

**Root Cause:** All failures trace back to line 144 in `instance_managers.py`:

```python
claude_dir = depends.get_sync(CLAUDE_DIR_KEY)  # ❌ String key "paths.claude_dir"
```

### 3. Modules Without Proper ACB DI

According to ACB specialist review (4/10 score):

1. **`session_buddy/di/__init__.py`** - Uses string keys for paths
1. **`session_buddy/utils/instance_managers.py`** - Mixed key types
1. **`session_buddy/server_core.py`** - Manual singleton management
1. **`session_buddy/core.py`** (SessionLifecycleManager) - Manual initialization

______________________________________________________________________

## Solution Architecture

### ACB DI Best Practices

**Type-Based Dependency Resolution:**

```python
# ✅ Correct: Use types/protocols for DI keys
from typing import Protocol


class PathsConfig(Protocol):
    claude_dir: Path
    logs_dir: Path
    commands_dir: Path


# Register with type
depends.set(PathsConfig, config_instance)

# Resolve with type
config = depends.get_sync(PathsConfig)
```

### Proposed Architecture

**1. Create Type-Safe Configuration Class**

```python
# session_buddy/di/config.py
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionPaths:
    """Type-safe path configuration for session management."""

    claude_dir: Path
    logs_dir: Path
    commands_dir: Path

    @classmethod
    def from_home(cls, home: Path | None = None) -> "SessionPaths":
        """Create paths from home directory."""
        if home is None:
            home = Path(os.path.expanduser("~"))
        claude_dir = home / ".claude"
        return cls(
            claude_dir=claude_dir,
            logs_dir=claude_dir / "logs",
            commands_dir=claude_dir / "commands",
        )
```

**2. Update DI Configuration**

```text
# session_buddy/di/__init__.py
def configure(*, force: bool = False) -> None:
    """Register default dependencies for the session-mgmt MCP stack."""
    global _configured
    if _configured and not force:
        return

    # Register type-safe paths
    paths = SessionPaths.from_home()
    _ensure_directories(paths)
    depends.set(SessionPaths, paths)

    # Register services (already correct)
    _register_logger(paths.logs_dir, force)
    _register_permissions_manager(paths.claude_dir, force)
    _register_lifecycle_manager(force)

    _configured = True
```

**3. Update Instance Managers**

```text
# session_buddy/utils/instance_managers.py
def _resolve_claude_dir() -> Path:
    """Resolve claude directory via type-safe DI."""
    with suppress(KeyError, AttributeError, RuntimeError):
        paths = depends.get_sync(SessionPaths)
        paths.claude_dir.mkdir(parents=True, exist_ok=True)
        return paths.claude_dir

    # Fallback
    default_dir = Path(os.path.expanduser("~")) / ".claude"
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir
```

______________________________________________________________________

## Implementation Plan

### Phase 1: Create Type-Safe Configuration (Day 1)

**Tasks:**

1. Create `session_buddy/di/config.py` with `SessionPaths` dataclass
1. Add comprehensive unit tests for `SessionPaths`
1. Verify frozen dataclass immutability
1. Test `from_home()` factory method with various inputs

**Estimated:** 2-3 hours
**Risk:** Low (new code, no existing dependencies)

### Phase 2: Update DI Configuration (Day 2)

**Tasks:**

1. Update `session_buddy/di/__init__.py` to use `SessionPaths`
1. Replace all `CLAUDE_DIR_KEY` references with `SessionPaths`
1. Update `_register_*` functions to accept `Path` parameters
1. Update tests to use new pattern
1. Verify `test_di_container.py` passes

**Estimated:** 3-4 hours
**Risk:** Medium (affects core DI setup)

### Phase 3: Update Instance Managers (Day 3)

**Tasks:**

1. Replace `_resolve_claude_dir()` to use `SessionPaths`
1. Update all `async def get_*()` functions
1. Remove `CLAUDE_DIR_KEY` imports
1. Update tests to use new pattern
1. Verify all 3 failing tests in `test_instance_managers.py` pass

**Estimated:** 3-4 hours
**Risk:** Medium (affects 5 manager functions)

### Phase 4: Deprecate String Keys (Day 4)

**Tasks:**

1. Mark `constants.py` keys as deprecated with warnings
1. Update any remaining usages across codebase
1. Add migration guide to documentation
1. Run full test suite to verify no regressions

**Estimated:** 2-3 hours
**Risk:** Low (cleanup phase)

### Phase 5: Documentation & Verification (Day 5)

**Tasks:**

1. Update architecture documentation
1. Add ACB DI patterns guide
1. Document migration path for future changes
1. Run full test suite with coverage
1. Verify all 4 DI tests pass
1. Update Week 7 completion documentation

**Estimated:** 2-3 hours
**Risk:** Low (documentation and verification)

______________________________________________________________________

## Testing Strategy

### Unit Tests (New)

**File:** `tests/unit/test_di_config.py`

```text
class TestSessionPaths:
    def test_create_from_home(self, tmp_path):
        """Should create paths from home directory."""
        paths = SessionPaths.from_home(tmp_path)

        assert paths.claude_dir == tmp_path / ".claude"
        assert paths.logs_dir == tmp_path / ".claude" / "logs"
        assert paths.commands_dir == tmp_path / ".claude" / "commands"

    def test_immutability(self):
        """Should be immutable (frozen dataclass)."""
        paths = SessionPaths.from_home()

        with pytest.raises(FrozenInstanceError):
            paths.claude_dir = Path("/tmp")

    def test_from_home_creates_directories(self, tmp_path):
        """Should create directory structure."""
        paths = SessionPaths.from_home(tmp_path)
        paths.claude_dir.mkdir(parents=True, exist_ok=True)

        assert paths.claude_dir.exists()
```

### Integration Tests (Modified)

**Files to Update:**

- `tests/unit/test_di_container.py` (2 tests)
- `tests/unit/test_instance_managers.py` (3 tests)

**Changes:**

```python
# Before
depends.get_sync(CLAUDE_DIR_KEY)  # String key

# After
paths = depends.get_sync(SessionPaths)
claude_dir = paths.claude_dir  # Type-safe access
```

### Regression Prevention

1. Run full test suite after each phase
1. Maintain 98% pass rate throughout
1. No new test failures introduced
1. All 4 DI infrastructure tests must pass by Phase 3

______________________________________________________________________

## Risk Analysis

### High Risk Areas

1. **Core DI Configuration Changes**

   - **Mitigation:** Implement in phases with tests after each
   - **Rollback:** Keep string keys deprecated but functional for 1 release

1. **Test Isolation Issues**

   - **Mitigation:** Ensure proper `configure(force=True)` in test fixtures
   - **Rollback:** Revert to singleton reset patterns if needed

1. **Performance Impact**

   - **Mitigation:** Benchmark DI resolution speed before/after
   - **Rollback:** Optimize if >10% performance degradation

### Medium Risk Areas

1. **Third-party Code Assumptions**

   - **Mitigation:** Search for external references to string keys
   - **Rollback:** Keep compatibility layer for external users

1. **Documentation Lag**

   - **Mitigation:** Update docs inline with code changes
   - **Rollback:** N/A (documentation only)

______________________________________________________________________

## Success Criteria

### Must Have (Week 7 Complete)

- ✅ All 4 DI infrastructure tests passing
- ✅ Zero new test failures introduced
- ✅ 98%+ test pass rate maintained
- ✅ No string-based DI keys in production code
- ✅ ACB specialist score improvement: 4/10 → 8/10+

### Nice to Have

- ✅ Full test coverage for new `SessionPaths` class
- ✅ Migration guide documentation
- ✅ Performance benchmarks showing no degradation
- ✅ Deprecation warnings for old patterns

______________________________________________________________________

## Technical Debt Addressed

### Before Week 7

- ❌ String-based DI keys causing bevy type confusion
- ❌ Mixed key types (strings + classes) in same container
- ❌ Manual singleton management in some modules
- ❌ 4 failing DI infrastructure tests
- ❌ ACB specialist score: 4/10

### After Week 7

- ✅ Type-safe DI keys using dataclasses/protocols
- ✅ Consistent class-based keys throughout
- ✅ Proper ACB DI patterns in all modules
- ✅ All DI infrastructure tests passing
- ✅ ACB specialist score: 8/10+

______________________________________________________________________

## Dependencies & Prerequisites

### Required Knowledge

- ACB dependency injection patterns
- Bevy DI container internals
- Python dataclasses and protocols
- Type-safe configuration patterns

### Required Tools

- ACB framework (already installed)
- Python 3.13+ with dataclasses support
- pytest for testing

### Blocking Issues

- None currently

______________________________________________________________________

## Timeline

| Day | Phase | Hours | Tasks |
|-----|-------|-------|-------|
| **Day 1** | Type-Safe Config | 2-3 | Create `SessionPaths`, tests |
| **Day 2** | DI Configuration | 3-4 | Update `di/__init__.py`, tests |
| **Day 3** | Instance Managers | 3-4 | Update managers, fix 3 tests |
| **Day 4** | Deprecation | 2-3 | Mark old keys deprecated |
| **Day 5** | Documentation | 2-3 | Docs, verification, completion |
| **Total** | | **12-17 hours** | **5 days** |

______________________________________________________________________

## Rollback Plan

If critical issues arise during implementation:

### Phase 1-2 Rollback

- Remove new `SessionPaths` class
- Restore string-based keys
- Impact: Minimal (new code only)

### Phase 3-4 Rollback

- Keep string keys alongside type-based keys
- Add compatibility layer
- Deprecate but don't remove string keys
- Impact: Moderate (requires dual support)

### Emergency Rollback

- Revert entire branch
- Return to Week 6 state
- Schedule follow-up planning
- Impact: High (lost work, rescheduling needed)

______________________________________________________________________

## Next Steps

1. **Review this plan** with team/stakeholders
1. **Begin Day 1 implementation** - Create `SessionPaths` class
1. **Execute phases sequentially** with testing after each
1. **Monitor test pass rate** continuously
1. **Document progress** in daily logs

______________________________________________________________________

## References

- **ACB Framework Documentation:** `/Users/les/Projects/acb/`
- **Week 6 Summary:** `docs/WEEK6_SUMMARY.md`
- **Agent Reviews:** Week 5 end-of-phase reviews
- **Current DI Code:** `session_buddy/di/__init__.py`

______________________________________________________________________

**Created:** 2025-10-29
**Author:** Claude Code + Les
**Project:** session-buddy
**Phase:** Week 7 Planning (Day 0)
