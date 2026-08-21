# Session-Buddy MCP Tool Profile — Rationale (W1.2 backfill, 2026-08-18)

**Status:** Backfilled 2026-08-19 (post-W1.2 wave; this doc was absent during
the original W1.2 dispatch because the rationale-doc convention was formalized
during W2+).

**Wave:** W1 (backfill) — adopted `apply_tool_profile()` before the formal plan.
**Helper:** `mcp_common.tools.dispatch._apply_tool_profile` (mcp-common 0.18.0+).
**Env var:** `SESSION_BUDDY_TOOL_PROFILE` (defaults to `FULL`).

## Context

Session-Buddy is the Bodai ecosystem's session/conversation store (port 8678).
The pre-W1 server registered 35+ register functions unconditionally, which is
overwhelming for an LLM session that only needs basic session lifecycle plus
health. W1.2 backfilled the W0 helper so operators can dial down to the
minimum needed for context-management workflows.

## Profile Tiers

Defined in `session_buddy/mcp/tools/profiles.py`:

| Tier | Tools / groups included | Operator profile |
|------|-------------------------|------------------|
| **MINIMAL** | `register_session_tools`, `register_search_tools`, `register_hooks_tools` (~3 tools), **plus** `register_health_tools_sb` via mandatory | Context-guard agents, lightweight MCP clients, pre-compact hooks |
| **STANDARD** | MINIMAL + `conversation`, `extraction`, `knowledge_graph`, `cache`, `intent`, `crackerjack`, `feature_flags`, `monitoring`, `access_log`, `channel_session_state`, `channel_tracking`, `cross_repo_work` (~15 tools) | Day-to-day dev with full conversation APIs |
| **FULL** | Every key in `REGISTRATION_MAP` (~35 tools) via `ALL_TOOLS` sentinel + `register_all_fn` | Full power-user mode |

Health (`register_health_tools_sb`) is **NOT** in any per-profile list — it
sits in `SESSION_BUDDY_MANDATORY_GROUPS` so the W0 helper registers it at
every profile without duplication.

## Why these groupings

- **MINIMAL = session + search + hooks** — chosen because that is the minimum
  a Claude Code pre-compact-hook session needs. The `hooks_tools` group is
  critical for context-management handoff and must survive even aggressive
  profile cuts.
- **STANDARD** — daily-development essentials: conversation replay,
  extraction, knowledge graph, cache, intent classification, crackerjack
  integration, monitoring, and channel-tracking (Dhara publisher).
- **FULL** — everything including serverless, conscious agent, code-graph,
  memory-health, migration, and worktree tools. These are heavy and only
  meaningful for specific workflows.

## Configuration

Env-only. session-buddy does not expose `tool_profile` in its YAML; the
`settings_yaml_loader` parameter to the W0 helper is intentionally `None`.

`get_active_profile()` reads from `SESSION_BUDDY_TOOL_PROFILE` via
`ToolProfile.from_env`. Missing or invalid values fall back to `FULL`.

## Cross-Repo / Architectural Notes

- **Dhara publisher build pattern:** `register_channel_tracking_tools` requires
  an extra `dhara_publisher` kwarg (the Dhara HTTP client). profiles.py
  pre-builds a single `_dhara_publisher = _make_dhara_publisher()` at module
  load and captures it in the `_register_channel_tracking` wrapper so the W0
  helper can call this wrapper with `(server)` only. This avoids per-call
  socket churn.
- **Subagent-killing recovery:** The W1.2 implementer was terminated by a
  Token Plan rate limit mid-execution. The orchestrator committed the partial
  work at `c28124e8` and the test pass (75 tests, 0 regressions) was confirmed
  post-resume. Severity: process-coverage; no missed functionality.

## Tests

`session_buddy/tests/unit/test_wiring.py` plus `test_mcp_registration_standard_profile.py`
plus `mcp/test_tool_profile_drift.py`. 75 tests pass; the legacy `test_profiles.py`

- `test_profiles_coverage.py` (54 tests) confirm behavior parity at FULL.

## References

- Master plan: `docs/superpowers/plans/2026-08-18-mcp-tool-profile-adoption.md`
- Helper source: `/Users/les/Projects/mcp-common/mcp_common/tools/dispatch.py`
- Profiles module: `session_buddy/mcp/tools/profiles.py`
- Register-call sites: `session_buddy/mcp/server.py`
