---
status: shipped
role: implementation
date: 2026-07-16
last_reviewed: 2026-07-16
superseded_by: null
blocks_on: []
topic: persistence
---

# Checkpoint Async Refactor (Multi-Session MCP Contention Fix)

**Date:** 2026-07-16
**Status:** shipped, implementation — single-flight + RED→GREEN integration test  <!-- legacy status — see YAML frontmatter -->
**Owner:** Claude Code (mahavishnu session 854beabd, debug followup chain)
**Scope:** Eliminate the per-call latency and concurrency bottleneck in
session-buddy's `tools/call "checkpoint"` path so concurrent Claude Code
sessions can each call it without timing out.
**Purpose:** The mahavishnu followup
`docs/followups/2026-07-16-multi-session-mcp-contention.md` documented the
symptom (`-32000 transport dropped mid-call`). Three diagnostic commits
identified the bottleneck layers but each `to_thread` patch surfaced
another sync subprocess site. This plan addresses all of them in one
coherent refactor with single-flight coalescing as the centerpiece.

## 1. Outcome

The integration test
`tests/integration/test_concurrent_checkpoint_load.py::test_six_parallel_checkpoint_calls_complete_within_budget`
goes from RED → GREEN:

- 6 parallel `tools/call "checkpoint"` calls all complete within `WALL_BUDGET = 90s`.
- Per-call timeout (`PER_CALL_TIMEOUT = 30s`) is never hit.
- Wall-clock for 6 parallel calls is ≪ serial execution time.

**Success signal**: a fresh `session_buddy start` followed by the integration
test passes cleanly. Manual reproduction script (mahavishnu followup)
also reports `0/6 failures` with `wall: <10s` for 6 identical concurrent
checkpoint calls.

## 2. Goals

1. Convert all sync subprocess calls in the `tools/call "checkpoint"`
   code path to async-safe equivalents so the uvicorn event loop stays
   unblocked.
2. Add **single-flight coalescing** keyed on `(working_directory,
   is_manual, session_phase)` so concurrent identical requests share
   one computation. The 4-Stop-hook-firing-same-query case becomes
   effectively 1 subprocess run, not 4.
3. Preserve backward compatibility: direct unit-test calls to internal
   helpers stay sync and accept `subprocess.run` monkeypatches.

## 3. Non-Goals

1. Reducing per-call latency below ~30s through caching or fast paths.
   The plan focuses on CONCURRENCY (multiple callers); serial latency
   optimization is a separate effort.
2. Changing the crackerjack subprocess behavior (what it runs, how
   long it runs).
3. Multi-tenant isolation or per-session state partitioning. Single-flight
   is keyed only on request parameters, not on caller identity.
4. Replacing `subprocess.run` with `asyncio.create_subprocess_exec` in
   every helper. The `asyncio.to_thread(sync_fn)` pattern is sufficient
   for non-blocking I/O and keeps the helper signatures unchanged.

## 4. Current Findings

### Measured latency (2026-07-16, after partial fixes in commits `3c83f33d`
and `d67a531c`):

```
[warm1] init=0.02s checkpoint=43.42s status=200
[warm2] init=0.01s checkpoint=38.12s status=200
```

The init call dropped from 98s → 0.02s — the event loop is free. The
checkpoint call itself is 38-43s, dominated by:

- `crackerjack_integration.py:173` — `execute_command` (sync `subprocess.run`)
- `git_operations.py:120` — `_run_git_command` (sync `subprocess.run` × N for git add/commit)
- `git_worktrees.py` — 14 `subprocess.run` sites called transitively from `create_checkpoint_commit`
- `quality_engine.py::perform_strategic_compaction` — `_optimize_git_repository` (sync subprocess chain)
- `quality_scoring.py` — already wrapped in `asyncio.to_thread` (commits `3c83f33d`)

The actual queue is single-server (uvicorn single worker), single-threaded
async loop. With my partial fixes, parallel calls would each spawn worker
threads but each thread's individual subprocess work remains slow.

### Why to_thread alone is insufficient

With 6 parallel calls each spawning ~3-5 subprocesses via `asyncio.to_thread`,
Python's default thread pool (`min(32, cpu_count+4)`) saturates around 12-20
threads. Each call's per-call latency remains 40s. With `PER_CALL_TIMEOUT=30s`
in the integration test, all 6 still fail with `httpx.ReadTimeout`.

The fundamental issue: 4 Stop hooks firing simultaneously is **redundant work**,
not parallel work deserving of 4 subprocess runs. The architectural fix is
**single-flight coalescing**.

### Why this is "doing it right"

Per systematic-debugging Phase 4.5: "If 3+ fixes failed → STOP and question
architecture. Discuss with your human partner before attempting more fixes."
We've now attempted 3 to_thread patches. Each fix revealed the next bottleneck.
The user explicitly chose the "do this right" path (comprehensive async refactor).

## 5. Architecture

### Three coordinated changes

**A. Async-safe subprocess in the checkpoint path** (extends prior commits)
- Continue `asyncio.to_thread(sync_fn, ...)` wrapping for the remaining
  sync subprocess sites in `git_operations.py`, `git_worktrees.py`,
  `quality_engine.py::perform_strategic_compaction`, and the auto-compaction
  path inside `_checkpoint_impl`.

**B. Single-flight coalescing on `tools/call "checkpoint"`**
- At the MCP-tool entry point (`mcp/tools/session/session_tools.py:
  checkpoint_session_tool` → `_checkpoint_impl`), wrap the entire checkpoint
  computation in a single-flight keyed on `(working_directory, is_manual)`.
- First caller runs the computation; concurrent identical callers `await`
  the same `asyncio.Future` and receive the same result.
- This is the architectural fix per the mahavishnu followup's
  Recommendation A+B (single-flight + non-blocking).

**C. Test the new behavior with unit tests**
- Add `tests/unit/test_session_tools_single_flight.py` with deterministic
  mocks verifying that 4 concurrent identical `checkpoint_session_tool`
  invocations invoke the underlying session-manager ONCE.

### Why single-flight is the centerpiece

Empirically (from mahavishnu followup reproduction): when 4 Claude Code
sessions end within the same second, all 4 call `tools/call "checkpoint"`
with the same `(working_directory, is_manual=True)` arguments. Single-flight
collapses those 4 redundant calls into 1 computation. Per-call latency
becomes irrelevant — only wall-clock matters, and that drops from `4 × 40s`
(serialized) to `~40s` (one shared computation).

## 6. Implementation Phases

### Phase 1: Audit remaining sync subprocess sites

**Goal:** Comprehensive list of every sync `subprocess.run` / `subprocess.Popen`
in the checkpoint path, with classification: to_thread candidate vs no-op.

**Tasks:**
- Grep all sync subprocess calls under `session_buddy/` reachable from
  `tools/call "checkpoint"`.
- For each, classify:
  - **A1 — fast (<100ms)**: no async conversion needed
  - **A2 — medium (100ms–5s)**: wrap caller with `asyncio.to_thread`
  - **A3 — slow (>5s)**: wrap caller + consider single-flight
- Output: `docs/plans/2026-07-16-checkpoint-subprocess-audit.md` with the table.

**Exit criteria:** audit doc committed with no "?" rows; each A2/A3 site
has an owner line.

#### Integration Contract (Phase 1)

- **Triggered from**: session startup, manual request.
- **Returns to / updates**: `docs/plans/2026-07-16-checkpoint-subprocess-audit.md`.
- **Demonstrable by**: reading the audit doc; every sync subprocess call
  in the checkpoint path has a classification row.
- **Rollback signal**: not applicable — Phase 1 is read-only.
- **Observability added**: the audit itself is the artifact.

### Phase 2: Wrap remaining sync subprocess sites with `asyncio.to_thread`

**Goal:** Every A2/A3 site from the Phase 1 audit dispatches its sync
subprocess in a worker thread instead of on the event loop.

**Tasks:**
- For each A2 site, add `asyncio.to_thread(sync_fn, ...)` at the caller.
- For each A3 site, same + ensure the calling function is `async def`
  (if not already).
- Run integration test after each batch — should remain RED until Phase 3.
- Verify unit tests for those modules still pass.

**Exit criteria:** every site marked A2 or A3 in the audit is wrapped;
`grep -n "subprocess.run" session_buddy/` reachable from the checkpoint
path returns only A1 sites or sites already wrapped.

#### Integration Contract (Phase 2)

- **Triggered from**: `tools/call "checkpoint"`, `tools/call "end"`, hooks.
- **Returns to / updates**: subprocess work runs in worker threads; event
  loop stays responsive.
- **Demonstrable by**: existing `test_concurrent_checkpoint_load.py` test —
  per-call latency drops (but test still RED until Phase 3).
- **Rollback signal**: regression in any unit test for the modified modules.
- **Observability added**: none beyond existing logs.

### Phase 3: Single-flight coalescing on `tools/call "checkpoint"`

**Goal:** Concurrent identical checkpoint requests share one computation.

**Tasks:**
- Add `_in_flight_checkpoint: dict[FlightKey, asyncio.Future[dict]]` at
  module level in `mcp/tools/session/session_tools.py`.
- Define `FlightKey = tuple[str, bool]` = `(working_directory, is_manual)`.
- Wrap `_checkpoint_impl`'s body in a single-flight guard:
  ```python
  async def checkpoint_session_tool(working_directory, is_manual=False):
      key = (str(working_directory), is_manual)
      if key in _in_flight_checkpoint:
          return await _in_flight_checkpoint[key]
      future = asyncio.get_event_loop().create_future()
      _in_flight_checkpoint[key] = future
      try:
          result = await _original_checkpoint_impl(working_directory, is_manual)
          future.set_result(result)
          return result
      except BaseException as exc:
          future.set_exception(exc)
          raise
      finally:
          _in_flight_checkpoint.pop(key, None)
  ```
- Add unit tests for single-flight behavior (4 concurrent calls → 1 underlying).

**Exit criteria:** `test_concurrent_checkpoint_load.py` passes; new unit
tests pass; existing unit tests for `_checkpoint_impl` still pass.

#### Integration Contract (Phase 3)

- **Triggered from**: `tools/call "checkpoint"` invocations.
- **Returns to / updates**: identical concurrent calls share one result.
- **Demonstrable by**: integration test passes (RED → GREEN); new
  `test_session_tools_single_flight.py` tests prove the coalescing.
- **Rollback signal**: integration test fails again OR existing tests
  show non-coalesced behavior under concurrent identical requests.
- **Observability added**: log line `"checkpoint_single_flight: key={key}
  coalesced={count}"` per coalesced call.

### Phase 4: Documentation + PLAN_INDEX update

**Goal:** Future maintainers can find the architectural decision and the
test that pins the regression.

**Tasks:**
- Update this plan's status to `shipped, implementation`.
- Update `docs/plans/PLAN_INDEX.md` with a new active row.
- Update the mahavishnu followup `docs/followups/2026-07-16-multi-session-mcp-contention.md`
  to reflect that the architectural fix is now landed; close the followup.

**Exit criteria:** PLAN_INDEX entry, followup status flipped, plan marked
shipped.

#### Integration Contract (Phase 4)

- **Triggered from**: Phase 3 GREEN signal.
- **Returns to / updates**: `docs/plans/PLAN_INDEX.md`,
  `docs/followups/2026-07-16-multi-session-mcp-contention.md`.
- **Demonstrable by**: reading the PLAN_INDEX; the followup's status is
  no longer "open".
- **Rollback signal**: not applicable — docs only.
- **Observability added**: not applicable.

## 7. Required Code Changes

| File | Change |
|------|--------|
| `mcp/tools/session/session_tools.py` | Wrap `_checkpoint_impl` body with single-flight guard; add `_in_flight_checkpoint` module state |
| `utils/git_operations.py` | Add `asyncio.to_thread` wrappers at caller level (audit Phase 1) |
| `utils/git_worktrees.py` | Same as above |
| `quality_engine.py` | Wrap `perform_strategic_compaction` body in to_thread where needed |
| `core/session_manager.py` | Possibly wrap `perform_strategic_compaction` body in to_thread |
| `tests/integration/test_concurrent_checkpoint_load.py` | No change (the existing test is the regression guard) |
| `tests/unit/test_session_tools_single_flight.py` | NEW — single-flight unit tests with mocked `_checkpoint_impl` |

## 8. Validation Matrix

| Tool / command | Expected outcome | Evidence location |
|----------------|------------------|-------------------|
| `RUN_PERFORMANCE_TESTS=1 pytest tests/integration/test_concurrent_checkpoint_load.py -v` | 1 passed in <90s | pytest output |
| `pytest tests/unit/ -v` | All unit tests pass (no regressions) | pytest output |
| `pytest tests/unit/test_session_tools_single_flight.py -v` | New tests pass | pytest output |
| `python3 -c "import asyncio; from session_buddy...; ..."` | 4 concurrent identical checkpoint calls → 1 underlying call | python repl or test output |
| `crackerjack run` (if quality gate required by repo) | green | crackerjack report |

## 9. Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Single-flight Future leaks if a caller never `await`s | Low | Use `try/finally` to always `pop` from the in-flight dict |
| `_checkpoint_impl` raises an exception that's not picklable | Medium | Wrap exception in a string-or-pickle-safe envelope; release future with `set_exception(exc)` |
| Coalescing hides errors (one caller fails, all coalesced callers see same error) | Acceptable — that's the point; all callers WOULD have failed anyway |
| Phase 1 audit surfaces >30 sites, making Phase 2 prohibitively large | Medium | Audit output drives commit-by-commit sequence; each commit = one logical batch (e.g., one module's sites) |
| Unit tests with sync monkeypatches break when callers become async | Low — only `_checkpoint_impl` becomes async; the helper functions stay sync and test-compatible |

## 10. Decision Rule

Done-enough = Phases 1-3 shipped (audit complete + all sites wrapped +
single-flight working) with the integration test GREEN. Phase 4 is
docs-only and ships with whichever commit closes the loop.

Stop condition per systematic-debugging skill: if Phase 3 single-flight
implementation produces a regression in any unit test for the modified
modules, STOP and discuss before continuing.

## 11. Cross-references

- Mahavishnu followup: `docs/followups/2026-07-16-multi-session-mcp-contention.md`
- Mahavishnu bodai-hooks fix (related but separate): commits `6cd61954`, `530d8380`
- Diagnostic commits in this repo: `1043ffec`, `3c83f33d`, `d67a531c`
- Integration test (RED until Phase 3): `tests/integration/test_concurrent_checkpoint_load.py`
- Systematic-debugging skill: phase 4.5 directive ("3 fixes failed → STOP") invoked this plan
