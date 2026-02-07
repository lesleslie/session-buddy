# Dead Code Detection Guide

## Overview

This project uses **Vulture** to detect unused/dead Python code. Dead code includes:
- Unused functions, classes, and variables
- Unused imports
- Entire `.py` files that are never imported
- Unreachable code paths

## Tools Available

### 1. Vulture (Primary Tool) ✅

**Installation**: Already installed (`vulture==2.14`)

**What It Does**:
- Static analysis (doesn't execute code)
- Detects unused functions, classes, variables, imports
- Can detect entire unused files
- Fast and lightweight

**Usage**:

```bash
# Basic scan (80% confidence threshold)
vulture session_buddy/

# More aggressive scan (60% confidence)
vulture session_buddy/ --min-confidence 60

# Generate whitelist from current code
vulture session_buddy/ --make-whitelist

# Sort results by size (find biggest dead code first)
vulture session_buddy/ --sort-by-size

# Exclude specific paths
vulture session_buddy/ --exclude tests/,*/migrations/
```

**Configuration**: See `[tool.vulture]` in `pyproject.toml`

### 2. Deadcode (Alternative Tool)

**Installation**: `uv add deadcode`

**Advantages over Vulture**:
- Can automatically fix unused code (remove it)
- Better handling of false positives
- More flexible configuration
- Presented at EuroPython 2024 (actively maintained)

**Usage**:

```bash
# Find dead code
deadcode session_buddy/

# Auto-fix (remove dead code)
deadcode session_buddy/ --fix
```

### 3. Coverage-Based Detection (Complementary)

**Tool**: `pytest-cov` (already configured)

**What It Does**:
- Detects code that's never executed during tests
- Complementary to static analysis (finds different issues)

**Usage**:

```bash
# Run tests with coverage
pytest --cov=session_buddy --cov-report=html

# Check for 0% coverage files (potential dead code)
open htmlcov/index.html
```

## How Vulture Could Have Detected `acb_cache_adapter.py`

### Before Deletion

If `acb_cache_adapter.py` still existed:

```bash
# Scan entire codebase
vulture session_buddy/

# Would have shown:
# session_buddy/acb_cache_adapter.py:54: unused class 'ACBChunkCache' (100% confidence)
# session_buddy/acb_cache_adapter.py:191: unused class 'ACBHistoryCache' (100% confidence)
# session_buddy/acb_cache_adapter.py:306: unused function 'get_chunk_cache' (100% confidence)
# session_buddy/acb_cache_adapter.py:316: unused function 'get_history_cache' (100% confidence)
```

### Confidence Levels

- **100%**: Definitely unused (no imports found)
- **90-99%**: Very likely unused
- **80-89%**: Probably unused
- **60-79%**: Might be unused (more false positives)

## Integration with Development Workflow

### Pre-Commit Hook

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Check for dead code before committing
vulture session_buddy/ --min-confidence 90
if [ $? -ne 0 ]; then
    echo "❌ Dead code detected. Please review or add to whitelist."
    exit 1
fi
```

### CI/CD Pipeline

Add to `.github/workflows/quality.yml`:

```yaml
- name: Check for dead code
  run: |
    vulture session_buddy/ --min-confidence 80
```

### Crackerjack Integration

Add to crackerjack workflow:

```bash
# Before committing
crackerjack lint && vulture session_buddy/ --min-confidence 90
```

## Handling False Positives

### Whitelist File

Create `.vulture-whitelist.py` for exceptions:

```python
"""Vulture whitelist for false positives."""

# Dynamic attribute access
getattr(obj, attr_name)  # noqa: F401

# Library API exports (used by external code)
from session_buddy.server import mcp  # noqa: F401

# Protocol implementations
class MyProtocol(Protocol):  # noqa: F401
    def method(self): ...
```

### Common False Positives

1. **MCP Tool Exports**: Tools registered via decorators
2. **Protocol Implementations**: Abstract base classes
3. **Dynamic Imports**: `importlib.import_module()`
4. **Test Fixtures**: Used by pytest discovery
5. **CLI Commands**: Typer/Click command functions

## Best Practices

### 1. Confidence Thresholds

- **Pre-commit**: 90% (only block on definite dead code)
- **CI/CD**: 80% (catch more issues, manual review)
- **Manual Scan**: 60% (thorough cleanup)

### 2. Review Before Deleting

Always verify before removing dead code:

```bash
# 1. Scan with high confidence
vulture session_buddy/ --min-confidence 90

# 2. Search for references (grep/ripgrep)
rg "ACBChunkCache" session_buddy/

# 3. Check tests
rg "ACBChunkCache" tests/

# 4. If no references found, safe to delete
```

### 3. Commit Dead Code Removal Separately

```bash
# Good: Separate commit for dead code removal
git commit -m "refactor: remove dead code detected by vulture

- Remove unused acb_cache_adapter.py (335 lines)
- Replaced by native implementations in token_optimizer.py
- No imports or tests reference this file"
```

## Current Findings

As of latest scan (2025-02-05):

```bash
$ vulture session_buddy/ --min-confidence 80
```

**Found**: 19 dead code issues
- Unused exception handler variables (11)
- Unused imports (2)
- Unused parameters (5)
- Dead code paths (1)

**Action Items**:
1. Review unused imports (`List`, `runtime_checkable`)
2. Fix unsatisfiable `if` condition in `ollama_provider.py:190`
3. Clean up exception handler variables (use `_` instead)

## See Also

- [Vulture GitHub Repository](https://github.com/jendrikseipp/vulture)
- [Deadcode GitHub Repository](https://github.com/albertas/deadcode)
- [Python Dead Code Detection Guide](https://codecut.ai/vulture-automatically-find-dead-python-code/)
- [EuroPython 2024: Deadcode Talk](https://ep2024.europython.eu/session/deadcode-a-tool-to-find-and-fix-unused-dead-python-code/)
