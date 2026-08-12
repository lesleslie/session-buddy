# Quality-Scoring Crackerjack CLI Fallback — Design (v2)

> **Status:** Re-spec addressing 5-agent review of v1. Substantive design changes — v1 is superseded.

**Date:** 2026-07-27 (v2)
**Date of v1:** 2026-07-27 (commit `e93219f8`, superseded)
**Owner:** Session-Buddy maintainers
**Repo:** `/Users/les/Projects/session-buddy`

## What changed from v1

The v1 spec was reviewed by five agents (mcp-integration-expert, oneiric-specialist, observability-incident-lead, python-pro, pwa-specialist) and found to have 13 Critical issues that made it unworkable as written:

| Issue | Source | v2 fix |
|---|---|---|
| YAML key shape won't be read by `SessionMgmtSettings.load()` | Oneiric C1 | Use flat `enable_crackerjack_fallback: bool` |
| Env-var prefix isn't what Oneiric strips for this project | Oneiric C2, Observability I3 | Use `SESSION_BUDDY_CRACKERJACK_FALLBACK` |
| Default value contradicts project's "safe rollout" pattern | Oneiric I1 | Default = `False` (opt-in) |
| Crackerjack CLI shape is wrong — `python -m crackerjack --no-color check` doesn't exist | Python M5 | Use `run` subcommand with `_build_command_flags` |
| Subprocess leaks on timeout — `wait_for` doesn't kill the process | Python C1 | `try/finally` with `proc.kill()` + `proc.wait()` |
| No concurrency protection — N parallel reads = N parallel subprocesses | PWA C3 | Module-level `asyncio.Lock` |
| Opt-out reintroduces the synthesize-100s antipattern | PWA C2 | Synthesis change is unconditional; flag controls only the CLI attempt |
| `unavailable: True` flag has no consumer — dead code on arrival | MCP C1, I1 | Extend `_format_metrics_section` to render the banner |
| `_format_metrics_section` crashes on `None` values | MCP C2 | Harden the formatter before wiring the flag |
| Counter namespace won't render in PromQL | Observability C1 | Use `session_buddy_crackerjack_fallback_*_total` (Prometheus convention) |
| No OTel spans despite existing stack | Observability C3 | Wrap invocation in `tracer.start_as_current_span` |
| Log line missing caller/correlation IDs | Observability C2 | Add `caller`, `project_name`, optional `session_id` |
| Success-path WARNING floods dashboards | PWA #7, Observability I2 | Log `success` at INFO; WARNING only for actionable failures |
| Outcome list omits `cancelled` and `permission_error` | Observability C4 | Expanded outcome taxonomy |
| `_calculate_complexity_metrics` re-synthesizes 100 on empty input | Python I1 | Post-filter in helper: skip keys whose parsed section was empty |
| `coverage_pct` deprecated param without `DeprecationWarning` | Python I4, Observability m3 | Drop the parameter; per Bodai pre-1.0 policy, no external callers |
| `missing_metrics: set[str]` should be `frozenset[str]` | Python C2 | `frozenset[str]` enforces immutability |
| Mock strategy depends on import style not pinned in spec | Python I3 | Spec mandates `import asyncio` style |

## Context

The recent `quality-scoring-field-audit` branch (commits `ceb181d7..63f4de63`) fixed what `_calculate_quality_metrics` does when specific metric keys are missing from a result dict. That fix distinguished "field absent" from "field present and zero," but it did not address two remaining gaps:

1. **Producer-side recovery**: when `execute_crackerjack_command`'s subprocess fails (timeout, exception, exit ≠ 0), `_create_error_result` returns `quality_metrics={}` with no recovery path.
1. **Consumer-side synthesis antipattern**: when no historical metrics exist, the coverage-file fallback path is absent, AND the reflection-DB search returns nothing, `_create_fallback_metrics` synthesizes perfect scores (`lint_score=100`, `security_score=100`, `complexity_score=100`) — the very antipattern Task 1 of the recent audit was adjacent to.

This design introduces a CLI-invocation helper that fires in both layers when prior data sources are insufficient, plus an unconditional rewrite of the synthesis function to emit explicit "unavailable" markers instead of perfect scores.

## Goals

- **Recover from a failed or missing metrics read** by invoking the Crackerjack CLI on-demand, picking the smallest crackerjack invocation that fills the missing-metric gaps.
- **Eliminate the synthesize-100s antipattern** unconditionally — when no measurement is possible, return `None` values + an `unavailable: True` flag, never perfect scores.
- **Wire the `unavailable: True` flag into a real consumer** — extend `_format_metrics_section` to render a banner when the flag is set, hardening it against `None` values first.
- **Provide a single opt-in flag** (`enable_crackerjack_fallback`, default `false`) so operators control whether the CLI fallback layer fires. The synthesis change ships regardless.
- **Make the fallback observable** via Prometheus counters, structured logs, and OpenTelemetry spans — using the existing observability stack's conventions.
- **Protect against concurrency and resource leaks** via an `asyncio.Lock` and proper subprocess cleanup.

## Non-goals

- **Revert the synthesis change when the flag is disabled.** The opt-out kills the *CLI attempt*, not the new contract. Disable means "no extra subprocess work," not "go back to perfect scores from no data."
- **Cache fallback results in-memory or in history DB.** The producer's `_store_result` already writes successful CLI invocations; the consumer chain is read-only. In-memory cache adds state without proportional benefit.
- **Add new crackerjack CLI commands.** We invoke existing commands and flag combinations only.
- **Refactor `_calculate_quality_metrics` end-to-end.** The per-helper shape is correct after the recent audit; the helper post-filters results to avoid the complexity 100-synthesis.
- **Replace the existing subprocess invocation in `execute_crackerjack_command` for the normal path.** The fallback only fires when the normal path fails (producer) or when there's no historical data (consumer).
- **Add caching of successful invocations within the helper.** Each call is a fresh subprocess.

## Architecture

### New module: `session_buddy/utils/crackerjack/fallback.py`

Exports one public coroutine:

```python
async def try_crackerjack_cli(
    project_dir: str | Path,
    missing_metrics: frozenset[str],
    timeout: float = 30.0,
    caller: Literal["producer_retry", "consumer_chain"] = "consumer_chain",
    correlation_context: dict[str, str] | None = None,
) -> dict[str, float] | None:
    """Return the requested metric keys via crackerjack CLI, or None on any failure.
    ...
    """
```

`frozenset` enforces immutability at the type level (matches existing `crackerjack_integration.py:120`, `ingesters/redaction.py:21`, `memory/causal.py:60` patterns).

### Three integration points

1. **Producer retry** (`session_buddy/crackerjack_integration.py:470` — `execute_crackerjack_command`)

   - On `TimeoutError`, before `_create_error_result(exit_code=-1, quality_metrics={})`, attempt one `try_crackerjack_cli` call with `caller="producer_retry"`.
   - Helper result (if any) merged into the metrics dict. `fallback_used=True` flag set on `CrackerjackResult`.
   - Subprocess leak prevention: `try/finally` with `proc.kill()` + `proc.wait()`.

1. **Consumer chain tier** (`session_buddy/utils/quality_scoring.py:_get_crackerjack_metrics`)

   - New tier between the coverage-file fallback and `_create_fallback_metrics`.
   - Calls `try_crackerjack_cli` with `caller="consumer_chain"` for any of the four scoring keys still absent.
   - **Module-level `asyncio.Lock`** serializes invocations to prevent N parallel subprocesses.

1. **Synthesis replacement** (`session_buddy/utils/quality_scoring.py:_create_fallback_metrics`)

   - **Unconditional**: returns `{code_coverage: None, lint_score: None, security_score: None, complexity_score: None, unavailable: True}`.
   - Old `coverage_pct` parameter dropped entirely (per Bodai pre-1.0 merge policy, no external callers).

1. **MCP banner rendering** (`session_buddy/mcp/tools/session/crackerjack_tools.py:_format_metrics_section`)

   - Hardened to handle `None` values (currently crashes per MCP C2).
   - Renders "⚠️ Quality metrics unavailable" banner when `unavailable: True` is in the dict.

### Data flow

**Consumer side**:

```
_get_crackerjack_metrics(project_dir)
  ├─ DB read (get_quality_metrics_history)
  ├─ Reflection-DB search (db.search_conversations)
  ├─ Coverage-file read (coverage.json / .coverage)
  ├─ try_crackerjack_cli(...)              ← NEW TIER
  │     └─ guarded by module-level asyncio.Lock
  └─ _create_fallback_metrics(...)          ← REWRITTEN (unconditional None + unavailable)
```

**Producer side**:

```
execute_crackerjack_command(command, args, working_directory, timeout)
  ├─ try: asyncio.create_subprocess_exec(...)
  ├─ on TimeoutError:
  │    ├─ try_crackerjack_cli(...)         ← NEW RETRY (guarded by same lock)
  │    └─ if helper returns dict → merge + return CrackerjackResult(fallback_used=True)
  ├─ on CancelledError → propagate
  ├─ on Exception → _create_error_result(exit_code=-2)
  └─ on success → _calculate_quality_metrics → return
```

## CLI invocation (corrected)

The v1 spec built argv as `["python", "-m", "crackerjack", "--no-color", "check"]`. This is **wrong** for crackerjack v0.47+, which uses a `run` subcommand with flag combinations.

The v2 helper uses `CrackerjackIntegration._build_command_flags(command, ai_agent_mode=False)` to construct the correct argv. The Python-pro reviewer's reading of the crackerjack CLI surface:

| Caller intent | Flag combination | What it produces |
|---|---|---|
| All four metrics | `run --comp` | lint + security + complexity + coverage |
| Just coverage | `run --run-tests` | test results + coverage |
| Just lint | `run --fast --quick` | lint only |
| Just security | `run --security` | security only |

**The plan's first task is a verification step** that runs each flag combination against a real crackerjack install, captures which keys appear in `parsed_data`, and locks the mapping with a regression test. This is mandatory — the design depends on the flag-to-metric mapping being correct.

## Helper internals

### Internal pipeline (inside `try_crackerjack_cli`)

1. **Disabled check**: if `not get_feature_flags().enable_crackerjack_fallback` → return `None` (early, DEBUG log, `disabled` outcome).
1. **Lock acquire**: `async with _FALLBACK_LOCK:` to serialize.
1. **Disabled re-check** (after lock): a second check inside the lock to handle race where the flag was flipped between step 1 and step 3.
1. **Build argv**: `_build_command_flags(command, ai_agent_mode=False)` from `CrackerjackIntegration`.
1. **OTel span start**: `with tracer.start_as_current_span("crackerjack.fallback", attributes={...})` (no-op if tracer not configured).
1. **Spawn subprocess**: `asyncio.create_subprocess_exec(*argv, cwd=project_dir, stdout=PIPE, stderr=PIPE)`.
1. **Wait with timeout**: `try: stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout); except (TimeoutError, asyncio.CancelledError): proc.kill(); await proc.wait(); raise`.
1. **Check exit code**: `if proc.returncode != 0` → log/counter `nonzero_exit`, return `None`.
1. **Parse output**: `CrackerjackOutputParser.parse_output(command, stdout, stderr)`.
1. **Extract requested keys**: call the four pure helpers; **post-filter** to drop keys whose corresponding section of `parsed_data` was empty.
1. **Return on success**: `{key: value for key, value in metrics.items() if key in missing}`.
1. **Return on any failure**: `None` with structured log + counter.

The four pure helpers (`_calculate_lint_metrics`, etc.) live on `CrackerjackIntegration` but should be refactored to `@staticmethod` (per Python I2) so the helper can call them without instantiating a DB-touching `CrackerjackIntegration` object. The plan includes a purity-verification + refactor task.

### Timeout policy

- Helper default: **30 seconds**, distinct from the producer's 300s default.
- Rationale: a fallback's purpose is recovery; a 300s wait is worse than the original failure.
- On timeout: log INFO + emit counter `outcome="timeout"`, kill subprocess, return `None`.

### Python interpreter

Helper uses `sys.executable` instead of `"python"` to pin the interpreter to the one that has Crackerjack installed:

```python
import sys
argv = [sys.executable, "-m", "crackerjack", *build_args]
```

## Configuration

### Opt-in flag

| Layer | Key | Default | Where |
|---|---|---|---|
| Oneiric setting (flat) | `enable_crackerjack_fallback` | `false` | `settings/session-buddy.yaml` |
| Env override | `SESSION_BUDDY_CRACKERJACK_FALLBACK` | `false` | shell env |
| Feature flag resolver | `get_feature_flags().enable_crackerjack_fallback` | `false` | runtime |

**Behavior**: helper checks the flag via `get_feature_flags()` at function entry (and again after acquiring the lock). If disabled, logs at DEBUG with `outcome=disabled`, increments the counter, returns `None`.

**Default rationale**: matches the project pattern (every existing flag in `session_buddy/config/feature_flags.py` defaults to `False` for safe rollouts). Operators opt in via the flag once the rollout is complete.

**Scope of the flag**: governs only the CLI fallback invocation. The synthesis change (None + unavailable) is unconditional and ships regardless of the flag's value.

### Boolean coercion

Per the project's `_get_env_bool` helper at `session_buddy/config/feature_flags.py:42-58`, accepted values are `true`/`false`/`1`/`0`/`yes`/`no`/`on`/`off` (case-insensitive). The plan includes a re-implementation of this pattern in the fallback helper's own env read if it doesn't go through `get_feature_flags()`.

## Observability

### Prometheus counters (Prometheus convention, NOT dotted names)

Following `session_buddy/metrics.py` and `session_buddy/mcp/metrics.py` (e.g., `session_buddy_provenance_pruned_total`, `session_buddy_periodic_jobs_errors_total`):

| Counter | Type | Labels | When emitted |
|---|---|---|---|
| `session_buddy_crackerjack_fallback_invocations_total` | counter | `command`, `outcome`, `caller` | Every invocation |
| `session_buddy_crackerjack_fallback_duration_seconds` | histogram | `command`, `caller` | Every invocation |

`outcome` values: `success`, `timeout`, `nonzero_exit`, `parse_error`, `empty_stdout`, `missing_executable`, `permission_error`, `cancelled`, `os_error`, `disabled`. Ten values total.

`command` cardinality: 4-5 distinct values (bounded by the crackerjack CLI surface). Document in the metric definition.

**Drop the redundant dedicated counters** that v1 proposed (`crackerjack.fallback.timeout{command}`, `crackerjack.fallback.disabled{command}`). Operators query by `outcome` label on the unified counter.

### Structured logs

Log level per outcome:

- `success` → **INFO** (the new normal; not actionable)
- `timeout`, `nonzero_exit`, `parse_error`, `empty_stdout`, `permission_error`, `cancelled`, `os_error` → **WARNING** (actionable failures)
- `missing_executable` → **ERROR** (environment problem, operator should investigate)
- `disabled` → **DEBUG** (silent path)

Log fields:

```python
logger.log(level, "crackerjack fallback invoked", extra={
    "command": command,
    "project_dir": str(project_dir),
    "project_name": Path(project_dir).name,        # basename, no PII in full path
    "missing_metrics": sorted(missing_metrics),    # sorted for log stability
    "duration_seconds": round(duration, 3),
    "outcome": outcome,
    "caller": caller,                              # "producer_retry" | "consumer_chain"
    "session_id": correlation_context.get("session_id") if correlation_context else None,
    "workflow_id": correlation_context.get("workflow_id") if correlation_context else None,
})
```

`missing_metrics` is always sorted lexicographically before logging. Anti-regression test locks this in.

### OpenTelemetry spans

Every invocation wrapped in:

```python
with tracer.start_as_current_span(
    "crackerjack.fallback",
    attributes={
        "command": command,
        "project_dir": str(project_dir),
        "caller": caller,
        "missing_metrics": sorted(missing_metrics),
    },
) as span:
    # ... helper body ...
    span.set_attribute("outcome", outcome)
    if outcome == "success":
        span.set_attribute("metrics_returned", list(metrics.keys()))
    elif outcome != "disabled":
        span.set_status(Status(StatusCode.ERROR, outcome))
```

No-op when the tracer is not configured (matches `session_buddy/mcp/telemetry.py:29-36` lazy-init pattern).

### Alert guidance (added — v1 omitted this)

Three recommended alert rules on the new metrics:

1. **Outcome ≠ success rate > 10% over 5 minutes** → Slack/PagerDuty
1. **`outcome="disabled"` rate > 0** → Slack (someone flipped the kill switch; informational)
1. **`session_buddy_crackerjack_fallback_duration_seconds` p99 > 25s** → Slack (close to the 30s timeout)

## Error contract (precise return-value semantics)

The helper returns `dict[str, float] | None`. Callers branch on truthiness (`if fallback_metrics:`).

| Condition | Return value | Log level | `outcome` counter value |
|---|---|---|---|
| Opt-in flag false | `None` | DEBUG | `disabled` |
| `sys.executable` not on PATH | `None` | ERROR | `missing_executable` |
| `crackerjack` module not found | `None` | ERROR | `missing_executable` |
| Subprocess times out | `None` | WARNING | `timeout` |
| Subprocess cancelled (parent shutdown) | `None` | WARNING | `cancelled` |
| Subprocess exits non-zero | `None` | WARNING | `nonzero_exit` |
| Permission denied on cwd | `None` | WARNING | `permission_error` |
| OS-level error (e.g., disk full) | `None` | WARNING | `os_error` |
| Parse raises exception | `None` | WARNING | `parse_error` |
| Stdout is empty | `None` | WARNING | `empty_stdout` |
| Parse succeeds, all requested keys present | `dict` with requested keys | INFO | `success` |
| Parse succeeds, some requested keys present (and those sections were non-empty) | `dict` with subset | INFO | `success` |
| Parse succeeds, none of the requested keys present (or all empty) | `{}` (empty dict, falsy) | INFO | `success` |

**Asymmetry**: helper returns `{}` for the "succeeded but empty" case, not `None`. Both are falsy; callers treat them identically. The log/counter distinguishes them for operators.

**Cascade**:

- Producer (after `None` or `{}`): falls through to `_create_error_result(exit_code=-1, quality_metrics={})`. Caller sees empty metrics, `fallback_used=False`.
- Consumer (after `None` or `{}`): falls through to `_create_fallback_metrics()` → `None` + `unavailable: True` dict.

No raised exceptions from the helper — all failure modes map to `None`.

## Integration points (concrete diff shape)

### Producer retry

```python
    except TimeoutError:
        # NEW: one CLI fallback attempt before degrading to empty metrics
        fallback_metrics = await try_crackerjack_cli(
            project_dir=working_directory,
            missing_metrics=frozenset({"code_coverage", "lint_score", "security_score", "complexity_score"}),
            timeout=30.0,
            caller="producer_retry",
        )
        if fallback_metrics:
            return self._create_error_result(
                exit_code=-1,
                quality_metrics=fallback_metrics,
                fallback_used=True,
            )
        return self._create_error_result(exit_code=-1, quality_metrics={})
```

`asyncio.CancelledError` propagates without invoking the helper (shutdown should not invoke a 30s subprocess).

### Consumer chain tier

```python
    # ... existing DB, reflection-DB, and coverage-file tiers unchanged ...

    # NEW TIER: CLI fallback before synthesis
    SCORING_KEYS = frozenset({"code_coverage", "lint_score", "security_score", "complexity_score"})
    missing = frozenset(k for k in SCORING_KEYS if metrics.get(k) is None)
    if missing:
        fallback = await try_crackerjack_cli(
            project_dir=project_dir,
            missing_metrics=missing,
            timeout=30.0,
            caller="consumer_chain",
        )
        if fallback:
            metrics.update(fallback)

    if not any(metrics.get(k) is not None for k in SCORING_KEYS):
        return _create_fallback_metrics()
    return metrics
```

### Synthesis replacement (unconditional)

```python
def _create_fallback_metrics() -> dict[str, Any]:
    """Last-resort fallback. Returns explicit unavailable markers, never perfect scores.

    Invoked only when every other tier (DB, reflection-DB, coverage-file, CLI) failed
    or was disabled. The ``unavailable: True`` flag is the explicit signal that no
    measurement occurred.
    """
    return {
        "code_coverage": None,
        "lint_score": None,
        "security_score": None,
        "complexity_score": None,
        "unavailable": True,
    }
```

`coverage_pct` parameter dropped entirely (per Bodai pre-1.0 merge policy, no external callers; plan verifies with a grep).

### MCP banner rendering

`session_buddy/mcp/tools/session/crackerjack_tools.py:_format_metrics_section` is hardened to:

1. Detect `unavailable: True` upfront and render `"⚠️ Quality metrics unavailable — every tier failed or was disabled"`.
1. Replace `f"{value:.1f}"` with `f"{value:.1f}" if value is not None else "unavailable"` to handle None values without crashing.

### Shared changes

- `session_buddy/utils/crackerjack/__init__.py` adds the export.
- `session_buddy/crackerjack_integration.py:CrackerjackResult` dataclass gains `fallback_used: bool = False`.
- The four pure helpers (`_calculate_lint_metrics`, etc.) are refactored to `@staticmethod` (or module-level functions) so the helper can call them without instantiating `CrackerjackIntegration`.
- `session_buddy/metrics.py` (or a new `session_buddy/mcp/fallback_metrics.py`) registers the two new Prometheus counters.

## Testing strategy

### Test pyramid

| Layer | File | Markers | Speed |
|---|---|---|---|
| Pure helper tests | `tests/unit/test_crackerjack_fallback.py` (NEW) | `unit` | Fast (\<1s total) |
| Command-selection tests | `tests/unit/test_crackerjack_fallback.py` (NEW) | `unit` | Fast |
| Producer retry tests | `tests/unit/test_crackerjack_integration.py` (extend) | `unit` | Fast |
| Consumer chain tests | `tests/unit/test_quality_scoring.py` (extend) | `unit` | Fast |
| Synthesis replacement tests | `tests/unit/test_quality_scoring.py` (extend) | `unit` | Fast |
| MCP banner tests | `tests/unit/test_crackerjack_tools.py` (extend) | `unit` | Fast |
| Subprocess leak test | `tests/unit/test_crackerjack_fallback.py` (NEW) | `unit` | Fast |
| Concurrency serialization test | `tests/unit/test_crackerjack_fallback.py` (NEW) | `unit` | Fast |
| Pure-helper refactor + purity test | `tests/unit/test_pure_helpers_purity.py` (NEW) | `unit` | Fast |
| CLI flag-to-metric verification | `tests/integration/test_crackerjack_fallback_real.py` (NEW) | `integration`, `requires_network` | Slow |
| Real-subprocess smoke | `tests/integration/test_crackerjack_fallback_real.py` (NEW) | `integration`, `requires_network` | Slow |

### Unit tests for the helper

Mock strategy: `monkeypatch.setattr("asyncio.create_subprocess_exec", ...)` (the spec mandates `import asyncio` style so the patch targets the right reference).

**Outcomes covered** (one test per row of the error-contract table — 13 cases):

- `test_helper_success_returns_requested_metrics`
- `test_helper_partial_success_returns_subset`
- `test_helper_no_relevant_metrics_returns_empty_dict`
- `test_helper_timeout_returns_none_and_kills_subprocess`
- `test_helper_cancelled_propagates`
- `test_helper_nonzero_exit_returns_none`
- `test_helper_missing_executable_returns_none`
- `test_helper_permission_error_returns_none`
- `test_helper_os_error_returns_none`
- `test_helper_parse_error_returns_none`
- `test_helper_empty_stdout_returns_none`
- `test_helper_disabled_flag_returns_none`
- `test_helper_default_timeout_is_30s`
- `test_helper_timeout_override`
- `test_helper_logs_info_on_success`
- `test_helper_logs_warning_on_actionable_failure`
- `test_helper_logs_debug_on_disabled`
- `test_helper_emits_prometheus_counter_on_invocation`
- `test_helper_emits_otel_span_when_tracer_configured`
- `test_helper_no_op_when_tracer_not_configured`
- `test_helper_serializes_concurrent_invocations` (test that the lock works)
- `test_helper_post_filters_keys_with_empty_parsed_section`

### CLI flag verification test (first integration test)

```python
@pytest.mark.integration
@pytest.mark.requires_network
def test_run_comp_produces_all_four_scoring_metrics(tmp_path):
    """Verify which metrics each crackerjack flag combination produces.
    This is a one-time verification that locks in the design's CLI-to-metric mapping.
    """
    (tmp_path / "hello.py").write_text("x = 1\n")
    for flag_combo, expected_keys in [
        (["--comp"], {"code_coverage", "lint_score", "security_score", "complexity_score"}),
        (["--run-tests"], {"code_coverage"}),
        (["--fast", "--quick"], {"lint_score"}),
        (["--security"], {"security_score"}),
    ]:
        result = subprocess.run(
            [sys.executable, "-m", "crackerjack", "run", *flag_combo],
            cwd=tmp_path, capture_output=True, timeout=60,
        )
        parsed = CrackerjackOutputParser.parse_output("run", result.stdout, result.stderr)
        # ... assert expected_keys ⊆ set(parsed.keys()) ...
```

If the expected_keys mapping is wrong, the plan's verification task updates the spec and re-derives the metric→command map.

### Real-subprocess smoke test

```python
@pytest.mark.integration
@pytest.mark.requires_network
async def test_helper_invokes_real_crackerjack(tmp_path):
    (tmp_path / "hello.py").write_text("x = 1\n")
    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score"}),
        timeout=60.0,
        caller="consumer_chain",
    )
    assert result is not None
    assert isinstance(result, dict)
```

### Coverage targets

| Module | Target |
|---|---|
| `session_buddy/utils/crackerjack/fallback.py` | 100% line + branch |
| `session_buddy/utils/quality_scoring.py` (modified sections) | ≥95% |
| `session_buddy/crackerjack_integration.py` (modified sections) | ≥95% |
| `session_buddy/mcp/tools/session/crackerjack_tools.py` (modified section) | ≥95% |

## Critical files

- `session_buddy/utils/crackerjack/fallback.py` (NEW)
- `session_buddy/utils/crackerjack/__init__.py` (add export)
- `session_buddy/utils/quality_scoring.py` (consumer chain tier + synthesis replacement + drop `coverage_pct` param)
- `session_buddy/crackerjack_integration.py` (producer retry + `fallback_used` field + helper refactor to `@staticmethod`)
- `session_buddy/mcp/tools/session/crackerjack_tools.py` (`_format_metrics_section` hardening + banner)
- `session_buddy/metrics.py` (or new `session_buddy/mcp/fallback_metrics.py`) (Prometheus counters)
- `session_buddy/config/feature_flags.py` (add `enable_crackerjack_fallback` field)
- `settings/session-buddy.yaml` (default for opt-in flag)
- `tests/unit/test_crackerjack_fallback.py` (NEW)
- `tests/unit/test_pure_helpers_purity.py` (NEW)
- `tests/unit/test_crackerjack_integration.py` (extend)
- `tests/unit/test_quality_scoring.py` (extend)
- `tests/unit/test_crackerjack_tools.py` (extend)
- `tests/integration/test_crackerjack_fallback_real.py` (NEW)

## Rollback signal

Three escalation tiers, in order of preference:

1. **Disable the CLI fallback layer** via `SESSION_BUDDY_CRACKERJACK_FALLBACK=false`. Synthesis change is unaffected; consumers still get `None` + `unavailable: True` instead of perfect scores. This is the safe rollback.
1. **Revert the synthesis replacement** if downstream consumers (after a full rollout) can't tolerate the new `None` contract. One-commit revert. Restores the synthesize-100s behavior, but the rest of the fallback layer continues to work.
1. **Full revert** of the four-to-six commits. Returns to pre-v2 behavior. Use only if the entire feature is misbehaving.

## Out-of-scope follow-ups

- **Read-write cache for consumer-side fallback invocations** — currently the consumer's CLI invocation is read-only. A future commit could write the result to history DB so subsequent reads don't re-invoke.
- **Per-project rate limiting** — currently the module-level lock serializes, not rate-limits. If one project's fallback fires excessively, it could starve others. A per-project semaphore is a future enhancement.
- **CLI invocation retry within the helper** — currently the helper makes one attempt. A retry-with-backoff for transient failures (e.g., `permission_error` on a temporarily-locked file) is a future enhancement.
- **In-memory result cache for repeated identical calls** — adds state without proportional benefit at current call rates.
- **Refactor `_calculate_quality_metrics` and helpers to module-level functions** — only happens if the purity verification step fails the `@staticmethod` refactor.
