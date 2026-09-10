---
name: code-archaeologist
description: Use ONLY when the user explicitly types `/session-buddy:code-archaeologist` or selects this Skill from the picker to trace caller/callee relationships of a symbol in the indexed code graph. Do not auto-trigger. Routes through `mcp__session_buddy__code_call_chain` to traverse transitive call relationships and surface the blast radius of a proposed change.
allowed-tools: mcp__session_buddy__code_call_chain, mcp__session_buddy__code_impact_analysis, mcp__session_buddy__code_search_symbols, Read
---

# code-archaeologist

## When to use

This Skill is the right entry point when the user is asking a question
about *who calls what* in the indexed Session-Buddy code graph — the
kind of question a code-archaeologist would ask before excavating a
ruin. Common cases:

- "What calls `init_signer_feed_state` in session-buddy?"
- "Show me all callers of `SkillsSigner.sign` across the Bodai
  ecosystem."
- "What's the blast radius if I rename `_lifespan_with_dhara_cleanup`?"
- "Trace the call graph from `register_skill_tools` to the FastMCP
  app constructor."
- "Is `search_by_concept` safe to refactor — does anything depend on
  its return type?"

The query is a symbol name (function, method, class) optionally
qualified by a module path. The Skill will:

1. Take the symbol name from the user.
2. Call `mcp__session_buddy__code_call_chain` with `symbol_name=<name>`,
   `direction="both"`, `max_depth=5` (default).
3. If the user wants one direction only, narrow to
   `direction="callers"` or `direction="callees"`.
4. Synthesize the result into a readable blast-radius report.

## What the tool does

`mcp__session_buddy__code_call_chain` traverses the stored Session-Buddy
code graph (built by the tree-sitter ingestion pipeline) to find
transitive callers and callees of a symbol. The function signature is:

```python
async def code_call_chain(
    symbol_name: str,
    direction: str = "both",  # "callers" | "callees" | "both"
    max_depth: int = 5,         # 1-10
    repo_path: str | None = None,
    edge_filter: list[str] | None = None,
) -> dict[str, Any]
```

The returned dict carries:

- `symbol_name` — the resolved canonical name (post-disambiguation)
- `direction` — echo of the request
- `max_depth` — echo of the request
- `chain` — list of `{depth, symbol, edge_type, file, line}` records
- `truncated` — boolean; True if the chain was capped at max_depth

Notes:

- `max_depth` is clamped to 1-10. Default 5 covers most refactor
  questions; raise to 10 only for cross-cutting concerns (lifespan,
  exception handlers, config loading).
- `repo_path` disambiguates when two repos define a symbol with the
  same bare name (e.g. `akosha` and `session_buddy` both define
  `init_signer_feed_state`). Pass the absolute repo path to lock the
  lookup.
- `edge_filter` narrows the traversal to specific edge types (e.g.
  `["calls", "imports"]`). Useful when you want to exclude
  `inherits` or `references` edges.

## Companion tools

- `mcp__session_buddy__code_impact_analysis` — combine caller
  traversal with heuristic risk scoring. Prefer this when the user
  asks "how risky is this change?" rather than "who calls X?"
- `mcp__session_buddy__code_search_symbols` — discover symbols by
  fuzzy name match. Use before `code_call_chain` if you're not sure
  of the canonical symbol name.

## When NOT to use

- For lexical search across source code, prefer
  `mcp__session_buddy__search_code`.
- For file-path searches, prefer shell `rg` / `grep`.
- For runtime call traces (not static analysis), use the OTel-aware
  tools in `session_buddy/mcp/tools/memory/`.

## Failure modes and how to handle them

- **Symbol not indexed**: the tool returns `chain=[]`. Surface this
  and suggest running
  `mcp__session_buddy__code_ingest_directory` first.
- **Repo path not indexed**: same empty `chain=[]`. Verify the repo
  path is absolute and the project has been ingested.
- **`max_depth` truncated**: the response carries `truncated=True`.
  Surface this — the user may want to raise `max_depth`.
- **Symbol name collision**: when `repo_path` is `None` and the bare
  name resolves to multiple canonical symbols, the tool picks the
  first match. If the user complains about the wrong match, ask for
  the qualified name.

## Example flow

User: "What's the blast radius if I rename `init_signer_feed_state` in
session-buddy?"

Skill action:

```python
result = await mcp__session_buddy__code_call_chain(
    symbol_name="init_signer_feed_state",
    direction="both",
    max_depth=10,
    repo_path="/Users/les/Projects/session-buddy",
)
# result["chain"] is the list of caller/callee records.
```

Synthesize the result into a grouped report:

1. List direct callers (depth=1) — these are the highest-risk touch
   points.
2. List indirect callers (depth>1) — these propagate the change but
   are usually safe.
3. List callees — the function's own dependencies; renaming
   `init_signer_feed_state` doesn't break them, but if the user is
   changing its signature, the callees need a signature review.
4. Surface `truncated` if True; suggest raising `max_depth` to 10.
