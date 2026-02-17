# Session Handoff: Week 3 Day 1 - Test Infrastructure Crisis

**Date:** 2025-10-28
**Session Type:** Execution - Critical Blocker Resolution
**Estimated Duration:** 8-16 hours
**Priority:** P0 - CRITICAL BLOCKER

______________________________________________________________________

## Executive Summary

**What Was Accomplished This Session:**
✅ Unified two overlapping implementation plans (10-week + 16-week) into single 13-week roadmap
✅ Reviewed by 6 specialized agents (documentation, architecture, delivery, python, code review)
✅ Identified critical blocker: 14 test collection errors preventing all validation
✅ Created comprehensive execution plan with clear phases and success criteria

**What's Next:**
🔥 Fix test infrastructure (Week 3 priority)
🎯 Restore test execution and coverage measurement
📊 Enable quality validation and feature testing

______________________________________________________________________

## Current Status: Week 3 Day 1

### The Critical Problem

**14 Test Collection Errors** blocking entire test suite:

```
ERROR session_buddy/tests/integration/test_monitoring.py::TestMonitoringTools
ERROR session_buddy/tests/integration/test_session_lifecycle.py
ERROR session_buddy/tests/unit/test_health_checks.py
ERROR session_buddy/tests/unit/test_resource_cleanup.py
... (10 more)
```

**Impact:**

- 735 tests defined but cannot execute
- Coverage shows 14.4% (meaningless - tests aren't running)
- All new features untested (DuckPGQ, health checks, shutdown)
- Quality gates blocked

**Root Cause:**
During Phase 2.7 DI refactoring, `SessionLogger` registration moved but tests weren't updated:

```python
# OLD (working):
from session_buddy.server import SessionLogger

logger = SessionLogger()

# NEW (broken in tests):
from acb.depends import depends

logger = depends.get_sync(SessionLogger)  # Returns coroutine in test environment!
```

**The Fix:**
Update test fixtures to properly mock SessionLogger via DI container.

______________________________________________________________________

## Week 3 Objectives (5 days)

### Day 1-2: Test Collection Fixes (P0) - START HERE

**Goal:** Resolve all 14 collection errors

**Tasks:**

1. [ ] Fix SessionLogger DI registration in `tests/conftest.py`
1. [ ] Update test_monitoring.py to use `depends.override()`
1. [ ] Update test_session_lifecycle.py
1. [ ] Update test_health_checks.py
1. [ ] Update test_resource_cleanup.py
1. [ ] Fix remaining 10 test files
1. [ ] Verify 0 collection errors: `pytest --co -q`

**Success Criteria:**

- ✅ `pytest --co -q` shows 0 errors
- ✅ Test collection completes successfully
- ✅ All 735 tests discovered

**Estimated Time:** 8-12 hours

### Day 3-4: Test Execution Restoration (P0)

**Goal:** Get 80%+ of tests passing

**Tasks:**

1. [ ] Run full test suite: `pytest -v`
1. [ ] Fix integration test failures (monitoring, lifecycle, crackerjack)
1. [ ] Fix health check test failures
1. [ ] Fix resource cleanup test failures
1. [ ] Target: 590+/735 tests passing (80%)

**Success Criteria:**

- ✅ ≥80% tests passing (590+/735)
- ✅ No collection errors
- ✅ CI/CD pipeline can run tests

**Estimated Time:** 6-8 hours

### Day 5: Coverage Baseline (P1)

**Goal:** Measure actual coverage and set ratchet

**Tasks:**

1. [ ] Run: `pytest --cov=session_buddy --cov-report=term-missing`
1. [ ] Measure actual coverage (expect 40-50%, not broken 14.4%)
1. [ ] Set coverage ratchet in CI: `--cov-fail-under=40`
1. [ ] Document coverage gaps for Week 4-6 work
1. [ ] Generate Week 3 checkpoint report

**Success Criteria:**

- ✅ Coverage measurable (expect 40-50%)
- ✅ Coverage ratchet set in CI
- ✅ Week 3 checkpoint report complete

**Estimated Time:** 2-4 hours

______________________________________________________________________

## Key Files to Work With

### Primary Files for Test Fixes

**1. Test Fixtures** (`tests/conftest.py`)

```python
# Current location: /Users/les/Projects/session-buddy/tests/conftest.py
# What to fix: Add SessionLogger mock to DI container


@pytest.fixture
def mock_session_logger():
    """Mock SessionLogger for tests."""
    from unittest.mock import MagicMock
    from session_buddy.utils.logging import SessionLogger
    from acb.depends import depends

    mock_logger = MagicMock(spec=SessionLogger)
    depends.override(SessionLogger, lambda: mock_logger)
    yield mock_logger
    depends.reset()  # Clean up after test
```

**2. Failing Test Files** (14 files)

```bash
# List all failing test files
pytest --co -q 2>&1 | grep "ERROR" | cut -d: -f1 | sort -u

# Common pattern to fix in each:
# OLD:
from session_buddy.server import SessionLogger
logger = SessionLogger()

# NEW:
from acb.depends import depends
from session_buddy.utils.logging import SessionLogger

def test_something(mock_session_logger):  # Add fixture
    logger = depends.get_sync(SessionLogger)
    # Rest of test...
```

**3. Reference Documents**

- **Unified Plan:** `docs/UNIFIED-IMPLEMENTATION-PLAN.md` (this is THE plan)
- **Test Improvement Plan:** `docs/TEST-IMPROVEMENT-PLAN.md` (historical, for patterns)
- **Phase 2.7 Review:** `docs/PHASE-2.7-COMPLETION-REVIEW.md` (DI migration details)

______________________________________________________________________

## Quick Reference Commands

### Test Infrastructure

```bash
# Check test collection (current: 14 errors)
pytest --co -q 2>&1 | head -50

# Run specific failing test file
pytest tests/integration/test_monitoring.py -v --tb=short

# Run all tests (after fixes)
pytest -v --tb=short

# Check coverage (after test fixes)
pytest --cov=session_buddy --cov-report=term-missing
```

### Git Status

```bash
# Current branch
git branch --show-current  # Should be: main

# Recent work
git log --oneline -10

# Uncommitted changes
git status
```

### Quality Checks

```bash
# Type checking
mypy session_buddy/

# Linting
ruff check .

# Complexity check
python -m crackerjack --complexity
```

______________________________________________________________________

## Known Issues & Solutions

### Issue 1: SessionLogger DI Registration

**Symptom:**

```
AttributeError: 'coroutine' object has no attribute 'info'
```

**Root Cause:**
`depends.get_sync(SessionLogger)` returns coroutine in test environment instead of actual logger.

**Solution:**
Use `depends.override()` in test fixtures to provide mock logger:

```python
@pytest.fixture
def mock_session_logger():
    from unittest.mock import MagicMock
    from acb.depends import depends

    mock_logger = MagicMock()
    depends.override(SessionLogger, lambda: mock_logger)
    yield mock_logger
    depends.reset()
```

### Issue 2: Test Imports Need Updating

**Symptom:**

```
ImportError: cannot import name 'SessionLogger' from 'session_buddy.server'
```

**Root Cause:**
SessionLogger moved during Phase 2.7 DI refactoring.

**Solution:**
Update imports:

```python
# OLD:
from session_buddy.server import SessionLogger

# NEW:
from session_buddy.utils.logging import SessionLogger
```

### Issue 3: Test Fixtures Missing DI Context

**Symptom:**

```
bevy.injection_types.DependencyResolutionError: No handler found for SessionLogger
```

**Root Cause:**
Tests don't set up DI container before calling code that uses `depends.get_sync()`.

**Solution:**
Add `mock_session_logger` fixture to test function parameters:

```python
# OLD:
def test_something():
    result = some_function()  # Fails if some_function uses depends.get_sync()


# NEW:
def test_something(mock_session_logger):
    result = some_function()  # Works - mock_session_logger sets up DI
```

______________________________________________________________________

## Success Metrics (Week 3 Exit Criteria)

### Must Have (Gate Blockers)

- ✅ 0 test collection errors
- ✅ ≥80% tests passing (590+/735)
- ✅ Coverage measurable (≥40%)

### Should Have (Quality Goals)

- ✅ CI/CD pipeline green
- ✅ Coverage ratchet set
- ✅ Week 3 checkpoint report

### Nice to Have (Stretch Goals)

- ✅ 90%+ tests passing (660+/735)
- ✅ Coverage ≥50%
- ✅ Some mypy errors fixed

______________________________________________________________________

## What NOT to Do (Scope Control)

❌ **Don't add new features** - Only fix test infrastructure
❌ **Don't refactor working code** - Only update test fixtures
❌ **Don't optimize performance** - Focus on getting tests passing
❌ **Don't write new tests** - Fix existing ones first
❌ **Don't jump to coverage work** - Fix collection errors first

**Remember:** Week 3 is about **unblocking validation**, not adding features!

______________________________________________________________________

## Context for Next Session

### What You Know

- ✅ Unified plan exists (`docs/UNIFIED-IMPLEMENTATION-PLAN.md`)
- ✅ Current phase: Week 3 Day 1 - Test infrastructure crisis
- ✅ Root cause: SessionLogger DI registration missing in tests
- ✅ Fix pattern: Use `depends.override()` in test fixtures

### What You Need to Find Out

- 🔍 Which test files have collection errors? (Run: `pytest --co -q`)
- 🔍 What specific errors are they hitting? (Run failing test with `-v --tb=short`)
- 🔍 Are there patterns to the fixes? (Check first 2-3 files, then batch fix)

### Starting Point

**First Command to Run:**

```bash
cd /Users/les/Projects/session-buddy
pytest --co -q 2>&1 | tee test-collection-errors.log
```

This will:

1. Show all 14 collection errors
1. Save to log file for analysis
1. Give you the list of files to fix

**Second Command:**

```bash
# Pick first failing test file from output
pytest tests/integration/test_monitoring.py -v --tb=short
```

This will:

1. Show the specific error in that file
1. Guide your fix for the SessionLogger DI issue
1. Provide pattern for fixing other 13 files

______________________________________________________________________

## Agent Recommendations (From Review)

### Documentation Specialist

> "Fix test infrastructure before ANY documentation updates. Current docs are accurate; tests just can't validate them."

### Architecture Council

> "DI pattern is sound. Test fixtures need updating, not the architecture. Don't refactor - just update test mocks."

### Delivery Lead

> "Week 3 is THE critical path. Every other week depends on this. Timebox to 40 hours max, escalate if blocked."

### Python Pro

> "Use `depends.override()` pattern consistently. Don't try different approaches per test file - pick one pattern and apply everywhere."

### Code Reviewer

> "Don't fix tests AND refactor code simultaneously. Fix tests to validate current code, THEN consider refactoring in Week 4+."

______________________________________________________________________

## Estimated Timeline (Week 3)

**Monday-Tuesday (16 hours):**

- Fix test collection errors (12 hours)
- Verify 0 collection errors (2 hours)
- Buffer (2 hours)

**Wednesday-Thursday (16 hours):**

- Fix test execution failures (12 hours)
- Get to 80% passing (3 hours)
- Buffer (1 hour)

**Friday (8 hours):**

- Measure coverage (2 hours)
- Set coverage ratchet (2 hours)
- Write checkpoint report (2 hours)
- Buffer (2 hours)

**Total: 40 hours (5 days)**

______________________________________________________________________

## Checkpoint Deliverables (Friday EOD)

By end of Week 3, deliver:

1. **Test Infrastructure Fixed**

   - 0 collection errors
   - 80%+ tests passing
   - CI/CD green

1. **Coverage Baseline Established**

   - Actual coverage measured (40-50%)
   - Ratchet set in CI
   - Gap analysis for Week 4-6

1. **Week 3 Checkpoint Report** (`docs/WEEK-3-CHECKPOINT-REPORT.md`)

   - Status: Tests fixed ✅
   - Coverage: 40-50% measured ✅
   - Blockers: None ✅
   - Next Week: Coverage restoration to 60%

______________________________________________________________________

## Quick Start Checklist

When you start the next session:

1. [ ] Read this handoff document
1. [ ] Read unified plan Week 3 section
1. [ ] Check current git status
1. [ ] Run: `pytest --co -q 2>&1 | tee test-collection-errors.log`
1. [ ] Pick first failing test file
1. [ ] Fix SessionLogger DI registration in that file
1. [ ] Verify fix: `pytest <that-file> -v`
1. [ ] Apply pattern to remaining 13 files
1. [ ] Verify all fixes: `pytest --co -q` (expect 0 errors)
1. [ ] Run full suite: `pytest -v --tb=short`

______________________________________________________________________

## Emergency Contacts & Escalation

**If Blocked on Test Fixes:**

- Escalate after 16 hours (2 days) if \<50% of collection errors resolved
- Consider alternate approach: Create new test suite vs fixing old tests
- Seek expert help: pytest-hypothesis-specialist agent

**If Coverage Can't Be Measured:**

- Acceptable: Move to Week 4 with manual test validation
- Not acceptable: Move to Week 4 without ANY test validation

**If Timeline Slips:**

- Week 3 can extend to 6-7 days (48-56 hours)
- Week 4-5 can compress if needed
- Week 6 mcp-common release is hard deadline

______________________________________________________________________

## Final Notes

**Why Week 3 is Critical:**

- Unblocks all feature validation
- Enables coverage measurement
- Unlocks quality gates
- Prerequisite for Week 4-13 work

**What Success Looks Like:**

- Tests run and pass
- Coverage measurable
- Quality gates functional
- Week 4 can start immediately

**Remember:**

> "Week 3 is not about perfection. It's about unblocking validation. Get tests passing, measure coverage, set baseline, move on."

______________________________________________________________________

**Handoff Complete** ✅
**Next Session Goal:** Complete Week 3 test infrastructure fixes
**Expected Outcome:** 0 collection errors, 80%+ tests passing, coverage measurable

Good luck! 🚀
