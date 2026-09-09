______________________________________________________________________

---
status: active
role: canonical
date: 2026-09-09
last_reviewed: 2026-09-09
superseded_by: null
blocks_on: []
topic: oneiric-config
---

# Claude/Qwen Config Sync

> **Archived on 2026-09-09.** The full documentation previously at this
> path has been moved to
> [docs/archive/CLAUDE_QWEN_CONFIG_SYNC.md](./archive/CLAUDE_QWEN_CONFIG_SYNC.md).
> The body content was 7 months stale (last refresh 2026-02-06); the
> archived copy is preserved as historical reference.

## The feature is still active

`sync_claude_qwen_config` is a **live MCP tool** — the underlying
implementation is maintained in the codebase:

- **Registration**: `session_buddy/mcp/tools/discovery_tools.py:232`
- **Implementation**: `session_buddy/mcp/tools/intelligence/llm_tools.py:436`
- **Test suite**: `tests/unit/test_llm_tools.py` (covers the operation)
- **LLM manager**: `session_buddy/llm_providers.py` (provides the
  bidirectional sync logic)

Use the MCP tool via your MCP client to sync Claude Code and Qwen Code
configurations (MCP servers, commands, and extension tracking). If the
archived documentation disagrees with the current implementation, trust
the implementation.
