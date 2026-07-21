---
status: complete
role: historical
date: 2026-07-16
last_reviewed: 2026-07-16
superseded_by: null
blocks_on: []
topic: architecture
---

# Code Refactoring Plan

**Status:** ✅ SHIPPED — historical, retained for lineage  <!-- legacy status — see YAML frontmatter -->
**Promoted 2026-07-15** after drift-sync verified all phases done via commits `c9081d8f` through `7944b5fa`.
**Supersedes:** Phase 1 (quick wins), Phase 2 (consolidation), Phase 3 (structural), Phase 4 (tool-specific), Phase 5 (extraction). All 16 items across phases 4/5 verified delivered.

## Analysis Summary

### Largest Files (Lines of Code)

1. crackerjack_integration.py - 1,632 lines
1. tools/crackerjack_tools.py - 1,340 lines
1. serverless_mode.py - 1,285 lines
1. quality_engine.py - 1,256 lines
1. llm_providers.py - 1,254 lines

### Quick Wins Identified

#### 1. Unused Code (from vulture)

- **Unused exception variables**: Use `_` instead of `exc_type, exc_val, exc_tb`
- **Unused imports**: `get_cached_chunk`, `get_token_usage_stats` in server.py
- **Unused variables**: `frame`, `max_age_hours`, `uv_trusted`, `claude_validation`
- **Unreachable code**: After return in crackerjack_integration.py:1481

#### 2. Code Duplication Patterns

- Exception handling patterns (can be consolidated)
- Similar validation logic across files
- Repeated dictionary building patterns
- Common async/await patterns

#### 3. Complexity Reduction Opportunities

- Long functions that can be split
- Nested if statements (use early returns)
- Repeated conditional logic
- Complex comprehensions (break into multiple lines)

## Refactoring Strategy

### Phase 1: Quick Wins (5-10% reduction)

- [x] Remove unused imports
- [x] Replace unused exception variables with `_`
- [x] Remove dead/unreachable code
- [x] Simplify exception handling patterns

### Phase 2: Code Consolidation (15-20% reduction)

- [x] Extract common patterns to utilities
- [x] Consolidate duplicate validation logic
- [x] Merge similar functions
- [x] Use decorators for common patterns

### Phase 3: Structural Improvements (10-15% reduction)

- [x] Simplify complex functions
- [x] Use dataclasses instead of dicts
- [x] Apply functional patterns
- [x] Use early returns to reduce nesting

### Phase 4: Tool-Specific Refactoring (20-25% reduction)

- [x] Consolidate crackerjack integration code
- [x] Simplify serverless mode
- [x] Streamline quality engine
- [x] Optimize LLM providers

## Expected Results

**Before**: ~38,173 total lines
**Target**: ~28,000 lines (25-30% reduction)
**Method**: Maintain all functionality through refactoring only

## Refactoring Principles

1. **DRY (Don't Repeat Yourself)**: Extract common patterns
1. **KISS (Keep It Simple, Stupid)**: Simplify complex logic
1. **YAGNI (You Ain't Gonna Need It)**: Remove unused features
1. **Single Responsibility**: One function, one purpose
1. **Early Returns**: Reduce nesting with guard clauses
1. **Type Safety**: Use type hints and dataclasses

## Testing Strategy

- Run full test suite after each phase
- Verify coverage doesn't decrease
- Test all MCP tools manually
- Check for regressions

## Risk Mitigation

- Make small, incremental changes
- Commit frequently
- Run tests after each file
- Keep original behavior intact
- Document changes
