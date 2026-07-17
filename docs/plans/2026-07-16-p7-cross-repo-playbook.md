---
status: active
role: implementation
date: 2026-07-16
last_reviewed: 2026-07-17
superseded_by: null
blocks_on: []
topic: lifecycle
---

# P7 Cross-Repo Plan-Lifecycle-Unification Playbook

**Date:** 2026-07-16
**Audience:** P7.B fan-out agents (one per repo: dhara / crackerjack / akosha / oneiric).
**Owning repo:** `session-buddy` (this file is the P7.A template artifact).
**Source plan:** `docs/plans/2026-07-16-frontmatter-validator-wiring-plan.md` (Task 8 fan-out reads this).

> **Read first (in order):**
> 1. Mahavishnu's `docs/schemas/document-frontmatter-v1.md` (and `docs/schemas/topic-vocabulary-v1.md`) — the canonical schema and topic vocabulary. This file is a *per-repo adoption guide*, not a schema amendment.
> 2. Mahavishnu's `scripts/validate_document_frontmatter.py` and `scripts/regenerate_plan_index.py` — copy both verbatim into your repo under `scripts/`.
> 3. Mahavishnu's `docs/superpowers/plans/2026-07-16-plan-lifecycle-unification.md` — read the "Approved Adjustments" section (Adjustment A — hybrid topic vocab; Adjustment B — two-pass migration). The two-pass pattern is load-bearing.

______________________________________________________________________

## 1. Per-Repo Convention Detection (Read Before Anything Else)

Different Bodai repos use radically different docs layout. Decide the layout **first**, then choose the right normalization strategy. Do not invent a 6-store layout if the repo already has one.

### How to inventory

```bash
cd /Users/les/Projects/<repo>
ls docs/                          # top-level layout
ls .claude/decisions/ 2>/dev/null  # decisions-only stores
find docs/ -maxdepth 1 -name "*.md" | wc -l   # loose root count
find docs/ -mindepth 2 -name "*.md" | wc -l   # nested count
ls docs/archive/ 2>/dev/null       # already-archived material
```

### Layouts observed across Bodai

| Layout | Repos using it | What to do |
|---|---|---|
| **6-store (Mahavishnu)** — `docs/adr/`, `docs/plans/`, `docs/superpowers/specs/`, `docs/superpowers/plans/`, `.claude/decisions/`, `docs/followups/` | mahavishnu (template) | Use the validator's `DEFAULT_STORES` as-is. No scanner changes. |
| **Flat docs/ + docs/plans/** (canonical + many loose .md) | **session-buddy** (P7.A template) | Add per-repo extra path: `docs/` (loose docs) and the schema docs themselves. See Step 3 below. |
| **One repo-specific store only** (e.g., `docs/specs/`, `docs/decisions/`) | some upstream community plugins | Adapt `DEFAULT_STORES` and re-export in the per-repo playbook run log. |
| **No docs/ tree at all** (code-only repos) | none observed in Bodai | Skip the frontmatter migration; only set up scripts/schemas if the repo wants to start documenting. |

### What to do *not* do

- **Do NOT create new empty stores** like `docs/adr/` if they do not exist in the target repo. Each repo's documentation layout should reflect what it actually has written, not what Mahavishnu has.
- **Do NOT touch `docs/archive/`** — files there are intentionally finalized; skip them via the validator's `ALWAYS_EXCLUDE_DIRS_REL` or by passing extra exclusions.
- **Do NOT rewrite project README.md** at the repo root — top-level README is for users discovering the project, not for status normalization. Leave it alone unless the team explicitly asks.

______________________________________________________________________

## 2. When to Skip Empty Stores

Two rules:

1. **If a store directory doesn't exist, do not create it.** A repo with no `docs/adr/` should not get one just because Mahavishnu has one. Empty stores add entropy without value.
2. **If a store exists but only contains generated or excluded files, do not normalize them.** For example, `docs/plans/PLAN_INDEX.md` is generated; the validator already excludes it. Adding frontmatter to it is unnecessary (the regenerator writes its own block).
3. **If a store exists and has 1-3 files, treat it like a normal store** — small isn't the same as empty.

______________________________________________________________________

## 3. Default Frontmatter Assignments

### Loose docs (e.g., `docs/*.md`)

Three rules cover 95% of loose content:

| File character | Default assignment |
|---|---|
| Historical or completed plan | `status: complete, role: historical` |
| Active living reference | `status: active, role: canonical` |
| User-facing guide (QUICK_START, DEPLOYMENT, etc.) | `status: active, role: canonical` |
| Migration summary (`*_COMPLETE.md`, `*_SUMMARY.md`) | `status: complete, role: historical` |

Topic defaults by subdirectory (session-buddy observed; other repos may differ):

- `docs/api/`, `docs/reference/`, `docs/user/`, `docs/developer/` → `mcp-design`, `lifecycle`, or `architecture`
- `docs/migrations/`, `docs/migrations/*COMPLETE.md` → `oneiric-config` or `storage-consolidation`
- `docs/migrations/V*_TO_V*` → `oneiric-config` (historical)
- `docs/security/`, `*JWT*`, `*AUTH*`, `*ENCRYPTION*` → `auth`
- `docs/performance/*_results.md` → `observability` (historical)
- `docs/guides/`, `docs/design/` → `architecture` (canonical)
- `docs/features/`, `docs/initialization/` → topic inferred from filename (often `lifecycle` or `learning-pipeline`)
- `docs/realtime/`, `*WEBSOCKET*` → `mcp-design`
- `docs/grafana/`, `*MONITORING*`, `*PROMETHEUS*` → `observability`

### Plans (`docs/plans/*.md`)

| Status string in body | Maps to | Plus role |
|---|---|---|
| `**Status:** shipped` | `status: shipped` | `role: implementation` |
| `**Status:** complete` / `**Status:** COMPLETE` / `PHASE X COMPLETE` | `status: complete` | `role: implementation` |
| `**Status:** Approved` / `Approved (rev N)` / `Active` | `status: active` | `role: implementation` |
| `**Status:** Draft` / `Proposed` / `Ready for Implementation` | `status: draft` | `role: implementation` |
| `**Status:** SUPERSEDED` | `status: complete` | `role: historical` (plus populate `superseded_by`) |
| No frontmatter and no Status line | `status: draft` | `role: implementation` |

### Schema/vocabulary docs

Schema and vocabulary files should always carry:

```yaml
status: active
role: canonical
topic: lifecycle
```

They are the source of truth and remain active indefinitely.

### Plugin commands / templates

```yaml
status: active
role: canonical
topic: plugin-standardization
```

These are part of the plugin surface and don't expire.

______________________________________________________________________

## 4. Topic Vocabulary Additions Per Repo

When you encounter topics that aren't in the seed list, **add them to `docs/schemas/topic-vocabulary-v1.md`** as part of the same PR/change. The validator only warns (doesn't fail) for unknown topics, but the playbook recommends adding them so the index stays searchable.

### session-buddy additions made during P7.A

- `architecture` — introduced 2026-07-16 for the `docs/architecture/`, `docs/design/`, `docs/developer/` directories and refactor plans.

### Likely additions for other repos

- **dhara** — `consensus`, `state-machine`, `snapshot-replication` (search body for patterns).
- **crackerjack** — `phase-coordinator`, `quality-gate`, `release-bump`.
- **akosha** — `embeddings`, `semantic-search`, `cross-system-knowledge`.
- **oneiric** — `resolver`, `configuration`, `lifecycle-hooks`.

Do not preemptively add these; add what you actually use during the sweep.

______________________________________________________________________

## 5. The Validator Copy + Command Sequence

### Step 1 — Copy artifacts (one-time per repo)

```bash
cd /Users/les/Projects/<repo>
mkdir -p scripts docs/schemas
cp /Users/les/Projects/mahavishnu/scripts/validate_document_frontmatter.py scripts/
cp /Users/les/Projects/mahavishnu/scripts/regenerate_plan_index.py scripts/
cp /Users/les/Projects/mahavishnu/docs/schemas/document-frontmatter-v1.md docs/schemas/
cp /Users/les/Projects/mahavishnu/docs/schemas/topic-vocabulary-v1.md docs/schemas/
```

### Step 2 — Initial scan to inventory

Each repo's structure is different; pass the appropriate paths explicitly:

```bash
# Mahavishnu-style (6-store): rely on DEFAULT_STORES
cd /Users/les/Projects/mahavishnu
uv run python scripts/validate_document_frontmatter.py --allow-nonstandard

# Session-buddy-style (flat docs/): pass `docs` as extra path
cd /Users/les/Projects/session-buddy
uv run python scripts/validate_document_frontmatter.py --allow-nonstandard docs

# Oneiric-style (single store): pass the store explicitly
cd /Users/les/Projects/oneiric
uv run python scripts/validate_document_frontmatter.py --allow-nonstandard docs/
```

Capture the file count and `missing=` count from the summary line. This becomes your migration manifest.

### Step 3 — Pass 1 (frontmatter-only write)

Use a Python helper modeled on `_frontmatter_apply_C1_2.py` (or a per-repo variant if structure is different):

1. Walk every file path the validator just identified.
2. Skip files that already have frontmatter.
3. For each remaining file, build a per-file assignment table (status, role, topic) keyed on the relative path.
4. Add legacy HTML comment (`<!-- legacy status ... see YAML frontmatter -->`) on the first `**Status:**` line so `--allow-nonstandard` stays green.

Pass 1 must NOT run `--validate-links`. Forward-pointing `superseded_by`/`blocks_on` are written verbatim.

### Step 4 — Pass 2 (link-validation sweep)

After Pass 1 lands for **all** stores in the repo:

```bash
uv run python scripts/validate_document_frontmatter.py --validate-links --allow-nonstandard
```

Expected: 0 ERROR. Fix any broken `superseded_by` paths by either editing the value or creating the successor file.

### Step 5 — Regenerate PLAN_INDEX

```bash
uv run python scripts/regenerate_plan_index.py
```

This overwrites `docs/plans/PLAN_INDEX.md`. Diff against previous version to confirm the index is richer.

### Step 6 — Smoke test

```bash
uv run python scripts/validate_document_frontmatter.py --validate-links --allow-nonstandard
uv run python scripts/regenerate_plan_index.py
git diff docs/plans/PLAN_INDEX.md  # second run should produce no diff
```

______________________________________________________________________

## 6. Commit Cadence

Per-scope, NOT all-at-once. Each fan-out subagent should produce 2-4 commits per target repo, mirroring Mahavishnu's Wave A-C pattern:

1. **Commit 1**: `scripts/` + `docs/schemas/` (the validator, regenerator, schemas).
2. **Commit 2**: Per-store normalization, ONE store per commit. For session-buddy: commit loose `docs/*.md` first, then `docs/plans/*.md`, then `commands/`/`templates/`/`session_buddy/`.
3. **Commit 3**: Link-sweep fixes (only if anything was broken).
4. **Commit 4**: Regenerated `docs/plans/PLAN_INDEX.md`.

### Subject line format

```
docs(<repo-name>): apply plan-lifecycle-unification playbook (P7.B for <repo>)
```

If split across multiple commits, use:

```
docs(<repo>): copy validator + schemas (P7.B seed)
docs(<repo>): normalize loose docs/ (P7.B sweep, batch 1/N)
docs(<repo>): regenerate docs/plans/PLAN_INDEX.md from frontmatter
```

### Author

Each agent must set the user/email explicitly (the agent default may not match the repo's convention):

```bash
git -c user.email=les@wedgwoodwebworks.com -c user.name=lesleslie commit -m "..."
```

### What NOT to commit

- Pre-existing dirty state on the target repo. If the agent sees modified files unrelated to P7.B work, surface them as warnings and do NOT bundle them.
- Generated artifacts that aren't frontmatter-aware (`__pycache__`, `.pytest_cache`, etc.).
- Edited files outside `scripts/`, `docs/schemas/`, and the docs stores being normalized.

______________________________________________________________________

## 7. Link Sweep Pattern

When `--validate-links` reports a broken link:

| Broken link target | Fix |
|---|---|
| Points to a non-existent file | Create the successor file with `status: draft, role: implementation` and matching topic, or null out the link. |
| Points to an unnormalized file | Run the normalizer on that target first, then re-sweep. |
| Points to an external repo | Replace with `ext:<identifier>` (planned but not yet enforced). Drop the absolute path until the registry ships. |
| Pure prose reference (`"see discussion in <X>"`) | Not validated; leave alone unless the user wants machine-readable links. |

After fixes:

```bash
uv run python scripts/validate_document_frontmatter.py --validate-links --allow-nonstandard
grep -c "\[ERROR\]" /tmp/<repo>-link-sweep.txt  # target: 0
```

______________________________________________________________________

## 8. P7.A Verified Recipe (session-buddy)

The following recipe was executed 2026-07-16 and produced session-buddy's frontmatter reality. Use it as a worked example.

### Inventory

- 124 `.md` files in scope across `docs/`, root-level loose, `commands/`, `templates/`, `session_buddy/analytics/`.
- Of those, 2 are the schema/vocab files we copy in (treated as "pre-existing but new to this repo"); the rest get frontmatter.
- 18 files were skipped on the first pass for "no assignment"; the second pass added entries for SKILL_METRICS_*, developer/*, AI_INTEGRATION, WEBSOCKET_API, JSON_SCHEMA_REFERENCE, plus all `commands/` and `templates/` plugin files.

### Helper used

`scripts/_frontmatter_apply_C1.py` — mirrors `_orphan_sweep_C1_2.py` from Mahavishnu but adapts to session-buddy's flat docs/ + 6 sub-store layout (api, design, developer, features, grafana, guides, initialization, integration, migrations, monitoring, performance, plans, realtime, reference, security, user).

### Link sweep result

```
Summary: total=101 ok=101 warning=0 missing=0 invalid=0
```

All 101 files have valid frontmatter AND all `superseded_by: null` / `blocks_on: []` placeholders link-validate cleanly.

### PLAN_INDEX

Regenerated to 128 lines, 5 sections. The legacy hand-maintained index (separate "Active" vs "Archived" lists) was overwritten — this is intentional. The new index is the single source of truth and groups entries by lifecycle + role.

### What did NOT need to change

- `.claude/decisions/` (does not exist in session-buddy; no creation).
- `docs/adr/`, `docs/superpowers/specs/`, `docs/superpowers/plans/`, `docs/followups/` (none of these exist; not created).
- `docs/archive/` (already finalized; skipped via the `EXCLUDED_DIRS` set in the helper).
- `CLAUDE.md`, `AGENTS.md`, top-level `README.md` (project-level, not docs).

______________________________________________________________________

## 9. Open Questions / Future Amendments

1. **Cross-repo `superseded_by` representation.** Currently all cross-repo references fall back to `null`. A registry of `ext:<id>` identifiers is planned but not yet enforced. When two repos need to chain (e.g., session-buddy checkpoints → mahavishnu routing), prefer renaming to a same-repo entry over a `superseded_by` cross-link.
2. **Schema amendments.** Any repo that needs a new lifecycle or role value should propose the amendment to `mahavishnu/docs/schemas/document-frontmatter-v1.md` first. P7 templates do not introduce new schema values; per-repo topic additions to `topic-vocabulary-v1.md` are an exception.
3. **CI gating.** The P7.B agents should NOT add CI hooks for the frontmatter check — that's a separate decision (Mahavishnu is the canonical rules-enforcer, but only via Crackerjack post-Phase 1, not via per-repo CI). If a repo wants local enforcement, manually add a pre-commit hook and surface it in this playbook's local-customization section.

______________________________________________________________________

## Verification (Final)

```bash
# 1. Validator passes all in-scope files with --validate-links
cd /Users/les/Projects/<repo>
uv run python scripts/validate_document_frontmatter.py --validate-links --allow-nonstandard
# Expected: 0 ERROR

# 2. Every in-scope .md carries `status:`
grep -L '^status:' $(find docs/ -name "*.md")
# Expected: empty output

# 3. PLAN_INDEX.md is deterministic
uv run python scripts/regenerate_plan_index.py
git diff docs/plans/PLAN_INDEX.md
# Expected: no diff on second run
```

______________________________________________________________________

**Self-Review** — this playbook captures per-repo convention detection (Step 1), the "skip empty stores" rule (Step 2), default frontmatter matrix (Step 3), topic vocabulary additions (Step 4), the exact command sequence (Step 5), commit cadence (Step 6), and link-sweep pattern (Step 7). The verified session-buddy recipe in Step 8 demonstrates the playbook end-to-end on the template repo. Open questions for cross-repo chain IDs and CI gating are deferred to future amendments (Step 9).
