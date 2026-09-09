______________________________________________________________________

---
status: active
role: canonical
date: 2026-08-12
last_reviewed: 2026-09-09
superseded_by: null
blocks_on: []
topic: feature-tracking
---

# Tool Registration Gaps

## Summary

Six MCP tool categories were documented in CLAUDE.md as available in the
default profile, but their `register_*` functions are not called by
`server_optimized.py:301-318`. They are reachable only via the
alternative profile-driven entrypoint.

This file tracks the gap and the implementation status of each
`register_*` function. It was extracted from CLAUDE.md on 2026-09-09
during the docs audit so the gap has a single canonical home and the
CLAUDE.md content stays focused on what ships in the default profile.

## Affected Categories

| Category | register_* function | Status |
|----------|---------------------|--------|
| Serverless | `register_serverless_tools` | implemented; not wired into `server_optimized.py` |
| Team | `register_team_tools` | implemented; not wired into `server_optimized.py` |
| Multi-Project | `register_multi_project_tools` | **does not exist** |
| App Monitoring | `register_app_monitoring_tools` | **does not exist** |
| Interruption Management | `register_interruption_tools` | **does not exist** |
| Natural Scheduling | `register_natural_scheduling_tools` | **does not exist** |

## Reachable Via

The alternative profile-driven entrypoint registers all six categories
when `SESSION_BUDDY_TOOL_PROFILE` is set appropriately. See
`session_buddy.mcp.server` for the profile wiring.

## Original Audit Note

The gap was first documented in the 2026-08-12 audit. The original
blockquote from CLAUDE.md:

> **Removed in 2026-08-12 audit:** Serverless, Team, Multi-Project, App
> Monitoring, Interruption Management, and Natural Scheduling categories
> were documented but their `register_*` functions
> (`register_serverless_tools`, `register_team_tools`,
> `register_multi_project_tools` (does not exist),
> `register_app_monitoring_tools` (does not exist),
> `register_interruption_tools` (does not exist),
> `register_natural_scheduling_tools` (does not exist)) are not called
> by `server_optimized.py:301-318`. They are reachable only via the
> alternative profile-driven entrypoint.

## Recommended Follow-up

Either:
1. **Implement the four missing `register_*` functions** to close the
   documentation/implementation gap. Until then, the categories should
   not appear in CLAUDE.md as if they ship by default.
2. **Remove the categories from CLAUDE.md** until the functions exist,
   so the doc only lists what actually ships.

This doc serves as a placeholder until either action is taken.
