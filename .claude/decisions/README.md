---
status: active
role: canonical
date: 2026-08-24
last_reviewed: 2026-08-24
topic: decisions-index
---

# Decisions Index

One file per topic. Each file follows the canonical shape: a brief `## Context`, a `## Decision` (or `## Decision rule`), and a `## Status` field. Existing entries:

| Topic | Date | Status | File |
|---|---|---|---|
| `cross-repo-work-vs-eventbridge` | 2026-08-10 | `active` | [`cross-repo-work-vs-eventbridge.md`](cross-repo-work-vs-eventbridge.md) |

## Adding a Decision

1. Create `.claude/decisions/<topic>.md` with the canonical frontmatter (`status`, `role`, `date`, `last_reviewed`, `topic`) and a short body following the shape above.
1. Add a row to the table here so the index stays in sync with the directory.
1. Cross-link from any plan or spec that depends on the decision via `blocks_on:` / `supersedes:` in its frontmatter.
