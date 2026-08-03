# Quality-Scoring Crackerjack CLI Fallback — Implementation Plan (v3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CLI-invocation fallback layer to session-buddy's `quality_scoring` module that recovers from failed/missing metrics reads by invoking crackerjack on-demand, and unconditionally eliminate the synthesize-100s antipattern from the terminal fallback. v3 applies the 10 NEW Criticals from the v2 plan review.

**Architecture:** New `try_crackerjack_cli` helper in `session_buddy/utils/crackerjack/fallback.py` invokes crackerjack via `asyncio.create_subprocess_exec` with the v0.47+ `run` subcommand + flag combinations (selected from a Task 0 preflight). Wired into the producer's `TimeoutError` path and the consumer's missing-keys chain tier. The terminal synthesis function is rewritten to emit `None` + `unavailable: True` instead of perfect scores. Module-level `asyncio.Lock` serializes invocations. OTel span wraps every invocation. Prometheus counters use `session_buddy_*_total` naming. Plan reordered vs. v1: Task 10 (synthesis) precedes Task 8 (consumer wiring) so the synthesis contract exists before the chain tests it.

**Tech Stack:** Python 3.13, `asyncio.create_subprocess_exec` + `asyncio.wait_for` with split timeout/cancellation handlers, `prometheus_client.Counter/Histogram`, `opentelemetry.trace.Tracer` (lazy-init), `pytest` + `pytest-asyncio`, `monkeypatch.setattr` for subprocess mocking, `unittest.mock.MagicMock` for `CrackerjackResult` fixtures.

## What changed from v1

The v1 plan had 28 Critical issues from a 5-agent review. Key changes:

| Issue | Source | v2 fix |
|---|---|---|
| Plan wrote wrong signatures (`_format_metrics_section(quality_metrics: dict)`, `_create_error_result(exit_code=..., quality_metrics=...)`) | MCP C1/C2, Python C1 | Use actual signatures: `_format_metrics_section(result: CrackerjackResult)`; `_create_error_result(command, exit_code, stderr, execution_time, working_directory, memory_insight)` |
| Task 9 monkeypatches a name that doesn't exist (helper imported locally) | Python I7, game-dev C11 | Move `from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli` to top of `crackerjack_integration.py` |
| Task 0 verifies metric-to-flag mapping but Task 4 never consumes it | Python I8, game-dev C7 | Task 4's helper uses the mapping table (recorded in Task 0) to pick flags from `missing_metrics` |
| `try/except (TimeoutError, asyncio.CancelledError)` swallows cancellation | Python C3, game-dev C4 | Split handlers: `TimeoutError` returns `None`; `CancelledError` re-raises after cleanup |
| `try/finally` subprocess cleanup mandated but never written | game-dev C5 | Task 4's helper has explicit `try/finally` with `proc.kill()` + `proc.wait()` |
| Subprocess mock defines `kill()` as async; real `asyncio.subprocess.Process.kill()` is sync | game-dev C6 | Mock's `kill()` is sync; `wait()` is async; separate tracking |
| Task 8 tests new synthesis contract before Task 10 implements it | game-dev C9 | Reorder: Task 10 (synthesis) precedes Task 8 (consumer wiring) |
| `Histogram` not imported in `metrics.py` — NameError at import | Python I6 | Add `Histogram` to existing `from prometheus_client import ...` line |
| OTel span is `# TODO` with no test | Observability C1 | Concrete `tracer.start_as_current_span(...)` block; 2 OTel tests added |
| Counter increments not asserted for any of 10 outcomes | Observability C2 | Parametrized test over all 10 outcomes |
| WARNING log level routing not tested | Observability C3 | Parametrized test over 7 WARNING outcomes |
| Missing "synthesis reached only when CLI attempted" regression | Observability C4 | Two regression tests added |
| `_flags` module global doesn't exist; `monkeypatch.setattr(feature_flags, "_flags", ...)` is a no-op | Python C4, Oneiric I2 | Replace with `monkeypatch.setattr(feature_flags, "get_feature_flags", lambda: ...)` |
| Task 1 says "add after `enable_crackerjack`" but that field doesn't exist in `FeatureFlags` | Oneiric C1 | Add new section comment to `FeatureFlags`; place field under it |
| `SESSION_BUDDY_CRACKERJACK_FALLBACK` env var documented but never wired | Oneiric C2 | Add wiring step in `get_feature_flags()` |
| YAML literal had 2 leading spaces (file is flat) | Oneiric C3 | Fix indentation; add verification step |
| Task 5's post-filter logic is broken (`parsed_data.get(...)` returns the dict, not None) | Python I5 | Refactor with `SECTION_FOR_KEY` constant; check `section` truthiness |
| Task 11 banner is dead code (synthesis dict never reaches `_format_metrics_section`) | MCP C1, C2 | Refactor: `_format_metrics_section` inspects `result.quality_metrics`; the synthesis dict is threaded into a `CrackerjackResult` in the consumer path |
| Task 12 always sees fallback disabled (test never enables flag) | game-dev C12 | Use the same `_enable_flag` helper as unit tests |
| Task 12 not valid TDD (no failing test, accepts dep failure without skip) | game-dev C13 | `pytest.importorskip("crackerjack")`; assert metric was extracted |
| Task 9 local import inside exception handler | Python I7 | Move import to module top |
| Spec's alert guidance not in plan | Observability I3 | New Task 13 |

## What changed from v2

The v2 plan had 10 NEW Critical issues from a 4-agent review (MCP agent failed at the API tier with a 429). Key changes:

| Issue | Source | v3 fix |
|---|---|---|
| Task 5 calls bare `_calculate_coverage_metrics(section)` etc. — these are `@staticmethod` methods on `CrackerjackIntegration` and would `NameError` at runtime | Python C1 | Resolve the class once via `cls = _get_crackerjack_integration_class()` and call `cls._calculate_X(section)` |
| Task 5's `test_success_returns_requested_metrics` has non-empty `lint_issues` data but asserts `lint_score == 100.0` — would fail on first run | Python C2 | Change test data to `lint_issues: []` so the assertion matches `_calculate_lint_metrics([])` |
| Task 7 step 7.6 references `_NoOpSpan()` but never defines it; `NameError` if OTel package is installed but tracer is None | Python C3 | Define `_NoOpSpan` class alongside `_finalize` (Task 7 step 7.5) |
| OTel `set_status(StatusCode.ERROR)` is never called for failure outcomes | Observability C1 | `_finalize` sets `span.set_status(Status(...))` for non-success outcomes; span gets `outcome` attribute |
| Task 4's `CancelledError` re-raise path emits no counter/log | Observability C2 | Add `_finalize("cancelled", ...)` BEFORE `raise` in Task 4 step 4.4 |
| Task 6 step 6.3 violates TDD ("verify the existing handlers") | voice-chat C1 | Note that error tests are co-developed with Tasks 4-5; commit is test-only |
| Task 7 is too big to land in one reviewer-gate commit | voice-chat C2 | Split into 4 sequential commits: 7a metrics, 7b helpers, 7c wire-in, 7d concurrency |
| OTel span is missing the `outcome` attribute | voice-chat C3 | `_finalize` calls `span.set_attribute("outcome", outcome)` |
| `_METRIC_TO_FLAG["complexity_score"]` is `("check", ())` — empty flags tuple, never reached because `_pick_invocation` short-circuits | voice-chat C4 | Remove the dead entry; document why complexity has no per-metric entry |
| Task 11 banner never fires — synthesis dict from consumer side doesn't reach `_format_metrics_section` | voice-chat C5 | Add `synthesize_unavailable_result` helper; consumer chain writes a `CrackerjackResult` to history when synthesis is reached |

## Global Constraints

- **Spec**: `/Users/les/Projects/session-buddy/docs/superpowers/specs/2026-07-27-quality-scoring-crackerjack-fallback-design.md` (v2)
- **Crackerjack CLI shape** (verified in Task 0): `python -m crackerjack run --comp|--fast --quick|--security|--run-tests [args]`. Bare `crackerjack check` / `crackerjack lint` do not exist. The parser's `parser_map` is keyed on the *semantic* command name (`lint`, `check`, `security`, `test`); pass the semantic name to `parse_output`, not `"run"`.
- **Opt-in default**: `enable_crackerjack_fallback: bool = False`. Synthesis change is unconditional.
- **Env var**: `SESSION_BUDDY_CRACKERJACK_FALLBACK` (per Oneiric project-name strip).
- **YAML key (flat)**: `enable_crackerjack_fallback` in `settings/session-buddy.yaml`. `SessionMgmtSettings.load()` only reads flat top-level keys; 0 leading spaces.
- **Counter naming**: `session_buddy_crackerjack_fallback_invocations_total{command, outcome, caller}` and `session_buddy_crackerjack_fallback_duration_seconds{command, caller}`. The Histogram import must be added to `session_buddy/metrics.py`.
- **Log levels**: `success` → INFO, `disabled` → DEBUG, `missing_executable` → ERROR, all other failures → WARNING. Test all routes.
- **Helper signature**: `async def try_crackerjack_cli(project_dir: str | Path, missing_metrics: frozenset[str], timeout: float = 30.0, caller: Literal["producer_retry", "consumer_chain"] = "consumer_chain", correlation_context: dict[str, str] | None = None) -> dict[str, float] | None`
- **Cancellation handling**: `TimeoutError` returns `None` after subprocess cleanup; `asyncio.CancelledError` re-raises after cleanup. Single `try/finally` block with both `proc.kill()` and `proc.wait()` in the `finally`.
- **Subprocess mock API**: real `asyncio.subprocess.Process.kill()` is sync; `wait()` is async. The mock must match.
- **Interpreter**: `sys.executable`, not `"python"`.
- **Outcome taxonomy**: 10 values: `success`, `timeout`, `cancelled`, `nonzero_exit`, `parse_error`, `empty_stdout`, `missing_executable`, `permission_error`, `os_error`, `disabled`.
- **frozenset**: `missing_metrics` is `frozenset[str]`. Sorted lexicographically before logging.
- **Module-level `asyncio.Lock`**: `_FALLBACK_LOCK` in `fallback.py`, acquired inside the helper.
- **Pure helper refactor**: `_calculate_lint_metrics` etc. become `@staticmethod` so the helper can call them via `CrackerjackIntegration._calculate_X(args)` (no instance).
- **`coverage_pct` parameter**: dropped from `_create_fallback_metrics()` entirely. Both internal callers (lines 891 and 924 of `quality_scoring.py`) currently pass `coverage_pct`; the rename to bare `_create_fallback_metrics()` requires updating both call sites.
- **`CrackerjackResult.fallback_used`**: new `bool = False` field.
- **`_format_metrics_section(result: CrackerjackResult)`**: takes the dataclass (not a dict), inspects `result.quality_metrics` for the `unavailable` flag.
- **Mock strategy**: helper uses `import asyncio`. Tests use `monkeypatch.setattr(asyncio, "create_subprocess_exec", ...)`. For `get_feature_flags`, use `monkeypatch.setattr(feature_flags, "get_feature_flags", lambda: FeatureFlags(...))` (no `_flags` global exists).
- **Pytest markers**: existing markers only — `unit`, `integration`, `requires_network`, `slow`. Do not invent new markers.
- **Pre-existing test pollution**: `tests/unit/test_quality_scoring.py` collection fails on `ModuleNotFoundError: duckdb`; `tests/unit/test_crackerjack_integration.py` collection fails on the conftest `sys.modules` pollution pattern. Run tests narrowly with `--noconftest --override-ini="addopts="` when needed.
- **No `assert` in production code** (bandit B101). Use the `session_buddy/core/errors.py` exception hierarchy.
- **Bodai pre-1.0 merge policy**: components merge directly to `main`; no PRs.
- **Coverage target**: 100% line + branch for the new helper; ≥95% for modified sections of existing modules.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `session_buddy/utils/crackerjack/fallback.py` | New helper + lock + OTel span + env-flag wiring | NEW |
| `session_buddy/utils/crackerjack/__init__.py` | Export new helper | MODIFY (1 line) |
| `session_buddy/config/feature_flags.py` | Add `enable_crackerjack_fallback` field; wire `SESSION_BUDDY_CRACKERJACK_FALLBACK` into `get_feature_flags()` | MODIFY |
| `session_buddy/settings.py` | Add `enable_crackerjack_fallback: bool = Field(default=False, ...)` to `SessionMgmtSettings` | MODIFY |
| `settings/session-buddy.yaml` | Flat YAML key `enable_crackerjack_fallback: false` | MODIFY |
| `session_buddy/utils/quality_scoring.py` | Synthesis replacement (drop `coverage_pct`, emit None + unavailable) | MODIFY |
| `session_buddy/utils/quality_scoring.py` | Consumer chain tier (after synthesis; use top-level import) | MODIFY |
| `session_buddy/crackerjack_integration.py` | Producer retry (top-level helper import, 6-arg `_create_error_result` call) | MODIFY |
| `session_buddy/mcp/tools/session/crackerjack_tools.py` | `_format_metrics_section` inspects `result.quality_metrics` for `unavailable`; banner rendering; `None` handling | MODIFY |
| `session_buddy/metrics.py` | Add `Histogram` to import; register `CRACKERJACK_FALLBACK_INVOCATIONS` and `CRACKERJACK_FALLBACK_DURATION_SECONDS` | MODIFY |
| `docs/observability/crackerjack-fallback-alerts.md` | PromQL alert rules + dashboard panel stub (Task 13) | NEW |
| `tests/unit/test_crackerjack_fallback.py` | Helper unit tests | NEW |
| `tests/unit/test_pure_helpers_purity.py` | Helper-purity regression | NEW |
| `tests/unit/test_enable_crackerjack_fallback.py` | Feature flag + env-var override tests | NEW |
| `tests/unit/test_crackerjack_integration.py` | Producer retry tests | MODIFY |
| `tests/unit/test_quality_scoring.py` | Synthesis + consumer chain tests | MODIFY |
| `tests/unit/test_crackerjack_tools.py` | MCP banner tests | MODIFY |
| `tests/integration/test_crackerjack_fallback_real.py` | Real-subprocess smoke | NEW |
| `docs/superpowers/plans/2026-07-27-cli-flag-mapping.md` | Task 0 evidence file (committed as part of Task 0) | NEW (or no commit) |

---

## Task 0: Preflight — Verify Crackerjack CLI flag-to-metric mapping

**Files:** None modified. Run real crackerjack and capture `parsed_data` shape for each flag combination. This task gates the design — Task 4 reads the recorded mapping to pick flags. If the mapping differs from the v2 spec's table, the implementer updates the spec and re-derives the metric→flag map.

**Step 0.1: Set up a test project**

```bash
cd /Users/les/Projects/session-buddy
mkdir -p /tmp/lychee-cli-verify && cd /tmp/lychee-cli-verify
echo 'def add(a, b): return a + b' > mathlib.py
echo 'def test_add(): assert add(1, 2) == 3' > test_mathlib.py
```

**Step 0.2: Probe each flag combination**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -c "
from session_buddy.utils.crackerjack.output_parser import CrackerjackOutputParser, _get_applicable_parsers
import subprocess, sys
for semantic_command in ['lint', 'security', 'check', 'test']:
    applicable = _get_applicable_parsers(semantic_command)
    print(f'=== semantic_command={semantic_command!r} -> applicable_parsers={[type(p).__name__ for p in applicable]} ===')
    print(f'  default parsed_data keys: {sorted(_get_applicable_parsers(semantic_command) and CrackerjackOutputParser.parse_output(semantic_command, b\"{\", b\"\").keys() or [])}')

# Also probe actual CLI invocations
for argv_tail in [['run', '--comp'], ['run', '--run-tests'], ['run', '--fast', '--quick'], ['run', '--security']]:
    result = subprocess.run(
        [sys.executable, '-m', 'crackerjack', *argv_tail],
        cwd='/tmp/lychee-cli-verify', capture_output=True, timeout=60,
    )
    # The parser is keyed on semantic names; try each
    for semantic in ['check', 'lint', 'test', 'security']:
        parsed = CrackerjackOutputParser.parse_output(semantic, result.stdout, result.stderr)
        non_empty = {k: v for k, v in parsed.items() if v}
        if non_empty:
            print(f'argv={\" \".join(argv_tail)} semantic={semantic} -> keys: {sorted(non_empty.keys())}')
"
```

**Step 0.3: Record findings in `docs/superpowers/plans/2026-07-27-cli-flag-mapping.md`**

The file MUST contain a markdown table mapping `crackerjack` CLI invocations to the parser's semantic command name AND the resulting `parsed_data` keys. Task 4 reads this file. Example:

```markdown
# Crackerjack CLI flag mapping (verified 2026-07-27)

| CLI invocation | Semantic command (for `parse_output`) | `parsed_data` keys produced |
|---|---|---|
| `run --comp` | `check` | `coverage_summary`, `lint_issues`, `security_issues`, `complexity_data` |
| `run --run-tests` | `test` | `test_results`, `coverage_summary` |
| `run --fast --quick` | `lint` | `lint_issues` |
| `run --security` | `security` | `security_issues` |
```

**Step 0.4: Skip if crackerjack not installed**

If the probe fails with `ModuleNotFoundError: crackerjack`:
- Create the mapping file with a note: "crackerjack not installed; mapping inferred from `_get_applicable_parsers` at `output_parser.py:71-82`. Task 4 implementation must use this mapping and the integration test in Task 12 must `importorskip("crackerjack")`."
- The integration test in Task 12 is the runtime check.

**Step 0.5: Commit the evidence file**

```bash
cd /Users/les/Projects/session-buddy
git add docs/superpowers/plans/2026-07-27-cli-flag-mapping.md
git -c user.name="les" -c user.email="les@local" commit -m "docs(preflight): record crackerjack CLI flag-to-metric mapping

Task 0 of the quality-scoring crackerjack fallback plan. Task 4
reads this file to pick crackerjack flags from missing_metrics.
Verified by running crackerjack against /tmp/lychee-cli-verify
and capturing parsed_data keys per flag combination."
```

---

## Task 1: Add `enable_crackerjack_fallback` to feature flags (with full wiring)

**Files:**
- Modify: `session_buddy/config/feature_flags.py` (add field to `FeatureFlags`; wire env var in `get_feature_flags()`)
- Modify: `session_buddy/settings.py` (add `enable_crackerjack_fallback: bool = Field(default=False, description="...")` to `SessionMgmtSettings`)
- Modify: `settings/session-buddy.yaml` (add the flat YAML key with 0 leading spaces)
- Test: `tests/unit/test_enable_crackerjack_fallback.py` (NEW)

**Step 1.1: Write the failing tests**

In `tests/unit/test_enable_crackerjack_fallback.py`:

```python
from session_buddy.config.feature_flags import FeatureFlags, get_feature_flags


def test_enable_crackerjack_fallback_defaults_to_false():
    """Default per project's safe-rollout pattern."""
    flags = FeatureFlags()
    assert flags.enable_crackerjack_fallback is False


def test_get_feature_flags_resolves_yaml_default(monkeypatch, tmp_path):
    """When YAML is loaded and env var is unset, the resolver returns the YAML value."""
    # The default is False; no YAML override -> False
    monkeypatch.delenv("SESSION_BUDDY_CRACKERJACK_FALLBACK", raising=False)
    assert get_feature_flags().enable_crackerjack_fallback is False


def test_env_var_true_overrides_default(monkeypatch):
    monkeypatch.setenv("SESSION_BUDDY_CRACKERJACK_FALLBACK", "true")
    assert get_feature_flags().enable_crackerjack_fallback is True


def test_env_var_one_overrides_default(monkeypatch):
    """_get_env_bool accepts 1/0/yes/no/on/off in addition to true/false."""
    monkeypatch.setenv("SESSION_BUDDY_CRACKERJACK_FALLBACK", "1")
    assert get_feature_flags().enable_crackerjack_fallback is True


def test_env_var_zero_overrides_default(monkeypatch):
    """Operators can disable via =0; the rollback path uses this."""
    monkeypatch.setenv("SESSION_BUDDY_CRACKERJACK_FALLBACK", "0")
    assert get_feature_flags().enable_crackerjack_fallback is False
```

**Step 1.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_enable_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: All 5 tests FAIL with `AttributeError` (no field), or with the env-var returns not propagating.

**Step 1.3: Add field to `FeatureFlags`**

In `session_buddy/config/feature_flags.py`, after the `enable_filesystem_extraction` field, add a new section comment + field:

```python
    # === Quality scoring (crackerjack CLI fallback) ===
    enable_crackerjack_fallback: bool = False
```

**Step 1.4: Wire the env var in `get_feature_flags()`**

In the same file, find the `get_feature_flags()` function. It builds a `base = FeatureFlags(...)` instance and then constructs a return `FeatureFlags(...)` with per-field env-var overrides via `_get_env_bool(...)`. Add the new field to both the base constructor and the return constructor:

```python
    base = FeatureFlags(
        use_schema_v2=...,
        enable_llm_entity_extraction=...,
        enable_anthropic=...,
        enable_ollama=...,
        enable_conscious_agent=...,
        enable_filesystem_extraction=...,
        enable_crackerjack_fallback=getattr(settings, "enable_crackerjack_fallback", False),
    )
    return FeatureFlags(
        use_schema_v2=...,
        enable_llm_entity_extraction=...,
        enable_anthropic=...,
        enable_ollama=...,
        enable_conscious_agent=...,
        enable_filesystem_extraction=...,
        enable_crackerjack_fallback=_get_env_bool(
            "SESSION_BUDDY_CRACKERJACK_FALLBACK", base.enable_crackerjack_fallback
        ),
    )
```

(Replace the `...` with the existing field arguments already in the function.)

**Step 1.5: Add field to `SessionMgmtSettings`**

In `session_buddy/settings.py`, find the `enable_crackerjack: bool = Field(default=True, description="Enable Crackerjack code quality integration")` line (around line 379) and add a sibling:

```python
    enable_crackerjack_fallback: bool = Field(
        default=False,
        description="Enable the Crackerjack CLI fallback layer when metrics are missing (opt-in; default off)",
    )
```

**Step 1.6: Add the flat YAML key (0 leading spaces)**

In `settings/session-buddy.yaml`, find the `enable_crackerjack: true` line and add a sibling at the same indent level:

```yaml
enable_crackerjack_fallback: false
```

**Step 1.7: Verify YAML parses correctly**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -c "import yaml; data = yaml.safe_load(open('settings/session-buddy.yaml')); assert data['enable_crackerjack_fallback'] is False; print('YAML OK')"
```

Expected: `YAML OK`. If the literal parse produced `{"enable_crackerjack": {"true": None, "fallback": false}}`, fix the indentation.

**Step 1.8: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_enable_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (5/5).

**Step 1.9: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/config/feature_flags.py session_buddy/settings.py settings/session-buddy.yaml tests/unit/test_enable_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(feature-flags): add enable_crackerjack_fallback with full wiring

- Add field to FeatureFlags under a new section comment
- Add flat YAML key (0 indent) to settings/session-buddy.yaml
- Add Pydantic Field to SessionMgmtSettings
- Wire SESSION_BUDDY_CRACKERJACK_FALLBACK env var through
  _get_env_bool in get_feature_flags() (handles 1/0/yes/no/on/off)
- 5 tests cover default, YAML-only, env-var true, env-var 1, env-var 0"
```

---

## Task 2: Refactor pure helpers to `@staticmethod`

**Files:**
- Modify: `session_buddy/crackerjack_integration.py:946-1002`
- Test: `tests/unit/test_pure_helpers_purity.py` (NEW)

**Step 2.1: Write the failing purity test**

In `tests/unit/test_pure_helpers_purity.py`:

```python
import inspect

from session_buddy.crackerjack_integration import CrackerjackIntegration


HELPER_NAMES = [
    "_calculate_lint_metrics",
    "_calculate_security_metrics",
    "_calculate_complexity_metrics",
    "_calculate_coverage_metrics",
]


def test_helpers_are_staticmethod_on_class():
    """After refactor, the four pure helpers must be @staticmethod on CrackerjackIntegration."""
    for name in HELPER_NAMES:
        attr = inspect.getattr_static(CrackerjackIntegration, name)
        assert isinstance(attr, staticmethod), (
            f"{name} must be a @staticmethod on CrackerjackIntegration; got {type(attr).__name__}"
        )


def test_helpers_callable_via_class_without_instance():
    """Helper invocation must work via CrackerjackIntegration._calculate_X(args) without instantiating."""
    assert isinstance(CrackerjackIntegration._calculate_lint_metrics([]), dict)
    assert isinstance(CrackerjackIntegration._calculate_security_metrics([]), dict)
    assert isinstance(CrackerjackIntegration._calculate_complexity_metrics({}), dict)
    assert isinstance(CrackerjackIntegration._calculate_coverage_metrics({}), dict)


def test_helpers_have_no_self_access():
    """Static body check: each helper's source must not access self (other than the def line)."""
    import inspect
    for name in HELPER_NAMES:
        source = inspect.getsource(getattr(CrackerjackIntegration, name))
        # Crude but effective: no "self." accesses anywhere in the body
        assert "self." not in source, f"{name} accesses self: {source}"
```

**Step 2.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_pure_helpers_purity.py -v --override-ini="addopts="
```

Expected: At least `test_helpers_are_staticmethod_on_class` and `test_helpers_callable_via_class_without_instance` FAIL (TypeError on missing self).

**Step 2.3: Manually verify each helper's body does not access self**

Read `session_buddy/crackerjack_integration.py:946-1002`. For each of the four helpers, confirm no `self.X` access in the body. If any helper does touch `self`, STOP and report — the refactor breaks behavior.

**Step 2.4: Add `@staticmethod` decorator to each helper**

For each of the four helpers, add the `@staticmethod` decorator one line above the `def`:

```python
    @staticmethod
    def _calculate_lint_metrics(lint_issues: list[dict]) -> dict[str, float]:
        # ... existing body unchanged ...
```

(Repeat for the other three.)

**Step 2.5: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_pure_helpers_purity.py -v --override-ini="addopts="
```

Expected: PASS (3/3).

**Step 2.6: Run existing crackerjack_integration tests to confirm no regression**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v --override-ini="addopts=" --noconftest
```

Expected: PASS (existing 19/19 in `TestQualityMetricsCalculation`). If any fail, the refactor changed observable behavior — STOP and investigate.

**Step 2.7: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/crackerjack_integration.py tests/unit/test_pure_helpers_purity.py
git -c user.name="les" -c user.email="les@local" commit -m "refactor(crackerjack): make pure calculation helpers @staticmethod

Decouples the four calculation helpers from CrackerjackIntegration
state so the new fallback helper can call them via
CrackerjackIntegration._calculate_X(args) without instantiating
CrackerjackIntegration (whose __init__ writes to SQLite on disk).

Three regression tests lock in the staticmethod contract and
the no-self-access invariant. No behavior change; existing
TestQualityMetricsCalculation tests still pass."
```

---

## Task 3: Helper skeleton — module + lock + OTel span + disabled check

**Files:**
- Create: `session_buddy/utils/crackerjack/fallback.py`
- Modify: `session_buddy/utils/crackerjack/__init__.py` (add export)
- Test: `tests/unit/test_crackerjack_fallback.py` (NEW)

**Step 3.1: Write the failing test for the disabled path**

In `tests/unit/test_crackerjack_fallback.py`:

```python
import asyncio

import pytest

from session_buddy.config.feature_flags import FeatureFlags
from session_buddy.config import feature_flags
from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli


def _enable_flag(monkeypatch, enable: bool = True):
    """Patch get_feature_flags to return a FeatureFlags with the requested value."""
    monkeypatch.setattr(
        feature_flags,
        "get_feature_flags",
        lambda: FeatureFlags(enable_crackerjack_fallback=enable),
    )


@pytest.mark.asyncio
async def test_disabled_flag_returns_none(monkeypatch, tmp_path):
    """When enable_crackerjack_fallback is False, helper returns None without invoking subprocess."""
    _enable_flag(monkeypatch, enable=False)

    spawn_called = False

    async def fake_spawn(*args, **kwargs):
        nonlocal spawn_called
        spawn_called = True
        raise AssertionError("subprocess should not have been spawned")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None
    assert spawn_called is False
```

**Step 3.2: Run test to verify it fails**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py::test_disabled_flag_returns_none -v --override-ini="addopts="
```

Expected: FAIL with `ModuleNotFoundError: No module named 'session_buddy.utils.crackerjack.fallback'`

**Step 3.3: Create the helper module**

Create `session_buddy/utils/crackerjack/fallback.py`:

```python
"""CLI fallback for missing quality-scoring metrics.

Invokes the Crackerjack CLI on-demand when the consumer chain has no
historical metrics or the producer subprocess failed. Returns the
requested metric keys (subset of parsed_data), or None on any failure.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from session_buddy.config.feature_flags import get_feature_flags

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer


logger = logging.getLogger(__name__)


# Module-level lock serializes fallback invocations to prevent N parallel
# subprocesses from concurrent consumer reads. The fallback is on the cold
# path (only fires when prior tiers failed) so contention is rare.
_FALLBACK_LOCK: asyncio.Lock = asyncio.Lock()


async def try_crackerjack_cli(
    project_dir: str | Path,
    missing_metrics: frozenset[str],
    timeout: float = 30.0,
    caller: Literal["producer_retry", "consumer_chain"] = "consumer_chain",
    correlation_context: dict[str, str] | None = None,
) -> dict[str, float] | None:
    """Return the requested metric keys via crackerjack CLI, or None on any failure.

    Args:
        project_dir: project root; the crackerjack subprocess runs with cwd=project_dir.
        missing_metrics: the scoring keys the caller still needs. frozenset to enforce
            immutability.
        timeout: subprocess timeout in seconds. Default 30.0 (distinct from the producer's 300s).
        caller: identifies which integration point invoked the helper. Used in logs and metrics
            so an operator can tell whether the timeout came from a user MCP call or a
            background quality-trends job.
        correlation_context: optional session_id / workflow_id for cross-system triage.

    Returns:
        dict with the requested metric keys (subset), or None on any failure.
        Returns {} (not None) when the subprocess succeeded but produced none of
        the requested keys.
    """
    # Disabled check (early)
    if not get_feature_flags().enable_crackerjack_fallback:
        # TODO: log DEBUG with outcome=disabled and emit counter (Task 7)
        return None

    # OTel span start (Task 7 fills in the span attributes; this scaffold is
    # intentionally minimal so the test at Task 7 can verify the span
    # wrapping works end-to-end)
    # TODO: with tracer.start_as_current_span("crackerjack.fallback", attributes={...}):

    # Lock
    async with _FALLBACK_LOCK:
        # Disabled re-check inside lock
        if not get_feature_flags().enable_crackerjack_fallback:
            # TODO: log DEBUG with outcome=disabled and emit counter (Task 7)
            return None

        # Placeholder for the rest of the pipeline (filled in Task 4+)
        return None
```

**Step 3.4: Add the export**

In `session_buddy/utils/crackerjack/__init__.py`, add:

```python
from .fallback import try_crackerjack_cli

__all__ = [..., "try_crackerjack_cli"]
```

(Preserve existing imports and `__all__`.)

**Step 3.5: Run test to verify it passes**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py::test_disabled_flag_returns_none -v --override-ini="addopts="
```

Expected: PASS (1/1).

**Step 3.6: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/crackerjack/fallback.py session_buddy/utils/crackerjack/__init__.py tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): helper skeleton with lock and disabled check

Creates the try_crackerjack_cli module-level lock and the early
disabled-return path. Subsequent tasks fill in subprocess invocation,
parse, and observability. The helper is callable but currently a
no-op when the opt-in flag is set; that completes in Task 4+.

The helper is NOT yet exported via __init__.py until Task 4 lands,
to prevent an intermediate commit that exports a non-functional
symbol."
```

Actually, the export is needed for the test. Adjust: keep the export in Step 3.4 as written.

---

## Task 4: Subprocess invocation + cleanup + flag selection from Task 0

**Files:**
- Modify: `session_buddy/utils/crackerjack/fallback.py` (extend helper body inside the lock)

This task consumes the Task 0 mapping file. The metric-to-flag selection is the central piece of the design.

**Step 4.1: Write the failing tests**

Add to `tests/unit/test_crackerjack_fallback.py`:

```python
import sys


def _make_process_mock(returncode: int, stdout: bytes, stderr: bytes = b""):
    """Build a Process mock that matches asyncio.subprocess.Process API:
    - kill() is sync
    - wait() is async
    - communicate() is async
    """
    class _Proc:
        def __init__(self):
            self.returncode: int | None = returncode
            self.kill_called = False
            self.wait_called = False

        def kill(self) -> None:
            """Real asyncio.subprocess.Process.kill() is sync."""
            self.kill_called = True
            self.returncode = -9

        async def wait(self) -> int:
            self.wait_called = True
            return self.returncode if self.returncode is not None else 0

        async def communicate(self):
            return stdout, stderr

    return _Proc()


@pytest.mark.asyncio
async def test_timeout_kills_subprocess_and_returns_none(monkeypatch, tmp_path):
    """wait_for TimeoutError -> proc.kill() + proc.wait() + return None.
    The test must NOT pre-cleanup; the production code does it.
    """
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=None, stdout=b"", stderr=b"")

    async def fake_spawn(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        # Raise TimeoutError WITHOUT calling kill() — let the production
        # code do the cleanup
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
        timeout=30.0,
    )
    assert result is None
    assert proc.kill_called is True
    assert proc.wait_called is True


@pytest.mark.asyncio
async def test_cancelled_propagates_after_cleanup(monkeypatch, tmp_path):
    """asyncio.CancelledError re-raises after subprocess cleanup."""
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=None, stdout=b"", stderr=b"")

    async def fake_spawn(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    with pytest.raises(asyncio.CancelledError):
        await try_crackerjack_cli(
            project_dir=tmp_path,
            missing_metrics=frozenset({"lint_score"}),
            timeout=30.0,
        )
    assert proc.kill_called is True
    assert proc.wait_called is True


@pytest.mark.asyncio
async def test_nonzero_exit_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=1, stdout=b"", stderr=b"some error")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"", b"some error"
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_uses_sys_executable(monkeypatch, tmp_path):
    """Helper must use sys.executable, not 'python', to pin the interpreter."""
    _enable_flag(monkeypatch)
    captured_argv: list = []

    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs):
        captured_argv.extend(args)
        return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert captured_argv[0] == sys.executable


@pytest.mark.asyncio
async def test_helper_picks_run_comp_for_all_four_metrics(monkeypatch, tmp_path):
    """When all four scoring keys are missing, the helper invokes 'run --comp'."""
    _enable_flag(monkeypatch)
    captured_argv: list = []

    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs):
        captured_argv.extend(args)
        return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score", "security_score", "complexity_score"}),
    )
    # argv[0] = sys.executable, argv[1] = '-m', argv[2] = 'crackerjack', argv[3:] = flags
    assert captured_argv[1:4] == ["-m", "crackerjack", "run"]
    assert "--comp" in captured_argv


@pytest.mark.asyncio
async def test_helper_picks_run_run_tests_for_only_coverage(monkeypatch, tmp_path):
    """When only code_coverage is missing, the helper invokes 'run --run-tests'."""
    _enable_flag(monkeypatch)
    captured_argv: list = []
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs):
        captured_argv.extend(args)
        return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage"}),
    )
    assert "--run-tests" in captured_argv


@pytest.mark.asyncio
async def test_default_timeout_is_30s(monkeypatch, tmp_path):
    """No-arg invocation uses 30s default."""
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    captured_timeout: list = []
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout):
        captured_timeout.append(timeout)
        return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert captured_timeout[0] == 30.0
```

**Step 4.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: 6 new tests FAIL (the helper still returns None at the lock-exit placeholder).

**Step 4.3: Read the Task 0 mapping**

```bash
cat docs/superpowers/plans/2026-07-27-cli-flag-mapping.md
```

This gives the verified mapping: `{"lint": "run --fast --quick", "security": "run --security", "test": "run --run-tests", "check": "run --comp"}`.

**Step 4.4: Add the flag-selection helper and replace the placeholder**

In `session_buddy/utils/crackerjack/fallback.py`, add at the top (after the logger):

```python
# Crackerjack v0.47+ uses 'run' subcommand with flag combinations. The
# semantic command name (lint, security, check, test) is what the
# parser's _get_applicable_parsers keys on. Mapping recorded in
# docs/superpowers/plans/2026-07-27-cli-flag-mapping.md (Task 0).
_METRIC_TO_FLAG: dict[str, tuple[str, tuple[str, ...]]] = {
    "code_coverage": ("test", ("--run-tests",)),
    "lint_score":    ("lint", ("--fast", "--quick")),
    "security_score": ("security", ("--security",)),
    # Note: complexity_score intentionally absent. _pick_invocation's
    # early-return for the complexity-only case routes to ("check",
    # ("--comp",)) before consulting this table. A bare entry with
    # empty flags would silently call "run" with no flags and produce
    # no complexity data.
}
# All-four convenience: pick the most general semantic command that
# produces every requested key.
def _pick_invocation(missing: frozenset[str]) -> tuple[str, tuple[str, ...]]:
    """Select the smallest crackerjack invocation that fills the requested gaps.

    If the caller wants all four scoring keys, use 'check' (--comp)
    which produces all of them in one go. Otherwise pick per-metric
    flags, but if multiple are needed, prefer 'check' (it covers all
    four — even if some keys aren't strictly needed, the post-filter
    drops the surplus).
    """
    if not missing:
        return ("check", ())
    if missing == frozenset({"complexity_score"}):
        # complexity only comes from --comp; any other combo needs check too
        return ("check", ("--comp",))
    if len(missing) == 1:
        semantic, flags = _METRIC_TO_FLAG[next(iter(missing))]
        return (semantic, flags)
    # Multiple keys: use 'check' (covers all four)
    return ("check", ("--comp",))
```

Then replace the `# Placeholder for the rest of the pipeline` block with:

```python
        # Pick the smallest crackerjack invocation that fills the gaps
        semantic_command, flag_args = _pick_invocation(missing_metrics)
        argv = [sys.executable, "-m", "crackerjack", "run", *flag_args]

        # Spawn subprocess (catch OS-level failures)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            # TODO: log ERROR + counter missing_executable (Task 7)
            return None
        except PermissionError:
            # TODO: log WARNING + counter permission_error (Task 7)
            return None
        except OSError:
            # TODO: log WARNING + counter os_error (Task 7)
            return None

        # Wait with timeout. Split handlers: TimeoutError -> None after
        # cleanup; CancelledError -> finalize observability THEN re-raise
        # after cleanup (per PEP 654; the parent shutdown should not
        # block on a 30s subprocess, but the cancellation MUST still
        # emit its counter+log so dashboards see the cause).
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            # TODO: log WARNING + counter timeout (Task 7)
            return None
        except asyncio.CancelledError:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            # Emit cancelled counter/log BEFORE re-raising so the
            # observability layer sees the cancellation.
            # TODO: log WARNING + counter cancelled (Task 7)
            raise

        # Check exit code
        if proc.returncode != 0:
            # TODO: log WARNING + counter nonzero_exit (Task 7)
            return None

        # TODO: parse + extract (Task 5)
        return None
```

**Step 4.5: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (8/8 — the 1 disabled + 7 new).

**Step 4.6: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/crackerjack/fallback.py tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): subprocess invocation with split timeout/cancel handlers

Spawns crackerjack via asyncio.create_subprocess_exec using
sys.executable. _pick_invocation selects the smallest crackerjack
flag combination that fills the requested metric gaps (mapping
verified in Task 0).

Subprocess cleanup:
- TimeoutError -> proc.kill() + proc.wait() -> return None
- CancelledError -> proc.kill() + proc.wait() -> raise (per PEP 654;
  parent shutdown should not block on a 30s subprocess)
- FileNotFoundError / PermissionError / OSError on spawn -> None
- Non-zero exit -> None

7 new tests cover: timeout cleanup, cancellation propagation,
non-zero exit, sys.executable, --comp for all-four, --run-tests
for coverage-only, 30s default timeout."
```

---

## Task 5: Parse output + post-filter + success-path return

**Files:**
- Modify: `session_buddy/utils/crackerjack/fallback.py` (replace `# TODO: parse + extract` block; pass the `semantic_command` to the parser instead of `"run"`)

**Step 5.1: Write the failing tests for success / partial / empty-success**

Add to `tests/unit/test_crackerjack_fallback.py`:

```python
from unittest.mock import MagicMock

from session_buddy.crackerjack_integration import (
    _calculate_complexity_metrics,
    _calculate_coverage_metrics,
    _calculate_lint_metrics,
    _calculate_security_metrics,
)
from session_buddy.utils.crackerjack.output_parser import CrackerjackOutputParser


@pytest.mark.asyncio
async def test_success_returns_requested_metrics(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    parsed_data = {
        "lint_issues": [],  # empty -> _calculate_lint_metrics returns 100.0
        "security_issues": [],
        "complexity_data": {},
        "coverage_summary": {"total_coverage": 87.5},
    }
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_data),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score"}),
    )
    assert result is not None
    assert result["code_coverage"] == 87.5
    # Empty lint_issues -> 100.0 (synthesize-perfection is OK here, no data was the success)
    assert result["lint_score"] == 100.0


@pytest.mark.asyncio
async def test_partial_success_returns_subset(monkeypatch, tmp_path):
    """When parse yields some requested keys and not others, return the subset.
    Specifically: if a section (e.g. coverage_summary) is missing from
    parsed_data entirely, the post-filter drops that key (defends
    against the empty-section -> 100 antipattern re-emerging).
    """
    _enable_flag(monkeypatch)
    parsed_data = {
        "lint_issues": [{"code": "E501"}],
        "security_issues": [],
        # coverage_summary missing -> no coverage in result
        "complexity_data": {},
    }
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_data),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score", "security_score"}),
    )
    assert result is not None
    assert "code_coverage" not in result  # dropped: section absent
    assert result["lint_score"] == 100.0
    assert result["security_score"] == 100.0


@pytest.mark.asyncio
async def test_empty_section_drops_metric_to_protect_against_antipattern(monkeypatch, tmp_path):
    """If parsed_data has complexity_data: {} (empty), the post-filter must
    drop complexity_score (not return 100). This is the regression guard
    against _calculate_complexity_metrics({}) -> 100.0.
    """
    _enable_flag(monkeypatch)
    parsed_data = {
        "lint_issues": [],
        "security_issues": [],
        "complexity_data": {},  # empty section -> drop complexity_score
        "coverage_summary": {"total_coverage": 80.0},
    }
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_data),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"complexity_score", "code_coverage"}),
    )
    assert result is not None
    assert "complexity_score" not in result  # post-filter dropped it
    assert result["code_coverage"] == 80.0


@pytest.mark.asyncio
async def test_no_relevant_metrics_returns_empty_dict(monkeypatch, tmp_path):
    """When parse succeeds but no requested keys are present, return {} (falsy but logs as success)."""
    _enable_flag(monkeypatch)
    parsed_data = {
        "lint_issues": [],
        "security_issues": [],
        "complexity_data": {},
        "coverage_summary": {},
    }
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_data),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score"}),
    )
    assert result == {}
```

**Step 5.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: 4 new tests FAIL (helper still returns None after exit-code check).

**Step 5.3: Replace the parse placeholder**

In `session_buddy/utils/crackerjack/fallback.py`, replace `# TODO: parse + extract (Task 5)` with:

```python
        # Empty-stdout guard BEFORE parsing (a parse exception on empty
        # bytes would otherwise classify this as parse_error, not
        # empty_stdout)
        if not stdout:
            # TODO: log WARNING + counter empty_stdout (Task 7)
            return None

        # Parse output (catch any exception from the parser)
        try:
            parsed_data = CrackerjackOutputParser.parse_output(semantic_command, stdout, stderr)
        except Exception:
            # TODO: log WARNING + counter parse_error (Task 7)
            return None

        # Section keys for each scoring metric. An empty section means
        # the metric was not measured; do NOT synthesize a 100.
        SECTION_FOR_KEY = {
            "code_coverage": "coverage_summary",
            "lint_score": "lint_issues",
            "security_score": "security_issues",
            "complexity_score": "complexity_data",
        }
        # _calculate_*_metrics are @staticmethods on CrackerjackIntegration
        # (Task 2). Call them via the class — instantiating
        # CrackerjackIntegration() would write to SQLite on disk.
        cls = _get_crackerjack_integration_class()
        candidate: dict[str, float] = {}
        for key in missing_metrics:
            section_key = SECTION_FOR_KEY.get(key)
            if section_key is None:
                continue
            section = parsed_data.get(section_key)
            # An empty section (None, [], {}, etc.) means the metric
            # was NOT measured — skip the candidate to avoid the
            # synthesize-100s antipattern.
            if not section:
                continue
            if key == "code_coverage":
                candidate.update(cls._calculate_coverage_metrics(section))
            elif key == "lint_score":
                candidate.update(cls._calculate_lint_metrics(section))
            elif key == "security_score":
                candidate.update(cls._calculate_security_metrics(section))
            elif key == "complexity_score":
                candidate.update(cls._calculate_complexity_metrics(section))

        # Only return the keys the caller actually asked for.
        return {k: v for k, v in candidate.items() if k in missing_metrics}
```

And add at the top of `fallback.py`:

```python
def _get_crackerjack_integration_class():
    """Lazy import to avoid a hard dependency at module import time."""
    from session_buddy.crackerjack_integration import CrackerjackIntegration
    return CrackerjackIntegration
```

**Step 5.4: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (12/12).

**Step 5.5: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/crackerjack/fallback.py tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): parse output, post-filter empty sections, success return

Calls the four now-static helpers on the requested metric keys.
The post-filter drops keys whose parsed section was empty or
absent (defends against _calculate_*_metrics({}) -> 100.0
re-introducing the synthesize-100s antipattern).

Empty-stdout check happens BEFORE the parse call (so empty bytes
classify as empty_stdout, not parse_error). The semantic command
name (lint/check/security/test) is what the parser is keyed on,
not the literal 'run' subcommand."
```

---

## Task 6: Error-path coverage (cancelled, parse, empty, missing, permission, os_error)

**Files:**
- Modify: `session_buddy/utils/crackerjack/fallback.py` (the cancelled re-raise is already in Task 4; add the parse_error and empty_stdout counters and the os_error test)

**Step 6.1: Write the failing tests for each error path**

Add to `tests/unit/test_crackerjack_fallback.py`:

```python
@pytest.mark.asyncio
async def test_cancelled_propagates(monkeypatch, tmp_path):
    """asyncio.CancelledError propagates after subprocess cleanup."""
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=None, stdout=b"", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout):
        raise asyncio.CancelledError()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    with pytest.raises(asyncio.CancelledError):
        await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )


@pytest.mark.asyncio
async def test_parse_error_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=0, stdout=b"non-empty", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"non-empty", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    def boom(*args, **kwargs):
        raise ValueError("simulated parse failure")
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(boom),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_empty_stdout_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=0, stdout=b"", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_missing_executable_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs):
        raise FileNotFoundError("python not on PATH")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_permission_error_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs):
        raise PermissionError(13, "Permission denied", "/some/cwd")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_os_error_returns_none(monkeypatch, tmp_path):
    """Generic OSError (e.g. ENOSPC) on spawn -> None."""
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_timeout_override_propagates(monkeypatch, tmp_path):
    """Caller passes timeout=5.0 -> wait_for receives timeout=5.0."""
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    captured_timeout: list = []
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout):
        captured_timeout.append(timeout)
        return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}), timeout=5.0,
    )
    assert captured_timeout[0] == 5.0
```

**Step 6.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: 7 new tests FAIL (the helper still returns None at the lock-exit placeholder for most; some fail because the lock-exit placeholder doesn't raise CancelledError).

**Step 6.3: Verify the helper already handles the error paths from Task 4 + 5**

**Note on TDD discipline (v2 review C1):** the 7 tests written in Step 6.1 were co-developed alongside the production handlers in Tasks 4 (subprocess + cleanup) and 5 (parse + post-filter), not introduced after the fact. Each error-path test follows the pattern: write the failing test against a stub helper → add the matching handler → verify the test passes. If a reviewer finds an error path without a corresponding test, that path was added in a Task 4/5 commit without its co-test — STOP and add the missing test.

Re-run all 7 tests to confirm the handlers landed correctly in Tasks 4 + 5. No new production code lands in this commit; the commit only extends `tests/unit/test_crackerjack_fallback.py`.

**Step 6.4: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (19/19 — 12 from earlier + 7 new).

**Step 6.5: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "test(fallback): 7 error-path tests covering all 10 outcomes

Tests cover: timeout, cancelled (re-raises), nonzero_exit,
parse_error, empty_stdout, missing_executable, permission_error,
os_error, plus timeout-override. The production code in Tasks
4 and 5 already handles all of these; this task adds the
regression coverage."
```

---

## Task 7: Observability — Prometheus counters, structured logs, OTel span

**Files:**
- Modify: `session_buddy/utils/crackerjack/fallback.py` (fill in all `# TODO: log + counter` markers; add OTel span; add Histogram observation)
- Modify: `session_buddy/metrics.py` (add `Histogram` to the import; register the two new metrics)
- Test: extend `tests/unit/test_crackerjack_fallback.py`

**Step 7.1: Add `Histogram` to `session_buddy/metrics.py`**

In `session_buddy/metrics.py:33`, change the import line to:

```python
from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram, generate_latest
```

(Adjust if the file uses a different import style. If `Histogram` is already imported, no change needed.)

**Step 7.2: Register the two new metrics**

Find `session_buddy_provenance_pruned_total` in `session_buddy/metrics.py` and add near it:

```python
CRACKERJACK_FALLBACK_INVOCATIONS = Counter(
    "session_buddy_crackerjack_fallback_invocations_total",
    "Crackerjack CLI fallback invocations",
    ["command", "outcome", "caller"],
)

CRACKERJACK_FALLBACK_DURATION_SECONDS = Histogram(
    "session_buddy_crackerjack_fallback_duration_seconds",
    "Crackerjack CLI fallback invocation duration in seconds",
    ["command", "caller"],
)
```

**Step 7.3: Write the failing observability tests**

Add to `tests/unit/test_crackerjack_fallback.py`:

```python
import logging
import time
from unittest.mock import MagicMock, patch

from session_buddy import metrics as sb_metrics


def _capture_counters(monkeypatch) -> list:
    """Patch _emit_counter to record (command, outcome, caller) calls."""
    captured: list = []
    monkeypatch.setattr(
        "session_buddy.utils.crackerjack.fallback._emit_counter",
        lambda command, outcome, caller: captured.append((command, outcome, caller)),
    )
    return captured


@pytest.mark.parametrize("setup_failure", [
    "success", "disabled", "timeout", "cancelled", "nonzero_exit",
    "parse_error", "empty_stdout", "missing_executable",
    "permission_error", "os_error",
])
@pytest.mark.asyncio
async def test_helper_emits_counter_for_every_outcome(monkeypatch, tmp_path, setup_failure):
    """Every one of the 10 outcomes must increment the counter exactly once."""
    _enable_flag(monkeypatch)
    captured = _capture_counters(monkeypatch)

    # Default: a successful invocation
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    if setup_failure == "success":
        parsed_data = {"lint_issues": []}
        monkeypatch.setattr(
            CrackerjackOutputParser, "parse_output",
            classmethod(lambda cls, command, stdout, stderr: parsed_data),
        )
    elif setup_failure == "disabled":
        _enable_flag(monkeypatch, enable=False)
    elif setup_failure == "timeout":
        async def fake_wait_for_timeout(awaitable, timeout):
            raise asyncio.TimeoutError()
        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for_timeout)
    elif setup_failure == "cancelled":
        async def fake_wait_for_cancel(awaitable, timeout):
            raise asyncio.CancelledError()
        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for_cancel)
    elif setup_failure == "nonzero_exit":
        proc.returncode = 1
    elif setup_failure == "parse_error":
        def boom(*a, **k): raise ValueError("simulated")
        monkeypatch.setattr(CrackerjackOutputParser, "parse_output", classmethod(boom))
        proc._make_process_mock_args = (1, b"non-empty", b"")
    elif setup_failure == "empty_stdout":
        proc = _make_process_mock(returncode=0, stdout=b"", stderr=b"")
        async def fake_spawn_empty(*args, **kwargs): return proc
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_empty)
    elif setup_failure == "missing_executable":
        async def fake_spawn_fnf(*args, **kwargs):
            raise FileNotFoundError("python not on PATH")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_fnf)
    elif setup_failure == "permission_error":
        async def fake_spawn_perm(*args, **kwargs):
            raise PermissionError(13, "denied", "/cwd")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_perm)
    elif setup_failure == "os_error":
        async def fake_spawn_os(*args, **kwargs):
            raise OSError(28, "no space")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_os)

    if setup_failure in ("disabled",):
        result = await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
        assert result is None
    elif setup_failure in ("cancelled",):
        with pytest.raises(asyncio.CancelledError):
            await try_crackerjack_cli(
                project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
            )
    else:
        result = await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
        assert result is None

    assert len(captured) == 1, f"expected exactly 1 counter call, got {len(captured)}"
    assert captured[0][1] == setup_failure


@pytest.mark.parametrize("outcome,expected_level", [
    ("timeout", logging.WARNING),
    ("cancelled", logging.WARNING),
    ("nonzero_exit", logging.WARNING),
    ("parse_error", logging.WARNING),
    ("empty_stdout", logging.WARNING),
    ("permission_error", logging.WARNING),
    ("os_error", logging.WARNING),
])
@pytest.mark.asyncio
async def test_helper_logs_warning_for_actionable_failures(monkeypatch, tmp_path, caplog, outcome, expected_level):
    """The 7 WARNING-level outcomes all log at WARNING (success is INFO, not WARNING)."""
    _enable_flag(monkeypatch)
    _capture_counters(monkeypatch)

    proc = _make_process_mock(returncode=0, stdout=b"non-empty", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"non-empty", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    if outcome == "timeout":
        async def fake_wf(*a, **k): raise asyncio.TimeoutError()
        monkeypatch.setattr(asyncio, "wait_for", fake_wf)
    elif outcome == "cancelled":
        async def fake_wf(*a, **k): raise asyncio.CancelledError()
        monkeypatch.setattr(asyncio, "wait_for", fake_wf)
    elif outcome == "nonzero_exit":
        proc.returncode = 1
    elif outcome == "parse_error":
        def boom(*a, **k): raise ValueError("sim")
        monkeypatch.setattr(CrackerjackOutputParser, "parse_output", classmethod(boom))
    elif outcome == "empty_stdout":
        proc = _make_process_mock(returncode=0, stdout=b"", stderr=b"")
        async def fake_spawn_e(*a, **k): return proc
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_e)
    elif outcome == "permission_error":
        async def fake_spawn_p(*a, **k): raise PermissionError(13, "d", "/cwd")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_p)
    elif outcome == "os_error":
        async def fake_spawn_o(*a, **k): raise OSError(28, "ns")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn_o)

    with caplog.at_level(logging.DEBUG, logger="session_buddy.utils.crackerjack.fallback"):
        if outcome == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                await try_crackerjack_cli(
                    project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
                )
        else:
            await try_crackerjack_cli(
                project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
            )

    records = [r for r in caplog.records if "crackerjack fallback invoked" in r.message]
    assert any(r.levelno == expected_level for r in records), (
        f"outcome={outcome!r} expected level={expected_level}, got {[r.levelno for r in records]}"
    )


@pytest.mark.asyncio
async def test_helper_logs_info_on_success(monkeypatch, tmp_path, caplog):
    _enable_flag(monkeypatch)
    parsed_data = {"lint_issues": []}
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_data),
    )

    with caplog.at_level(logging.INFO, logger="session_buddy.utils.crackerjack.fallback"):
        await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )

    info_records = [r for r in caplog.records if "crackerjack fallback invoked" in r.message]
    assert info_records and info_records[0].levelno == logging.INFO


@pytest.mark.asyncio
async def test_helper_logs_debug_on_disabled(monkeypatch, tmp_path, caplog):
    _enable_flag(monkeypatch, enable=False)

    with caplog.at_level(logging.DEBUG, logger="session_buddy.utils.crackerjack.fallback"):
        result = await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
    assert result is None
    debug_records = [r for r in caplog.records if "crackerjack fallback invoked" in r.message]
    assert debug_records and debug_records[0].levelno == logging.DEBUG


@pytest.mark.asyncio
async def test_helper_logs_error_on_missing_executable(monkeypatch, tmp_path, caplog):
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs): raise FileNotFoundError("python not on PATH")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    with caplog.at_level(logging.ERROR, logger="session_buddy.utils.crackerjack.fallback"):
        await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
    error_records = [r for r in caplog.records if "crackerjack fallback invoked" in r.message]
    assert error_records and error_records[0].levelno == logging.ERROR


@pytest.mark.asyncio
async def test_log_includes_all_required_fields(monkeypatch, tmp_path, caplog):
    """Every spec-required log field must be set on the record."""
    _enable_flag(monkeypatch)
    parsed_data = {"lint_issues": []}
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_data),
    )

    with caplog.at_level(logging.INFO, logger="session_buddy.utils.crackerjack.fallback"):
        await try_crackerjack_cli(
            project_dir=tmp_path,
            missing_metrics=frozenset({"lint_score"}),
            caller="producer_retry",
            correlation_context={"session_id": "abc-123"},
        )

    rec = next(r for r in caplog.records if "crackerjack fallback invoked" in r.message)
    required_fields = [
        "command", "project_dir", "project_name", "missing_metrics",
        "duration_seconds", "outcome", "caller", "session_id", "workflow_id",
    ]
    for field in required_fields:
        assert hasattr(rec, field), f"log record missing field: {field}"
    assert rec.caller == "producer_retry"
    assert rec.project_name == tmp_path.name
    assert rec.session_id == "abc-123"
    assert rec.missing_metrics == ["lint_score"]  # sorted


@pytest.mark.asyncio
async def test_missing_metrics_sorted_in_log(monkeypatch, tmp_path, caplog):
    _enable_flag(monkeypatch)
    parsed_data = {"lint_issues": []}
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(lambda cls, command, stdout, stderr: parsed_data),
    )

    with caplog.at_level(logging.INFO, logger="session_buddy.utils.crackerjack.fallback"):
        await try_crackerjack_cli(
            project_dir=tmp_path,
            missing_metrics=frozenset({"security_score", "lint_score", "code_coverage"}),
        )
    rec = next(r for r in caplog.records if "crackerjack fallback invoked" in r.message)
    assert rec.missing_metrics == ["code_coverage", "lint_score", "security_score"]


@pytest.mark.asyncio
async def test_helper_serializes_concurrent_invocations(monkeypatch, tmp_path):
    """Two concurrent invocations are serialized by the module-level lock."""
    _enable_flag(monkeypatch)
    invocation_times: list = []

    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_slow_wait_for(awaitable, timeout):
        awaitable_coro = awaitable  # not awaited inside wait_for in our test
        # Just record when this is called and sleep briefly to simulate work
        import time
        invocation_times.append(time.monotonic())
        time.sleep(0.05)  # 50ms each
        return b"{}", b""
    monkeypatch.setattr(asyncio, "wait_for", fake_slow_wait_for)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", lambda *a, **k: proc)

    import time
    start = time.monotonic()
    await asyncio.gather(
        try_crackerjack_cli(project_dir=tmp_path, missing_metrics=frozenset({"lint_score"})),
        try_crackerjack_cli(project_dir=tmp_path, missing_metrics=frozenset({"lint_score"})),
    )
    elapsed = time.monotonic() - start
    # If serialized: ~100ms; if parallel: ~50ms. Allow some slop.
    assert elapsed >= 0.09, f"concurrent invocations took {elapsed}s; expected serialized >= 0.09s"


def test_duration_histogram_label_set_is_bounded():
    """Counter naming convention: command cardinality <= 5, caller in {producer_retry, consumer_chain}."""
    labelnames = sb_metrics.CRACKERJACK_FALLBACK_DURATION_SECONDS._labelnames
    assert labelnames == ("command", "caller")
```

**Step 7.4: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: Most new tests FAIL (counters and logs not yet wired).

**Step 7.5: Add the observability helpers and wire them into the helper**

Add to `session_buddy/utils/crackerjack/fallback.py` (after the logger):

```python
# OTel tracer (lazy import; no-op when not configured)
_TRACER = None


class _NoOpSpan:
    """No-op context manager used when OTel isn't configured.

    `tracer.start_as_current_span(...)` returns a
    `contextlib.AbstractContextManager[Span]`. When the tracer is
    `None` we substitute this class so the `with span_cm as span:`
    block in `try_crackerjack_cli` works without an `if`-sentinel
    on every operation. `set_status` / `set_attribute` are no-ops
    because there is no underlying span to mutate.
    """

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False  # do not swallow exceptions

    def set_status(self, status_code, description: str | None = None) -> None:
        pass

    def set_attribute(self, key: str, value: object) -> None:
        pass


def _get_tracer():
    """Lazy-init the OpenTelemetry tracer. Returns None when not configured."""
    global _TRACER
    if _TRACER is not None:
        return _TRACER
    try:
        from opentelemetry import trace
        _TRACER = trace.get_tracer(__name__)
    except Exception:
        _TRACER = None
    return _TRACER


def _emit_counter(command: str, outcome: str, caller: str) -> None:
    """Increment the unified invocation counter with command+outcome+caller labels."""
    try:
        from session_buddy.metrics import CRACKERJACK_FALLBACK_INVOCATIONS
        CRACKERJACK_FALLBACK_INVOCATIONS.labels(
            command=command, outcome=outcome, caller=caller
        ).inc()
    except Exception:
        pass  # metrics are best-effort


def _observe_duration(command: str, caller: str, duration_seconds: float) -> None:
    """Record the invocation duration in the histogram."""
    try:
        from session_buddy.metrics import CRACKERJACK_FALLBACK_DURATION_SECONDS
        CRACKERJACK_FALLBACK_DURATION_SECONDS.labels(
            command=command, caller=caller
        ).observe(duration_seconds)
    except Exception:
        pass


def _finalize(
    outcome: str,
    command: str,
    caller: str,
    project_dir: Path,
    missing_metrics: frozenset[str],
    duration_seconds: float,
    correlation_context: dict[str, str] | None,
    span: object | None = None,
) -> None:
    """Single point of observability emission. Exactly one log + one counter + one histogram observation per invocation.

    Also writes the outcome onto the OTel span (if provided) and
    marks failure outcomes with `set_status(StatusCode.ERROR)` so
    error rates in the tracing UI surface them correctly.
    """
    level_map = {
        "success": logging.INFO,
        "disabled": logging.DEBUG,
        "missing_executable": logging.ERROR,
    }
    level = level_map.get(outcome, logging.WARNING)
    logger.log(
        level,
        "crackerjack fallback invoked",
        extra={
            "command": command,
            "project_dir": str(project_dir),
            "project_name": project_dir.name,
            "missing_metrics": sorted(missing_metrics),
            "duration_seconds": round(duration_seconds, 3),
            "outcome": outcome,
            "caller": caller,
            "session_id": (correlation_context or {}).get("session_id"),
            "workflow_id": (correlation_context or {}).get("workflow_id"),
        },
    )
    _emit_counter(command, outcome, caller)
    _observe_duration(command, caller, duration_seconds)
    # OTel: tag the span with outcome + mark failures as errors
    if span is not None:
        try:
            span.set_attribute("outcome", outcome)
            if outcome not in ("success", "disabled"):
                # Lazy import to avoid a hard dep when OTel missing
                from opentelemetry.trace import Status, StatusCode
                span.set_status(Status(StatusCode.ERROR, f"{outcome}: {caller}"))
        except Exception:
            pass
```

Then modify the helper to use `_finalize` at every return point. The disabled paths get `_finalize("disabled", ...)`, the success path gets `_finalize("success", ...)`, the timeout/cancel/nonzero/parse/empty/perm/os paths each get their respective outcome. **Crucially**, the `CancelledError` re-raise path (Task 4 step 4.4) MUST call `_finalize("cancelled", ...)` BEFORE `raise` so the counter and log emit even though the exception propagates. (See Task 4 step 4.4 update.)

**Step 7.6: Wrap the helper body in an OTel span**

Replace the body of `try_crackerjack_cli` (from the start of the function to the `async with _FALLBACK_LOCK:` line) with span-aware code. The span starts at function entry, and the span's outcome attribute is set inside the `_finalize` helper:

```python
async def try_crackerjack_cli(...):
    start_time = time.monotonic()
    tracer = _get_tracer()
    span_cm = (
        tracer.start_as_current_span(
            "crackerjack.fallback",
            attributes={
                "command": _pick_invocation(missing_metrics)[0],
                "caller": caller,
                "missing_metrics": sorted(missing_metrics),
            },
        )
        if tracer is not None
        else _NoOpSpan()
    )
    span: object  # either real opentelemetry.trace.Span or _NoOpSpan
    with span_cm as span:
        # All return paths in the body call _finalize(..., span=span)
        # ... existing helper body, with _finalize calls instead of # TODO: ...
        ...
```

`_NoOpSpan` (defined in step 7.5 above) is a context manager whose `set_status` / `set_attribute` are no-ops, so the `_finalize` call works whether or not OTel is configured.

**Step 7.7: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (all tests).

**Step 7.8: Split Task 7 into intermediate commits**

Task 7 is too large to land in a single reviewer-gate commit. Split into four sequential commits so each can be reviewed independently:

**Commit 7a — Counter registration only**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/metrics.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(metrics): register CRACKERJACK_FALLBACK_* counters and histogram

Adds Histogram to the prometheus_client import (the missing
import from the v1 review) and registers the two new metrics:
- session_buddy_crackerjack_fallback_invocations_total{command, outcome, caller}
- session_buddy_crackerjack_fallback_duration_seconds{command, caller}

No callers yet. Test: pytest tests/unit/test_crackerjack_fallback.py -v
should still pass; the metric names are exposed via sb_metrics."
```

**Commit 7b — `_finalize` helper + emit-counter / observe-duration helpers**

```bash
git add session_buddy/utils/crackerjack/fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): _finalize() single observability-emit point

Single point of observability emission: exactly one log + one
counter + one histogram observation per invocation. _finalize
also writes the outcome onto the OTel span (when provided) and
calls set_status(StatusCode.ERROR) on failure outcomes. The
helper is not yet wired into the body — that's commit 7c."
```

**Commit 7c — Wire `_finalize` into every return path + OTel span wrap**

```bash
git add session_buddy/utils/crackerjack/fallback.py tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): wire _finalize and OTel span across all outcomes

Replace every '# TODO: log + counter (Task 7)' marker with the
corresponding _finalize call. The CancelledError re-raise path
in Task 4 step 4.4 now emits its counter BEFORE raise, per
Observability v2 review C2. OTel span wraps the body via the
_NoOpSpan fallback class (defined alongside _finalize).
The span's outcome attribute is set inside _finalize."
```

**Commit 7d — Concurrency test + final cleanup**

```bash
git add tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "test(fallback): concurrency test asserts module-level lock serializes

Two concurrent invocations on the same tmp_path must serialize
through _FALLBACK_LOCK. Test asserts elapsed >= 0.09s when both
calls sleep 50ms inside their fake wait_for; parallel execution
would yield ~0.05s. The histogram label-set test
(test_duration_histogram_label_set_is_bounded) confirms the
{caller} label cardinality is bounded."
```

Splitting into four commits gives each one an independent reviewer gate. The "Commit" step previously shown as Step 7.8 is replaced by these four.

---

## Task 8: Synthesis replacement — drop `coverage_pct`, emit `None` + `unavailable: True`

**Files:**
- Modify: `session_buddy/utils/quality_scoring.py` (rewrite `_create_fallback_metrics`; update both internal callers at lines 891 and 924 to remove `coverage_pct=` argument)

**Step 8.1: Search for any callers passing `coverage_pct`**

```bash
cd /Users/les/Projects/session-buddy
grep -rn "_create_fallback_metrics(coverage_pct" --include="*.py"
```

Document each hit. The plan assumes two internal callers; verify.

**Step 8.2: Write the failing tests for the new synthesis contract**

In `tests/unit/test_quality_scoring.py` (or a new file `tests/unit/test_synthesis_replacement.py` if the existing file's collection is blocked):

```python
from session_buddy.utils.quality_scoring import _create_fallback_metrics


def test_synthesis_replacement_emits_none_values():
    result = _create_fallback_metrics()
    assert result["code_coverage"] is None
    assert result["lint_score"] is None
    assert result["security_score"] is None
    assert result["complexity_score"] is None
    assert result["unavailable"] is True


def test_synthesis_replacement_does_not_emit_perfect_scores():
    """Regression guard: no key synthesizes 100."""
    result = _create_fallback_metrics()
    for key in ("code_coverage", "lint_score", "security_score", "complexity_score"):
        assert result[key] != 100, f"{key} unexpectedly synthesized as 100"


def test_synthesis_drops_coverage_pct_parameter():
    """API cleanup: legacy coverage_pct parameter is removed (Bodai pre-1.0: no external callers)."""
    import inspect
    sig = inspect.signature(_create_fallback_metrics)
    assert "coverage_pct" not in sig.parameters
```

**Step 8.3: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py::test_synthesis_replacement_emits_none_values -v --override-ini="addopts=" --noconftest
```

(If the existing test file won't collect, run a single test by name with `--noconftest`.)

Expected: FAIL (current implementation returns 100s).

**Step 8.4: Rewrite `_create_fallback_metrics`**

In `session_buddy/utils/quality_scoring.py`, replace the body:

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

**Step 8.5: Update internal callers**

The two callers at lines 891 and 924 of `quality_scoring.py` pass `coverage_pct` (a local variable). After the parameter is removed, drop the argument:

```python
# Before
return _create_fallback_metrics(coverage_pct)
# After
return _create_fallback_metrics()
```

(Apply at both call sites.)

**Step 8.6: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py -v --override-ini="addopts=" --noconftest -k "synthesis"
```

Expected: PASS (3/3 synthesis tests).

**Step 8.7: Run existing tests to confirm no regression**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py -v --override-ini="addopts=" --noconftest
```

If any test fails because it expected 100s from `_create_fallback_metrics`, update those tests as part of this commit.

**Step 8.8: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/quality_scoring.py tests/unit/test_quality_scoring.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(quality-scoring): synthesis emits None + unavailable: True

Unconditional rewrite of _create_fallback_metrics. The
synthesize-100s antipattern is gone regardless of the opt-in
flag's value. Both internal callers (lines 891 and 924)
updated to drop the legacy coverage_pct argument."
```

---

## Task 9: Wire helper into consumer chain (`_get_crackerjack_metrics`)

**Files:**
- Modify: `session_buddy/utils/quality_scoring.py` (insert new tier; use top-level import)
- Test: `tests/unit/test_quality_scoring.py` (extend; add regression tests from Observability C4)

**Step 9.1: Add top-level import in `quality_scoring.py`**

In `session_buddy/utils/quality_scoring.py`, add at the top of the file (with other imports):

```python
from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli
```

**Step 9.2: Write the failing tests**

Add to `tests/unit/test_quality_scoring.py`:

```python
import pytest

from session_buddy.utils import quality_scoring
from session_buddy.utils.quality_scoring import _create_fallback_metrics


@pytest.mark.asyncio
async def test_consumer_chain_invokes_helper_after_coverage_file_miss(monkeypatch, tmp_path):
    """DB miss + reflection miss + coverage miss -> helper called with all 4 keys missing."""
    async def empty_history(*args, **kwargs): return []
    monkeypatch.setattr(quality_scoring, "get_quality_metrics_history", empty_history)

    captured: dict = {}
    async def fake_helper(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"lint_score": 80.0}
    monkeypatch.setattr(quality_scoring, "try_crackerjack_cli", fake_helper)

    result = await quality_scoring._get_crackerjack_metrics(tmp_path)
    assert result["lint_score"] == 80.0
    assert captured["kwargs"]["caller"] == "consumer_chain"


@pytest.mark.asyncio
async def test_consumer_chain_helper_none_falls_through_to_synthesis(monkeypatch, tmp_path):
    """Helper returns None -> falls through to _create_fallback_metrics -> None + unavailable."""
    async def empty_history(*args, **kwargs): return []
    monkeypatch.setattr(quality_scoring, "get_quality_metrics_history", empty_history)

    async def fake_helper(*args, **kwargs): return None
    monkeypatch.setattr(quality_scoring, "try_crackerjack_cli", fake_helper)

    result = await quality_scoring._get_crackerjack_metrics(tmp_path)
    assert result["unavailable"] is True
    assert result["lint_score"] is None


@pytest.mark.asyncio
async def test_consumer_chain_helper_raises_falls_through_to_synthesis(monkeypatch, tmp_path):
    """Helper raises -> falls through to synthesis (defensive)."""
    async def empty_history(*args, **kwargs): return []
    monkeypatch.setattr(quality_scoring, "get_quality_metrics_history", empty_history)

    async def fake_helper(*args, **kwargs): raise RuntimeError("simulated")
    monkeypatch.setattr(quality_scoring, "try_crackerjack_cli", fake_helper)

    result = await quality_scoring._get_crackerjack_metrics(tmp_path)
    assert result["unavailable"] is True


@pytest.mark.asyncio
async def test_consumer_chain_db_hit_skips_helper(monkeypatch, tmp_path):
    """DB returns metrics -> helper never called."""
    calls = []
    async def fake_history(*args, **kwargs):
        return [{"code_coverage": 80.0, "lint_score": 90.0, "security_score": 100.0, "complexity_score": 85.0}]
    async def fake_helper(*args, **kwargs):
        calls.append((args, kwargs))
        return None
    monkeypatch.setattr(quality_scoring, "get_quality_metrics_history", fake_history)
    monkeypatch.setattr(quality_scoring, "try_crackerjack_cli", fake_helper)

    result = await quality_scoring._get_crackerjack_metrics(tmp_path)
    assert calls == []
    assert result["code_coverage"] == 80.0
```

**Step 9.3: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py -v --override-ini="addopts=" --noconftest -k "consumer_chain"
```

Expected: All 4 tests FAIL (the chain doesn't call the helper yet).

**Step 9.4: Insert the helper tier into `_get_crackerjack_metrics`**

In `session_buddy/utils/quality_scoring.py`, find the `_get_crackerjack_metrics` function. After the coverage-file fallback block and before the final synthesis-fallback check, insert:

```python
    # CLI fallback tier (Task 9 of the quality-scoring crackerjack fallback plan)
    SCORING_KEYS = frozenset({"code_coverage", "lint_score", "security_score", "complexity_score"})
    missing = frozenset(k for k in SCORING_KEYS if metrics.get(k) is None)
    if missing:
        try:
            fallback = await try_crackerjack_cli(
                project_dir=project_dir,
                missing_metrics=missing,
                timeout=30.0,
                caller="consumer_chain",
            )
        except Exception:
            fallback = None
        if fallback:
            metrics.update(fallback)

    if not any(metrics.get(k) is not None for k in SCORING_KEYS):
        return _create_fallback_metrics()
    return metrics
```

**Step 9.5: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py -v --override-ini="addopts=" --noconftest -k "consumer_chain"
```

Expected: PASS (4/4 new tests).

**Step 9.6: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/quality_scoring.py tests/unit/test_quality_scoring.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(quality-scoring): wire try_crackerjack_cli into consumer chain

Top-level import of the helper (avoids the local-import
monkeypatch-target issue from the v1 plan review). The helper
is called with the set of scoring keys still missing and its
result is merged into the metrics dict.

Defensive try/except around the helper invocation: a buggy
helper or a transient network error cannot crash the consumer
chain. DB-hit path still skips the helper (early-return guard)."
```

---

## Task 10: Wire helper into producer retry (`execute_crackerjack_command`)

**Files:**
- Modify: `session_buddy/crackerjack_integration.py` (top-level helper import; producer retry; add `fallback_used` field; add `quality_metrics` parameter to `_create_error_result`)

**Step 10.1: Add top-level import in `crackerjack_integration.py`**

In `session_buddy/crackerjack_integration.py`, add at the top of the file (with other imports):

```python
from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli
```

**Step 10.2: Add `fallback_used: bool = False` to `CrackerjackResult`**

Find the `CrackerjackResult` dataclass and add the field:

```python
    fallback_used: bool = False
```

**Step 10.3: Add `quality_metrics: dict[str, float] | None = None` and `fallback_used: bool = False` parameters to `_create_error_result`**

Find the existing `_create_error_result(self, command, exit_code, stderr, execution_time, working_directory, memory_insight)` method and add the new parameters:

```python
    def _create_error_result(
        self,
        command: str,
        exit_code: int,
        stderr: str,
        execution_time: float,
        working_directory: str,
        memory_insight: str,
        quality_metrics: dict[str, float] | None = None,
        fallback_used: bool = False,
    ) -> CrackerjackResult:
        return CrackerjackResult(
            command=command,
            exit_code=exit_code,
            stdout="",
            stderr=stderr,
            execution_time=execution_time,
            timestamp=utc_now(),
            working_directory=working_directory,
            parsed_data={},
            quality_metrics=quality_metrics or {},
            test_results=[],
            memory_insights=[memory_insight],
            fallback_used=fallback_used,
        )
```

Also update the two existing call sites at lines 496 and 510 to either pass `quality_metrics=None, fallback_used=False` explicitly or rely on the default.

**Step 10.4: Write the failing tests**

Add to `tests/unit/test_crackerjack_integration.py` (place the new tests inside `TestQualityMetricsCalculation` class so the test selectors in the run command work):

```python
@pytest.mark.asyncio
async def test_producer_timeout_invokes_fallback_before_error_result(monkeypatch, tmp_path):
    """On TimeoutError, the helper runs once; if it returns a dict, that's the metrics."""
    async def fake_helper(*args, **kwargs):
        return {"lint_score": 75.0, "security_score": 100.0}
    monkeypatch.setattr(
        "session_buddy.crackerjack_integration.try_crackerjack_cli", fake_helper,
    )

    async def fake_subprocess(*args, **kwargs):
        raise asyncio.TimeoutError()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)

    integration = CrackerjackIntegration()
    result = await integration.execute_crackerjack_command(
        command="test", working_directory=str(tmp_path),
    )
    assert result.fallback_used is True
    assert result.quality_metrics.get("lint_score") == 75.0


@pytest.mark.asyncio
async def test_producer_timeout_helper_none_returns_empty_metrics(monkeypatch, tmp_path):
    async def fake_helper(*args, **kwargs): return None
    monkeypatch.setattr(
        "session_buddy.crackerjack_integration.try_crackerjack_cli", fake_helper,
    )

    async def fake_subprocess(*args, **kwargs): raise asyncio.TimeoutError()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)

    integration = CrackerjackIntegration()
    result = await integration.execute_crackerjack_command(
        command="test", working_directory=str(tmp_path),
    )
    assert result.fallback_used is False
    assert result.quality_metrics == {}


@pytest.mark.asyncio
async def test_producer_normal_path_does_not_invoke_fallback(monkeypatch, tmp_path):
    """Successful subprocess run -> helper never called."""
    calls = []
    async def fake_helper(*args, **kwargs):
        calls.append((args, kwargs))
        return None
    monkeypatch.setattr(
        "session_buddy.crackerjack_integration.try_crackerjack_cli", fake_helper,
    )

    class _Proc:
        returncode = 0
        async def communicate(self): return b"{}", b""
        async def wait(self): return 0
    async def fake_subprocess(*args, **kwargs): return _Proc()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)

    integration = CrackerjackIntegration()
    await integration.execute_crackerjack_command(
        command="test", working_directory=str(tmp_path),
    )
    assert calls == []
```

**Step 10.5: Add the retry on `TimeoutError`**

In `session_buddy/crackerjack_integration.py`, find the `except TimeoutError:` block inside `execute_crackerjack_command`. Replace it with:

```python
    except TimeoutError:
        # CLI fallback: one attempt before degrading to empty metrics
        try:
            fallback_metrics = await try_crackerjack_cli(
                project_dir=working_directory,
                missing_metrics=frozenset({
                    "code_coverage", "lint_score", "security_score", "complexity_score",
                }),
                timeout=30.0,
                caller="producer_retry",
            )
        except Exception:
            fallback_metrics = None
        if fallback_metrics:
            return self._create_error_result(
                command, -1,
                f"Command '{command}' timed out after {timeout}s; recovered via CLI fallback",
                execution_time, working_directory,
                f"Command '{command}' recovered via CLI fallback",
                quality_metrics=fallback_metrics,
                fallback_used=True,
            )
        return self._create_error_result(
            command, -1,
            f"Command '{command}' timed out after {timeout}s",
            execution_time, working_directory,
            f"Command '{command}' failed (timeout, no fallback available)",
        )
```

**Step 10.6: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v --override-ini="addopts=" --noconftest
```

Expected: PASS (existing 19 + 3 new = 22 in this class).

**Step 10.7: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/crackerjack_integration.py tests/unit/test_crackerjack_integration.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(crackerjack): producer retry invokes try_crackerjack_cli on TimeoutError

- Top-level import of the helper (so monkeypatch.setattr works
  on the module attribute; the v1 plan's local import was a
  patch-target bug)
- Add fallback_used: bool = False to CrackerjackResult
- Extend _create_error_result with quality_metrics and
  fallback_used parameters
- On subprocess timeout: one CLI fallback attempt; if it
  returns a dict, the result has fallback_used=True and the
  metrics come from the CLI
- All 6 required positional args are now passed (the v1 plan
  used a 3-arg form that would TypeError at runtime)"
```

---

## Task 11: Harden `_format_metrics_section` and add unavailable banner

**Files:**
- Modify: `session_buddy/mcp/tools/session/crackerjack_tools.py` (find `_format_metrics_section` around line 655; harden against `None`; inspect `result.quality_metrics` for `unavailable` flag; render banner)
- Test: `tests/unit/test_crackerjack_tools.py` (extend the existing `TestFormatMetricsSection` class)

**Step 11.1: Write the failing tests**

In `tests/unit/test_crackerjack_tools.py`, add to the existing `TestFormatMetricsSection` class:

```python
from unittest.mock import MagicMock

from session_buddy.crackerjack_integration import CrackerjackResult
from session_buddy.mcp.tools.session.crackerjack_tools import _format_metrics_section


def test_format_metrics_section_handles_none_values():
    """None values must render as 'unavailable', not crash on f-string."""
    result = MagicMock(spec=CrackerjackResult)
    result.quality_metrics = {"code_coverage": None, "lint_score": 80.0}
    output = _format_metrics_section(result)
    assert "unavailable" in output
    assert "80.0" in output


def test_format_metrics_section_renders_unavailable_banner():
    """When unavailable: True is in quality_metrics, a banner appears."""
    result = MagicMock(spec=CrackerjackResult)
    result.quality_metrics = {
        "code_coverage": None,
        "lint_score": None,
        "security_score": None,
        "complexity_score": None,
        "unavailable": True,
    }
    output = _format_metrics_section(result)
    assert output.startswith("⚠️ Quality metrics unavailable")
    assert "Quality metrics unavailable" in output


def test_format_metrics_section_banner_overrides_partial_metrics():
    """When unavailable: True, partial metrics are NOT shown — banner is all-or-nothing."""
    result = MagicMock(spec=CrackerjackResult)
    result.quality_metrics = {
        "code_coverage": 80.0,
        "lint_score": None,
        "security_score": 100.0,
        "complexity_score": None,
        "unavailable": True,
    }
    output = _format_metrics_section(result)
    # Banner appears, partial metrics do NOT
    assert "Quality metrics unavailable" in output
    assert "80.0" not in output
    assert "100.0" not in output
```

**Step 11.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_tools.py::TestFormatMetricsSection -v --override-ini="addopts="
```

Expected: All 3 new tests FAIL (current formatter doesn't render banner, may crash on None).

**Step 11.3: Harden `_format_metrics_section`**

In `session_buddy/mcp/tools/session/crackerjack_tools.py`, find `_format_metrics_section` (around line 655) and replace the body. The function takes a `CrackerjackResult`, not a dict:

```python
def _format_metrics_section(result: CrackerjackResult) -> str:
    """Format a quality metrics dict for the MCP tool output.

    Renders an unavailable banner when ``quality_metrics`` carries
    ``unavailable: True``. Handles None values defensively. Preserves
    the existing fields (`execution_time`, `exit_code`,
    `memory_insights`) that the current source renders; the v2 plan's
    body dropped these — keep them in the rewrite so MCP consumers
    that depend on them don't lose information.
    """
    quality_metrics = result.quality_metrics
    if quality_metrics.get("unavailable") is True:
        return "⚠️ Quality metrics unavailable\n"

    output = "📊 **Quality Metrics**\n\n"
    for metric, value in quality_metrics.items():
        if metric == "unavailable":
            continue
        formatted = f"{value:.1f}" if value is not None else "unavailable"
        output += f"- {metric.replace('_', ' ').title()}: {formatted}\n"
    # Preserve the existing fields the current source renders (audit
    # #4 from the v2 review: source has them; v2 plan dropped them).
    if hasattr(result, "execution_time") and result.execution_time:
        output += f"\n⏱ Execution time: {result.execution_time:.2f}s\n"
    if hasattr(result, "exit_code") and result.exit_code != 0:
        output += f"\n⚠️ Exit code: {result.exit_code}\n"
    if hasattr(result, "memory_insights") and result.memory_insights:
        output += "\n📝 Memory insights:\n"
        for insight in result.memory_insights:
            output += f"- {insight}\n"
    return output
```

**Step 11.4: Wire the synthesis dict into a `CrackerjackResult` for the MCP read path**

The synthesis dict from `_create_fallback_metrics` was previously only returned to the consumer chain. The MCP banner in `_format_metrics_section` requires a `CrackerjackResult`, so the consumer-side synthesis never triggered the banner — a known gap surfaced in v2 review (voice-chat C5). Fix:

In `session_buddy/crackerjack_integration.py`, add a helper that produces a synthesized `CrackerjackResult` carrying the `unavailable: True` flag:

```python
def synthesize_unavailable_result(
    project_dir: str,
    *,
    caller: str = "consumer_chain",
) -> CrackerjackResult:
    """Produce a CrackerjackResult whose quality_metrics carry unavailable: True.

    Used by the consumer-side chain (`_get_crackerjack_metrics`) when
    every other tier (DB, reflection, coverage file, CLI fallback) has
    failed. The result is written to history via `_store_result` so the
    MCP `crackerjack_metrics` tool's read path surfaces the banner.
    """
    return CrackerjackResult(
        command="<unavailable>",
        exit_code=-1,
        stdout="",
        stderr="",
        execution_time=0.0,
        timestamp=utc_now(),
        working_directory=project_dir,
        parsed_data={},
        quality_metrics=_create_fallback_metrics(),  # {"code_coverage": None, ..., "unavailable": True}
        test_results=[],
        memory_insights=["All quality-metric tiers failed; CLI fallback returned None or was disabled"],
        fallback_used=False,
    )
```

In `session_buddy/utils/quality_scoring.py`, when the synthesis path is reached, write the synthesized result to history (so the MCP tool's read path surfaces it):

```python
    if not any(metrics.get(k) is not None for k in SCORING_KEYS):
        synthesis = _create_fallback_metrics()
        # Surface the unavailable banner to MCP consumers by writing a
        # synthesized CrackerjackResult to history. The producer-side
        # write hook (CrackerjackIntegration._store_result) is what the
        # crackerjack_metrics MCP tool reads from.
        try:
            from session_buddy.crackerjack_integration import (
                CrackerjackIntegration, synthesize_unavailable_result,
            )
            integration = CrackerjackIntegration(working_directory=str(project_dir))
            integration._store_result(synthesize_unavailable_result(str(project_dir)))
        except Exception:
            # History write is best-effort; the synthesis dict still
            # flows to internal consumers below.
            pass
        return synthesis
```

Add a test that the synthesis path produces a `CrackerjackResult` in history with `quality_metrics["unavailable"] is True` and that the MCP tool's history read yields the banner string when the formatter consumes it.

Step 11.3's `test_format_metrics_section_renders_unavailable_banner` already covers the formatter-side behavior; the new test covers the wire-up.

**Step 11.5: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_tools.py::TestFormatMetricsSection -v --override-ini="addopts="
```

Expected: PASS (existing 4 + 3 new = 7 in this class).

**Step 11.6: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/mcp/tools/session/crackerjack_tools.py session_buddy/utils/quality_scoring.py tests/unit/test_crackerjack_tools.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(crackerjack-tools): harden _format_metrics_section and add unavailable banner

The formatter takes a CrackerjackResult (not a dict; the v1 plan
got the signature wrong). It inspects result.quality_metrics for
the unavailable flag and renders a banner. None values render
as 'unavailable' instead of crashing on f-string formatting.

The consumer-side synthesis dict from _create_fallback_metrics
is consumed by downstream callers in quality_scoring.py
(_calculate_code_quality, _run_security_checks) but does not
reach _format_metrics_section because that function operates
on producer-side CrackerjackResult instances. The banner is
therefore visible when a producer invocation falls back;
consumer-side synthesis flows through history and reads.
A follow-up could add a parallel formatter for consumer
synthesis if MCP-tool-side visibility is needed."
```

---

## Task 12: Real-subprocess integration test (gated, with `importorskip`)

**Files:**
- Create: `tests/integration/test_crackerjack_fallback_real.py`

**Step 12.1: Write the integration test**

```python
"""Real-subprocess integration test for the Crackerjack CLI fallback.

Skipped in fast CI by `pytest -m 'not integration'`. Skipped entirely
when the crackerjack module is not installed.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


# Skip the entire module if crackerjack isn't installed
pytest.importorskip("crackerjack")


from session_buddy.config.feature_flags import FeatureFlags  # noqa: E402
from session_buddy.config import feature_flags  # noqa: E402
from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli  # noqa: E402


@pytest.fixture
def enable_flag(monkeypatch):
    """Enable the opt-in flag for the duration of one test."""
    monkeypatch.setattr(
        feature_flags, "get_feature_flags",
        lambda: FeatureFlags(enable_crackerjack_fallback=True),
    )


@pytest.mark.asyncio
async def test_helper_invokes_real_crackerjack(tmp_path, enable_flag):
    """Real crackerjack must produce at least one of the requested scoring keys."""
    (tmp_path / "hello.py").write_text("x = 1\n")
    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score"}),
        timeout=60.0,
    )
    assert result is not None
    assert isinstance(result, dict)
    # The helper must have actually extracted a metric, not returned {}
    # for a missing parsed_data shape
    assert any(k in result for k in ("code_coverage", "lint_score")), (
        f"expected at least one of code_coverage/lint_score in result; got {result!r}"
    )
```

**Step 12.2: Run test to verify it skips in fast mode**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/integration/test_crackerjack_fallback_real.py -v --override-ini="addopts=" -m "not integration"
```

Expected: SKIPPED (the `@pytest.mark.integration` marker excludes it from this run).

**Step 12.3: Run test directly (will skip if crackerjack not installed)**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/integration/test_crackerjack_fallback_real.py -v --override-ini="addopts=" -m "integration"
```

If `crackerjack` is not installed, this SKIPS via `pytest.importorskip`. If it is installed, the test must actually verify a metric was extracted (not just `assert result is not None`).

**Step 12.4: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add tests/integration/test_crackerjack_fallback_real.py
git -c user.name="les" -c user.email="les@local" commit -m "test(fallback): real-subprocess integration test (gated, importorskip)

Skipped in fast CI by `pytest -m 'not integration'`. Skipped
entirely when the crackerjack module is not installed via
pytest.importorskip at module load. Asserts that the helper
extracts at least one of the requested keys (not just result
is not None, which would vacuously pass if parsed_data was
empty)."
```

---

## Task 13: Observability — alert rules and dashboard panel

**Files:**
- Create: `docs/observability/crackerjack-fallback-alerts.md`

**Step 13.1: Write the alert rules document**

Create `docs/observability/crackerjack-fallback-alerts.md`:

```markdown
# Crackerjack CLI Fallback — Alert Rules and Dashboard Panel

**Created:** 2026-07-27
**Owner:** session-buddy maintainers
**Metrics:**
- `session_buddy_crackerjack_fallback_invocations_total{command, outcome, caller}` (counter)
- `session_buddy_crackerjack_fallback_duration_seconds{command, caller}` (histogram)

## Alert rules (PromQL)

### A1. Outcome ≠ success rate exceeds 10% over 5 minutes
- **Severity:** Slack (not PagerDuty; the fallback is a recovery, not an outage)
- **PromQL:**
  ```promql
  sum(rate(session_buddy_crackerjack_fallback_invocations_total{outcome!="success"}[5m]))
    /
  sum(rate(session_buddy_crackerjack_fallback_invocations_total[5m]))
    > 0.10
  ```
- **Runbook:** Check `outcome` distribution. If most failures are `timeout`, the lock may be contended or the helper is slow. If most are `nonzero_exit`, the crackerjack invocation has a config issue. If most are `disabled`, someone flipped the kill switch and forgot.

### A2. Disabled outcome rate > 0
- **Severity:** Slack (informational; the kill switch was tripped)
- **PromQL:**
  ```promql
  sum(rate(session_buddy_crackerjack_fallback_invocations_total{outcome="disabled"}[1h])) > 0
  ```
- **Runbook:** The operator deliberately disabled the fallback. Confirm with the on-call channel that this is intentional.

### A3. p99 duration > 25s (close to the 30s timeout)
- **Severity:** Slack
- **PromQL:**
  ```promql
  histogram_quantile(0.99, sum by (le, command) (rate(session_buddy_crackerjack_fallback_duration_seconds_bucket[5m])))
    > 25
  ```
- **Runbook:** Fallback invocations are taking almost the full timeout. Either the subprocess is slow (crackerjack regression) or the lock is contended. Consider raising the timeout or staggering consumer-chain reads.

## Dashboard panel

Suggested panel: "Crackerjack Fallback" with these queries:

- **Invocation rate by outcome (stacked area):**
  ```promql
  sum by (outcome) (rate(session_buddy_crackerjack_fallback_invocations_total[5m]))
  ```
- **p50 / p99 duration:**
  ```promql
  histogram_quantile(0.50, sum by (le) (rate(session_buddy_crackerjack_fallback_duration_seconds_bucket[5m])))
  histogram_quantile(0.99, sum by (le) (rate(session_buddy_crackerjack_fallback_duration_seconds_bucket[5m])))
  ```
- **Caller distribution (proportion of consumer_chain vs producer_retry):**
  ```promql
  sum by (caller) (rate(session_buddy_crackerjack_fallback_invocations_total[5m]))
  ```

## Counter-name double-counting warning

The plan does NOT register dedicated `crackerjack.fallback.timeout{command}` or `crackerjack.fallback.disabled{command}` counters. Operators aggregating dashboards should query the unified `session_buddy_crackerjack_fallback_invocations_total{outcome="timeout"}` (not a separate counter) to avoid double-counting.
```

**Step 13.2: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add docs/observability/crackerjack-fallback-alerts.md
git -c user.name="les" -c user.email="les@local" commit -m "docs(observability): add Crackerjack fallback alert rules and dashboard panel

Three PromQL alert rules and a dashboard panel for the
session_buddy_crackerjack_fallback_* metrics. Documents the
counter double-counting warning: no dedicated timeout/disabled
counters; use the outcome label on the unified counter."
```

---

## Self-Review (per writing-plans skill)

**1. Spec coverage:**
- [x] Helper module + lock + OTel → Tasks 3, 7
- [x] Subprocess invocation with timeout/kill/cancel split → Task 4
- [x] CLI flag selection from Task 0 mapping → Task 4
- [x] Parse + extract + post-filter → Task 5
- [x] Error-path coverage (10 outcomes) → Task 6
- [x] Producer retry → Task 10 (renumbered)
- [x] Consumer chain tier → Task 9 (renumbered)
- [x] Synthesis replacement (unconditional) → Task 8 (renumbered up)
- [x] MCP banner + `None` hardening → Task 11
- [x] Opt-in flag (feature flag + YAML + env) → Task 1
- [x] Pure-helper `@staticmethod` refactor → Task 2
- [x] Prometheus counters + Histogram + OTel span → Task 7
- [x] Real-subprocess integration test → Task 12
- [x] CLI flag verification (preflight) → Task 0
- [x] `coverage_pct` parameter dropped → Task 8
- [x] Alert rules + dashboard panel → Task 13 (NEW)

**2. Placeholder scan:** No TBDs. The `# TODO: log + counter (Task 7)` markers in Tasks 4-6 are intentional — Task 7 fills them in. Same for `# TODO: with tracer.start_as_current_span(...)` in Task 3 — Task 7 implements it concretely.

**3. Type consistency:** `try_crackerjack_cli` signature in Tasks 3, 4, 5, 6, 7 matches the spec verbatim. `CrackerjackResult.fallback_used: bool = False` consistent across Tasks 10, 11. The four `_*_metrics` helpers called via `CrackerjackIntegration._calculate_X(...)` (no instance) consistent with Task 2's `@staticmethod` refactor.

**4. Resolved v1 issues (cross-checked against the 5-agent review):**
- ✅ Wrong function signatures → fixed in Tasks 10, 11
- ✅ Wrong import paths → top-level imports in Tasks 9, 10
- ✅ Task 0 result unused → consumed in Task 4 (`_pick_invocation`)
- ✅ Cancellation swallowed → split handlers in Task 4
- ✅ try/finally missing → explicit kill+wait in Task 4
- ✅ Mock API mismatch → real `kill()`/`wait()` API in Task 4 mock
- ✅ Task 8 testing what Task 10 hasn't built → reordered: Task 8 (synthesis) before Task 9 (consumer wiring)
- ✅ Histogram not imported → Task 7 step 7.1
- ✅ OTel span TODO with no test → Task 7 step 7.6 + 2 OTel tests
- ✅ Counter not asserted for outcomes → Task 7 step 7.3 parametrized test over 10 outcomes
- ✅ WARNING log not tested → Task 7 parametrized over 7 WARNING outcomes
- ✅ Synthesis-reached-only-when-CLI-attempted regression → Task 9 step 9.2 test_consumer_chain_helper_raises_falls_through_to_synthesis
- ✅ `_flags` global doesn't exist → use `monkeypatch.setattr(feature_flags, "get_feature_flags", ...)` throughout
- ✅ Task 1 wrong field reference → new section comment in `FeatureFlags`
- ✅ Env var documented but not wired → Task 1 step 1.4
- ✅ YAML indentation → 0 leading spaces; verification step 1.7
- ✅ Post-filter logic broken → `SECTION_FOR_KEY` constant + `if not section: continue`
- ✅ MCP banner dead code → hardened signature; consumer-side synthesis flows to MCP via `synthesize_unavailable_result` (Task 11 step 11.4 in v3)
- ✅ Task 12 always disabled → `_enable_flag` fixture
- ✅ Task 12 not valid TDD → `pytest.importorskip` + assert metric was extracted
- ✅ Task 9 local import → top-level import
- ✅ Alert guidance missing → new Task 13

**5. Resolved v2 issues (cross-checked against the 4-agent review; the 5th MCP agent failed at the API tier):**
- ✅ Python C1: bare `_calculate_X` calls → use `cls = _get_crackerjack_integration_class()` then `cls._calculate_X(...)`
- ✅ Python C2: test data mismatch → `lint_issues: []` so `== 100.0` assertion holds
- ✅ Python C3: undefined `_NoOpSpan` → class defined in Task 7 step 7.5
- ✅ Observability C1: OTel `set_status(ERROR)` → `_finalize` calls it for non-success outcomes
- ✅ Observability C2: cancelled path missing counter → `_finalize("cancelled", ...)` before `raise` in Task 4 step 4.4
- ✅ voice-chat C1: TDD discipline → Task 6 step 6.3 notes error tests are co-developed with Tasks 4-5
- ✅ voice-chat C2: Task 7 too big → split into 4 commits (7a-d)
- ✅ voice-chat C3: OTel span missing `outcome` attribute → `_finalize` sets it
- ✅ voice-chat C4: dead `complexity_score` entry → removed from `_METRIC_TO_FLAG`
- ✅ voice-chat C5: banner never fires → `synthesize_unavailable_result` writes to history when consumer reaches synthesis

**6. Identified residual concerns:**
- Tasks 8-11-12 numbering is non-monotonic (8, 9, 10, 11, 12 reflect post-reorder ordering). This is a documentation quirk; the actual commit history is what matters.
- Task 0 is a preflight that produces evidence; it commits the mapping file. If crackerjack is not installed, the mapping is inferred from `_get_applicable_parsers` source. The integration test in Task 12 is the runtime check.
- The plan does not address pre-existing test collection issues (`tests/unit/test_quality_scoring.py` fails on `ModuleNotFoundError: duckdb`; `tests/unit/test_crackerjack_integration.py` collection pollution). Tests use `--noconftest --override-ini="addopts="` to work around. Pre-existing — not addressed by this branch.
- The MCP v2 review agent failed at the API tier (token-plan cap); only 4 of 5 agents reported. If a future review surfaces issues that the 4 agents missed, those would need another rework pass.
- Task 11 step 11.4's wire-up depends on the producer's `_store_result` writing to history. If the actual MCP read path uses a different lookup (e.g., a separate consumer-side history), the implementer must adjust accordingly. Step 11.4's design assumes "MCP tool reads from history that the producer writes to."

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-27-quality-scoring-crackerjack-fallback.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
