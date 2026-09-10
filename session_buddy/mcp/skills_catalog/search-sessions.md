---
name: search-sessions
description: Use ONLY when the user explicitly types `/session-buddy:search-sessions` or selects this Skill from the picker to run a hybrid semantic + lexical search across the Session-Buddy memory corpus. Do not auto-trigger. Routes through `mcp__session_buddy__search_by_concept` to find semantically similar reflections, conversation checkpoints, and learned patterns scoped to a project.
allowed-tools: mcp__session_buddy__search_by_concept, mcp__session_buddy__search_by_source, mcp__session_buddy__quick_search, Read
---

# search-sessions

## When to use

This Skill is the right entry point when the user is asking a question
whose answer exists somewhere in the indexed Session-Buddy memory
corpus — across the active conversation history, captured reflection
database, learned patterns, and stored checkpoints. Common cases:

- "What did we do last time we hit a path-traversal regression in
  Session-Buddy?"
- "Find past conversations about FastMCP lifespan wiring."
- "Search the corpus for anything mentioning `mcp_common`."
- "Are there any reflections on Phase 1.5 signer issues?"
- "Show me prior sessions that touched `session_buddy/mcp/server.py`."

The query is a natural-language question. The Skill will:

1. Take the user's query verbatim.
2. Call `mcp__session_buddy__search_by_concept` with
   `concept=<the text>`, `limit=10`, `include_files=True`.
3. If the user names a specific project, pass it through `project=`
   so the results are scoped to that project; otherwise leave it `None`
   to search across all indexed projects.
4. Read back the top results and synthesize an answer with citations
   to the source `session_id` + `checkpoint_id` pairs.

## What the tool does

`mcp__session_buddy__search_by_concept` performs **hybrid semantic +
lexical** retrieval against the Session-Buddy reflection database:

- **Semantic**: encodes the query with the local embedding model and
  runs a vector similarity search against the indexed reflections.
- **Lexical**: the same call also tokenizes the query and ranks by
  token overlap. The two signals are fused before ranking.

The function signature is:

```python
async def search_by_concept(
    concept: str,
    include_files: bool = True,
    limit: int = 10,
    project: str | None = None,
) -> str
```

Notes:

- `limit` is clamped to 1-50; defaults to 10.
- `project` filters by the indexed project name; pass `None` to search
  across all projects.
- The returned string is a formatted reflection dump (suitable for
  direct LLM consumption) — not a JSON envelope.

## Companion tools

- `mcp__session_buddy__search_by_source` — filter by `source_type`
  (e.g. "checkpoint", "reflection") and `project`. Use this when the
  user asks "find reflections from project X" specifically.
- `mcp__session_buddy__quick_search` — fast lexical-only search.
  Prefer this when the user wants exact-token matches and not
  semantic similarity.

## When NOT to use

- For raw keyword search across one specific system, prefer
  `mcp__session_buddy__search_by_source` (entity-keyed) instead.
- For OTel trace queries, use the OTel-aware tools in
  `session_buddy/mcp/tools/memory/`.
- For code-pattern search, use
  `mcp__session_buddy__code_search_symbols`.

## Failure modes and how to handle them

- **No results**: the tool returns an empty results block. Surface
  this to the user; do not hallucinate content.
- **Embedding service down**: same empty-results block. Surface the
  degraded mode.
- **Rate limited / auth failed**: surface the error verbatim.
- **Project not indexed**: results are empty; suggest the user
  run `mcp__session_buddy__init_reflection_adapter` or check
  whether the project name matches the indexed name exactly
  (case-sensitive).

## Example flow

User: "What did we do last time crackerjack broke on httpx2 migration?"

Skill action:

```python
result = await mcp__session_buddy__search_by_concept(
    concept="crackerjack httpx2 migration regression",
    limit=10,
    include_files=True,
    project=None,
)
# result is a formatted string dump of the top-K matching reflections.
```

Synthesize the answer with citations to the top 3 results, surfacing
the `session_id` and `checkpoint_id` for each citation so the user
can revisit the source session.
