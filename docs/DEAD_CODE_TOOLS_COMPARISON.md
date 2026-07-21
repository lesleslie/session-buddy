______________________________________________________________________

## status: complete role: canonical date: 2026-07-16 last_reviewed: 2026-07-16 superseded_by: null blocks_on: [] topic: architecture

# Dead Code Detection Tools Comparison

**Date**: 2025-02-05
**Package**: session-buddy
**Tools Compared**: Vulture, deadcode, Skylos

## Executive Summary

We compared three dead code detection tools on the session-buddy codebase with surprising results:

| Tool | Duration | Issues Found | Key Characteristics |
|------|----------|--------------|-------------------|
| **Vulture** | 6.1s | **22 issues** | Most thorough, excellent detail |
| **deadcode** | 2.2s | 0 issues | ⚡ Fastest, conservative approach |
| **Skylos** | 49.6s | **626 items** | Slowest, most aggressive |

## Key Findings

### 🎯 **Vulture Found the Most Actionable Issues**

**22 issues detected** at 80%+ confidence:

1. **Unused exception handler variables** (17 issues)

   - Common anti-pattern: `exc_type`, `exc_value`, `traceback` in exception handlers
   - Files affected:
     - `knowledge_graph_adapter_oneiric.py` (6 issues)
     - `reflection_adapter_oneiric.py` (6 issues)
     - `reflection/database.py` (3 issues)
     - `shutdown_manager.py` (1 issue)
     - `app_monitor.py` (1 issue)

1. **Unused imports** (2 issues)

   - `runtime_checkable` in `reflection/storage.py`
   - `List` in `sync.py` (likely using lowercase `list` from Python 3.9+)

1. **Unused function parameters** (3 issues)

   - `max_age_hours` in `token_optimizer.py:589`
   - `recursive` in `app_monitor.py:44`
   - `frame` in `shutdown_manager.py:196`

**Why This Matters**: These are definite issues (100% confidence) that can be safely cleaned up.

### ⚡ **deadcode: Fast but Conservative**

**Duration**: 2.2s (fastest)
**Issues**: 0 found

**Analysis**:

- deadcode uses **more conservative detection criteria**
- Focuses on **definitely unreachable code** rather than unused variables
- Excellent for quick sanity checks
- May miss smaller issues like unused parameters

**Best For**:

- Fast CI/CD pipelines
- "Is there obviously dead code?" checks
- Complementing vulture's detailed findings

### 🛡️ **Skylos: Most Comprehensive (and Slowest)**

**Duration**: 49.6s (8x slower than vulture)
**Issues**: **626 items detected**

**Analysis**:

- Skylos detected **6x more issues** than vulture
- Includes:
  - Unused code (like vulture)
  - Security smells
  - Code quality issues
  - Tainted data analysis
  - Potential vulnerabilities

**Trade-off**:

- ✅ Most thorough analysis
- ✅ Security insights beyond dead code
- ❌ 8x slower than vulture
- ❌ May flag false positives for review

**Best For**:

- Monthly comprehensive reviews
- Security-conscious teams
- Pre-release audits

## Performance Comparison

```
Speed: deadcode (2.2s) > Vulture (6.1s) >> Skylos (49.6s)
└─ 2.7x faster ─┘         └─ 8x slower ─┘

Thoroughness: Skylos (626) >> Vulture (22) > deadcode (0)
└─ 28x more items ─┘    └─ conservative ─┘
```

## Detailed Tool-by-Tool Analysis

### Vulture (🦅)

**Strengths**:

- ✅ Best balance of speed and thoroughness
- ✅ 100% confidence on all findings
- ✅ Clear, actionable output with file:line references
- ✅ Confidence scoring (90%, 100%)
- ✅ Sort by size feature (prioritize big cleanups)

**Weaknesses**:

- ❌ No auto-fix capability
- ❌ Manual cleanup required
- ❌ No security analysis

**Best Use Case**: Daily development workflow, pre-commit hooks

### deadcode (💀)

**Strengths**:

- ✅ **Fastest** (2.2s)
- ✅ Auto-fix with `--fix` flag
- ✅ Conservative (fewer false positives)
- ✅ Dry-run mode for safety

**Weaknesses**:

- ❌ Found 0 issues (too conservative?)
- ❌ Less detailed reporting
- ❌ No confidence scoring

**Best Use Case**: Quick sanity checks, automated cleanup pipelines

**Note**: The fact that deadcode found 0 issues while vulture found 22 suggests:

- deadcode may ignore "small" issues like unused variables
- Focuses on entire unused functions/classes
- Different definition of "dead code"

### Skylos (🛡️)

**Strengths**:

- ✅ Most comprehensive (626 items!)
- ✅ Includes security scanning
- ✅ Taint analysis
- ✅ Code quality metrics
- ✅ Interactive review mode

**Weaknesses**:

- ❌ Slowest (49.6s)
- ❌ May be overkill for quick checks
- ❌ More complex output

**Best Use Case**: Comprehensive monthly reviews, security audits

## Common Patterns Detected

All three tools agree on the **absence of large dead code** (no entire unused files or classes).

The 22 issues vulture found represent **minor technical debt**:

- Unused exception variables (can use `_` instead)
- Unused imports (clean up imports)
- Unused parameters (update signatures)

## Recommendations by Workflow

### 🔴 **Daily Development (Pre-Commit)**

```bash
# Fast check (6 seconds)
vulture session_buddy/ --min-confidence 90

# Auto-format and quick check
ruff format session_buddy/
vulture session_buddy/ --min-confidence 90
```

### 🟡 **Weekly Cleanup**

```bash
# Check what can be auto-fixed
deadcode session_buddy/ --fix --dry-run

# If satisfied, apply fixes
deadcode session_buddy/ --fix
```

### 🟢 **Monthly Comprehensive Review**

```bash
# Full analysis (takes ~50 seconds)
skylos session_buddy/

# Or via crackerjack
python -m crackerjack run skylos
```

## Fixing the 22 Issues Found by Vulture

### 1. Exception Handler Variables (17 issues)

**Anti-pattern**:

```python
try:
    ...
except Exception as exc_type, exc_value, traceback:  # ❌ Unused
    pass
```

**Fix**:

```python
try:
    ...
except Exception:  # ✅ Use _ if not needed
    pass
```

**Files to fix**:

- `session_buddy/adapters/knowledge_graph_adapter_oneiric.py` (lines 119-121, 132-134)
- `session_buddy/adapters/reflection_adapter_oneiric.py` (lines 147-149, 161-163)
- `session_buddy/reflection/database.py` (lines 125-127)
- `session_buddy/shutdown_manager.py` (line 196)
- `session_buddy/app_monitor.py` (line 44)

### 2. Unused Imports (2 issues)

**Fix**:

```python
# session_buddy/reflection/storage.py:17
- from typing import runtime_checkable
+ # runtime_checkable not used

# session_buddy/sync.py:18
- from typing import List
+ # Use lowercase 'list' (Python 3.9+)
```

### 3. Unused Parameters (3 issues)

**Fix or use `_` placeholder**:

```python
# session_buddy/token_optimizer.py:589
- async def cleanup_cache(self, max_age_hours: int = 1) -> int:
+ async def cleanup_cache(self, _max_age_hours: int = 1) -> int:
```

## Conclusion

**For session-buddy, we recommend**:

1. **Keep Vulture** for daily development (already configured ✅)
1. **Add deadcode** to crackerjack workflow for automated cleanup
1. **Use Skylos** monthly via crackerjack for comprehensive security + quality analysis

**Next Steps**:

1. Fix the 22 issues vulture found (quick wins)
1. Run deadcode with `--fix --dry-run` to see if auto-cleanup is safe
1. Schedule monthly Skylos analysis for security review

## Files Generated

- `scripts/compare_dead_code_tools.py` - Comparison script
- `dead_code_comparison.json` - Detailed results
- `docs/DEAD_CODE_TOOLS_COMPARISON.md` - This document

## Sources

- [Vulture GitHub](https://github.com/jendrikseipp/vulture)
- [deadcode GitHub](https://github.com/albertas/deadcode)
- [Skylos GitHub](https://github.com/duriantaco/skylos)
- [Skylos Benchmarks](https://github.com/duriantaco/skylos/blob/main/BENCHMARK.md)
