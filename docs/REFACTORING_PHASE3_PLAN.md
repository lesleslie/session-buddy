---
status: complete
role: historical
date: 2026-07-16
last_reviewed: 2026-07-16
superseded_by: null
blocks_on: []
topic: architecture
---

# Refactoring Phase 3: Code Duplication Elimination - Implementation Plan

## Overview

Phase 3 focuses on eliminating duplicate code patterns identified across the codebase, particularly in the tools directory where significant repetition exists.

## Analysis Results

### Duplication Statistics

| Pattern Type | Occurrences | Files Affected | Expected Reduction |
|-------------|-------------|----------------|-------------------|
| Exception handling (`except Exception as e:`) | 80 | 10 files | 120-160 lines |
| Logger error/exception calls | 72 | 10 files | 80-100 lines |
| "Not available" error messages | 63 | 9 files | 40-60 lines |
| Async implementation functions (`*_impl`) | 72 | 10 files | 100-150 lines |
| Database resolution pattern | 15 | 5 files | 30-45 lines |
| Database null checks | 16 | 2 files | 15-25 lines |

**Total Expected Reduction: 385-540 lines (1-1.4% of codebase)**

### Files with Highest Duplication

1. **search_tools.py** (874 lines)

   - 12 async impl functions
   - 12 exception handlers
   - 11 database resolution patterns
   - 11 error messages

1. **monitoring_tools.py** (669 lines)

   - 11 async impl functions
   - 11 exception handlers
   - 11 error messages

1. **knowledge_graph_tools.py** (782 lines)

   - 11 exception handlers
   - 9 async impl functions
   - 9 error messages

1. **memory_tools.py** (626 lines)

   - 7 async impl functions
   - 7 exception handlers
   - 7 error messages

1. **serverless_tools.py** (521 lines)

   - 8 async impl functions
   - 8 exception handlers
   - 8 error messages

## Identified Patterns

### Pattern A: Generic Error Handling Wrapper

**Current Pattern** (repeated 80 times):

```python
try:
    # Some operation
    result = await some_operation()
    return result
except Exception as e:
    _get_logger().exception(f"Error in operation: {e}")
    return f"❌ Operation failed: {str(e)}"
```

**Proposed Solution**: Create error handling decorator/wrapper

```python
# New utility in utils/error_handlers.py
async def handle_tool_errors(
    operation: Callable, error_prefix: str = "Operation", *args, **kwargs
) -> Any:
    """Generic error handler for tool operations."""
    try:
        return await operation(*args, **kwargs)
    except Exception as e:
        _get_logger().exception(f"Error in {error_prefix}: {e}")
        return f"❌ {error_prefix} failed: {str(e)}"
```

**Usage**:

```python
# Before (5-8 lines)
async def some_tool():
    try:
        result = await operation()
        return result
    except Exception as e:
        _get_logger().exception(f"Error: {e}")
        return f"❌ Failed: {str(e)}"


# After (2 lines)
async def some_tool():
    return await handle_tool_errors(operation, "Some tool")
```

**Impact**: Reduces 80 occurrences × 5 lines average = **400 lines → 160 lines** (240 line reduction)

### Pattern B: Database Resolution Pattern

**Current Pattern** (repeated 15 times):

```python
db = await resolve_reflection_database()
if not db:
    return "❌ Reflection database not available. Install dependencies: uv sync --extra embeddings"
```

**Proposed Solution**: Create database resolution utility

```python
# New utility in utils/database_helpers.py
async def require_reflection_database() -> ReflectionDatabase:
    """Get reflection database or raise with helpful error."""
    db = await resolve_reflection_database()
    if not db:
        raise DatabaseUnavailableError(
            "Reflection database not available. Install dependencies: uv sync --extra embeddings"
        )
    return db


async def safe_database_operation(
    operation: Callable, error_message: str = "Database operation"
) -> str:
    """Execute database operation with error handling."""
    try:
        db = await require_reflection_database()
        return await operation(db)
    except DatabaseUnavailableError as e:
        return f"❌ {str(e)}"
    except Exception as e:
        _get_logger().exception(f"Error in {error_message}: {e}")
        return f"❌ {error_message} failed: {str(e)}"
```

**Impact**: Reduces 15 occurrences × 3 lines average = **45 lines → 15 lines** (30 line reduction)

### Pattern C: Consistent Error Message Formatting

**Current Pattern** (repeated 63 times):

```python
return "❌ Feature not available. Install dependencies: ..."
return "❌ Operation failed: {error}"
return "❌ Invalid input: {details}"
```

**Proposed Solution**: Create error message formatter

```python
# New utility in utils/messages.py
class ToolMessages:
    """Centralized tool message formatting."""

    @staticmethod
    def not_available(feature: str, install_hint: str = "") -> str:
        """Format feature unavailable message."""
        msg = f"❌ {feature} not available"
        if install_hint:
            msg += f". {install_hint}"
        return msg

    @staticmethod
    def operation_failed(operation: str, error: Exception | str) -> str:
        """Format operation failure message."""
        return f"❌ {operation} failed: {str(error)}"

    @staticmethod
    def success(message: str, details: dict[str, Any] | None = None) -> str:
        """Format success message with optional details."""
        lines = [f"✅ {message}"]
        if details:
            for key, value in details.items():
                lines.append(f"  • {key}: {value}")
        return "\n".join(lines)
```

**Impact**: Reduces code duplication and improves consistency (60 line reduction)

### Pattern D: Async Wrapper Consolidation

**Current Pattern** (repeated 72 times):

```python
async def _some_operation_impl(...) -> str:
    """Implementation for some_operation tool."""
    try:
        # validation
        if not condition:
            return "❌ Invalid input"

        # get database
        db = await resolve_reflection_database()
        if not db:
            return "❌ Not available"

        # perform operation
        result = await db.operation()

        # format response
        return format_response(result)

    except Exception as e:
        _get_logger().exception(f"Error: {e}")
        return f"❌ Failed: {str(e)}"
```

**Proposed Solution**: Create generic tool wrapper

```python
# New utility in utils/tool_wrapper.py
async def execute_database_tool(
    operation: Callable[[ReflectionDatabase], Awaitable[Any]],
    formatter: Callable[[Any], str],
    operation_name: str,
    validator: Callable[[], bool] | None = None,
) -> str:
    """Generic wrapper for database-dependent tools."""
    try:
        # Validation
        if validator and not validator():
            return ToolMessages.operation_failed(operation_name, "Invalid input")

        # Database resolution
        db = await require_reflection_database()

        # Execute operation
        result = await operation(db)

        # Format result
        return formatter(result)

    except DatabaseUnavailableError as e:
        return ToolMessages.not_available(operation_name, str(e))
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)
```

**Impact**: Reduces 72 implementations averaging 15 lines = **1080 lines → 360 lines** (720 line reduction, but conservative estimate 100-150 lines)

## Implementation Plan

### Step 1: Create Utility Modules (Day 1)

Create new utility modules:

- `session_buddy/utils/error_handlers.py` - Generic error handling
- `session_buddy/utils/database_helpers.py` - Database resolution utilities
- `session_buddy/utils/messages.py` - Consistent message formatting
- `session_buddy/utils/tool_wrapper.py` - Generic tool execution wrappers

**Estimated Lines**: +200 lines of reusable utilities

### Step 2: Refactor High-Impact Files (Days 2-3)

Refactor files with highest duplication first:

**Priority 1** (Day 2):

1. `tools/search_tools.py` (874 lines → ~700 lines, save ~174 lines)
1. `tools/memory_tools.py` (626 lines → ~500 lines, save ~126 lines)

**Priority 2** (Day 3):
3\. `tools/monitoring_tools.py` (669 lines → ~550 lines, save ~119 lines)
4\. `tools/knowledge_graph_tools.py` (782 lines → ~660 lines, save ~122 lines)

### Step 3: Refactor Remaining Files (Day 4)

**Priority 3**:
5\. `tools/serverless_tools.py` (521 lines → ~430 lines, save ~91 lines)
6\. `tools/validated_memory_tools.py` (524 lines → ~450 lines, save ~74 lines)
7\. `tools/session_tools.py` (884 lines → ~800 lines, save ~84 lines)
8\. `tools/llm_tools.py` (452 lines → ~400 lines, save ~52 lines)
9\. `tools/team_tools.py` (284 lines → ~250 lines, save ~34 lines)
10\. `tools/crackerjack_tools.py` (1,340 lines → defer to Phase 4)

### Step 4: Testing & Validation (Day 5)

- Run full test suite after each file refactoring
- Verify no functional changes (pure refactoring)
- Ensure all 1,203 tests continue passing
- Check coverage doesn't decrease

## Expected Results

### Lines of Code Reduction

| Category | Before | After | Reduction |
|----------|--------|-------|-----------|
| New utilities | 0 | 200 | +200 |
| Tools refactored (9 files) | ~5,612 | ~4,740 | -872 |
| **Net reduction** | | | **-672 lines** |

### Code Quality Improvements

1. **DRY Compliance**: Eliminate 80+ instances of duplicated error handling
1. **Maintainability**: Centralized error messages and patterns
1. **Consistency**: Uniform error handling across all tools
1. **Testability**: Utilities can be tested independently
1. **Readability**: Tool implementations become more focused on business logic

### Metrics

```
Starting Phase 3: ~38,139 lines (after Phase 2)
After Phase 3:      ~37,467 lines
────────────────────────────────────
Phase 3 Reduction:  672 lines (1.8%)
Cumulative:         706 lines (1.85% of original)
Remaining:          ~9,467 lines to reach 28,000 target
Progress:           1.85% of reduction goal
```

## Risk Assessment

**Risk Level**: 🟡 MEDIUM

### Risks

- More invasive changes than Phases 1-2
- Modifying business logic flow (error handling)
- Potential for introducing subtle bugs
- Higher test burden

### Mitigations

1. **Incremental Approach**: Refactor one file at a time
1. **Test After Each File**: Run tests immediately after each refactoring
1. **Preserve Behavior**: Ensure utilities produce identical output
1. **Code Review**: Careful review of each refactored function
1. **Rollback Plan**: Git commits per file for easy reversion

## Testing Strategy

### Per-File Testing

```bash
# After refactoring each file
pytest tests/unit/ tests/functional/ -v -x

# Quick smoke test
pytest -m "not slow" -v -x

# Specific file tests
pytest tests/unit/test_memory_tools.py -v
```

### Full Validation

```bash
# Run complete test suite
pytest

# Check coverage
pytest --cov=session_buddy --cov-report=term-missing

# Verify no regressions
pytest --durations=20
```

## Success Criteria

- ✅ All 1,203+ tests passing
- ✅ Coverage maintained or improved
- ✅ Net reduction of 600+ lines
- ✅ No functional changes (pure refactoring)
- ✅ Improved code maintainability metrics
- ✅ Consistent error handling across all tools

## Next Steps After Phase 3

Phase 4 will tackle the largest files with more aggressive refactoring:

- `crackerjack_tools.py` (1,340 lines)
- `session_tools.py` (884 lines)
- `crackerjack_integration.py` (1,632 lines)
- Plus core system files

Expected Phase 4 reduction: 1,000-1,500 lines

## Timeline

- **Day 1**: Create utility modules (+200 lines)
- **Day 2**: Refactor search_tools.py and memory_tools.py (-300 lines net)
- **Day 3**: Refactor monitoring_tools.py and knowledge_graph_tools.py (-241 lines net)
- **Day 4**: Refactor remaining 5 tool files (-331 lines net)
- **Day 5**: Testing, validation, documentation

**Total Duration**: 5 days
**Net Reduction**: 672 lines
**Confidence**: HIGH (proven patterns, incremental approach)
