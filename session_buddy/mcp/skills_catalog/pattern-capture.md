---
name: pattern-capture
description: Use ONLY when the user explicitly types `/session-buddy:pattern-capture` or selects this Skill from the picker to persist a high-quality workflow pattern into the Session-Buddy reflection database for cross-project reuse. Do not auto-trigger. Routes through `mcp__session_buddy__capture_successful_pattern` with strict outcome_score thresholding (≥0.75) and pattern_type validation.
allowed-tools: mcp__session_buddy__capture_successful_pattern, mcp__session_buddy__search_similar_patterns, mcp__session_buddy__apply_pattern, Read
---

# pattern-capture

## When to use

This Skill is the right entry point when the user has just completed a
session that produced a **reusable, high-quality** pattern — a
solution, workaround, or optimization that should propagate to other
projects. Common cases:

- "I just fixed the path-traversal regression in `_build_unsigned_metadata`.
  Capture that as a reusable pattern."
- "This `SkillsSigner.from_keypair` invocation is the canonical way to
  build a signer — capture it so future servers don't reinvent it."
- "We just verified the dual-track drift fix; capture the
  `REGISTRATION_TOOLS` vs inline-registration split as a pattern."
- "Persist the FastMCP lifespan guard pattern so future lifespan
  wrappers don't drop the redundant-init issue."

The Skill enforces **strict outcome_score thresholding** — patterns
below 0.75 are rejected at the API boundary. This keeps the reflection
database from accumulating low-signal noise.

## What the tool does

`mcp__session_buddy__capture_successful_pattern` persists a pattern
record into the Session-Buddy intelligence engine. The function
signature is:

```python
async def capture_successful_pattern(
    pattern_type: str,        # "solution" | "workaround" | "optimization"
    project_id: str,          # indexed project name
    context: dict[str, Any],  # the problem context (free-form)
    solution: dict[str, Any], # the resolution (free-form)
    outcome_score: float,     # 0.0-1.0; threshold 0.75 to be captured
    tags: list[str] | None = None,
) -> dict[str, Any]
```

The returned dict carries:

- `success` — boolean
- `pattern_id` — the persisted record's unique ID (when success=True)
- `message` — informational
- `pattern_type` / `project_id` / `outcome_score` — echo of inputs

## Outcome_score thresholding

The `outcome_score` is the **single most important input** — it gates
whether the pattern is captured at all. The Skill applies these rules:

| Score | Treatment |
|---|---|
| ≥ 0.75 | Captured, eligible for cross-project promotion |
| 0.50-0.74 | Captured, scoped to the originating project only |
| < 0.50 | Rejected — surface the rejection to the user |

The threshold is enforced both at the API boundary (in the MCP tool's
own validation) and by the Skill before calling the tool. Double-
gating prevents low-quality patterns from polluting the corpus.

## pattern_type validation

The `pattern_type` must be one of `["solution", "workaround",
"optimization"]`. Use:

- `solution` — a clean fix to a recurring problem.
- `workaround` — a tactical fix that papers over a deeper issue; tag
  with `["workaround", "<root-cause>"]` so future searches can
  surface it.
- `optimization` — a performance or readability improvement that
  doesn't fix a bug.

## Companion tools

- `mcp__session_buddy__search_similar_patterns` — before capturing,
  search for existing patterns to avoid duplicates. Pass the
  `current_context` matching the problem context.
- `mcp__session_buddy__apply_pattern` — record a pattern application
  for tracking. Use after a captured pattern is applied to a new
  project.
- `mcp__session_buddy__rate_pattern_outcome` — provide feedback on
  whether an applied pattern worked. Closes the learning loop.

## When NOT to use

- For low-quality or speculative patterns, do NOT use this Skill —
  use `mcp__session_buddy__store_reflection` directly to record a
  lower-fidelity memory without the cross-project propagation.
- For project-specific one-offs, use the project-local reflection
  store; patterns are for cross-project reuse.

## Failure modes and how to handle them

- **`outcome_score` out of range [0.0, 1.0]**: tool returns
  `success=False`. Surface the error verbatim.
- **`pattern_type` not in the allowlist**: tool returns
  `success=False`. Surface the error.
- **Project not indexed**: tool returns
  `success=False` with a "project not found" error. Surface and
  suggest running `mcp__session_buddy__init_reflection_adapter`.
- **Duplicate pattern (same context hash)**: tool may return
  `success=False` with a duplicate-detection error. Surface and
  suggest `mcp__session_buddy__search_similar_patterns` to verify
  the existing pattern is what you meant to capture.

## Example flow

User: "I just fixed the redundant-init issue in
`_lifespan_with_dhara_cleanup`. Capture that pattern so other
async-lifespan wrappers in the Bodai ecosystem don't repeat the
mistake."

Skill action:

```python
result = await mcp__session_buddy__capture_successful_pattern(
    pattern_type="solution",
    project_id="session-buddy",
    context={
        "problem": (
            "async lifespan wrapper re-initializes state that the "
            "wrapped lifespan already initialized"
        ),
        "symptom": (
            "every restart bumps generation token twice; "
            "/health reports inconsistent feed state"
        ),
        "files": ["session_buddy/mcp/server.py"],
    },
    solution={
        "approach": (
            "guard the wrapper's init with `if get_X_state() is None` "
            "so it becomes a no-op when the wrapped lifespan "
            "already populated the state"
        ),
        "code_shape": (
            "if get_signer_feed_state() is None:\n"
            "    init_signer_feed_state()"
        ),
        "verification": (
            "restart produces generation=0; without the guard it "
            "would be 1"
        ),
    },
    outcome_score=0.92,  # well above the 0.75 cross-project threshold
    tags=["lifespan", "defense-in-depth", "review-finding"],
)
```

Synthesize the result into a short report: the `pattern_id` for
follow-up references, the `outcome_score` for context, and a pointer
to `mcp__session_buddy__apply_pattern` for future invocations.
