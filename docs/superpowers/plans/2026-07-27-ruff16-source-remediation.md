# Ruff 0.16 Source Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate every live Ruff 0.16 default finding in `session_buddy/` while preserving the existing dirty worktree and runtime contracts.

**Architecture:** Add one small UTC parsing boundary utility, then migrate timestamp, exception, logging, structural, and subprocess findings in bounded file batches. Behavior-sensitive changes are test-first; mechanical changes are followed by explicit rule sweeps and focused regression tests. The implementation keeps Ruff 0.16 enabled and does not weaken its rule selection.

**Tech Stack:** Python 3.13, Ruff 0.16.0, pytest/pytest-asyncio, Crackerjack 0.70.2, DuckDB/SQLite, asyncio, standard-library `datetime.UTC`.

## Global Constraints

- Work from `/Users/les/Projects/session-buddy` for every repository command.
- Preserve all existing tracked and untracked changes; do not reset, stash, checkout, or overwrite dirty hunks.
- Keep Ruff 0.16; do not add a Ruff upper bound or disable the newly exposed rules.
- Target `uv run ruff check session_buddy`, not `ruff check --select ALL`.
- New instant timestamps are timezone-aware UTC values; legacy naive ISO strings are interpreted as UTC at read boundaries.
- Narrow exceptions by operation; retain a broad catch only at a documented graceful-degradation boundary with observable logging and a local `# noqa: BLE001` rationale.
- Use `logger.exception("operation failed")` without interpolating the active exception; preserve user-facing exception text separately when the API returns it.
- Keep sync subprocess helpers synchronous and call them from async functions via `asyncio.to_thread`.
- Do not change public CLI/MCP signatures, persisted schema shapes, or cross-service payload keys.
- Run focused tests with `--no-cov`; run the repository coverage/fast-hook gate only at wave boundaries and at the end.
- Do not commit, push, or create a PR unless the user separately authorizes that action. Replace the generic commit step with an external diff checkpoint.
- After each mutation wave, verify file contents and the actual diff; do not rely on an agent’s report alone.

---

## File Map

### New files

- `session_buddy/utils/time.py` — UTC-aware timestamp normalization at string/datetime boundaries.
- `tests/unit/test_time_utils.py` — parser and timezone contract tests.
- `tests/unit/test_dtz_regressions.py` — representative legacy timestamp, TTL, and elapsed-time regressions.

### Timestamp migration files

The live DTZ findings are in these files:

```text
session_buddy/adapters/serverless_storage_adapter.py
session_buddy/adapters/session_storage_adapter.py
session_buddy/adapters/storage_oneiric.py
session_buddy/advanced_features.py
session_buddy/analytics/ab_testing.py
session_buddy/analytics/collaborative_filtering.py
session_buddy/analytics/predictive.py
session_buddy/app_monitor.py
session_buddy/backends/local_backend.py
session_buddy/context_manager.py
session_buddy/core/causal_chains.py
session_buddy/core/conversation_storage.py
session_buddy/core/hooks.py
session_buddy/core/lifecycle/handoff.py
session_buddy/core/permissions.py
session_buddy/core/session_manager.py
session_buddy/core/skills_tracker.py
session_buddy/crackerjack_integration.py
session_buddy/integrations/cicd_tracker.py
session_buddy/integrations/crackerjack_hooks.py
session_buddy/interruption_manager.py
session_buddy/llm/models.py
session_buddy/llm/providers/anthropic_provider.py
session_buddy/llm/providers/gemini_provider.py
session_buddy/llm/providers/ollama_provider.py
session_buddy/llm/providers/openai_provider.py
session_buddy/llm_providers.py
session_buddy/mcp/tools/advanced/recommendation_engine.py
session_buddy/mcp/tools/infrastructure/access_log_tools.py
session_buddy/mcp/tools/infrastructure/history_cache.py
session_buddy/mcp/tools/memory/memory_tools.py
session_buddy/mcp/tools/memory/search_tools.py
session_buddy/mcp/tools/memory/validated_memory_tools.py
session_buddy/mcp/tools/session/crackerjack_tools.py
session_buddy/mcp/tools/skills/phase4_tools.py
session_buddy/memory/conscious_agent.py
session_buddy/memory/entity_extractor.py
session_buddy/memory/migration.py
session_buddy/memory_optimizer.py
session_buddy/natural_scheduler.py
session_buddy/quality_engine.py
session_buddy/search_enhanced.py
session_buddy/serverless_mode.py
session_buddy/services/git_maintenance.py
session_buddy/team_knowledge.py
session_buddy/token_optimizer.py
session_buddy/utils/git_worktrees.py
session_buddy/utils/logging.py
session_buddy/utils/messages.py
session_buddy/utils/quality_scoring.py
session_buddy/utils/scheduler/time_parser.py
session_buddy/worktree_manager.py
```

### Structural and process files

```text
session_buddy/advanced_search.py
session_buddy/backends/s3_backend.py
session_buddy/storage/skills_embeddings.py
session_buddy/adapters/knowledge_graph_adapter_phase3.py
session_buddy/ingesters/claude_code_transcript.py
session_buddy/integrations/cicd_tracker.py
session_buddy/integrations/crackerjack_hooks.py
session_buddy/integrations/ide_plugin.py
session_buddy/memory/category_evolution.py
session_buddy/rewriting/query_rewriter.py
session_buddy/utils/path_validation.py
session_buddy/mcp/tools/monitoring/workflow_metrics_tools.py
session_buddy/reflection/embeddings.py
session_buddy/utils/subprocess_executor.py
session_buddy/doctor.py
session_buddy/mcp/tools/session/crackerjack_tools.py
session_buddy/worktree_manager.py
session_buddy/mcp/tools/ide.py
```

### Exception/logging files

The exact live manifest is generated before each exception batch with:

```bash
uv run ruff check session_buddy --output-format=json > /tmp/session-buddy-ruff-current.json || true
python - <<'PY'
import json
from collections import defaultdict
from pathlib import Path

rows = json.loads(Path('/tmp/session-buddy-ruff-current.json').read_text())
for code in ('BLE001', 'S110', 'S112', 'TRY401', 'G201', 'TRY002', 'TRY004', 'TRY203'):
    files = sorted({row['filename'] for row in rows if row['code'] == code})
    print(code, *files, sep='\n  ')
PY
```

This prevents the plan from becoming stale as each wave removes findings and respects the already-dirty file set.

---

## Task 0: Capture the dirty-tree baseline

**Files:**
- Read: all files reported by the live Ruff JSON output.
- Create outside the repository: `/tmp/session-buddy-ruff16-baseline/` snapshots only.

**Interfaces:**
- Consumes: current working tree and installed Ruff 0.16.0.
- Produces: baseline JSON/counts, status manifest, per-file hashes, and focused-test baseline.

- [ ] **Step 1: Record status and versions**

```bash
cd /Users/les/Projects/session-buddy
mkdir -p /tmp/session-buddy-ruff16-baseline
python - <<'PY'
import hashlib
import json
import subprocess
from pathlib import Path

root = Path('/Users/les/Projects/session-buddy')
files = sorted((root / 'session_buddy').rglob('*.py'))
hashes = {
    str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in files
}
metadata = {
    'ruff': subprocess.run(['uv', 'run', 'ruff', '--version'], capture_output=True, text=True, check=True).stdout.strip(),
    'status': subprocess.run(['git', 'status', '--short', '--untracked-files=all'], cwd=root, capture_output=True, text=True, check=True).stdout,
    'hashes': hashes,
}
Path('/tmp/session-buddy-ruff16-baseline/metadata.json').write_text(json.dumps(metadata, indent=2))
PY
uv run ruff check session_buddy --output-format=json > /tmp/session-buddy-ruff16-baseline/ruff.json || true
uv run ruff check session_buddy --statistics > /tmp/session-buddy-ruff16-baseline/ruff-statistics.txt || true
git -C /Users/les/Projects/session-buddy diff --binary > /tmp/session-buddy-ruff16-baseline/preexisting.diff
```

Expected: Ruff reports the current 838-finding baseline; no repository file changes occur.

- [ ] **Step 2: Run the baseline focused regression net**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_advanced_search.py \
  tests/unit/test_serverless_storage_adapter.py \
  tests/unit/test_session_storage_adapter.py \
  tests/unit/test_workflow_metrics.py \
  tests/unit/test_workflow_metrics_tools.py \
  tests/unit/test_embedding_cache.py \
  tests/unit/test_subprocess_core.py \
  tests/unit/test_subprocess_security.py \
  tests/unit/test_doctor.py \
  tests/unit/test_interruption_manager.py \
  tests/unit/test_worktree_manager.py \
  tests/unit/test_quality_scoring_metrics_registry.py
```

Expected: record the baseline result; if a pre-existing test fails, stop and report it before modifying source.

- [ ] **Step 3: Create an external wave checkpoint**

```bash
cd /Users/les/Projects/session-buddy
python - <<'PY'
from pathlib import Path
import subprocess
Path('/tmp/session-buddy-ruff16-baseline/status-after-baseline.txt').write_text(
    subprocess.run(['git', 'status', '--short', '--untracked-files=all'], capture_output=True, text=True, check=True).stdout
)
PY
```

Do not commit or alter the existing dirty tree.

---

## Task 1: Add and test the UTC boundary utility

**Files:**
- Create: `session_buddy/utils/time.py`
- Create: `tests/unit/test_time_utils.py`

**Interfaces:**
- Consumes: `str | datetime` values from existing persisted/event paths.
- Produces: `utc_now() -> datetime` and `parse_utc_timestamp(value: str | datetime) -> datetime`, both returning timezone-aware UTC values.

- [ ] **Step 1: Write failing contract tests**

```python
from datetime import UTC, datetime

import pytest

from session_buddy.utils.time import parse_utc_timestamp, utc_now


def test_utc_now_returns_aware_utc() -> None:
    value = utc_now()
    assert value.tzinfo is UTC


def test_parse_utc_timestamp_adds_utc_to_legacy_naive_value() -> None:
    value = parse_utc_timestamp('2026-07-27T12:00:00')
    assert value == datetime(2026, 7, 27, 12, tzinfo=UTC)


def test_parse_utc_timestamp_converts_offset_value_to_utc() -> None:
    value = parse_utc_timestamp('2026-07-27T05:00:00-07:00')
    assert value == datetime(2026, 7, 27, 12, tzinfo=UTC)


def test_parse_utc_timestamp_accepts_datetime() -> None:
    value = parse_utc_timestamp(datetime(2026, 7, 27, 12, tzinfo=UTC))
    assert value.tzinfo is UTC


def test_parse_utc_timestamp_rejects_empty_text() -> None:
    with pytest.raises(ValueError):
        parse_utc_timestamp('')
```

- [ ] **Step 2: Run the new tests and verify the import fails**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q tests/unit/test_time_utils.py
```

Expected: collection fails because `session_buddy.utils.time` does not yet exist.

- [ ] **Step 3: Implement the smallest utility**

```python
from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current instant as an aware UTC datetime."""
    return datetime.now(UTC)


def parse_utc_timestamp(value: str | datetime) -> datetime:
    """Parse a timestamp and normalize it to aware UTC.

    Naive legacy values are interpreted as UTC to preserve existing stored data.
    """
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
```

- [ ] **Step 4: Run the contract tests**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q tests/unit/test_time_utils.py
uv run ruff check session_buddy/utils/time.py tests/unit/test_time_utils.py
```

Expected: all tests pass and the new module has no Ruff findings.

- [ ] **Step 5: Record the wave diff without committing**

```bash
git -C /Users/les/Projects/session-buddy diff --binary -- session_buddy/utils/time.py tests/unit/test_time_utils.py > /tmp/session-buddy-ruff16-baseline/wave-1.diff
```

---

## Task 2: Migrate datetime findings in domain batches

**Files:**
- Modify: the timestamp migration files listed in the File Map, in the three batches below.
- Create/modify: `tests/unit/test_dtz_regressions.py`.
- Modify: existing focused storage/analytics tests only when a timestamp assertion must become explicitly UTC-aware.

**Interfaces:**
- Consumes: `utc_now()` and `parse_utc_timestamp()` from Task 1.
- Produces: UTC-aware writers/readers without schema or payload-key changes.

### Batch 2A — adapters and analytics

- [ ] **Step 1: Write regression tests before edits**

```python
from datetime import UTC, datetime, timedelta

from session_buddy.utils.time import parse_utc_timestamp


def test_legacy_timestamp_subtracts_safely_after_normalization() -> None:
    now = datetime(2026, 7, 27, 12, tzinfo=UTC)
    stored = parse_utc_timestamp('2026-07-27T11:00:00')
    assert now - stored == timedelta(hours=1)


def test_legacy_ttl_value_is_compared_as_utc() -> None:
    expires_at = parse_utc_timestamp('2026-07-27T12:00:00')
    now = datetime(2026, 7, 27, 12, 0, 1, tzinfo=UTC)
    assert now > expires_at
```

- [ ] **Step 2: Replace wall-clock construction in these files**

```text
session_buddy/adapters/serverless_storage_adapter.py
session_buddy/adapters/session_storage_adapter.py
session_buddy/adapters/storage_oneiric.py
session_buddy/analytics/ab_testing.py
session_buddy/analytics/collaborative_filtering.py
session_buddy/analytics/predictive.py
```

Use `utc_now()` or `datetime.now(UTC)` for writes, `datetime.fromtimestamp(value, UTC)` for filesystem metadata, and `parse_utc_timestamp()` before TTL/window arithmetic. Do not alter SQLite column names or serialized dictionary keys.

- [ ] **Step 3: Run domain tests and DTZ checks**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_serverless_storage_adapter.py \
  tests/unit/test_session_storage_adapter.py \
  tests/unit/test_storage_oneiric.py \
  tests/unit/test_dtz_regressions.py
uv run ruff check --select DTZ001,DTZ005,DTZ006 \
  session_buddy/adapters session_buddy/analytics
```

Expected: the batch’s DTZ findings are zero and focused tests pass.

### Batch 2B — app/core/lifecycle

- [ ] **Step 1: Convert current timestamps in these files**

```text
session_buddy/advanced_features.py
session_buddy/app_monitor.py
session_buddy/context_manager.py
session_buddy/core/causal_chains.py
session_buddy/core/conversation_storage.py
session_buddy/core/hooks.py
session_buddy/core/lifecycle/handoff.py
session_buddy/core/permissions.py
session_buddy/core/session_manager.py
session_buddy/core/skills_tracker.py
session_buddy/interruption_manager.py
```

Use `time.monotonic()` for hook elapsed-time measurement. Normalize values returned by `datetime.fromisoformat()` before subtracting from UTC values. Preserve handoff filename formats and session metadata keys.

- [ ] **Step 2: Add behavior tests**

Cover app-monitor recent-event scoring, handoff filename generation, permission/session ID generation, and hook execution duration. Assert that a legacy naive stored timestamp does not cause `TypeError` when compared to `utc_now()`.

- [ ] **Step 3: Run the core batch gate**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_hooks_system.py \
  tests/unit/test_core/test_hooks.py \
  tests/unit/test_interruption_manager.py \
  tests/unit/test_session_manager.py \
  tests/unit/test_session_manager_comprehensive.py
uv run ruff check --select DTZ001,DTZ005,DTZ006 \
  session_buddy/advanced_features.py session_buddy/app_monitor.py \
  session_buddy/context_manager.py session_buddy/core session_buddy/interruption_manager.py
```

### Batch 2C — remaining integrations/tools/utilities

- [ ] **Step 1: Convert the remaining listed files**

```text
session_buddy/crackerjack_integration.py
session_buddy/integrations/cicd_tracker.py
session_buddy/integrations/crackerjack_hooks.py
session_buddy/llm/models.py
session_buddy/llm/providers/anthropic_provider.py
session_buddy/llm/providers/gemini_provider.py
session_buddy/llm/providers/ollama_provider.py
session_buddy/llm/providers/openai_provider.py
session_buddy/llm_providers.py
session_buddy/mcp/tools/advanced/recommendation_engine.py
session_buddy/mcp/tools/infrastructure/access_log_tools.py
session_buddy/mcp/tools/infrastructure/history_cache.py
session_buddy/mcp/tools/memory/memory_tools.py
session_buddy/mcp/tools/memory/search_tools.py
session_buddy/mcp/tools/memory/validated_memory_tools.py
session_buddy/mcp/tools/session/crackerjack_tools.py
session_buddy/mcp/tools/skills/phase4_tools.py
session_buddy/memory/conscious_agent.py
session_buddy/memory/entity_extractor.py
session_buddy/memory/migration.py
session_buddy/memory_optimizer.py
session_buddy/natural_scheduler.py
session_buddy/quality_engine.py
session_buddy/search_enhanced.py
session_buddy/serverless_mode.py
session_buddy/services/git_maintenance.py
session_buddy/team_knowledge.py
session_buddy/token_optimizer.py
session_buddy/utils/git_worktrees.py
session_buddy/utils/logging.py
session_buddy/utils/messages.py
session_buddy/utils/quality_scoring.py
session_buddy/utils/scheduler/time_parser.py
session_buddy/worktree_manager.py
```

- [ ] **Step 2: Run remaining DTZ tests and the live count**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_quality_scoring.py \
  tests/unit/test_quality_scoring_helpers.py \
  tests/unit/test_migration.py \
  tests/unit/test_crackerjack_hooks.py
uv run ruff check --select DTZ001,DTZ005,DTZ006 session_buddy
uv run ruff check session_buddy --output-format=statistics
```

Expected: all DTZ findings are gone and the total live count is no greater than the Task 0 baseline.

---

## Task 3: Fix logging mechanics and narrow, local exception rules

**Files:**
- Modify: all current `TRY401`, `G201`, `S110`, `S112`, `TRY002`, `TRY004`, and `TRY203` files from the generated manifest.
- Modify: focused tests in `tests/unit/test_hooks_system.py`, `tests/unit/test_workflow_metrics.py`, `tests/unit/test_migration.py`, and the relevant MCP/tool tests.

**Interfaces:**
- Consumes: existing logger names, structured `extra` dictionaries, and fallback return contracts.
- Produces: parameterized exception logs and operation-specific exception tuples.

- [ ] **Step 1: Add a structured logging regression test**

Append this test to `tests/unit/test_git_maintenance_service.py` and keep the existing lock-release assertion:

```python
def test_exception_releases_lock_and_preserves_repository_log_context(
    self,
    tmp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GitMaintenanceService()
    release = Mock()
    log = Mock()
    monkeypatch.setattr(
        "session_buddy.services.git_maintenance.logger",
        log,
    )
    monkeypatch.setattr(service, "_release_lock", release)
    monkeypatch.setattr(
        "session_buddy.services.git_maintenance.schedule_automatic_git_gc",
        Mock(side_effect=RuntimeError("GC failed")),
    )

    result = service.perform_maintenance(tmp_git_repo)

    assert result["success"] is False
    assert result["message"] == "Exception: GC failed"
    release.assert_called()
    log.exception.assert_called_once_with(
        "Git maintenance exception",
        repository=str(tmp_git_repo),
    )
```

The assertion deliberately checks the structured repository field and the absence of a redundant `error`/`exc_info` message argument after the `G201` conversion.

- [ ] **Step 2: Apply the `TRY401` transformation**

Change this pattern:

```python
except OSError as exc:
    logger.exception(f"Failed to load {path}: {exc}")
    return None
```

to this pattern when the exception is not otherwise returned:

```python
except OSError:
    logger.exception("Failed to load %s", path)
    return None
```

When a user-facing string needs the exception, keep the variable for the return value but remove it from the log message:

```python
except OSError as exc:
    logger.exception("Failed to load %s", path)
    return f"Failed to load {path}: {exc}"
```

- [ ] **Step 3: Apply `G201` without losing structured fields**

Change `.error(..., exc_info=True)` to `.exception(...)`. For `services/git_maintenance.py`, retain `extra={'repository': ...}` and let the active traceback carry the exception instead of storing a duplicate string field.

- [ ] **Step 4: Fix the small exception taxonomy rules**

Use these exact choices after reading each local call path:

```text
session_buddy/di/container.py: RuntimeError -> TypeError for invalid type arguments
session_buddy/llm_providers.py: remove the try/except that immediately re-raises
session_buddy/storage/ipfs.py: define and raise IPFSStorageError for provider failures
session_buddy/knowledge_graph_db.py: suppress only the connection-close errors that the close path documents
session_buddy/mcp/tools/session/channel_tracking_tools.py: narrow the import/settings probe to its observed failure classes
```

- [ ] **Step 5: Make every continue/pass observable**

For each S110/S112 site, either narrow the exception tuple or add a debug/warning log immediately before the existing `continue`/fallback. Keep the loop’s success/failure counters unchanged. Add one malformed-item regression test per loop family.

- [ ] **Step 6: Run the logging/exception sweep**

```bash
cd /Users/les/Projects/session-buddy
uv run ruff check --select TRY401,G201,S110,S112,TRY002,TRY004,TRY203 session_buddy
uv run pytest --no-cov -q \
  tests/unit/test_hooks_system.py \
  tests/unit/test_migration.py \
  tests/unit/test_workflow_metrics.py \
  tests/unit/test_crackerjack_tools.py \
  tests/unit/test_crackerjack_tools_extras.py
```

Expected: the selected rules report zero and structured logging/fallback tests pass.

- [ ] **Step 7: Save the wave diff without committing**

```bash
git -C /Users/les/Projects/session-buddy diff --binary > /tmp/session-buddy-ruff16-baseline/wave-3-logging-exceptions.diff
```

---

## Task 4: Classify BLE001 by subsystem

**Files:**
- Modify: the exact files emitted by the current BLE001 manifest, in the four batches below.
- Test: the closest existing unit/integration test for each changed boundary.

**Interfaces:**
- Consumes: the existing fallback/error return contract of each function.
- Produces: narrower catches or locally justified, logged boundary catches.

### Batch 4A — adapters, backends, storage

- [ ] **Step 1: Narrow operation-specific catches**

Use database exception classes for DuckDB/SQLite operations, `OSError` for filesystem operations, `ValueError`/`TypeError`/`KeyError` for data conversion, and provider-specific HTTP/client errors for network calls. Do not catch a tuple solely to silence Ruff; inspect the operation inside the `try` block first.

- [ ] **Step 2: Test fallback behavior**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_reflection_adapter.py \
  tests/unit/test_reflection_adapter_oneiric.py \
  tests/unit/test_storage_oneiric.py \
  tests/unit/test_serverless_storage_adapter.py \
  tests/unit/test_session_storage_adapter.py \
  tests/unit/test_embedding_cache.py \
  tests/unit/test_subprocess_security.py
```

### Batch 4B — core, analytics, services, lifecycle

- [ ] **Step 1: Preserve graceful fallback contracts**

At each broad catch, retain the existing return shape (`None`, empty collection, `HookResult`, or error string), add `logger.exception`/`logger.warning`, and annotate only unavoidable API-boundary catches with a local rationale such as:

```python
except Exception:  # noqa: BLE001 - MCP boundary must return its documented error envelope.
    logger.exception("Tool execution failed")
    return error_envelope
```

Do not add a file-level `# ruff: noqa`.

- [ ] **Step 2: Test representative failure paths**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_hooks_system.py \
  tests/unit/test_interruption_manager.py \
  tests/unit/test_session_manager.py \
  tests/unit/test_session_manager_edge_cases.py \
  tests/unit/test_doctor.py \
  tests/unit/test_quality_scoring.py
```

### Batch 4C — MCP tools and server boundaries

- [ ] **Step 1: Separate tool-boundary catches from inner operation catches**

Inner database/parser/filesystem catches must be narrow. A top-level MCP tool may retain a broad catch only if it returns the existing structured error response and logs the traceback. Keep tool names, parameter models, and response keys unchanged.

- [ ] **Step 2: Run MCP regression tests**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_crackerjack_tools.py \
  tests/unit/test_crackerjack_tools_extras.py \
  tests/unit/test_knowledge_graph_phase3_tools.py \
  tests/unit/test_workflow_metrics_tools.py \
  tests/integration/test_mcp_crackerjack_tools.py
```

### Batch 4D — LLM, utility, and remaining modules

- [ ] **Step 1: Narrow optional-provider and utility catches**

Use provider/library exception classes where available. For provider fallback chains whose contract is to try the next provider, retain the broad catch only at the chain boundary, log the failed provider, and add a local rationale.

- [ ] **Step 2: Run import and fallback smoke tests**

```bash
cd /Users/les/Projects/session-buddy
uv run python - <<'PY'
import importlib
from pathlib import Path

root = Path('session_buddy')
for path in sorted(root.rglob('*.py')):
    module = '.'.join(path.with_suffix('').parts)
    if module.endswith('.__init__'):
        module = module.removesuffix('.__init__')
    importlib.import_module(module)
print('all session_buddy modules imported')
PY
uv run ruff check --select BLE001 session_buddy
```

Expected: zero BLE001 findings; any remaining `noqa` is explicitly reviewed in the diff.

- [ ] **Step 3: Save the exception-wave diff without committing**

```bash
git -C /Users/les/Projects/session-buddy diff --binary > /tmp/session-buddy-ruff16-baseline/wave-4-exceptions.diff
```

---

## Task 5: Fix closures, mutable defaults, cache ownership, and mechanical semantics

**Files:**
- Modify: `session_buddy/advanced_search.py`
- Modify: `session_buddy/backends/s3_backend.py`
- Modify: `session_buddy/storage/skills_embeddings.py`
- Modify: `session_buddy/adapters/knowledge_graph_adapter_phase3.py`
- Modify: `session_buddy/ingesters/claude_code_transcript.py`
- Modify: `session_buddy/integrations/cicd_tracker.py`
- Modify: `session_buddy/integrations/crackerjack_hooks.py`
- Modify: `session_buddy/integrations/ide_plugin.py`
- Modify: `session_buddy/memory/category_evolution.py`
- Modify: `session_buddy/rewriting/query_rewriter.py`
- Modify: `session_buddy/utils/path_validation.py`
- Modify: `session_buddy/mcp/tools/monitoring/workflow_metrics_tools.py`
- Modify: `session_buddy/reflection/embeddings.py`
- Modify: `session_buddy/utils/subprocess_executor.py`
- Test: `tests/unit/test_advanced_search.py`, `tests/unit/test_embedding_cache.py`, `tests/unit/test_workflow_metrics.py`, `tests/unit/test_workflow_metrics_tools.py`, and the closest adapter/integration tests.

**Interfaces:**
- Consumes: current filter objects, class lookup tables, service cache API, and workflow metrics output.
- Produces: identical public method signatures with correctly bound values and instance-safe cache ownership.

- [ ] **Step 1: Lock down advanced-search filter behavior**

Add parameterized tests for `eq`, `ne`, `in`, `not_in`, `contains`, `starts_with`, `ends_with`, and `range`, asserting each generated SQL fragment uses the current loop’s field, negation, value, and parameter list.

- [ ] **Step 2: Replace the late-bound lambda table**

Use a direct dispatch helper that receives all values as arguments:

```python
def _apply_filter_operator(
    self,
    operator: str,
    sql_field: str,
    negation: str,
    filter_obj: SearchFilter,
    params: list[object],
) -> str:
    handlers = {
        'eq': self._apply_eq_filter,
        'ne': self._apply_ne_filter,
        'in': self._apply_in_filter,
        'not_in': self._apply_not_in_filter,
        'contains': self._apply_contains_filter,
        'starts_with': self._apply_starts_with_filter,
        'ends_with': self._apply_ends_with_filter,
        'range': self._apply_range_filter,
    }
    return handlers[operator](sql_field, negation, filter_obj, params)
```

Adapt the helper call to the existing return type; do not change SQL parameterization.

- [ ] **Step 3: Bind S3 cleanup keys explicitly**

Replace the deferred lambda capture with `functools.partial` or a local `key` binding so each executor call owns its object key. Add a test with two distinct S3 objects and assert two distinct delete calls.

- [ ] **Step 4: Move the embedding cache to a free function**

Factor the uncached implementation into a module-level function and decorate that function, preserving the service methods:

```python
@lru_cache(maxsize=1024)
def _cached_embedding(text: str) -> np.ndarray | None:
    return _generate_embedding_impl(text)

class SkillsEmbeddingService:
    def _generate_embedding_cached(self, text: str) -> np.ndarray | None:
        return _cached_embedding(text)

    def clear_cache(self) -> None:
        _cached_embedding.cache_clear()
```

Keep provider availability/error behavior unchanged. Update `tests/unit/test_embedding_cache.py` to verify cache hits, clearing, and that the cache key does not retain a service instance.

- [ ] **Step 5: Annotate lookup tables and apply mechanical fixes**

Add `ClassVar` to immutable class dictionaries; change dictionary iteration to `.items()`; combine only side-effect-free nested `if` statements; merge nested contexts only where exception scope remains equivalent; remove read-only `global` declarations.

- [ ] **Step 6: Resolve the workflow sort branch with a regression test**

Read existing callers/tests, write a test that distinguishes `quality` ordering from other ordering values, then replace the duplicate conditional branch with the intended direction. Do not make the change solely because Ruff suggests it.

- [ ] **Step 7: Run structural rule sweeps**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_advanced_search.py \
  tests/unit/test_embedding_cache.py \
  tests/unit/test_workflow_metrics.py \
  tests/unit/test_workflow_metrics_tools.py \
  tests/unit/test_knowledge_graph_phase3_patch.py
uv run ruff check --select B023,B019,RUF012,RUF034,PLC0206,SIM102,SIM117,PLW0602 session_buddy
```

Expected: selected structural rules report zero.

---

## Task 6: Fix async subprocesses, explicit process options, and executable modes

**Files:**
- Modify: `session_buddy/doctor.py`
- Modify: `session_buddy/mcp/tools/session/crackerjack_tools.py`
- Modify: `session_buddy/worktree_manager.py`
- Modify: `session_buddy/mcp/tools/ide.py`
- Modify: `session_buddy/utils/subprocess_executor.py`
- Modify file modes/shebangs for the 56 EXE001 paths from the live manifest.
- Test: `tests/unit/test_doctor.py`, `tests/unit/test_crackerjack_tools.py`, `tests/unit/test_worktree_manager.py`, `tests/unit/test_subprocess_core.py`, `tests/security/test_subprocess_safety.py`.

**Interfaces:**
- Consumes: current synchronous helper return values and subprocess security constraints.
- Produces: non-blocking async callers and executable entry points with unchanged CLI behavior.

- [ ] **Step 1: Write async blocking regression tests**

Mock the existing sync subprocess helper and assert an async caller executes it through a worker thread without changing its return object or timeout/check arguments. Keep direct synchronous helper tests unchanged.

- [ ] **Step 2: Extract or reuse sync helpers**

Use this pattern:

```python
def _run_health_probe(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

async def run_health_probe(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(_run_health_probe, command, timeout)
```

Apply it to the four ASYNC221 locations while preserving the existing command allowlists and result handling.

- [ ] **Step 3: Make PLW1510 calls explicit**

Add `check=False` where callers inspect `returncode`; use `check=True` only where a raised `CalledProcessError` is already part of the function contract. Preserve `SafeSubprocess.run_safe`’s existing default behavior.

- [ ] **Step 4: Classify shebangs**

Keep a shebang and set mode `0755` only for actual executable scripts (`session_buddy/__main__.py` and any verified root CLI script). Remove shebangs from importable package modules such as tool modules, compatibility wrappers, and utility modules. Do not chmod every module merely to silence Ruff.

- [ ] **Step 5: Run process and CLI tests**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_doctor.py \
  tests/unit/test_crackerjack_tools.py \
  tests/unit/test_worktree_manager.py \
  tests/unit/test_subprocess_core.py \
  tests/security/test_subprocess_safety.py \
  tests/security/test_git_subprocess.py
uv run ruff check --select EXE001,ASYNC221,PLW1510,B008 session_buddy
uv run python -m session_buddy --help
uv run session-buddy --help
```

Expected: selected process rules report zero and both CLI help commands exit zero.

---

## Task 7: Residual live-Ruff sweep

**Files:**
- Modify only files named by the current live Ruff JSON output after Tasks 2–6.
- Test: the focused test associated with each residual file.

**Interfaces:**
- Consumes: all previous wave changes and their regression tests.
- Produces: zero live default Ruff findings with no unreviewed suppression.

- [ ] **Step 1: Generate the residual rule manifest**

```bash
cd /Users/les/Projects/session-buddy
uv run ruff check session_buddy --output-format=json > /tmp/session-buddy-ruff16-residual.json || true
python - <<'PY'
import json
from collections import Counter
from pathlib import Path
rows = json.loads(Path('/tmp/session-buddy-ruff16-residual.json').read_text())
print('residual_total=', len(rows))
print('residual_codes=', dict(Counter(row['code'] for row in rows)))
for row in rows:
    print(f"{row['filename']}:{row['location']['row']}:{row['code']} {row['message']}")
PY
```

- [ ] **Step 2: Resolve each residual finding with a single minimal change**

For each row, inspect the complete surrounding function, add a regression test when behavior can change, make one edit, and rerun the smallest relevant rule sweep. Do not introduce a new global ignore or bundle unrelated refactors.

- [ ] **Step 3: Verify monotonic convergence**

```bash
python - <<'PY'
import json
from pathlib import Path
for name in ('ruff.json', 'ruff16-residual.json'):
    path = Path('/tmp/session-buddy-ruff16-baseline') / name
    if path.exists():
        print(name, len(json.loads(path.read_text())))
PY
uv run ruff check session_buddy --statistics
```

Expected: residual count is zero.

---

## Task 8: Full validation and delivery review

**Files:**
- Read: all changed source and test files.
- Modify: no source unless a validation failure identifies a concrete regression.
- Create outside repository: final validation report under `/tmp/session-buddy-ruff16-baseline/`.

**Interfaces:**
- Consumes: zero-finding source tree and all focused regression tests.
- Produces: verified maintenance result and a faithful diff/status report.

- [ ] **Step 1: Run the complete explicit rule matrix**

```bash
cd /Users/les/Projects/session-buddy
for rules in \
  BLE001,S110,S112,TRY401,G201,TRY002,TRY004,TRY203 \
  DTZ001,DTZ005,DTZ006 \
  B023,B019,RUF012,RUF034,PLC0206,SIM102,SIM117,PLW0602 \
  EXE001,ASYNC221,PLW1510,B008; do
  uv run ruff check --select "$rules" session_buddy
 done
uv run ruff check session_buddy
uv run ruff format --check session_buddy
```

Expected: every command exits zero.

- [ ] **Step 2: Run the focused and integration regression matrix**

```bash
cd /Users/les/Projects/session-buddy
uv run pytest --no-cov -q \
  tests/unit/test_time_utils.py \
  tests/unit/test_dtz_regressions.py \
  tests/unit/test_advanced_search.py \
  tests/unit/test_serverless_storage_adapter.py \
  tests/unit/test_session_storage_adapter.py \
  tests/unit/test_workflow_metrics.py \
  tests/unit/test_workflow_metrics_tools.py \
  tests/unit/test_embedding_cache.py \
  tests/unit/test_subprocess_core.py \
  tests/unit/test_subprocess_security.py \
  tests/unit/test_doctor.py \
  tests/unit/test_interruption_manager.py \
  tests/unit/test_worktree_manager.py \
  tests/unit/test_hooks_system.py \
  tests/unit/test_quality_scoring.py \
  tests/unit/test_migration.py \
  tests/unit/test_crackerjack_tools.py \
  tests/unit/test_crackerjack_tools_extras.py \
  tests/unit/test_knowledge_graph_phase3_patch.py \
  tests/security/test_subprocess_safety.py \
  tests/security/test_git_subprocess.py \
  tests/integration/test_serverless_storage.py \
  tests/integration/test_migration_rollback.py
```

- [ ] **Step 3: Run the repository fast quality gate**

```bash
cd /Users/les/Projects/session-buddy
uv run crackerjack run --no-config-update --verbose
```

Expected: the fast-hook suite passes. If it reports a non-Ruff failure, classify it separately rather than weakening the Ruff remediation.

- [ ] **Step 4: Run the orphan audit and inspect the final diff**

```bash
cd /Users/les/Projects/session-buddy
python scripts/audit_orphans.py
python - <<'PY'
import subprocess
from pathlib import Path
root = Path('/Users/les/Projects/session-buddy')
status = subprocess.run(['git', 'status', '--short', '--untracked-files=all'], cwd=root, capture_output=True, text=True, check=True).stdout
changed = subprocess.run(['git', 'diff', '--name-only'], cwd=root, capture_output=True, text=True, check=True).stdout
Path('/tmp/session-buddy-ruff16-baseline/final-status.txt').write_text(status)
Path('/tmp/session-buddy-ruff16-baseline/final-files.txt').write_text(changed)
print(status)
print('--- diff check ---')
subprocess.run(['git', 'diff', '--check'], cwd=root, check=True)
PY
git diff --stat
```

Expected: no orphaned production symbols attributable to the remediation, no whitespace errors, and the final report clearly separates pre-existing dirty files from files changed by these waves.

- [ ] **Step 5: Report completion without claiming a commit**

Report:

- baseline and final Ruff counts;
- each wave’s rule/file manifest;
- focused and full commands with pass/fail output;
- retained local `# noqa: BLE001` comments and their rationale;
- any test or hook that was skipped and why;
- the fact that no commit, push, reset, or stash was performed.

## Integration Contract

- **Triggered from:** the session-buddy Ruff/Crackerjack fast hook.
- **Returns to / updates:** session-buddy source modules, focused regression tests, and the Ruff-compatible quality gate.
- **Demonstrable by:** `uv run ruff check session_buddy` returning zero findings and the final Crackerjack fast hook passing.
- **Rollback signal:** any wave increases findings, changes a public contract, fails focused tests, or overlaps an unreviewed dirty hunk.
- **Observability added:** structured exception logs, wave count snapshots, timestamp normalization tests, async subprocess tests, and explicit final status reporting.
