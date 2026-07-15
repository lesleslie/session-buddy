# Phase 4 Refactoring Plan - Large Core Files

**Status:** ✅ SHIPPED — historical, retained for lineage  
**Promoted 2026-07-15** after drift-sync verified all Phase 4 days + Phase 5 done.
**Goal**: Target large core files (900+ lines) for modularization and refactoring
**Estimated Impact**: 2,000-3,500 line reduction

## Delivered LOC Reductions

| File | Before | After | Reduction | Commit |
|---|---|---|---|---|
| crackerjack_integration.py | 1,632 | 1,147 | -485 | `350bf197` |
| quality_engine.py | 1,256 | 1,023 | -233 | `2c945661` |
| serverless_mode.py | 1,285 | 219 | -1,066 | `87638657` |
| session_manager.py | 947 | (refactored) | - | `33306c93` |
| llm_providers.py | 1,254 | 777 | -477 | `ead3ebd8` |
| advanced_search.py | 1,023 | (Phase 5) | - | `18c198b9` |
| server_core.py | 983 | (Phase 5) | - | `7944b5fa` |
| natural_scheduler.py | 964 | (Phase 5) | - | `2e7e8988` |

## Phase 4 Overview

After successfully refactoring tool files in Phase 3 (758 lines eliminated), Phase 4 targets the largest files in the codebase for modularization, extraction of reusable components, and architectural improvements.

## Target Files Analysis

### Top 10 Largest Files

```
1. crackerjack_integration.py    1,632 lines
2. crackerjack_tools.py          1,340 lines
3. serverless_mode.py            1,285 lines
4. quality_engine.py             1,256 lines
5. llm_providers.py              1,254 lines
6. advanced_search.py            1,023 lines
7. server_core.py                  983 lines
8. natural_scheduler.py            964 lines
9. session_manager.py              947 lines
10. team_knowledge.py              924 lines
```

**Total lines in top 10**: 11,608 lines (30.4% of estimated 38k codebase)

## Phase 4 Strategy

### Approach

1. **Analyze each large file** for extraction opportunities
1. **Identify common patterns** across files
1. **Extract modules** where appropriate
1. **Create specialized utilities** for specific domains
1. **Maintain 100% functionality** throughout

### Focus Areas

1. **Modularization** - Break large files into logical modules
1. **Extraction** - Pull reusable components into utilities
1. **Simplification** - Reduce complexity and duplication
1. **Organization** - Better file structure and separation of concerns

## Priority Targets (Days 1-5)

### Day 1: Crackerjack Integration (1,632 lines)

**File**: `crackerjack_integration.py`
**Estimated Reduction**: 400-600 lines (25-37%)

**Analysis Needed**:

- Command execution patterns
- Output parsing logic
- Progress tracking
- Result aggregation
- Quality metrics calculation

**Extraction Opportunities**:

- `utils/crackerjack/command_execution.py` - Command runners
- `utils/crackerjack/output_parser.py` - Parse tool output
- `utils/crackerjack/progress_tracker.py` - Progress tracking
- `utils/crackerjack/metrics_aggregator.py` - Metrics collection

**Expected Structure**:

```
crackerjack_integration.py (1,032 lines after)
  └─ utils/crackerjack/
      ├─ command_execution.py (150 lines)
      ├─ output_parser.py (200 lines)
      ├─ progress_tracker.py (150 lines)
      └─ metrics_aggregator.py (100 lines)
```

### Day 2: Quality Engine (1,256 lines)

**File**: `quality_engine.py`
**Estimated Reduction**: 300-500 lines (24-40%)

**Analysis Needed**:

- Quality scoring algorithms
- Project health checks
- Code analysis integration
- Trend analysis
- Recommendation generation

**Extraction Opportunities**:

- `utils/quality/scoring.py` - Quality score algorithms
- `utils/quality/health_checks.py` - System health checks
- `utils/quality/trend_analysis.py` - Historical trends
- `utils/quality/recommendations.py` - Recommendation engine

**Expected Structure**:

```
quality_engine.py (756-956 lines after)
  └─ utils/quality/
      ├─ scoring.py (150 lines)
      ├─ health_checks.py (150 lines)
      ├─ trend_analysis.py (100 lines)
      └─ recommendations.py (100 lines)
```

### Day 3: Serverless Mode (1,285 lines)

**File**: `serverless_mode.py`
**Estimated Reduction**: 300-450 lines (23-35%)

**Analysis Needed**:

- Storage backend implementations
- Session serialization
- State management
- Backend-specific adapters
- Configuration handling

**Extraction Opportunities**:

- `backends/redis_backend.py` - Redis storage implementation
- `backends/s3_backend.py` - S3-compatible storage
- `backends/local_backend.py` - Local file storage
- `utils/session_serialization.py` - Serialization utilities

**Expected Structure**:

```
serverless_mode.py (835-985 lines after)
  └─ backends/
      ├─ redis_backend.py (150 lines)
      ├─ s3_backend.py (150 lines)
      ├─ local_backend.py (100 lines)
      └─ base_backend.py (100 lines)
```

### Day 4: Session Manager (947 lines)

**File**: `core/session_manager.py`
**Estimated Reduction**: 250-400 lines (26-42%)

**Analysis Needed**:

- Session lifecycle operations
- Quality assessment integration
- Git operations
- Context management
- State tracking

**Extraction Opportunities**:

- `core/lifecycle.py` - Session lifecycle operations
- `core/quality_assessment.py` - Quality checks
- `core/context_manager.py` - Context handling
- `core/state_tracker.py` - State management

**Expected Structure**:

```
session_manager.py (547-697 lines after)
  └─ core/
      ├─ lifecycle.py (150 lines)
      ├─ quality_assessment.py (100 lines)
      ├─ context_manager.py (100 lines)
      └─ state_tracker.py (100 lines)
```

### Day 5: LLM Providers (1,254 lines)

**File**: `llm_providers.py`
**Estimated Reduction**: 350-500 lines (28-40%)

**Analysis Needed**:

- Provider-specific implementations
- API client wrappers
- Response formatting
- Error handling per provider
- Configuration management

**Extraction Opportunities**:

- `llm/providers/openai_provider.py` - OpenAI implementation
- `llm/providers/gemini_provider.py` - Google Gemini
- `llm/providers/ollama_provider.py` - Ollama local
- `llm/base_provider.py` - Base provider class
- `llm/response_formatter.py` - Response formatting

**Expected Structure**:

```
llm_providers.py (754-904 lines after)
  └─ llm/
      ├─ base_provider.py (150 lines)
      ├─ response_formatter.py (100 lines)
      └─ providers/
          ├─ openai_provider.py (150 lines)
          ├─ gemini_provider.py (150 lines)
          └─ ollama_provider.py (150 lines)
```

## Secondary Targets (Days 6-8)

### Day 6: Advanced Search (1,023 lines)

**Estimated Reduction**: 250-350 lines (24-34%)

**Extraction Opportunities**:

- Faceted search logic
- Full-text indexing
- Aggregation functions
- Query builders

### Day 7: Server Core (983 lines)

**Estimated Reduction**: 200-300 lines (20-31%)

**Extraction Opportunities**:

- MCP server setup
- Tool registration logic
- Middleware configuration
- Request handling

### Day 8: Natural Scheduler (964 lines)

**Estimated Reduction**: 200-300 lines (21-31%)

**Extraction Opportunities**:

- Time parsing logic
- Schedule management
- Reminder system
- Task queue

## Estimated Impact Summary

### Priority Targets (Days 1-5)

| File | Current | Estimated After | Reduction | % |
|------|---------|----------------|-----------|---|
| crackerjack_integration.py | 1,632 | 1,032-1,232 | 400-600 | 25-37% |
| quality_engine.py | 1,256 | 756-956 | 300-500 | 24-40% |
| serverless_mode.py | 1,285 | 835-985 | 300-450 | 23-35% |
| session_manager.py | 947 | 547-697 | 250-400 | 26-42% |
| llm_providers.py | 1,254 | 754-904 | 350-500 | 28-40% |
| **TOTAL** | **6,374** | **3,924-4,774** | **1,600-2,450** | **25-38%** |

### Secondary Targets (Days 6-8)

| File | Current | Estimated After | Reduction | % |
|------|---------|----------------|-----------|---|
| advanced_search.py | 1,023 | 673-773 | 250-350 | 24-34% |
| server_core.py | 983 | 683-783 | 200-300 | 20-31% |
| natural_scheduler.py | 964 | 664-764 | 200-300 | 21-31% |
| **TOTAL** | **2,970** | **2,020-2,320** | **650-950** | **22-32%** |

### Phase 4 Total Potential

- **Files targeted**: 8 large files
- **Current lines**: 9,344 lines
- **Estimated reduction**: 2,250-3,400 lines (24-36%)
- **New modules created**: ~25-30 specialized modules
- **Duration**: 8 working days

## Implementation Principles

### 1. Module Extraction Pattern

```python
# Before: All in one file
class BigClass:
    def method1(self): ...
    def method2(self): ...
    def method3(self): ...

    # ... 50 more methods


# After: Separated by concern
# component1.py
class Component1:
    def method1(self): ...


# component2.py
class Component2:
    def method2(self): ...


# main_file.py
from .component1 import Component1
from .component2 import Component2


class BigClass:
    def __init__(self):
        self.comp1 = Component1()
        self.comp2 = Component2()
```

### 2. Backend/Provider Pattern

```python
# Before: All providers in one file
class LLMProviders:
    def openai_call(self): ...
    def gemini_call(self): ...
    def ollama_call(self): ...


# After: Each provider separate
# providers/base.py
class BaseProvider: ...


# providers/openai_provider.py
class OpenAIProvider(BaseProvider): ...


# llm_providers.py
from .providers.openai_provider import OpenAIProvider
```

### 3. Utility Extraction Pattern

```python
# Before: Utility functions mixed with business logic
class Manager:
    def parse_output(self, text): ...  # 50 lines
    def calculate_score(self, data): ...  # 40 lines
    def main_logic(self): ...  # Uses above


# After: Utilities extracted
# utils/parsers.py
def parse_output(text): ...


# utils/scoring.py
def calculate_score(data): ...


# manager.py
from utils.parsers import parse_output
from utils.scoring import calculate_score


class Manager:
    def main_logic(self): ...
```

## Testing Strategy

### For Each Refactoring

1. **Before**: Read file, count lines, test imports
1. **Extract**: Create new modules with extracted code
1. **Integrate**: Update original file to use extracted modules
1. **Test**: Verify imports work, no functionality changes
1. **Commit**: Individual commit per file refactored

### Validation Checklist

- ✅ All imports successful
- ✅ Original file significantly smaller
- ✅ New modules are focused and cohesive
- ✅ No duplicate code between modules
- ✅ Clear module boundaries
- ✅ 100% functional compatibility

## Success Criteria

### Phase 4 Goals

- [x] Reduce 8 large files by 2,250-3,400 lines (24-36%)
- [x] Create 25-30 focused, reusable modules
- [x] Improve codebase organization and maintainability
- [x] Maintain 100% functional compatibility
- [x] All tests passing
- [x] Zero breaking changes

### Combined Progress (Phases 1-4)

- **Phase 1-2**: 34 lines (test infrastructure)
- **Phase 3**: 758 lines (tool file duplication)
- **Phase 4**: 2,250-3,400 lines (large file modularization)
- **Total**: 3,042-4,192 lines eliminated
- **Progress to goal**: 30-42% of 10,000 line target

## Risk Mitigation

### Potential Issues

1. **Import cycles** - Careful module organization needed
1. **Dependency injection** - May need to refactor DI setup
1. **Test updates** - Tests may reference old locations
1. **Documentation** - Need to update module references

### Mitigation Strategies

1. Use clear module hierarchies to avoid cycles
1. Leverage existing ACB DI patterns
1. Use import-based testing to catch issues early
1. Update CLAUDE.md as we go

## Next Steps

1. **Start with Day 1** - Analyze crackerjack_integration.py
1. **Create extraction plan** - Identify specific extraction boundaries
1. **Extract modules** - Create new focused modules
1. **Refactor main file** - Use extracted modules
1. **Test and commit** - Validate and commit changes
1. **Repeat** - Move to next file

Let's begin with **crackerjack_integration.py** (1,632 lines)! 🚀

______________________________________________________________________

*Previous phases: docs/archive/completion-reports/REFACTORING_PHASE3_COMPLETE.md*
