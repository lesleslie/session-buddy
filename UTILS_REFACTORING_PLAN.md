# Utils Directory Refactoring Plan

**Created:** 2026-02-03
**Status:** 📋 Planning
**Goal:** Improve codebase discoverability through descriptive naming

`★ Insight ─────────────────────────────────────`
This refactoring follows the "self-documenting code" principle: file names should immediately convey their purpose without requiring developers to open them. Generic names like `utils.py` and `helpers.py` create navigation friction, especially in larger codebases.
`─────────────────────────────────────────────────`

## Problem Analysis

### Current State
- **26 files** in `session_buddy/utils/`
- **13 files** (50%) use generic suffixes (`_utils`, `_helpers`, `_helper`)
- **Inconsistent naming** creates cognitive load

### Impact
- New developers must open files to understand purpose
- Codebase navigation is slower
- Duplicate functionality is harder to detect (e.g., `git_utils.py` vs `git_operations.py`)

## Refactoring Strategy

### Phase 1: High Priority (Clear Redundancy or Ambiguity)

#### 1.1 Git Operations Separation
**Issue:** `git_utils.py` (164 lines) vs `git_operations.py` (687 lines)
- `git_utils.py`: Contains **worktree operations** (poorly named)
- `git_operations.py`: Contains **git command execution** utilities

**Action:**
- Rename `git_utils.py` → `git_worktrees.py`
- Keep `git_operations.py` as-is (name is accurate)

**Imports to Update:** 1 file
- `session_buddy/quality_engine.py:33`

---

#### 1.2 Quality Scoring Versioning
**Issue:** `quality_utils.py` (264 lines) + `quality_utils_v2.py` (889 lines)
- V1: Basic score extraction utilities
- V2: Comprehensive quality scoring with Crackerjack integration

**Action:**
- Rename `quality_utils.py` → `quality_score_parser.py` (describes actual purpose)
- Rename `quality_utils_v2.py` → `quality_scoring.py` (primary implementation)
- Keep V2 as the main quality scoring system
- V1 becomes a specialized parser utility

**Imports to Update:** 2 files
- `session_buddy/quality_engine.py`
- `session_buddy/utils/quality_scoring.py` (self-import)

---

### Phase 2: Medium Priority (Improve Discoverability)

#### 2.1 Replace `*_utils.py` Suffix (7 files)

| Current Name | Better Name | Rationale | Import Count |
|-------------|-------------|-----------|--------------|
| `file_utils.py` | `filesystem.py` | Describes domain (filesystem operations) | 2 |
| `format_utils.py` | `text_formatter.py` | Describes function (formatting text) | 0 |
| `logging_utils.py` | `log_helpers.py` | Merge with `logging.py` or clarify as helpers | 0 |
| `reflection_utils.py` | `memory_operations.py` | Matches domain (memory/reflection system) | 0 |

**Low Priority (consider later):**
- `tool_wrapper.py` - Already specific enough
- `lazy_imports.py` - Already specific enough

---

#### 2.2 Replace `*_helpers.py` Suffix (3 files)

| Current Name | Better Name | Rationale | Import Count |
|-------------|-------------|-----------|--------------|
| `database_helpers.py` | `database_tools.py` | "Tools" > "helpers" (more active) | 4 |
| `error_handlers.py` | `error_management.py` | Describes function (managing errors) | 15+ |
| `server_helpers.py` | `server_utilities.py` | "Utilities" > "helpers" | 1 |

---

#### 2.3 Replace `*_helper.py` Suffix (1 file)

| Current Name | Better Name | Rationale | Import Count |
|-------------|-------------|-----------|--------------|
| `subprocess_helper.py` | `subprocess_executor.py` | Describes function (executing subprocesses) | 20+ |

---

## Migration Strategy

### Option A: Big Bang (Recommended for this codebase)
1. Create all new files with correct names
2. Add deprecation warnings to old files
3. Update all imports in single commit
4. Remove deprecated files in next release

**Pros:** Clean migration, clear history
**Cons:** Large single commit

### Option B: Gradual (Alternative)
1. Add aliases in `__init__.py` for old names
2. Update imports gradually over multiple PRs
3. Remove aliases after transition period

**Pros:** Smaller, reviewable changes
**Cons:** Longer migration period, potential confusion

### Recommendation: **Option A**
- Session Buddy is actively developed
- Import scope is manageable (50+ files, not hundreds)
- Single clear migration prevents technical debt

---

## Implementation Steps

### Step 1: Preparation
- [ ] Create this plan document ✅
- [ ] Identify all import locations
- [ ] Verify test coverage for affected modules

### Step 2: File Renaming (High Priority)
- [ ] Rename `git_utils.py` → `git_worktrees.py`
- [ ] Rename `quality_utils.py` → `quality_score_parser.py`
- [ ] Rename `quality_utils_v2.py` → `quality_scoring.py`

### Step 3: Import Updates
- [ ] Update imports in `session_buddy/quality_engine.py`
- [ ] Update imports in `session_buddy/utils/quality_scoring.py`
- [ ] Update imports in tests (2 test files)

### Step 4: Verification
- [ ] Run all tests with `pytest -m "not slow"`
- [ ] Run type checking with `crackerjack typecheck`
- [ ] Verify no broken imports with `grep -r "from.*git_utils\|quality_utils"`

### Step 5: Medium Priority (Optional)
- [ ] Rename `*_utils.py` files (4 high-impact files)
- [ ] Rename `*_helpers.py` files (3 high-impact files)
- [ ] Rename `*_helper.py` files (1 high-impact file)
- [ ] Update all imports across codebase
- [ ] Full test suite run

---

## Rollback Plan

If issues arise after deployment:
1. Revert commit(s) renaming files
2. Restore original names immediately
3. Investigate failure in isolated branch
4. Retry with improved migration strategy

**Estimated Rollback Time:** <5 minutes (git revert)

---

## Success Metrics

- ✅ All files have descriptive names (no `*_utils.py` or `*_helpers.py`)
- ✅ All tests passing (`pytest -m "not slow"`)
- ✅ No broken imports (`grep` verification)
- ✅ Type checking passes (`crackerjack typecheck`)
- ✅ Code review approval from team

---

## References

- Original insight: Naming agent's success demonstrates descriptive naming eliminates ambiguity
- CLAUDE.md guidance: "EVERY LINE OF CODE IS A LIABILITY" - clarity prevents technical debt
- Python naming conventions: PEP 8 (modules should have short, all-lowercase names)

---

## Notes

- This refactoring aligns with Phase 2 architecture improvements (clean layer separation)
- Consider running this refactoring through code review before implementation
- Some files (like `tool_wrapper.py`, `lazy_imports.py`) are already well-named and don't need changes
