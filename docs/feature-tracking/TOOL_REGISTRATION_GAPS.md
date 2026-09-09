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

The 2026-08-12 audit documented six MCP tool categories whose `register_*`
functions were not called by `server_optimized.py`. Investigation on
2026-09-09 corrected that picture:

- **Serverless** and **Team**: functions exist and ARE registered via
  the profile-driven entrypoint (`REGISTRATION_MAP` in `profiles.py`).
  Reachable at `SESSION_BUDDY_TOOL_PROFILE=full`. NOT a gap.
- **App Monitoring** and **Interruption Management**: these were never
  separate functions. Their tools are bundled inside
  `register_monitoring_tools` and ship at STANDARD profile. NOT a gap.
- **Multi-Project** and **Natural Scheduling**: backing modules
  exist (`multi_project_coordinator.py` 24.8 KB;
  `natural_scheduler.py` 22.4 KB) but no MCP wrappers. Genuine gap.

This file tracks the genuine gaps (Multi-Project, Natural Scheduling).

## Affected Categories (corrected 2026-09-09)

| Category | register_* function | Status (corrected) |
|---|---|---|
| Serverless | `register_serverless_tools` | implemented; in REGISTRATION_MAP; ships at FULL profile |
| Team | `register_team_tools` | implemented; in REGISTRATION_MAP; ships at FULL profile |
| App Monitoring | (no separate function) | tools bundled in `register_monitoring_tools`; ships at STANDARD profile |
| Interruption Management | (no separate function) | tools bundled in `register_monitoring_tools`; ships at STANDARD profile |
| Multi-Project | `register_multi_project_tools` | **NEWLY IMPLEMENTED 2026-09-09** |
| Natural Scheduling | `register_natural_scheduling_tools` | **NEWLY IMPLEMENTED 2026-09-09** |

## 2026-09-09 Resolution

Both genuine gaps were closed by adding:

- `session_buddy/mcp/tools/collaboration/multi_project_tools.py` — 6 MCP tools
  over `MultiProjectCoordinator`
- `session_buddy/mcp/tools/infrastructure/natural_scheduling_tools.py` — 6 MCP
  tools over `ReminderScheduler`
- REGISTRATION_MAP entries in `session_buddy/mcp/tools/profiles.py`
- e2e tests at `tests/integration/test_*_tools_e2e.py`

After this change, all 6 categories originally documented as gaps are
shipped via the profile-driven entrypoint at FULL profile.
