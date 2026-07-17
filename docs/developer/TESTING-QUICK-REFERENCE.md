---
status: complete
role: canonical
date: 2026-07-16
last_reviewed: 2026-07-16
superseded_by: null
blocks_on: []
topic: lifecycle
---

# Testing Quick Reference Guide

Quick commands and patterns for testing session-buddy

## Running Tests

### Run All Tests

```bash
pytest
pytest --cov=session_buddy --cov-report=term-missing
```

### Run New Comprehensive Tests

```bash
# All new tests
pytest tests/unit/test_*_comprehensive.py tests/unit/test_*_property_based.py -v

# Database tests only
pytest tests/unit/test_reflection_database_comprehensive.py -v

# Search tests only
pytest tests/unit/test_search_comprehensive.py -v

# Property-based tests only
pytest tests/unit/test_utilities_property_based.py -v
```

### Run Specific Test

```bash
# By class
pytest tests/unit/test_reflection_database_comprehensive.py::TestReflectionDatabaseStorage -v

# By method
pytest tests/unit/test_reflection_database_comprehensive.py::TestReflectionDatabaseStorage::test_store_conversation -xvs

# With coverage
pytest tests/unit/test_reflection_database_comprehensive.py::TestReflectionDatabaseStorage -v --cov=session_buddy
```

### Quick Coverage Check

```bash
pytest --cov=session_buddy -q
```

## Test File Organization

### Database Tests (`test_reflection_database_comprehensive.py`)

```
TestReflectionDatabaseInitialization  # Setup, connection, tables
TestReflectionDatabaseStorage         # Storing conversations/reflections
TestReflectionDatabaseRetrieval       # Searching conversations/reflections
TestReflectionDatabaseSearch          # Search operations
TestReflectionDatabaseErrorHandling   # Edge cases (empty, very long, special chars)
TestReflectionDatabaseConcurrency     # Concurrent operations
TestReflectionDatabaseMetadata        # Metadata preservation
```

### Search Tests (`test_search_comprehensive.py`)

```
TestFullTextSearch        # Basic search operations
TestSearchFiltering       # Result limiting, pagination
TestSemanticSearch        # Semantic similarity search
TestTagSearch            # Tag-based search
TestSearchPerformance    # Large dataset performance
TestSearchErrorHandling  # SQL injection, Unicode, special chars
```

### Property-Based Tests (`test_utilities_property_based.py`)

Uses Hypothesis to generate 100+ test cases for each test

```
TestSessionLoggerPropertyBased      # Logger with random inputs
TestQualityScorePropertyBased       # Quality metrics calculations
TestUtilityStringHandling           # String edge cases
TestUtilityContainers              # Container operations
TestUtilityNumbers                 # Numeric operations
TestUtilityBooleanLogic            # Boolean combinations
TestUtilityEdgeCases               # Edge cases (empty, Unicode, very long)
```

## Common Patterns

### Async Database Fixture

```python
@pytest.fixture
async def initialized_db():
    """Proper fixture for async database tests."""
    db = ReflectionDatabase(":memory:")
    await db.initialize()  # CRITICAL: must await
    yield db
    db.close()


@pytest.mark.asyncio
async def test_something(initialized_db):
    result = await initialized_db.store_conversation("text", {})
    assert result is not None
```

### Property-Based Testing

```python
@given(st.text(min_size=1, max_size=100))
def test_with_random_text(text: str):
    """Hypothesis generates 100+ test cases."""
    # Your test code here
    assert len(text) >= 1
```

### Search Testing with Fixture

```python
@pytest.fixture
async def searchable_db():
    db = ReflectionDatabase(":memory:")
    await db.initialize()
    await db.store_conversation("content", {"key": "value"})
    yield db
    db.close()


@pytest.mark.asyncio
async def test_search(searchable_db):
    results = await searchable_db.search_conversations("content", limit=10)
    assert isinstance(results, list)
```

## Test Statistics

| Category | Count | Pass Rate | Status |
|----------|-------|-----------|--------|
| Database | 28 | 97% | 🟢 |
| Search | 27 | 100% | 🟢 |
| Property-Based | 13 | 100% | 🟢 |
| **Total** | **68** | **100%** | **✅** |

## Debugging Failed Tests

### Check Test Output

```bash
# Verbose output
pytest tests/unit/test_reflection_database_comprehensive.py -xvs

# Show local variables
pytest tests/unit/test_reflection_database_comprehensive.py -xvs --tb=long

# Stop on first failure
pytest tests/unit/test_reflection_database_comprehensive.py -x
```

### Database Issues

```bash
# Test just initialization
pytest tests/unit/test_reflection_database_comprehensive.py::TestReflectionDatabaseInitialization -xvs

# Check if async is working
pytest tests/unit/test_reflection_database_comprehensive.py -xvs --tb=short
```

### Hypothesis Issues

```bash
# Show Hypothesis statistics
pytest tests/unit/test_utilities_property_based.py -v --hypothesis-show-statistics

# Replay specific failing example
# (Hypothesis prints the failing example, add it to the test)
```

## Next Steps for Coverage Improvement

### 1. Session Manager Tests (2 hours)

```bash
# Complete framework ready
pytest tests/unit/test_session_manager_comprehensive.py -v
```

### 2. Server Tests (3 hours)

```bash
# New tests needed
pytest tests/unit/test_server.py -v  # TODO
```

### 3. Tools Tests (4 hours)

```bash
# New tests needed
pytest tests/unit/test_session_tools.py -v      # TODO
pytest tests/unit/test_memory_tools.py -v       # TODO
pytest tests/unit/test_search_tools.py -v       # TODO
```

## Useful References

- **Database API:** session_buddy/reflection_tools.py
- **Test Files:** tests/unit/test\_\*\_comprehensive.py
- **Progress Report:** docs/TEST-IMPROVEMENT-PROGRESS.md
- **Final Summary:** docs/TEST-IMPROVEMENT-FINAL-SUMMARY.md

## Tips & Tricks

### Run Tests in Parallel

```bash
pytest -n auto  # Requires pytest-xdist
```

### Fail Fast

```bash
pytest -x  # Stop on first failure
pytest --tb=short  # Shorter error messages
```

### Generate Coverage Report

```bash
pytest --cov=session_buddy --cov-report=html
# Open htmlcov/index.html in browser
```

### Watch Tests (if using pytest-watch)

```bash
ptw  # Auto-re-run on file changes
```

______________________________________________________________________

**Last Updated:** October 26, 2025
**Status:** Ready for use  <!-- legacy status — see YAML frontmatter -->
**Coverage:** 68 tests, 100% passing
