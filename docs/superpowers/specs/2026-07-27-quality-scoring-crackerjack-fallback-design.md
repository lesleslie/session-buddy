# Quality-Scoring Crackerjack CLI Fallback — Design

> **Status:** Brainstorming complete. Pending user review.

**Date:** 2026-07-27
**Owner:** Session-Buddy maintainers
**Repo:** `/Users/les/Projects/session-buddy`

## Context

The recent `quality-scoring-field-audit` branch (commits `ceb181d7..63f4de63`) fixed what `_calculate_quality_metrics` does when specific metric keys are *missing from a result dict*. That fix distinguished "field absent" from "field present and zero," but it did not address what happens when *the upstream Crackerjack invocation fails entirely*.

The current metrics pipeline has three gaps:

1. **Producer-side**: When `execute_crackerjack_command`'s subprocess times out or raises, `_create_error_result` returns `quality_metrics={}` and the caller has no recovery path.
2. **Consumer-side**: When `get_quality_metrics_history` returns empty AND the reflection-DB search returns nothing AND the coverage file is absent, `_create_fallback_metrics` synthesizes perfect scores (`lint_score=100`, `security_score=100`, `complexity_score=100`) — the very antipattern Task 1 of the recent audit was adjacent to.
3. **No CLI invocation as fallback**: The Crackerjack CLI is never invoked to produce fresh metrics when the historical read is empty.

This design introduces a unified fallback chain that addresses all three gaps with one shared CLI-invocation helper.

## Goals

- Recover from a failed or missing metrics read by invoking the Crackerjack CLI on-demand, picking the smallest crackerjack command that fills the missing-metric gaps.
- Replace the `synthesize-100s` terminal with explicit `None` values + an `unavailable: True` flag, so downstream consumers can distinguish "no data" from "perfect score."
- Provide a single opt-out flag (`crackerjack.fallback.enabled`, default `true`) so operators can disable the fallback when it's noisy or slow.
- Emit structured logs and Dhara/Akosha counters for every fallback invocation, so operators see fallback rate, duration, and outcomes in existing Grafana dashboards.

## Non-goals

- **Replace the existing subprocess invocation in `execute_crackerjack_command`** — that's the normal path. The fallback only fires when the normal path fails (producer) or when there's no data to read (consumer).
- **Refactor `_calculate_quality_metrics`** — its per-helper shape is correct after the recent audit. The fallback reuses the same helpers (after a purity verification step).
- **Add new CLI commands to crackerjack** — we only invoke existing commands (`test`, `lint`, `security`, `check`).
- **Write successful fallback results back to history DB** — the consumer-side fallback is read-only. Producer-side retries already write via `_store_result`; consumers reading in the future will see fresh data from that path.
- **Cache fallback results in-memory** — every call is a fresh subprocess invocation. Caching adds state without proportional benefit at this scale.

## Architecture

### New module

`session_buddy/utils/crackerjack/fallback.py` exports one public coroutine:

```python
async def try_crackerjack_cli(
    project_dir: str | Path,
    missing_metrics: set[str],
    timeout: float = 30.0,
) -> dict[str, float] | None:
    """Return the requested metric keys via crackerjack CLI, or None on any failure."""
```

### Three integration points

1. **Producer retry** (`session_buddy/crackerjack_integration.py:470` — `execute_crackerjack_command`)
   - On `TimeoutError`, before calling `_create_error_result(exit_code=-1, quality_metrics={})`, attempt one `try_crackerjack_cli` call.
   - If helper returns a dict, merge its values into the metrics dict and set `fallback_used=True` on the result.
   - If helper returns `None`, fall through to existing `_create_error_result` behavior.

2. **Consumer chain tier** (`session_buddy/utils/quality_scoring.py:_get_crackerjack_metrics`)
   - Insert a new tier **between** the coverage-file fallback and the synthesis `_create_fallback_metrics` call.
   - The new tier calls `try_crackerjack_cli` for any of the four scoring keys still absent after the coverage-file check.

3. **Synthesis replacement** (`session_buddy/utils/quality_scoring.py:_create_fallback_metrics`)
   - Replace `{code_coverage: 0, lint_score: 100, security_score: 100, complexity_score: 100}` with `{code_coverage: None, lint_score: None, security_score: None, complexity_score: None, unavailable: True}`.

### Consumer chain (after the change)

```
_get_crackerjack_metrics(project_dir)
  ├─ DB read (get_quality_metrics_history)
  ├─ Reflection-DB search (db.search_conversations)
  ├─ Coverage-file read (coverage.json / .coverage)
  ├─ try_crackerjack_cli(...)              ← NEW TIER
  └─ _create_fallback_metrics(...)          ← REWRITTEN
```

### Producer retry path (after the change)

```
execute_crackerjack_command(command, args, working_directory, timeout)
  ├─ asyncio.create_subprocess_exec(...)
  ├─ on TimeoutError:
  │    ├─ try_crackerjack_cli(working_directory, ...)    ← NEW RETRY
  │    └─ if helper returns dict → merge + return CrackerjackResult(fallback_used=True)
  ├─ on Exception → _create_error_result(exit_code=-2)    ← unchanged
  └─ on success → _calculate_quality_metrics → return
```

### Module surface

- Helper imports `CrackerjackOutputParser.parse_output` from `session_buddy/utils/crackerjack/output_parser.py`.
- No new third-party dependencies.

## Design — Helper internals

### Metric → Command map

| Metric key | Produced by |
|---|---|
| `code_coverage` | `test`, `check`, `all` |
| `lint_score` | `lint`, `check`, `all` |
| `security_score` | `security`, `check`, `all` |
| `complexity_score` | `check`, `all` |

`complexity_score` only comes from `check` or `all` — no per-domain command exists. This asymmetry shapes the selection algorithm.

### Command selection algorithm

```python
def select_command(missing: set[str]) -> str:
    if not missing:
        return "check"  # defensive default
    if missing == {"code_coverage"}:
        return "test"
    if missing == {"lint_score"}:
        return "lint"
    if missing == {"security_score"}:
        return "security"
    # complexity_score only comes from check/all; any other combo needs check
    if missing == {"complexity_score"} or len(missing) > 1:
        return "check"
    return "check"  # unreachable — defensive
```

17 input combinations covered exhaustively (see Testing). `all` is never selected because `check` already covers all four scoring metrics and avoids minutes of test execution.

### Internal pipeline (inside `try_crackerjack_cli`)

1. **Disabled check**: if opt-out flag is false → return `None` (early).
2. **Select command**: `select_command(missing_metrics)` → e.g. `"check"`.
3. **Build argv**: `["python", "-m", "crackerjack", "--no-color", command]`.
4. **Spawn subprocess**: `asyncio.create_subprocess_exec(..., cwd=project_dir)`.
5. **Wait with timeout**: `asyncio.wait_for(proc.communicate(), timeout=timeout)`.
6. **Parse output**: `CrackerjackOutputParser.parse_output(command, stdout, stderr)`.
7. **Extract requested keys**: call the four pure helpers (`_calculate_lint_metrics`, `_calculate_security_metrics`, `_calculate_complexity_metrics`, `_calculate_coverage_metrics`) on `parsed_data`; keep only keys present in `missing_metrics`.
8. **Return on success**: `{key: value for key, value in metrics.items() if key in missing}`.
9. **Return on any failure**: `None` (catches: `TimeoutError`, `FileNotFoundError`, non-zero exit, parse exception, empty stdout).

The four pure helpers live on `CrackerjackIntegration` but don't use instance state — they're pure on their inputs. **The implementation plan includes a verification step** (one of the first tasks) to confirm this by reading each helper's body and asserting no `self.X` access. If any helper touches `self`, it's refactored to module-level as part of the same task.

### Timeout policy

- Helper default: **30 seconds**, distinct from the producer's 300s default.
- Rationale: a fallback's purpose is recovery; a 300s wait is worse than the original failure mode.
- Configurable via parameter — callers can override when invoking.
- On timeout: log WARNING + emit counter `crackerjack.fallback.timeout{command}`, then return `None`.

## Design — Integration points (concrete diff shape)

### Integration point 1 — Producer retry

```python
    except TimeoutError:
        # NEW: one CLI fallback attempt before degrading to empty metrics
        fallback_metrics = await try_crackerjack_cli(
            project_dir=working_directory,
            missing_metrics={"code_coverage", "lint_score", "security_score", "complexity_score"},
            timeout=30.0,
        )
        if fallback_metrics:
            return self._create_error_result(
                exit_code=-1,
                quality_metrics=fallback_metrics,
                fallback_used=True,
            )
        return self._create_error_result(exit_code=-1, quality_metrics={})
```

The new `fallback_used: bool = False` field on `CrackerjackResult` makes the fallback observable to the caller without parsing logs.

### Integration point 2 — Consumer chain tier

```python
    # ... existing DB, reflection-DB, and coverage-file tiers unchanged ...

    # NEW TIER: CLI fallback before synthesis
    SCORING_KEYS = {"code_coverage", "lint_score", "security_score", "complexity_score"}
    missing = {k for k in SCORING_KEYS if metrics.get(k) is None}
    if missing:
        fallback = await try_crackerjack_cli(
            project_dir=project_dir,
            missing_metrics=missing,
            timeout=30.0,
        )
        if fallback:
            metrics.update(fallback)

    if not any(metrics.get(k) is not None for k in SCORING_KEYS):
        return _create_fallback_metrics()
    return metrics
```

The missing-keys computation happens **after** the coverage-file tier, before the synthesis fallback. Ordering means a missing `code_coverage` after coverage-file attempt triggers `test` if it's the only missing key, or `check` if multiple metrics are missing.

### Integration point 3 — Synthesis replacement

```python
def _create_fallback_metrics(coverage_pct: float = 0) -> dict[str, Any]:
    """Last-resort fallback. Returns explicit unavailable markers, never perfect scores.

    Invoked only when every other tier (DB, reflection-DB, coverage-file, CLI) failed.
    The ``unavailable: True`` flag is the explicit signal that no measurement occurred.
    """
    return {
        "code_coverage": None,
        "lint_score": None,
        "security_score": None,
        "complexity_score": None,
        "unavailable": True,
    }
```

The `coverage_pct` parameter is preserved but unused (kept for backward compat with any external caller; flagged `@deprecated` in docstring). Removed in a follow-up.

### Shared changes

- `session_buddy/utils/crackerjack/__init__.py` adds the export: `from .fallback import try_crackerjack_cli`
- `session_buddy/crackerjack_integration.py:CrackerjackResult` dataclass gains `fallback_used: bool = False`
- No changes to public APIs of `get_quality_metrics_history`, `execute_crackerjack_command`, or any MCP tool signatures

## Design — Observability, configuration, and error contract

### Structured logs

Every fallback invocation emits exactly one WARNING-level log line:

```python
logger.warning(
    "crackerjack fallback invoked",
    extra={
        "command": command,
        "project_dir": str(project_dir),
        "missing_metrics": sorted(missing_metrics),
        "duration_seconds": round(duration, 3),
        "outcome": outcome,
    },
)
```

`outcome` values: `success`, `timeout`, `missing_executable`, `nonzero_exit`, `parse_error`, `empty_stdout`, `disabled`. Seven values total.

A DEBUG line follows on success showing the returned metric dict (`logger.debug("fallback metrics", extra={"metrics": dict})`).

### Counter metrics (Dhara / Akosha)

Naming follows snake_case, namespaced under `crackerjack.fallback.*`:

| Counter | Type | Tags | When emitted |
|---|---|---|---|
| `crackerjack.fallback.invocations` | counter | `command`, `outcome` | Every invocation |
| `crackerjack.fallback.duration_seconds` | histogram | `command` | Every invocation |
| `crackerjack.fallback.timeout` | counter | `command` | When `wait_for` raises `TimeoutError` |
| `crackerjack.fallback.disabled` | counter | (none) | When opt-out flag is false |

Surfaced via the existing Dhara → Akosha → Grafana chain. Operators see a "Crackerjack Fallback" panel in the existing Mahavishnu dashboard.

### Configuration (opt-out flag)

| Layer | Key | Default | Where |
|---|---|---|---|
| Oneiric setting | `crackerjack.fallback.enabled` | `true` | `settings/session-buddy.yaml` |
| Env override | `MAHAVISHNU_CRACKERJACK_FALLBACK` | `true` | shell env |

**Behavior**: helper checks the flag at function entry. If disabled, increments `crackerjack.fallback.disabled`, logs at DEBUG (not WARNING), returns `None`.

The flag governs **only** the new helper. Existing CLI invocation paths are unaffected.

### Error contract (precise return-value semantics)

The helper returns `dict[str, float] | None`. Callers branch on truthiness (`if fallback_metrics:`).

| Condition | Return value | Log outcome | Counter outcome |
|---|---|---|---|
| Opt-out flag false | `None` | `disabled` (DEBUG) | `disabled` |
| `python` not on PATH | `None` | `missing_executable` (ERROR) | `missing_executable` |
| `crackerjack` module not found | `None` | `missing_executable` (ERROR) | `missing_executable` |
| Subprocess times out | `None` | `timeout` (WARNING) | `timeout` |
| Subprocess exits non-zero | `None` | `nonzero_exit` (WARNING) | `nonzero_exit` |
| Parse raises exception | `None` | `parse_error` (WARNING) | `parse_error` |
| Stdout is empty | `None` | `empty_stdout` (WARNING) | `empty_stdout` |
| Parse succeeds, all requested keys present | `dict` with requested keys | `success` (WARNING) | `success` |
| Parse succeeds, some requested keys present | `dict` with subset | `success` (WARNING) | `success` |
| Parse succeeds, none of the requested keys present | `{}` (empty dict, falsy) | `success` (WARNING) | `success` |

**Important asymmetry**: the helper returns `{}` for the "succeeded but empty" case, not `None`. Both are falsy, so callers treat them identically. But the log/counter distinguishes them — operators see a `success` outcome with no metric values, which is meaningfully different from a `timeout` or `disabled`.

### Cascade behavior across layers

If the helper returns `None` or `{}`, the calling layer continues with its existing degradation:

- **Producer** (after `None` or `{}`): falls through to `_create_error_result(exit_code=-1, quality_metrics={})`. Caller sees empty metrics, `fallback_used=False`.
- **Consumer** (after `None` or `{}`): falls through to `_create_fallback_metrics()` → `None` + `unavailable: True` dict. Final consumer sees the explicit unavailable marker.

No new exception types. No raised exceptions from the helper.

## Design — Testing strategy

### Test pyramid

| Layer | File | Markers | Speed |
|---|---|---|---|
| Pure helper tests | `tests/unit/test_crackerjack_fallback.py` (NEW) | `unit` | Fast (<1s total) |
| Command-selection tests | `tests/unit/test_crackerjack_fallback.py` (NEW) | `unit` | Fast |
| Producer retry tests | `tests/unit/test_crackerjack_integration.py` (extend) | `unit` | Fast |
| Consumer chain tests | `tests/unit/test_quality_scoring.py` (extend) | `unit` | Fast |
| Regression tests | `tests/unit/test_quality_scoring.py` (extend) | `unit` | Fast |
| Real-subprocess smoke | `tests/integration/test_crackerjack_fallback_real.py` (NEW) | `integration`, `requires_network` | Slow (~30s) |

### Unit tests for the helper

Mock strategy: `monkeypatch.setattr` on `asyncio.create_subprocess_exec` to return an `AsyncMock` whose `communicate()` returns `(stdout_bytes, stderr_bytes)` and whose `returncode` is configurable.

**Outcomes covered** (one test per row of the error-contract table):

- `test_helper_success_returns_requested_metrics`
- `test_helper_partial_success_returns_subset`
- `test_helper_no_relevant_metrics_returns_empty_dict`
- `test_helper_timeout_returns_none`
- `test_helper_nonzero_exit_returns_none`
- `test_helper_missing_executable_returns_none`
- `test_helper_parse_error_returns_none`
- `test_helper_empty_stdout_returns_none`
- `test_helper_disabled_flag_returns_none`
- `test_helper_default_timeout_is_30s`
- `test_helper_timeout_override`
- `test_helper_logs_warning_on_invocation`
- `test_helper_emits_duration_histogram`

### Command-selection tests (exhaustive — 17 cases)

One parametrized test, 17 cases:

- Empty set → `check`
- Each single-metric set → smallest matching command (`test`, `lint`, `security`, or `check`)
- Each two-metric subset → `check`
- Each three-metric subset → `check`
- All four → `check`
- `{"unknown_metric"}` → `check` (defensive)

Asserts the function never raises.

### Producer retry tests

- `test_producer_timeout_invokes_fallback_before_error_result`
- `test_producer_timeout_helper_returns_none_returns_empty_metrics`
- `test_producer_normal_path_does_not_invoke_fallback`
- `test_producer_generic_exception_does_not_invoke_fallback`
- `test_crackerjack_result_dataclass_has_fallback_used_field`

### Consumer chain tests

- `test_consumer_invokes_helper_after_coverage_file_miss`
- `test_consumer_helper_success_merges_metrics`
- `test_consumer_helper_none_falls_through_to_synthesis`
- `test_consumer_helper_partial_returns_partial`
- `test_consumer_db_hit_skips_helper`
- `test_consumer_partial_db_hit_skips_helper_for_present_keys`
- `test_synthesis_replacement_emits_none_values`
- `test_synthesis_replacement_does_not_emit_perfect_scores`
- `test_mcp_metrics_tool_renders_unavailable_banner`

### Pure-helper purity verification

Before the helper can call `_calculate_lint_metrics` etc., we must verify they're pure. One of the plan tasks is a read-only verification step in `tests/unit/test_pure_helpers_purity.py`:

```python
def test_lint_helper_does_not_access_self_attributes():
    import inspect
    from session_buddy.crackerjack_integration import _calculate_lint_metrics
    source = inspect.getsource(_calculate_lint_metrics)
    body = source.split(":", 1)[1]
    assert "self." not in body, f"_calculate_lint_metrics accesses self: {source}"
```

Same check for the three other helpers. If any fails, the helper function is refactored to module-level as part of the same task.

### Real-subprocess smoke test

```python
@pytest.mark.integration
@pytest.mark.requires_network
async def test_helper_invokes_real_crackerjack_check(tmp_path):
    (tmp_path / "hello.py").write_text("x = 1\n")
    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics={"code_coverage", "lint_score"},
        timeout=60.0,
    )
    assert result is not None
    assert isinstance(result, dict)
```

Skipped in fast CI by `pytest -m "not integration"`.

### Coverage targets

| Module | Target |
|---|---|
| `session_buddy/utils/crackerjack/fallback.py` | 100% line + branch |
| `session_buddy/utils/quality_scoring.py` (modified sections) | ≥95% |
| `session_buddy/crackerjack_integration.py` (modified sections) | ≥95% |

### Pre-existing test compatibility

The synthesis replacement breaks any test asserting `_create_fallback_metrics` returns 100s. Search the test tree before starting implementation; update as part of the plan.

## Critical files

- `session_buddy/utils/crackerjack/fallback.py` (NEW)
- `session_buddy/utils/crackerjack/__init__.py` (add export)
- `session_buddy/utils/quality_scoring.py` (consumer chain tier + synthesis replacement)
- `session_buddy/crackerjack_integration.py` (producer retry + `fallback_used` field)
- `session_buddy/mcp/tools/session/crackerjack_tools.py` (MCP tool banner tweak)
- `settings/session-buddy.yaml` (default for opt-out flag)
- `tests/unit/test_crackerjack_fallback.py` (NEW)
- `tests/unit/test_pure_helpers_purity.py` (NEW)
- `tests/unit/test_crackerjack_integration.py` (extend)
- `tests/unit/test_quality_scoring.py` (extend)
- `tests/integration/test_crackerjack_fallback_real.py` (NEW)

## Rollback signal

If the CLI fallback fires excessively in production (>10% of metrics reads triggering it), or if the `_create_fallback_metrics` change breaks downstream consumers that haven't been updated for `None` values, disable via `MAHAVISHNU_CRACKERJACK_FALLBACK=false`. The opt-out path returns the system to current behavior (synthesize 100s on no-data) within one config change — no code rollback needed.

If the opt-out flag is insufficient (e.g., the helper itself crashes on import), revert the four commits introduced by this change:
1. New helper module
2. Producer retry integration
3. Consumer chain integration + synthesis replacement
4. Test additions

A `git revert` of the merge commit reverses all four atomically.

## Out-of-scope follow-ups

- **Cache successful fallback results back to history DB** — currently the producer's `_store_result` is the only writer. If read-write caching becomes desirable, it's a separate feature.
- **In-memory cache for repeated calls** — adds state without proportional benefit at current call rates.
- **Async fallback for tests that need it** — current testing strategy mocks subprocess; a real-subprocess harness is out of scope.
- **Refactor `_calculate_quality_metrics` and its helpers to module-level functions** — only happens if the purity verification step fails. Otherwise the instance-method shape stays.
