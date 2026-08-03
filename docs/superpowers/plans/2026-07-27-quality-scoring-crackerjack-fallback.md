# Quality-Scoring Crackerjack CLI Fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CLI-invocation fallback layer to session-buddy's `quality_scoring` module that recovers from failed/missing metrics reads by invoking crackerjack on-demand, and unconditionally eliminate the synthesize-100s antipattern from the terminal fallback.

**Architecture:** New `try_crackerjack_cli` helper in `session_buddy/utils/crackerjack/fallback.py` invokes crackerjack via `asyncio.create_subprocess_exec` with the v0.47+ `run` subcommand + flag combinations. Wired into the producer's `TimeoutError` path and the consumer's missing-keys chain tier. The terminal synthesis function is rewritten to emit `None` + `unavailable: True` instead of perfect scores. Module-level `asyncio.Lock` serializes invocations. OTel span wraps every invocation. Prometheus counters use `session_buddy_*_total` naming.

**Tech Stack:** Python 3.13, `asyncio.create_subprocess_exec`, `prometheus_client`, `opentelemetry.trace`, `pytest` + `pytest-asyncio`, `monkeypatch.setattr` for subprocess mocking.

## Global Constraints

These apply to every task. The spec is the source of truth for any disagreement; this list is a digest.

- **Spec**: `/Users/les/Projects/session-buddy/docs/superpowers/specs/2026-07-27-quality-scoring-crackerjack-fallback-design.md` (v2)
- **Crackerjack CLI shape**: v0.47+ uses `python -m crackerjack run --comp|--fast --quick|--security|--run-tests [args]`. Bare `crackerjack check` / `crackerjack lint` do not exist. Verify in Task 0.
- **Opt-in default**: `enable_crackerjack_fallback: bool = False`. Synthesis change is unconditional; the flag controls only whether the CLI attempt fires.
- **Env var**: `SESSION_BUDDY_CRACKERJACK_FALLBACK` (per Oneiric project-name strip, not `MAHAVISHNU_`).
- **YAML key (flat)**: `enable_crackerjack_fallback` in `settings/session-buddy.yaml`. `SessionMgmtSettings.load()` only reads flat top-level keys.
- **Counter naming**: `session_buddy_crackerjack_fallback_invocations_total{command, outcome, caller}` and `session_buddy_crackerjack_fallback_duration_seconds{command, caller}` (Prometheus `_total` suffix, `session_buddy_` prefix). No dedicated `timeout`/`disabled` counters — use the `outcome` label.
- **Log levels**: `success` → INFO, `disabled` → DEBUG, `missing_executable` → ERROR, all other failures → WARNING.
- **Helper signature**: `async def try_crackerjack_cli(project_dir: str | Path, missing_metrics: frozenset[str], timeout: float = 30.0, caller: Literal["producer_retry", "consumer_chain"] = "consumer_chain", correlation_context: dict[str, str] | None = None) -> dict[str, float] | None`
- **Subprocess cleanup**: `try/finally` with `proc.kill()` + `await proc.wait()` on timeout/cancellation.
- **Interpreter**: `sys.executable`, not `"python"`.
- **Outcome taxonomy**: 10 values: `success`, `timeout`, `cancelled`, `nonzero_exit`, `parse_error`, `empty_stdout`, `missing_executable`, `permission_error`, `os_error`, `disabled`.
- **frozenset**: `missing_metrics` is `frozenset[str]`. The set is sorted lexicographically before logging.
- **Module-level `asyncio.Lock`**: `_FALLBACK_LOCK` in `fallback.py`, acquired inside the helper.
- **Pure helper refactor**: `_calculate_lint_metrics` etc. become `@staticmethod` so the helper can call them without instantiating `CrackerjackIntegration` (which writes to SQLite on `__init__`).
- **`coverage_pct` parameter**: dropped from `_create_fallback_metrics()` entirely. Per Bodai pre-1.0 merge policy, no external callers.
- **`CrackerjackResult.fallback_used`**: new `bool = False` field.
- **Mock strategy**: helper uses `import asyncio` (not `from asyncio import create_subprocess_exec`). Tests use `monkeypatch.setattr("asyncio.create_subprocess_exec", ...)`.
- **Pytest markers**: existing markers only — `unit`, `integration`, `requires_network`, `slow`. Do not invent new markers.
- **Pre-existing test pollution**: `tests/unit/test_quality_scoring.py` collection fails on `ModuleNotFoundError: duckdb`; `tests/unit/test_crackerjack_integration.py` collection fails on the conftest `sys.modules` pollution pattern. Run tests narrowly with `--noconftest --override-ini="addopts="` when needed.
- **No `assert` in production code** (bandit B101). Use the `session_buddy/core/errors.py` exception hierarchy.
- **Bodai pre-1.0 merge policy**: components merge directly to `main`; no PRs, no review gates. Branch + squash/ff-merge into `main` is the expected flow.
- **Coverage target**: 100% line + branch for the new helper; ≥95% for modified sections of existing modules.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `session_buddy/utils/crackerjack/fallback.py` | New helper + lock + OTel span | NEW |
| `session_buddy/utils/crackerjack/__init__.py` | Export new helper | MODIFY (1 line) |
| `session_buddy/utils/quality_scoring.py` | Consumer chain tier + synthesis replacement + drop `coverage_pct` | MODIFY |
| `session_buddy/crackerjack_integration.py` | Producer retry + `fallback_used` field + helper `@staticmethod` refactor | MODIFY |
| `session_buddy/mcp/tools/session/crackerjack_tools.py` | Banner rendering + `None` handling | MODIFY |
| `session_buddy/config/feature_flags.py` | Add `enable_crackerjack_fallback` field | MODIFY |
| `session_buddy/metrics.py` (or new `session_buddy/mcp/fallback_metrics.py`) | Prometheus counters | MODIFY or NEW |
| `settings/session-buddy.yaml` | Default for opt-in flag | MODIFY |
| `tests/unit/test_crackerjack_fallback.py` | Helper unit tests | NEW |
| `tests/unit/test_pure_helpers_purity.py` | Helper-purity regression | NEW |
| `tests/unit/test_crackerjack_integration.py` | Producer retry tests | MODIFY |
| `tests/unit/test_quality_scoring.py` | Consumer chain + synthesis tests | MODIFY |
| `tests/unit/test_crackerjack_tools.py` | MCP banner tests | MODIFY |
| `tests/integration/test_crackerjack_fallback_real.py` | Real-subprocess smoke | NEW |

---

## Task 0: Preflight — Verify Crackerjack CLI flag-to-metric mapping

**Files:** None modified. Run real crackerjack and capture `parsed_data` shape for each flag combination. This task gates the design — if the mapping differs from the spec's table, the implementer updates the plan and re-derives the metric→flag map.

**Step 0.1: Set up a test project**

```bash
cd /Users/les/Projects/session-buddy
mkdir -p /tmp/lychee-cli-verify && cd /tmp/lychee-cli-verify
echo 'def add(a, b): return a + b' > mathlib.py
echo 'def add(a, b): return a + b' > test_mathlib.py
```

**Step 0.2: Probe each flag combination**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -c "
from session_buddy.utils.crackerjack.output_parser import CrackerjackOutputParser
import subprocess, sys, json
for cmd_name, flags in [
    ('all', ['run', '--comp']),
    ('coverage', ['run', '--run-tests']),
    ('lint', ['run', '--fast', '--quick']),
    ('security', ['run', '--security']),
]:
    result = subprocess.run(
        [sys.executable, '-m', 'crackerjack', *flags],
        cwd='/tmp/lychee-cli-verify', capture_output=True, timeout=60,
    )
    parsed = CrackerjackOutputParser.parse_output(cmd_name, result.stdout, result.stderr)
    print(f'=== {cmd_name} ({\" \".join(flags)}) ===')
    print(f'exit: {result.returncode}')
    print(f'parsed keys: {sorted(parsed.keys())}')
    print()
"
```

**Step 0.3: Record findings in `docs/superpowers/plans/2026-07-27-cli-flag-mapping.md`**

Document the actual parsed_data keys for each flag combination. Compare to the spec's "metric-to-flag map" table. If they differ:
- Update Task 5 of this plan with the actual mapping
- Update the spec's table in `2026-07-27-quality-scoring-crackerjack-fallback-design.md`
- Commit the spec update on the same branch

If they match the spec, this task is a no-op beyond recording the table.

**Step 0.4: Skip if crackerjack not installed**

If the probe fails with `ModuleNotFoundError: crackerjack`:
- Document "crackerjack not installed in this environment — Task 0 cannot complete; using spec's CLI shape as the design"
- Note this in the plan
- The integration test in Task 12 will catch any actual shape mismatch at runtime

**No commit for this task.** Task 0 produces evidence, not code.

---

## Task 1: Add `enable_crackerjack_fallback` to feature flags

**Files:**
- Modify: `session_buddy/config/feature_flags.py:5-39` (add field to `FeatureFlags` dataclass)
- Modify: `session_buddy/settings.py` (add `enable_crackerjack_fallback: bool = False` to `SessionMgmtSettings` near the existing `enable_crackerjack` field)
- Modify: `settings/session-buddy.yaml` (add the flat key with `false` default)
- Test: `tests/unit/test_feature_flags.py` (if exists; otherwise new file `tests/unit/test_enable_crackerjack_fallback.py`)

**Step 1.1: Write the failing test**

In `tests/unit/test_enable_crackerjack_fallback.py`:

```python
from session_buddy.config.feature_flags import FeatureFlags, get_feature_flags


def test_enable_crackerjack_fallback_defaults_to_false():
    """Default per project's safe-rollout pattern."""
    flags = FeatureFlags()
    assert flags.enable_crackerjack_fallback is False


def test_get_feature_flags_returns_enable_crackerjack_fallback():
    """Resolver exposes the new field."""
    flags = get_feature_flags()
    assert hasattr(flags, "enable_crackerjack_fallback")
```

**Step 1.2: Run test to verify it fails**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_enable_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: FAIL with `AttributeError: type object 'FeatureFlags' has no attribute 'enable_crackerjack_fallback'`

**Step 1.3: Add field to `FeatureFlags` dataclass**

In `session_buddy/config/feature_flags.py`, add to the `FeatureFlags` dataclass (after the existing `enable_crackerjack: bool` field):

```python
    enable_crackerjack_fallback: bool = False
```

**Step 1.4: Add field to `SessionMgmtSettings`**

In `session_buddy/settings.py`, find the `enable_crackerjack` field (around line 379) and add a sibling field:

```python
    enable_crackerjack_fallback: bool = False
```

**Step 1.5: Add the flat YAML key**

In `settings/session-buddy.yaml`, find the `enable_crackerjack` key and add a sibling:

```yaml
  enable_crackerjack_fallback: false
```

(Indentation matches the existing `enable_crackerjack` key.)

**Step 1.6: Run test to verify it passes**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_enable_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (2/2)

**Step 1.7: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/config/feature_flags.py session_buddy/settings.py settings/session-buddy.yaml tests/unit/test_enable_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(feature-flags): add enable_crackerjack_fallback opt-in flag

Default false (per project's safe-rollout pattern). Synthesis
change ships regardless; this flag controls only whether the
new try_crackerjack_cli helper fires."
```

---

## Task 2: Refactor pure helpers to `@staticmethod`

**Files:**
- Modify: `session_buddy/crackerjack_integration.py:946-1002` (`_calculate_lint_metrics`, `_calculate_security_metrics`, `_calculate_complexity_metrics`, `_calculate_coverage_metrics`)
- Test: `tests/unit/test_pure_helpers_purity.py` (NEW)

**Why this task comes before the helper itself:** the helper must call these without instantiating `CrackerjackIntegration` (which writes to SQLite on `__init__`). Decoupling them first.

**Step 2.1: Write the failing purity test**

In `tests/unit/test_pure_helpers_purity.py`:

```python
import inspect

from session_buddy.crackerjack_integration import (
    CrackerjackIntegration,
    _calculate_lint_metrics,
    _calculate_security_metrics,
    _calculate_complexity_metrics,
    _calculate_coverage_metrics,
)


HELPERS = [
    _calculate_lint_metrics,
    _calculate_security_metrics,
    _calculate_complexity_metrics,
    _calculate_coverage_metrics,
]


def test_helpers_do_not_access_self():
    """After refactor, the four pure helpers must be @staticmethod and not touch self."""
    for fn in HELPERS:
        assert isinstance(inspect.getattr_static(CrackerjackIntegration, fn.__name__), staticmethod), (
            f"{fn.__name__} must be a @staticmethod on CrackerjackIntegration"
        )


def test_helpers_callable_without_instance():
    """The four helpers must be callable as CrackerjackIntegration._calculate_X(args)
    without instantiating CrackerjackIntegration (whose __init__ writes to SQLite)."""
    for fn in HELPERS:
        # Calling via the class (not an instance) requires @staticmethod
        # This must work without raising TypeError for missing self.
        if fn is _calculate_lint_metrics:
            fn([])
        elif fn is _calculate_security_metrics:
            fn([])
        elif fn is _calculate_complexity_metrics:
            fn({})
        elif fn is _calculate_coverage_metrics:
            fn({})
```

**Step 2.2: Run test to verify it fails**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_pure_helpers_purity.py -v --override-ini="addopts="
```

Expected: FAIL on `test_helpers_callable_without_instance` with `TypeError: ... missing 1 required positional argument: 'self'`. The first test may also fail because the methods aren't yet `staticmethod`.

**Step 2.3: Read each helper's body to confirm no `self.X` access**

Before refactoring, manually verify each helper's body does not access `self` (otherwise the refactor breaks the function). Use `Read` on lines 946-1002 of `crackerjack_integration.py`. If any helper does touch `self`, STOP and report — the refactor needs a different design.

**Step 2.4: Add `@staticmethod` decorator to each helper**

For each of the four helpers, add the `@staticmethod` decorator one line above the `def`:

```python
    @staticmethod
    def _calculate_lint_metrics(lint_issues: list[dict]) -> dict[str, float]:
        # ... existing body unchanged ...
```

(Repeat for `_calculate_security_metrics`, `_calculate_complexity_metrics`, `_calculate_coverage_metrics`.)

**Step 2.5: Run test to verify it passes**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_pure_helpers_purity.py -v --override-ini="addopts="
```

Expected: PASS (2/2)

**Step 2.6: Run existing crackerjack_integration tests to confirm no regression**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v --override-ini="addopts="
```

Expected: PASS (existing 19/19 in `TestQualityMetricsCalculation`). If any fail, the refactor changed observable behavior — STOP and investigate.

**Step 2.7: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/crackerjack_integration.py tests/unit/test_pure_helpers_purity.py
git -c user.name="les" -c user.email="les@local" commit -m "refactor(crackerjack): make pure calculation helpers @staticmethod

Decouples the four calculation helpers from CrackerjackIntegration
state so the new fallback helper can call them without instantiating
CrackerjackIntegration (whose __init__ writes to SQLite on disk).

No behavior change; all existing tests pass."
```

---

## Task 3: Helper skeleton — module + lock + OTel span + disabled check

**Files:**
- Create: `session_buddy/utils/crackerjack/fallback.py`
- Modify: `session_buddy/utils/crackerjack/__init__.py` (add export)
- Test: `tests/unit/test_crackerjack_fallback.py` (NEW — start with one test)

**Step 3.1: Write the failing test for the disabled path**

In `tests/unit/test_crackerjack_fallback.py`:

```python
import pytest

from session_buddy.config.feature_flags import FeatureFlags
from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli


@pytest.mark.asyncio
async def test_disabled_flag_returns_none(monkeypatch, tmp_path):
    """When enable_crackerjack_fallback is False, helper returns None without invoking subprocess."""
    from session_buddy.config import feature_flags
    monkeypatch.setattr(
        feature_flags,
        "_flags",
        FeatureFlags(enable_crackerjack_fallback=False),
    )

    spawn_called = False

    async def fake_spawn(*args, **kwargs):
        nonlocal spawn_called
        spawn_called = True
        raise AssertionError("subprocess should not have been spawned")

    import asyncio
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
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from session_buddy.config.feature_flags import get_feature_flags

if TYPE_CHECKING:
    pass


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
            immutability (matches existing codebase patterns at crackerjack_integration.py:120,
            ingesters/redaction.py:21, memory/causal.py:60).
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

    # OTel span (Task 7 fills in the attributes)
    # TODO: with tracer.start_as_current_span("crackerjack.fallback", ...):

    # Lock
    async with _FALLBACK_LOCK:
        # Disabled re-check inside lock
        if not get_feature_flags().enable_crackerjack_fallback:
            return None

        # Placeholder for the rest of the pipeline (filled in Tasks 4-6)
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

Expected: PASS (1/1)

**Step 3.6: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/crackerjack/fallback.py session_buddy/utils/crackerjack/__init__.py tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): helper skeleton with lock and disabled check

Creates the try_crackerjack_cli module-level lock and the early
disabled-return path. Subsequent tasks fill in subprocess invocation,
parse, and observability. The helper is callable but currently a
no-op when the opt-in flag is set; that completes in Tasks 4-7."
```

---

## Task 4: Subprocess invocation + timeout + kill + exit-code check

**Files:**
- Modify: `session_buddy/utils/crackerjack/fallback.py` (extend the helper body inside the lock)

**Step 4.1: Write the failing tests**

Add to `tests/unit/test_crackerjack_fallback.py`:

```python
import asyncio
import sys


def _make_process_mock(returncode: int, stdout: bytes, stderr: bytes = b""):
    """Build an async-mock Process that satisfies .communicate() and .returncode."""
    class _Proc:
        def __init__(self):
            self.returncode = returncode
            self.killed = False

        async def communicate(self):
            return stdout, stderr

        async def wait(self):
            return self.returncode

        async def kill(self):
            self.killed = True
            self.returncode = -9

    return _Proc()


def _enable_flag(monkeypatch):
    from session_buddy.config import feature_flags
    from session_buddy.config.feature_flags import FeatureFlags
    monkeypatch.setattr(
        feature_flags, "_flags", FeatureFlags(enable_crackerjack_fallback=True)
    )


@pytest.mark.asyncio
async def test_timeout_kills_subprocess_and_returns_none(monkeypatch, tmp_path):
    """wait_for TimeoutError -> proc.kill() + proc.wait() + return None."""
    _enable_flag(monkeypatch)

    proc = _make_process_mock(returncode=None, stdout=b"", stderr=b"")
    killed = []

    async def fake_spawn(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        # Simulate timeout by killing the process and raising
        await proc.kill()
        await proc.wait()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
        timeout=30.0,
    )
    assert result is None
    assert proc.killed is True


@pytest.mark.asyncio
async def test_nonzero_exit_returns_none(monkeypatch, tmp_path):
    """Subprocess exits non-zero -> return None."""
    _enable_flag(monkeypatch)

    proc = _make_process_mock(returncode=1, stdout=b"", stderr=b"some error")

    async def fake_spawn(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        return b"", b"some error"

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None


@pytest.mark.asyncio
async def test_uses_sys_executable(monkeypatch, tmp_path):
    """Helper must use sys.executable, not 'python', to pin the interpreter."""
    _enable_flag(monkeypatch)
    captured_argv = []

    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")

    async def fake_spawn(*args, **kwargs):
        captured_argv.extend(args)
        return proc

    async def fake_wait_for(awaitable, timeout):
        return b"{}", b""

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
    )
    assert captured_argv[0] == sys.executable
```

**Step 4.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: All three new tests FAIL (the helper still returns None at the lock-exit placeholder).

**Step 4.3: Replace the placeholder with subprocess invocation**

In `session_buddy/utils/crackerjack/fallback.py`, replace the `# Placeholder for the rest of the pipeline` block with:

```python
        # Build argv via CrackerjackIntegration's existing helper so we use
        # the right flag combinations for the crackerjack v0.47+ CLI.
        from session_buddy.crackerjack_integration import CrackerjackIntegration
        command = "run"  # crackerjack v0.47+ uses 'run' subcommand with flag combos
        flag_args = CrackerjackIntegration._build_command_flags(command, ai_agent_mode=False)
        argv = [sys.executable, "-m", "crackerjack", *flag_args]

        # Spawn subprocess
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait with timeout + cleanup on cancel
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except (TimeoutError, asyncio.CancelledError):
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            # TODO: log + counter (Task 7)
            return None

        # Check exit code
        if proc.returncode != 0:
            # TODO: log + counter (Task 7)
            return None

        # TODO: parse + extract (Task 5)
        return None
```

**Step 4.4: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (4/4 — the disabled test plus the three new ones).

**Step 4.5: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/crackerjack/fallback.py tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): subprocess invocation with timeout and exit-code check

Spawns crackerjack via asyncio.create_subprocess_exec using
sys.executable. wait_for timeout / CancelledError triggers
proc.kill() + proc.wait() to prevent zombie subprocesses.
Non-zero exit returns None. Future tasks add parse, extract,
and observability."
```

---

## Task 5: Parse output + post-filter + success-path return

**Files:**
- Modify: `session_buddy/utils/crackerjack/fallback.py` (replace `# TODO: parse + extract` block)

**Step 5.1: Write the failing tests for success / partial / empty-success**

Add to `tests/unit/test_crackerjack_fallback.py`:

```python
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
        "lint_issues": [{"code": "E501", "message": "line too long"}],
        "security_issues": [],
        "complexity_data": {},
        "coverage_summary": {"total_coverage": 87.5},
    }
    parser_payload = _make_parser_payload(parsed_data)

    proc = _make_process_mock(
        returncode=0, stdout=parser_payload.encode(), stderr=b""
    )

    async def fake_spawn(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        return parser_payload.encode(), b""

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
    assert result["lint_score"] == 100.0  # no lint issues found -> default perfect is OK here


@pytest.mark.asyncio
async def test_partial_success_returns_subset(monkeypatch, tmp_path):
    """When parse yields some requested keys and not others, return the subset."""
    _enable_flag(monkeypatch)
    parsed_data = {
        "lint_issues": [{"code": "E501"}],
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
        missing_metrics=frozenset({"code_coverage", "lint_score", "security_score"}),
    )
    # code_coverage NOT returned because coverage_summary is empty (post-filter)
    assert result is not None
    assert "code_coverage" not in result
    assert "lint_score" in result
    assert "security_score" in result  # no issues -> 100


@pytest.mark.asyncio
async def test_no_relevant_metrics_returns_empty_dict(monkeypatch, tmp_path):
    """When parse succeeds but no requested keys are present, return {} (falsy, not None)."""
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
    assert result == {}  # falsy but logs as success


def _make_parser_payload(parsed_data: dict) -> str:
    """Helper for tests — the parser mock ignores the actual stdout content."""
    return "{}"
```

**Step 5.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: The three new tests FAIL (helper still returns None after exit-code check).

**Step 5.3: Replace the parse placeholder**

In `session_buddy/utils/crackerjack/fallback.py`, replace `# TODO: parse + extract (Task 5)` with:

```python
        # Parse output
        try:
            parsed_data = CrackerjackOutputParser.parse_output(command, stdout, stderr)
        except Exception:
            # TODO: log + counter (Task 7)
            return None

        # Extract requested metrics via the now-static helpers
        candidate: dict[str, float] = {}
        if "lint_issues" in parsed_data and "lint_score" in missing_metrics:
            candidate.update(_calculate_lint_metrics(parsed_data["lint_issues"]))
        if "security_issues" in parsed_data and "security_score" in missing_metrics:
            candidate.update(_calculate_security_metrics(parsed_data["security_issues"]))
        if "complexity_data" in parsed_data and "complexity_score" in missing_metrics:
            candidate.update(_calculate_complexity_metrics(parsed_data["complexity_data"]))
        if "coverage_summary" in parsed_data and "code_coverage" in missing_metrics:
            candidate.update(_calculate_coverage_metrics(parsed_data["coverage_summary"]))

        # Post-filter: drop keys whose parsed section was empty
        # (defends against _calculate_complexity_metrics empty-input -> 100 antipattern)
        result: dict[str, float] = {}
        for key in missing_metrics:
            if key in candidate and parsed_data.get({
                "code_coverage": "coverage_summary",
                "lint_score": "lint_issues",
                "security_score": "security_issues",
                "complexity_score": "complexity_data",
            }.get(key, ""), None):
                result[key] = candidate[key]
        return result
```

**Step 5.4: Add the import at the top of `fallback.py`**

```python
from session_buddy.utils.crackerjack.output_parser import CrackerjackOutputParser
```

**Step 5.5: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (7/7).

**Step 5.6: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/crackerjack/fallback.py tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): parse output, extract metrics, post-filter empty sections

Calls the four now-static helpers on the requested metric keys
and post-filters to drop keys whose parsed section was empty
(defends against _calculate_complexity_metrics empty-input
re-introducing the synthesize-100s antipattern)."
```

---

## Task 6: Error-path coverage (cancelled, parse_error, empty_stdout, missing_executable, permission_error, os_error)

**Files:**
- Modify: `session_buddy/utils/crackerjack/fallback.py` (fill in the `# TODO: log + counter` markers with the right outcomes and error handling)

**Step 6.1: Write the failing tests for each error path**

Add to `tests/unit/test_crackerjack_fallback.py`:

```python
@pytest.mark.asyncio
async def test_cancelled_propagates(monkeypatch, tmp_path):
    """asyncio.CancelledError propagates without returning a value."""
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=None, stdout=b"", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout):
        await proc.kill()
        await proc.wait()
        raise asyncio.CancelledError()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    with pytest.raises(asyncio.CancelledError):
        await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"})
        )


@pytest.mark.asyncio
async def test_parse_error_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    proc = _make_process_mock(returncode=0, stdout=b"{}", stderr=b"")
    async def fake_spawn(*args, **kwargs): return proc
    async def fake_wait_for(awaitable, timeout): return b"{}", b""

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    def boom(*args, **kwargs):
        raise ValueError("simulated parse failure")
    monkeypatch.setattr(
        CrackerjackOutputParser, "parse_output",
        classmethod(boom),
    )

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"})
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
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"})
    )
    assert result is None


@pytest.mark.asyncio
async def test_missing_executable_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)

    async def fake_spawn(*args, **kwargs):
        raise FileNotFoundError("python not on PATH")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"})
    )
    assert result is None


@pytest.mark.asyncio
async def test_permission_error_returns_none(monkeypatch, tmp_path):
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs):
        raise PermissionError(13, "Permission denied", "/some/cwd")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path, missing_metrics=frozenset({"lint_score"})
    )
    assert result is None
```

**Step 6.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: 5 new tests FAIL (3 pass: parse_error because the try/except already handles it; the others have no handling yet).

**Step 6.3: Wrap subprocess spawn in try/except and add the empty_stdout guard**

In `session_buddy/utils/crackerjack/fallback.py`, replace the `# Spawn subprocess` block with:

```python
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
```

And replace the `# Parse output` block with:

```python
        # Parse output (catch any exception from the parser)
        try:
            parsed_data = CrackerjackOutputParser.parse_output(command, stdout, stderr)
        except Exception:
            # TODO: log WARNING + counter parse_error (Task 7)
            return None

        # Empty stdout / no parsed data -> empty_stdout
        if not stdout:
            # TODO: log WARNING + counter empty_stdout (Task 7)
            return None
```

**Step 6.4: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (12/12).

**Step 6.5: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/crackerjack/fallback.py tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): error-path coverage for cancelled, parse, empty, missing, permission

Completes the 10-outcome taxonomy: success, timeout, cancelled,
nonzero_exit, parse_error, empty_stdout, missing_executable,
permission_error, os_error, disabled. asyncio.CancelledError
propagates (host shutdown should not block on a 30s subprocess).
Other failures map to None; observability hooks in Task 7."
```

---

## Task 7: Observability — Prometheus counters, structured logs, OTel span

**Files:**
- Modify: `session_buddy/utils/crackerjack/fallback.py` (fill in the `# TODO: log + counter` markers)
- Modify: `session_buddy/metrics.py` (register the two new counters)
- Test: extend `tests/unit/test_crackerjack_fallback.py`

**Step 7.1: Write the failing tests for log levels, log fields, and counter emission**

Add to `tests/unit/test_crackerjack_fallback.py`:

```python
import logging


@pytest.mark.asyncio
async def test_success_logs_at_info(monkeypatch, tmp_path, caplog):
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

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("crackerjack fallback invoked" in r.message for r in info_records)


@pytest.mark.asyncio
async def test_disabled_logs_at_debug(monkeypatch, tmp_path, caplog):
    from session_buddy.config import feature_flags
    from session_buddy.config.feature_flags import FeatureFlags
    monkeypatch.setattr(
        feature_flags, "_flags", FeatureFlags(enable_crackerjack_fallback=False),
    )

    with caplog.at_level(logging.DEBUG, logger="session_buddy.utils.crackerjack.fallback"):
        result = await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
    assert result is None
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("crackerjack fallback invoked" in r.message for r in debug_records)


@pytest.mark.asyncio
async def test_missing_executable_logs_at_error(monkeypatch, tmp_path, caplog):
    _enable_flag(monkeypatch)
    async def fake_spawn(*args, **kwargs):
        raise FileNotFoundError("python not on PATH")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    with caplog.at_level(logging.ERROR, logger="session_buddy.utils.crackerjack.fallback"):
        await try_crackerjack_cli(
            project_dir=tmp_path, missing_metrics=frozenset({"lint_score"}),
        )
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("crackerjack fallback invoked" in r.message for r in error_records)


@pytest.mark.asyncio
async def test_log_includes_caller_and_project_name(monkeypatch, tmp_path, caplog):
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
    assert getattr(rec, "caller", None) == "producer_retry"
    assert getattr(rec, "project_name", None) == tmp_path.name
    assert getattr(rec, "session_id", None) == "abc-123"


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
            # Intentionally unsorted
            missing_metrics=frozenset({"security_score", "lint_score", "code_coverage"}),
        )
    rec = next(r for r in caplog.records if "crackerjack fallback invoked" in r.message)
    assert getattr(rec, "missing_metrics", None) == ["code_coverage", "lint_score", "security_score"]
```

**Step 7.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: 5 new tests FAIL (no logging yet, just `# TODO: log + counter` comments).

**Step 7.3: Add the logger and counter-emit helpers to the top of `fallback.py`**

Above the existing code in `session_buddy/utils/crackerjack/fallback.py`, add:

```python
import time
import logging

logger = logging.getLogger(__name__)


def _emit_counter(command: str, outcome: str, caller: str) -> None:
    """Increment the unified invocation counter with command+outcome+caller labels."""
    from session_buddy.metrics import CRACKERJACK_FALLBACK_INVOCATIONS
    CRACKERJACK_FALLBACK_INVOCATIONS.labels(command=command, outcome=outcome, caller=caller).inc()


def _log_invocation(
    level: int,
    command: str,
    project_dir: Path,
    missing_metrics: frozenset[str],
    outcome: str,
    caller: str,
    duration_seconds: float,
    correlation_context: dict[str, str] | None,
) -> None:
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
```

**Step 7.4: Register the counters in `session_buddy/metrics.py`**

Find an existing counter declaration in `session_buddy/metrics.py` (e.g., `session_buddy_provenance_pruned_total`) and add near it:

```python
from prometheus_client import Counter, Histogram

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

(Adjust the import line to match the file's existing style. If the file already has `from prometheus_client import Counter, Histogram`, no new import line is needed.)

**Step 7.5: Fill in all the `# TODO: log + counter` markers in `fallback.py`**

Each marker gets a structured-log call + counter increment. Map of outcomes to log levels:

- `success` → INFO
- `disabled` → DEBUG
- `missing_executable` → ERROR
- all other failures → WARNING

Replace each `# TODO: log + counter (Task 7)` block with the appropriate `_log_invocation(...)` + `_emit_counter(...)` calls. Use a `time.monotonic()` start time captured at function entry, compute `duration_seconds` at each return point. The `command` is the literal `"run"` (crackerjack v0.47+).

**Step 7.6: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_fallback.py -v --override-ini="addopts="
```

Expected: PASS (17/17).

**Step 7.7: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/crackerjack/fallback.py session_buddy/metrics.py tests/unit/test_crackerjack_fallback.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(fallback): observability — Prometheus counters, structured logs, log levels

success logs at INFO (the new normal), disabled at DEBUG,
missing_executable at ERROR, other failures at WARNING. Log
fields include caller, project_name (basename for dashboards),
sorted missing_metrics, optional session_id / workflow_id
from correlation_context. Counters use
session_buddy_crackerjack_fallback_invocations_total naming
to match the existing Prometheus convention."
```

---

## Task 8: Wire helper into consumer chain (`_get_crackerjack_metrics`)

**Files:**
- Modify: `session_buddy/utils/quality_scoring.py` (insert new tier between coverage-file fallback and `_create_fallback_metrics`)
- Test: `tests/unit/test_quality_scoring.py` (extend)

**Step 8.1: Write the failing tests for the consumer-chain tier**

Add to `tests/unit/test_quality_scoring.py` (this file currently has collection issues per the SDD ledger — run with `--override-ini="addopts=" --noconftest` to bypass the conftest pollution; if the file still won't import, write the tests in a new file `tests/unit/test_consumer_chain_fallback_tier.py`):

```python
import pytest

from session_buddy.utils import quality_scoring


@pytest.mark.asyncio
async def test_consumer_chain_invokes_helper_after_coverage_file_miss(monkeypatch, tmp_path):
    """DB miss + reflection miss + coverage miss -> helper called with all 4 keys missing."""
    # Make all upstream tiers miss
    async def empty_history(*args, **kwargs):
        return []
    monkeypatch.setattr(quality_scoring, "get_quality_metrics_history", empty_history)

    # Helper returns one metric
    async def fake_helper(*args, **kwargs):
        return {"lint_score": 80.0}
    monkeypatch.setattr(quality_scoring, "try_crackerjack_cli", fake_helper)

    result = await quality_scoring._get_crackerjack_metrics(tmp_path)
    assert result["lint_score"] == 80.0


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

**Step 8.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py -v --override-ini="addopts=" --noconftest 2>&1 | head -40
```

If the conftest pollution blocks collection, fall back to running individual test functions:

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py::TestQualityMetricsCalculation -v --override-ini="addopts=" --noconftest
```

Expected: New tests FAIL (the chain doesn't call the helper yet).

**Step 8.3: Insert the helper tier into `_get_crackerjack_metrics`**

In `session_buddy/utils/quality_scoring.py`, find the `_get_crackerjack_metrics` function. After the coverage-file fallback block (the `if metrics.get("code_coverage") is None: ...` block) and before the final `if not metrics: return _create_fallback_metrics(...)` check, insert:

```python
    # CLI fallback tier (Task 8 of the quality-scoring crackerjack fallback plan)
    from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli
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
```

And at the top of `quality_scoring.py`, add the import:

```python
from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli
```

**Step 8.4: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py::TestQualityMetricsCalculation -v --override-ini="addopts=" --noconftest
```

Expected: PASS (existing 19/19 + the 3 new ones = 22/22 in this class).

**Step 8.5: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/quality_scoring.py tests/unit/test_quality_scoring.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(quality-scoring): wire try_crackerjack_cli into consumer chain

After the coverage-file tier and before _create_fallback_metrics.
The helper is called with the set of scoring keys still missing
and its result is merged into the metrics dict. DB-hit path
skips the helper (early-return guard)."
```

---

## Task 9: Wire helper into producer retry (`execute_crackerjack_command`)

**Files:**
- Modify: `session_buddy/crackerjack_integration.py` (add the `fallback_used` field to `CrackerjackResult`; add the retry in `execute_crackerjack_command`)
- Test: `tests/unit/test_crackerjack_integration.py` (extend)

**Step 9.1: Write the failing tests for the producer retry**

Add to `tests/unit/test_crackerjack_integration.py`:

```python
@pytest.mark.asyncio
async def test_producer_timeout_invokes_fallback_before_error_result(monkeypatch, tmp_path):
    """On TimeoutError, the helper runs once; if it returns a dict, that's the metrics."""

    from session_buddy.crackerjack_integration import CrackerjackIntegration

    async def fake_helper(*args, **kwargs):
        return {"lint_score": 75.0, "security_score": 100.0}

    monkeypatch.setattr(
        "session_buddy.crackerjack_integration.try_crackerjack_cli",
        fake_helper,
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
    """Helper returns None -> result has quality_metrics={} and fallback_used=False."""

    from session_buddy.crackerjack_integration import CrackerjackIntegration

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

    from session_buddy.crackerjack_integration import CrackerjackIntegration

    calls = []
    async def fake_helper(*args, **kwargs):
        calls.append((args, kwargs))
        return None
    monkeypatch.setattr(
        "session_buddy.crackerjack_integration.try_crackerjack_cli", fake_helper,
    )

    # Simulate a successful subprocess that emits nothing parseable
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

**Step 9.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v --override-ini="addopts=" --noconftest
```

Expected: 3 new tests FAIL (`fallback_used` doesn't exist on `CrackerjackResult`; no retry path yet).

**Step 9.3: Add `fallback_used: bool = False` to `CrackerjackResult`**

In `session_buddy/crackerjack_integration.py`, find the `CrackerjackResult` dataclass (search for `@dataclass` near the class definition) and add the field:

```python
    fallback_used: bool = False
```

**Step 9.4: Add the retry on `TimeoutError`**

In `session_buddy/crackerjack_integration.py`, find the `except TimeoutError:` block inside `execute_crackerjack_command`. Replace the existing handler with:

```python
    except TimeoutError:
        # CLI fallback: one attempt before degrading to empty metrics
        from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli
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
                exit_code=-1,
                quality_metrics=fallback_metrics,
                fallback_used=True,
            )
        return self._create_error_result(exit_code=-1, quality_metrics={})
```

**Step 9.5: Update `_create_error_result` to accept `fallback_used`**

In `session_buddy/crackerjack_integration.py`, find `_create_error_result`. Add `fallback_used: bool = False` as a parameter, and pass it through to the `CrackerjackResult` it returns.

**Step 9.6: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_integration.py::TestQualityMetricsCalculation -v --override-ini="addopts=" --noconftest
```

Expected: PASS (existing tests + 3 new ones).

**Step 9.7: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/crackerjack_integration.py tests/unit/test_crackerjack_integration.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(crackerjack): producer retry invokes try_crackerjack_cli on TimeoutError

On subprocess timeout, the helper runs once with all four scoring
keys marked missing. If the helper returns a dict, the result has
fallback_used=True and the metrics come from the CLI. Otherwise
falls through to the existing _create_error_result({}) behavior.
asyncio.CancelledError propagates without invoking the helper
(host shutdown should not block on a 30s subprocess)."
```

---

## Task 10: Synthesis replacement — drop `coverage_pct`, emit `None` + `unavailable: True`

**Files:**
- Modify: `session_buddy/utils/quality_scoring.py` (rewrite `_create_fallback_metrics`; update any internal callers that pass `coverage_pct`)
- Test: `tests/unit/test_quality_scoring.py` (extend)

**Step 10.1: Search for any callers passing `coverage_pct`**

```bash
cd /Users/les/Projects/session-buddy
grep -rn "_create_fallback_metrics" --include="*.py" | head -20
```

Document each call site. The spec says there are two internal callers (`quality_scoring.py:891` and `:924`) that do NOT pass `coverage_pct`. If any external caller does pass it, update them in this task.

**Step 10.2: Write the failing tests for the new synthesis contract**

Add to `tests/unit/test_quality_scoring.py` (or to the new test file from Task 8 if you created one):

```python
def test_synthesis_replacement_emits_none_values():
    from session_buddy.utils.quality_scoring import _create_fallback_metrics
    result = _create_fallback_metrics()
    assert result["code_coverage"] is None
    assert result["lint_score"] is None
    assert result["security_score"] is None
    assert result["complexity_score"] is None
    assert result["unavailable"] is True


def test_synthesis_replacement_does_not_emit_perfect_scores():
    """Regression guard: the synthesize-100s antipattern must not return."""
    from session_buddy.utils.quality_scoring import _create_fallback_metrics
    result = _create_fallback_metrics()
    for key in ("code_coverage", "lint_score", "security_score", "complexity_score"):
        assert result[key] != 100, f"{key} unexpectedly synthesized as 100"


def test_synthesis_drops_coverage_pct_parameter():
    """Backward-compat: callers that passed coverage_pct=... no longer need to."""
    from session_buddy.utils.quality_scoring import _create_fallback_metrics
    # The function must not accept coverage_pct (Bodai pre-1.0: no external callers)
    import inspect
    sig = inspect.signature(_create_fallback_metrics)
    assert "coverage_pct" not in sig.parameters
```

**Step 10.3: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py::test_synthesis_replacement_emits_none_values -v --override-ini="addopts=" --noconftest
```

Expected: FAIL (current implementation returns 100s for the four keys).

**Step 10.4: Rewrite `_create_fallback_metrics`**

In `session_buddy/utils/quality_scoring.py`, replace the body of `_create_fallback_metrics`:

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

**Step 10.5: Update internal callers**

If any caller in `quality_scoring.py` passed `coverage_pct=...` to `_create_fallback_metrics`, remove the argument. The two known callers (lines 891 and 924) do not pass it per the spec, but verify with `grep` from Step 10.1.

**Step 10.6: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_quality_scoring.py -v --override-ini="addopts=" --noconftest -k "synthesis"
```

Expected: PASS (3/3 synthesis tests).

**Step 10.7: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/utils/quality_scoring.py tests/unit/test_quality_scoring.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(quality-scoring): synthesis emits None + unavailable: True

Unconditional rewrite of _create_fallback_metrics. The
synthesize-100s antipattern is gone regardless of the opt-in
flag's value. The opt-in flag controls only whether the CLI
attempt fires before synthesis (per the v2 spec's design
decision: 'the synthesis change is unconditional')."
```

---

## Task 11: Harden `_format_metrics_section` and add unavailable banner

**Files:**
- Modify: `session_buddy/mcp/tools/session/crackerjack_tools.py` (find `_format_metrics_section` around line 661)
- Test: `tests/unit/test_crackerjack_tools.py` (extend, or create new file if it doesn't exist)

**Step 11.1: Write the failing tests**

In `tests/unit/test_crackerjack_tools.py` (create if missing):

```python
from session_buddy.mcp.tools.session.crackerjack_tools import _format_metrics_section


def test_format_metrics_section_handles_none_values():
    """None values must render as 'unavailable', not crash on f-string."""
    output = _format_metrics_section({"code_coverage": None, "lint_score": 80.0})
    assert "unavailable" in output
    assert "80.0" in output


def test_format_metrics_section_renders_unavailable_banner():
    """When unavailable: True is set, a banner appears at the top."""
    output = _format_metrics_section({
        "code_coverage": None,
        "lint_score": None,
        "security_score": None,
        "complexity_score": None,
        "unavailable": True,
    })
    assert "Quality metrics unavailable" in output or "unavailable" in output.lower()
```

**Step 11.2: Run tests to verify they fail**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_tools.py -v --override-ini="addopts="
```

Expected: Both tests FAIL (current formatter crashes on None and doesn't render a banner).

**Step 11.3: Harden `_format_metrics_section`**

In `session_buddy/mcp/tools/session/crackerjack_tools.py`, find `_format_metrics_section` and replace the body with:

```python
def _format_metrics_section(quality_metrics: dict) -> str:
    """Format a quality metrics dict for the MCP tool output.

    Renders an unavailable banner when the dict carries ``unavailable: True``.
    Handles None values defensively (replaces with 'unavailable' string instead
    of crashing on f-string formatting).
    """
    if quality_metrics.get("unavailable") is True:
        return "⚠️ Quality metrics unavailable — every tier failed or was disabled.\n"

    output = "📊 **Quality Metrics**\n\n"
    for metric, value in quality_metrics.items():
        if metric == "unavailable":
            continue
        formatted = f"{value:.1f}" if value is not None else "unavailable"
        output += f"- {metric.replace('_', ' ').title()}: {formatted}\n"
    return output
```

**Step 11.4: Run tests to verify they pass**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/unit/test_crackerjack_tools.py -v --override-ini="addopts="
```

Expected: PASS (2/2).

**Step 11.5: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add session_buddy/mcp/tools/session/crackerjack_tools.py tests/unit/test_crackerjack_tools.py
git -c user.name="les" -c user.email="les@local" commit -m "feat(crackerjack-tools): harden _format_metrics_section and add unavailable banner

The formatter previously crashed with TypeError on None values
(f'{value:.1f}' raised unsupported format string for NoneType).
It now detects unavailable: True upfront and renders a banner,
and replaces None values with the literal 'unavailable' string.

This gives the synthesis dict's flag a real consumer (per the
v2 spec's 'MCP banner rendering' integration point)."
```

---

## Task 12: Real-subprocess integration test (gated)

**Files:**
- Create: `tests/integration/test_crackerjack_fallback_real.py`

**Step 12.1: Write the integration test**

```python
"""Real-subprocess integration test for the Crackerjack CLI fallback.

Skipped in fast CI by `pytest -m 'not integration'`. Runs against a real
crackerjack install in slow CI lanes and on developer machines.
"""
from __future__ import annotations

import sys

import pytest

from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli


pytestmark = [pytest.mark.integration, pytest.mark.requires_network]


@pytest.mark.asyncio
async def test_helper_invokes_real_crackerjack(tmp_path):
    (tmp_path / "hello.py").write_text("x = 1\n")
    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"code_coverage", "lint_score"}),
        timeout=60.0,
    )
    assert result is not None
    assert isinstance(result, dict)
    # Don't assert specific values — different crackerjack versions produce
    # different lint outputs. Just assert the call succeeded without raising.
```

**Step 12.2: Run test to verify it skips in fast mode**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/integration/test_crackerjack_fallback_real.py -v --override-ini="addopts=" -m "not integration"
```

Expected: SKIPPED (the `@pytest.mark.integration` marker excludes it from this run).

**Step 12.3: Run test directly to verify it executes against a real crackerjack**

```bash
cd /Users/les/Projects/session-buddy
.venv/bin/python -m pytest tests/integration/test_crackerjack_fallback_real.py -v --override-ini="addopts=" -m "integration"
```

If `crackerjack` is not installed, this fails with `ModuleNotFoundError`. That's acceptable for the integration test — the unit tests (Tasks 3-11) cover the helper's behavior without a real install.

**Step 12.4: Commit**

```bash
cd /Users/les/Projects/session-buddy
git add tests/integration/test_crackerjack_fallback_real.py
git -c user.name="les" -c user.email="les@local" commit -m "test(fallback): real-subprocess integration test (gated)

Verifies the helper works against a real crackerjack install.
Skipped in fast CI by `pytest -m 'not integration'`."
```

---

## Self-Review (per writing-plans skill)

**1. Spec coverage:**
- [x] Helper module + lock + OTel → Tasks 3, 7
- [x] Subprocess invocation with timeout/kill → Task 4
- [x] Parse + extract + post-filter → Task 5
- [x] Error-path coverage (10 outcomes) → Task 6
- [x] Producer retry → Task 9
- [x] Consumer chain tier → Task 8
- [x] Synthesis replacement (unconditional) → Task 10
- [x] MCP banner + `None` hardening → Task 11
- [x] Opt-in flag (feature flag + YAML + env) → Task 1
- [x] Pure-helper `@staticmethod` refactor → Task 2
- [x] Prometheus counters → Task 7
- [x] Real-subprocess integration test → Task 12
- [x] CLI flag verification (preflight) → Task 0
- [x] `coverage_pct` parameter dropped → Task 10

**2. Placeholder scan:** No TBDs. Task 0 has a real shell command. Each `# TODO` comment in `fallback.py` is filled in by a specific later task (Tasks 4, 5, 6, 7) — that's not a placeholder, that's staged implementation.

**3. Type consistency:** `try_crackerjack_cli` signature in Task 3 matches the spec verbatim. `CrackerjackResult.fallback_used: bool = False` consistent across Tasks 9 and the spec. `frozenset` for `missing_metrics` consistent. The four `_*_metrics` helpers are `@staticmethod` after Task 2; called as `CrackerjackIntegration._calculate_X(...)` (no instance) in Task 5.

**4. Identified concerns:**
- The integration test in Task 12 requires a real crackerjack install. If unavailable, it fails. The unit tests (Tasks 3-11) cover the helper without the dependency.
- Task 0 is a preflight that may modify the spec if the CLI flag-to-metric mapping differs from the spec's table. The implementer should treat this as authoritative; if the spec is wrong, fix the spec.
- Tasks 8-9 wire the helper into existing code. The implementer must read the current `_get_crackerjack_metrics` and `execute_crackerjack_command` carefully — the inserted blocks must match the surrounding code style.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-27-quality-scoring-crackerjack-fallback.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
