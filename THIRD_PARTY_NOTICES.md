______________________________________________________________________

## status: active role: canonical date: 2026-07-16 last_reviewed: 2026-07-16 superseded_by: null blocks_on: [] topic: lifecycle

# Third-Party Notices (Session-Buddy)

This file lists third-party projects adopted by Session-Buddy, with version, license, URL, copyright, integration posture, and AGPL/SSPL posture where applicable.

**Last updated:** 2026-06-23
**Maintained by:** Session-Buddy / Bodai ecosystem

Session-Buddy's adoption surface is narrower than Mahavishnu's. Session-Buddy provides memory + distillation primitives consumed by other Bodai components.

## Adopted third-party projects

### Direct dependencies (in `pyproject.toml`)

These are Python packages consumed by Session-Buddy source code.

| Project | License | URL | AGPL posture |
|---|---|---|---|
| duckdb | MIT | https://duckdb.org | N/A |
| pydantic | MIT | https://github.com/pydantic/pydantic | N/A |
| structlog | Apache-2.0 / MIT | https://github.com/hynek/structlog | N/A |
| aiosqlite | MIT | https://github.com/omnilib/aiosqlite | N/A |
| (others — see `pyproject.toml`) | (various permissive) | | N/A |

### Indirect adoption (via Bodai plans that affect Session-Buddy)

These are projects adopted by other Bodai components that may surface through Session-Buddy's consumption surface.

| Project | License | URL | AGPL posture | Notes |
|---|---|---|---|---|
| None currently | — | — | — | Session-Buddy does not currently consume any AGPL-licensed upstream |

## Conventions

- **Mode** indicates integration posture:
  - **Reimplement** — pattern borrowed, code built in-tree (no dep)
  - **Wrap as service** — external daemon/container, talk via stdio/HTTP/OTLP
  - **Run as CLI subprocess** — invoke on demand, no long-lived process
- **License** is the upstream project's published license.
- **AGPL posture** notes the legal/compliance status where the upstream is AGPL-3.0 or SSPL.

## Legal posture summary

1. **No source linking**: Session-Buddy does not import AGPL libraries directly.
1. **No source distribution**: Session-Buddy repos do not bundle AGPL source.
1. **Attribution**: This file provides attribution per project.
1. **AGPL inheritance**: If Session-Buddy gains a runtime dependency that loads AGPL code, this file must be updated before the dependency lands.

## How to update

When adopting a new third-party project:

1. Add a row to the appropriate table.
1. Document version, license, URL, copyright (look up upstream `LICENSE` file).
1. Specify integration mode.
1. If AGPL/SSPL: add legal posture note.
1. Commit with PR title `chore: add <project> to THIRD_PARTY_NOTICES.md`.

## Cross-references

- `/Users/les/Projects/mahavishnu/THIRD_PARTY_NOTICES.md` — primary cross-repo third-party registry (Mahavishnu-adopted projects).
- `/Users/les/Projects/mahavishnu/docs/superpowers/eval/2026-06-22-bodai-ecosystem-candidates.md` — source evaluation for these adoptions.
- `/Users/les/.claude/plans/update-the-report-with-rippling-matsumoto.md` — implementation plans.
