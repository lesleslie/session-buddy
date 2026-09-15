______________________________________________________________________

---
status: active
role: followup
date: 2026-09-15
last_reviewed: 2026-09-15
superseded_by: null
blocks_on: []
topic: tooling
---

# Release Audit: Cross-Repo / Dependency Symbol Claims

**Date:** 2026-09-15
**Owning repo (where the audit lives):** `crackerjack`
**Owning repo (where the failure surfaced):** `session-buddy`
**Triggering release audit run:** `crackerjack run -p minor` on `session-buddy@0.26.4` (post ty-warning fix)

> **Read first:**
>
> 1. `crackerjack/checks/release_audit.py` — the audit whose scope this plan extends.
> 1. The diff for `session-buddy@1d42e7` ("feat: emit health-aggregator metrics from /health probe") — the commit that produced the symbol claim CHANGELOG couldn't satisfy.

______________________________________________________________________

## 1. Problem

`crackerjack.checks.release_audit._verify_added` only greps the audited repo's own
source tree (`source_root = project_root / <package_dir>`). Any CHANGELOG "Added"
bullet whose backticked fully-qualified symbol lives in a dependency is rejected:

```
[FAIL] CHANGELOG claims mcp_common.health.metrics.update_health_metrics was added
       but no definition found in source
```

This is a real audit limitation: cross-module claims are common in the Bodai
ecosystem. The session-buddy /health probe at `session_buddy/server_optimized.py:374`
imports `update_health_metrics` from `mcp_common.health.metrics`, and that wiring
IS in the product — but it's in the dep, not in `session_buddy/`.

The CHANGELOG is technically correct; the audit just can't follow the import.

## 2. Trigger (full repro)

```bash
cd /Users/les/Projects/session-buddy
uv run crackerjack run -p minor          # FAILS at run_publishing_phase → publish manager
                                        # raises ValueError("Release-audit failed; refusing to bump version")
```

The audit parse + verify pipeline runs as:

```
crackerjack/checks/release_audit.py:358  check_release_audit()
  → _parse_changelog(text)               # finds `mcp_common.health.metrics.update_health_metrics`
  → _verify_added(claim, source_root)    # source_root = session_buddy/
  → _symbol_in_source(symbol, source_root)
    → rglob("*.py") under session_buddy/ for `def update_health_metrics`
    → never found                       # symbol lives in mcp_common/health/metrics.py
    → FAIL
```

## 3. Workaround (already applied)

To unblock the immediate publish, the CHANGELOG entry for the offending commit
was reworded so the FQN is no longer backticked:

```diff
-- session-buddy: Wire `mcp_common.health.metrics.update_health_metrics` into
-+ session-buddy: Wire update_health_metrics (from mcp_common.health.metrics) into
```

Why this works: the audit's regex `r"`([\w.]+)`"` requires backticks. Bare-text
FQNs aren't extracted as claims, so no verification is attempted.

Verified with `crackerjack.checks.release_audit.check_release_audit` invoked
directly on session-buddy: **PASS (0 errors, exit 0)**.

This workaround is local and reversible; the next time someone references a dep
symbol it'll trip the audit again. Hence this follow-up.

## 4. Proposed Fix (crackerjack-side)

Extend `_symbol_in_source` (and `_verify_added` / `_verify_removed`) to ALSO
search the project's installed dependencies when the symbol's module prefix
doesn't live in the audited repo.

Sketch:

```python
# crackerjack/checks/release_audit.py
def _symbol_in_source(symbol: str, source_root: Path, *, search_venv: bool = True) -> bool:
    """Grep source tree for a fully-qualified or short symbol definition.

    Order:
      1. source_root (audited repo's own package)
      2. site-packages dist-info MATCHED_BY the symbol's top-level module
         (e.g. `mcp_common` → /Users/.../site-packages/mcp_common/)
      3. fallback: any installed package whose top-level prefix matches
    """
    if _symbol_in_source_tree(symbol, source_root):
        return True
    if search_venv:
        top_pkg = symbol.split(".", 1)[0].replace("_", "-")  # mcp_common → mcp-common
        for dist_root in _find_installed_distributions([top_pkg]):
            if _symbol_in_source_tree(symbol, dist_root):
                return True
    return False
```

Acceptance criteria:

- [ ] `crackerjack run -p minor` on session-buddy passes after reverting the
      CHANGELOG workaround (i.e. the audit accepts the original backticked FQN).
- [ ] No false positives: a clearly bogus FQN like
      `mcp_common.health.metrics.does_not_exist` still fails.
- [ ] Coverage of all common Bodai dep top-levels: `mcp_common`, `crackerjack`,
      `mahavishnu`, `oneiric`, `session_buddy`, `akosha`, `dhara`.
- [ ] No regression on the 0 errors currently passing in session-buddy.

## 5. Test Plan (when implementing)

- [ ] Unit test: `test_symbol_in_source_finds_dep_symbol` —
      `mcp_common.health.aggregator.aggregate_feed_states` resolves against an
      installed `mcp-common` venv.
- [ ] Unit test: `test_symbol_in_source_rejects_bogus_dep_symbol` —
      `mcp_common.health.aggregator.does_not_exist` still fails.
- [ ] Unit test: `test_symbol_in_source_local_still_works` — local symbols
      keep short-circuiting before the venv search (perf guard).
- [ ] Integration: run `crackerjack run -p minor --dry-run` against
      session-buddy with the workaround reverted; expect PASS.

## 6. Rollout

1. Land the audit change in `crackerjack` behind a default-on flag.
2. Publish a crackerjack release that includes the fix.
3. Bump `crackerjack` floor in session-buddy (and other Bodai repos) so they
   pick up the fix.
4. Revert the CHANGELOG workaround in session-buddy; re-run `crackerjack run -p minor`.
5. Repeat for any other Bodai repo whose CHANGELOG has backticked dep-symbol
   claims (grep candidate: `git grep -nE '^\s*-\s+`\w+\.\w+\.\w+\.\w+`' CHANGELOG.md`).

## 7. Integration Contract (per `wire-up-contract.md`)

- **Triggered from:** `crackerjack run -p minor` (and `crackerjack publish`) on
  any Bodai repo whose CHANGELOG references a dep symbol.
- **Returns to / updates:** `crackerjack.checks.release_audit.VerifyResult.passed`
  for cross-module claims; no change to local-symbol behavior.
- **Demonstrable by:** reverting the CHANGELOG workaround and re-running
  `crackerjack run -p minor --dry-run` on `session-buddy`.
- **Rollback signal:** false-positive (audit accepts a bogus FQN) → revert the
  crackerjack release, restore the CHANGELOG workaround on every affected repo.
- **Observability added:** audit log gains `dep_search_path=` and
  `dep_search_hits=` per claim so operators can see why a dep-symbol passed.

## 8. References

- `crackerjack/checks/release_audit.py` — the audit this extends
- `crackerjack/checks/release_audit.py:175-196` — `_symbol_in_source`
- `crackerjack/managers/publish_manager.py:629-657` — `_validate_release_audit`
- `session-buddy/CHANGELOG.md:24-26` — the line the workaround addresses
- `session_buddy/server_optimized.py:374` — the wiring that's in product but in dep
- `mcp_common/health/metrics.py` — where `update_health_metrics` actually lives

______________________________________________________________________
