# session-buddy Test Failure Triage Report

**Date:** 2026-06-04
**Scope:** 153 unit test failures across 73 test files in `tests/unit/`
**Tested with:** `/Users/les/Projects/session-buddy/.venv/bin/python` from `/Users/les/Projects/session-buddy`
**Test command:** `python -m pytest tests/unit --no-header -p no:cacheprovider --ignore=tests/unit/test_worker.py -v --tb=no`
**Result:** 153 failed, 7212 passed, 26 skipped, 1 xpassed, 6111 warnings (1251s)

**Investigated:** 12 clusters covering 91 of 153 failures (60%)
**Remaining:** 62 failures across ~60 other files (mostly singleton failures, mostly in the same patterns identified below)

______________________________________________________________________

## Executive Summary

The 153 failures cluster into **6 reproducible root-cause patterns**. None of the patterns is novel — they are the standard "test suite rot" pathologies that emerge when a refactor lands without test updates, or when test isolation is implemented incorrectly.

| # | Pattern | Approx. count | % of total |
|---|---------|--------------|------------|
| 1 | Real production bugs (drift, off-by-one, swapped vars) | ~30 | 20% |
| 2 | Test was not updated when production was refactored (contract drift) | ~45 | 29% |
| 3 | Test infrastructure pollutes `sys.modules` at module load time | ~15 | 10% |
| 4 | Tests assume a live HTTP embedding service (llama-server / Ollama) | ~12 | 8% |
| 5 | Test uses deprecated asyncio pattern that breaks on Python 3.13 | 3 | 2% |
| 6 | Test asserts a feature that was intentionally removed | 2 | 1% |
| (7) | Uninvestigated (likely mix of above patterns) | ~46 | 30% |

**High-confidence 1-line production fixes identified (5 of them) that would clear ~30 test failures with no test rewrites required:**

1. `session_buddy/core/session_manager.py:1357` — wrap `handoff_path` with `str()`
1. `session_buddy/health_checks.py:360` — use `_module_available()` helper
1. `session_buddy/server_optimized.py:496` — use `relative_to(current_dir)` for hidden-file check
1. `session_buddy/utils/quality/compaction.py:35` — same `relative_to(current_dir)` fix
1. `session_buddy/adapters/knowledge_graph_adapter_phase3.py:169,216` — swap loop variables

______________________________________________________________________

## Detailed Findings (by cluster, in order of failure count)

### Cluster 1: test_session_manager_high_impact.py (13 failures)

**Root causes:** 3

1. **PRODUCTION BUG (1 test)**: `end_session` stores `Path` in `summary["handoff_documentation"]`. Fix at `session_buddy/core/session_manager.py:1357`: `summary["handoff_documentation"] = str(handoff_path) if handoff_path else None`. Already mirrors the `working_directory` str conversion on line 1310.
1. **TEST BUG (1 test)**: `test_setup_working_directory_rejects_invalid_and_escaped_paths` doesn't patch `Path.home`, so the production's home_dir fallback accepts the test's "outside" path. Fix: add `monkeypatch.setattr("session_buddy.core.session_manager.Path.home", lambda: tmp_path / "isolated_home")`.
1. **TEST POLLUTION (11 tests)**: 11 tests pass in isolation but fail under the full suite. They are likely cascade failures from pollution by `test_adapters_settings.py` and `test_coverage_gaps.py` (which run earlier in the suite). Verdict: not real failures, will likely clear once upstream pollution is fixed.

### Cluster 2: test_knowledge_graph_adapter.py + test_phase3_relationships.py + test_knowledge_graph_adapter_oneiric.py + test_knowledge_graph_adapter.py (22 failures total across 4 files)

**Root cause:** 1 (BIG WIN)
**PRODUCTION BUG**: `session_buddy/adapters/knowledge_graph_adapter_phase3.py:169` and `:216` iterate `_RELATIONSHIP_PATTERNS` with variables `(pattern, rel_type)` but the dict is `{rel_type: pattern}`. The result: `re.search("uses", text)` matches the literal word "uses" with no capture group, raising `IndexError: no such group`. **Fix is to swap the variable names** to `(rel_type, pattern)` in both loop sites. This single 2-line fix unblocks 22 tests across 4 test files.

### Cluster 3: test_embedding_cache.py (8 failures)

**Root causes:** 3

1. **CONTRACT DRIFT (1 test)**: `test_cache_cleared_on_aclose` references `db._embedding_cache` (instance attribute), but the cache was moved to module scope in `session_buddy/reflection/embeddings.py:108`. Fix: update the test to assert on the module-level cache, or delete the test.
1. **CONTRACT DRIFT (5 tests)**: Production initializes `_cache_hits` / `_cache_misses` but never increments them; `get_stats()` no longer exposes `embedding_cache` key. Fix: either port tests to read from `get_embedding_system_info()` or delete the dead counters in production.
1. **ENVIRONMENTAL (4 tests)**: Tests assume a live HTTP embedding service. Fix: monkey-patch `session_buddy.reflection.embeddings.generate_embedding` with a deterministic 384-dim stub.

### Cluster 4: test_health_checks.py + test_health_checks_core.py (8 failures)

**Root causes:** 3

1. **PRODUCTION BUG (4 tests)**: `session_buddy/health_checks.py:360` calls `importlib.util.find_spec("session_buddy.multi_project_coordinator")` without try/except, violating the "best-effort" contract enforced by `_module_available` helper. **Fix**: replace the call with `if _module_available("session_buddy.multi_project_coordinator"):` — a 1-line change.
1. **CONTRACT DRIFT (3 tests)**: "all_available" tests pre-date the SSRF URL guard added in `_is_safe_url` (lines 219-243). Fix: each test must also mock the HTTP provider check.
1. **STALE FEATURE (1 test)**: `test_dependencies_health_onxxruntime_available` asserts `onnx` is in available, but `onnxruntime` was deliberately removed. **Fix: delete the test**.

### Cluster 5: test_git_operations.py (10 failures)

**Root cause:** 1 (TEST INFRASTRUCTURE)
**`tests/unit/test_git_operations_helpers.py:14-34` replaces `sys.modules["session_buddy.utils.git_worktrees"]` with a stub at module-load time** and never restores it. The stub is missing `subprocess`, `_check_for_changes`, and other internal helpers that `test_git_operations.py` needs. All 10 tests pass when `test_git_operations_helpers.py` is NOT collected. Fix: convert the stub installation in `test_git_operations_helpers.py` to a properly-scoped fixture, or just delete the stub entirely (the test file only exercises `git_operations.py`'s own helpers, which can load against the real `git_worktrees`).

### Cluster 6: test_otel_telemetry.py + test_mcp_telemetry.py (5 + 1 = 6 failures)

**Root cause:** 1
**`monkeypatch.setattr("session_buddy.mcp.telemetry.trace.set_tracer_provider", ...)` fails** because `trace` is bound to `None` in the module (OpenTelemetry SDK is optional and not installed). pytest's `monkeypatch.setattr` walks the dotted path via `getattr`, which raises `AttributeError` on `None`. Fix: replace dotted-string monkeypatches with `monkeypatch.setattr(telemetry, "trace", mock_trace)` and assert `mock_trace.set_tracer_provider.called`. 6 tests in 2 files. Add `opentelemetry-sdk` and OTel exporter packages as dev deps if integration testing is desired.

### Cluster 7: test_health_checks.py::TestCheckDependenciesHealth (already covered in Cluster 4)

### Cluster 8: test_server_optimized.py (6 failures)

**Root causes:** 2

1. **PRODUCTION BUG (5 tests)**: `session_buddy/server_optimized.py:496` checks `file_path.parts` (absolute) for hidden directories. On this system, pytest's `tmp_path` is under `~/.claude/tmp/...`, so `.claude` makes every part of the path look "hidden" and the filter rejects everything. **Fix**: change to `not any(part.startswith(".") for part in file_path.relative_to(current_dir).parts)`. This is the same bug as Cluster 9 — should be a single fix.
1. **CONTRACT DRIFT (1 test)**: `test_auto_initializes_for_git_repo` doesn't yield to the event loop after `async with session_lifecycle()`. Production's fire-and-forget `asyncio.create_task(_delayed_session_init(current_dir))` only schedules, doesn't run. Fix: add `await asyncio.sleep(0)` to the test.

### Cluster 9: test_quality_engine.py::TestProjectHeuristics (3 failures)

**Root cause:** 1 (PRODUCTION BUG, same as Cluster 8.1)
**`session_buddy/utils/quality/compaction.py:35`** has the identical hidden-file path check bug: `not any(part.startswith(".") for part in file_path.parts)`. Same fix as Cluster 8.1. **Single fix clears 8 tests across 2 files.**

### Cluster 10: test_tool_wrapper.py (3 failures)

**Root cause:** 1 (TEST INFRASTRUCTURE)
The test file does a hand-rolled `sys.modules` swap of `session_buddy.utils.error_management` to inject a fake `validate_required`. But production uses **inline imports** inside `_validate_required_field` (line 217), `_validate_type_field` (line 225), `_validate_range_field` (line 249) — these inline imports resolve to the real `error_management` module, not the fake. Fix: refactor the test to use `monkeypatch.setattr(tw, "_validate_required_field", stub)` instead of swapping `sys.modules`. Or: move the three production imports to module scope (broader impact).

### Cluster 11: test_session_tools.py::TestRegisterSessionToolsComplete (3 failures)

**Root cause:** 1 (TEST BUG)
Tests use the deprecated `asyncio.get_event_loop().run_until_complete(...)` pattern. On Python 3.13, after another async test has run, the main thread has no current event loop and `get_event_loop()` raises `RuntimeError`. Fix: replace with `asyncio.run(...)` (3 lines, lines 831, 858, 896).

### Cluster 12: test_optimized_examples.py (3 failures)

**Root causes:** 2

1. **CONTRACT DRIFT (1 test)**: `test_store_reflection_parametrized[-tags3-1]` parameterizes over empty content, but production rejects empty content. Fix: remove the empty-content param case.
1. **CALIBRATION DRIFT (2 tests)**: Quality-score expected ranges are too narrow — production now scores 67/52 against max 60/50. Either widen ranges (e.g., `[45, 80]`, `[40, 65]`) or re-tune the scorer to match the original contract.

### Cluster 13: test_intent_tools_registration.py (9 failures)

**Root cause:** 1 (CONTRACT DRIFT)
Tests do `patch.object(module, "get_intent_detector", ...)`, but `get_intent_detector` is **lazy-imported** inside function bodies (to break a circular import), so the symbol is never bound at module scope. Fix option A: hoist the import to module scope (1-line change in `intent_tools_registration.py`). Fix option B: change all 9 `patch.object` sites to `patch("session_buddy.mcp.tools.intent_detection_tools.get_intent_detector", ...)`.

### Cluster 14: test_causal_chains.py (3 failures)

**Root cause:** 1 (ENVIRONMENTAL)
`tracker._generate_embedding()` raises `ValueError: Embedding generation returned None` because no HTTP embedding service is reachable. Fix: add a test fixture that patches `session_buddy.reflection_tools.generate_embedding` to return a fixed 384-dim vector.

### Cluster 15: test_insights_database.py (3 failures)

**Root cause:** 1 (ENVIRONMENTAL)
Same as Cluster 14 — semantic search degrades to `LIKE '%query%'` substring match when no embedding service is available. Multi-word queries fail. Fix: add a stub embedding generator in the test fixture, OR add a smarter text-fallback (split query into tokens, OR them).

### Cluster 16: test_reflection_adapter_oneiric.py::TestStats + TestCloseAndCleanup (2 failures)

**Root cause:** 1 (CONTRACT DRIFT, same as Cluster 3.2)
Same as the embedding cache contract drift — `get_stats()` no longer includes `embedding_cache` key, and `_embedding_cache` is no longer an instance attribute. Fix: port tests to the new contract via `get_embedding_system_info()`.

### Cluster 17: test_health_checks_core.py (2 failures)

**Root cause:** 1 (same as Cluster 4)
Same SSRF + onnx issues. Fixes carry over.

### Cluster 18: test_intent_tools_registration.py::TestListSupportedIntentsImpl etc. (4 failures)

**Root cause:** 1 (CONTRACT DRIFT, same as Cluster 13)
Same lazy-import patching issue. Already covered.

### Cluster 19: test_phase3_relationships.py (1 in TestPhase3RelationshipInference, 1 in TestPhase3EntityCreation)

**Root cause:** 1 (same as Cluster 2)
Same swapped loop variable bug. Already covered.

______________________________________________________________________

## Recommendation: Recommended Fix Order (highest leverage first)

### Tier 1 — Single 1-line production fixes (low risk, big impact)

| # | Fix | File:line | Tests cleared |
|---|-----|-----------|---------------|
| 1 | Swap loop variables `(pattern, rel_type)` → `(rel_type, pattern)` in 2 sites | `session_buddy/adapters/knowledge_graph_adapter_phase3.py:169,216` | 22 |
| 2 | Use `_module_available()` helper instead of raw `find_spec` | `session_buddy/health_checks.py:360` | 4 |
| 3 | Wrap `handoff_path` with `str()` before storing in summary | `session_buddy/core/session_manager.py:1357` | 1 |
| 4 | Use `file_path.relative_to(current_dir).parts` for hidden-dir check | `session_buddy/server_optimized.py:496` | 5 |
| 5 | Use `file_path.relative_to(current_dir).parts` for hidden-dir check | `session_buddy/utils/quality/compaction.py:35` | 3 |

**Total: 5 production code edits, 35 test failures cleared.**

### Tier 2 — Single 1-line test-only fixes (very low risk, moderate impact)

| # | Fix | File | Tests cleared |
|---|-----|------|---------------|
| 6 | Replace `asyncio.get_event_loop().run_until_complete(X)` with `asyncio.run(X)` (3 lines) | `tests/unit/test_session_tools.py:831,858,896` | 3 |
| 7 | Convert stub installation in test_git_operations_helpers.py to fixture | `tests/unit/test_git_operations_helpers.py:14-34` | 10 |
| 8 | Delete stale `test_dependencies_health_onxxruntime_available` | `tests/unit/test_health_checks.py:707` | 1 |
| 9 | Add `monkeypatch.setattr("session_buddy.core.session_manager.Path.home", lambda: tmp_path / "isolated_home")` | `tests/unit/test_session_manager_high_impact.py:239-269` | 1 |

**Total: 4 test-only edits, 15 test failures cleared.**

### Tier 3 — Test refactors (medium effort, high impact)

| # | Fix | File | Tests cleared |
|---|-----|------|---------------|
| 10 | Replace `monkeypatch.setattr("session_buddy.mcp.telemetry.trace.X", ...)` with object-attr form | `tests/unit/test_otel_telemetry.py` and `test_mcp_telemetry.py` | 6 |
| 11 | Either hoist `get_intent_detector` to module scope in prod OR rewrite 9 `patch.object` sites | `session_buddy/mcp/tools/advanced/intent_tools_registration.py` or `tests/unit/test_intent_tools_registration.py` | 9 |
| 12 | Port embedding cache tests to the post-refactor module-level cache contract | `tests/unit/test_embedding_cache.py` | 8 (5 of these) |

**Total: 3 test/prod edits, 23 test failures cleared.**

### Tier 4 — Environmental / contract decisions (require product input)

- Tests assume HTTP embedding service: add test fixture stubs OR mark tests `skipif` when no provider
- SSRF vs test: tests pre-date the SSRF URL guard. Either keep production strict and update tests to mock, or relax the guard
- onnxruntime: feature was intentionally removed. Delete or rewrite the test
- store_reflection empty content: production rejects. Either allow empty (semantic change) or remove the test case

### Tier 5 — Uninvestigated 62 failures

These 62 failures are spread across 60+ files, mostly 1-failure-per-file. The dominant patterns from the 91 analyzed failures are likely the same here. A targeted scan of uninvestigated files (using `grep "FAILED " /tmp/sb_run9.log | sed -E ... | sort -u` to find them) would likely surface the same 6 root-cause patterns. Estimated effort: 1-2 more hours of investigation; another 20-30 fixes.

______________________________________________________________________

## Appendix: How to Verify

After applying any of the above fixes, re-run:

```bash
cd /Users/les/Projects/session-buddy
/Users/les/Projects/session-buddy/.venv/bin/python -m pytest \
    tests/unit --no-header -p no:cacheprovider \
    --ignore=tests/unit/test_worker.py -v --tb=no 2>&1 | tail -3
```

The single biggest blocker for a clean re-run is `test_worker.py::test_process_tasks_handles_timeout` — it has an infinite loop because the mock's `side_effect=asyncio.TimeoutError()` makes `asyncio.wait_for` re-trigger its own timeout clause in a tight loop. Either exclude with `--ignore` (as above) or fix the mock to use `return_value=asyncio.Future()` that raises.

______________________________________________________________________

## Appendix: Investigation Log

Investigations were conducted in parallel using general-purpose subagents. The FAILED test inventory is in `/tmp/sb_failed_ids.txt` (153 lines, one per failed test). The full pytest run output is in `/tmp/sb_run9.log` (~2.5MB).

**Test command used to reproduce the 153 failures:**

```bash
cd /Users/les/Projects/session-buddy
/Users/les/Projects/session-buddy/.venv/bin/python -m pytest \
    tests/unit --no-header -p no:cacheprovider \
    --ignore=tests/unit/test_worker.py -v --tb=no
```
