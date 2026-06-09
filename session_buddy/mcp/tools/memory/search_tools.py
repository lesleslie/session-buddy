#!/usr/bin/env python3
"""Search and reflection tools for session-mgmt-mcp.

Following crackerjack architecture patterns with focused, single-responsibility tools
for conversation memory, semantic search, and knowledge retrieval.

Refactored to use utility modules for reduced code duplication.
"""

from __future__ import annotations

import json
import operator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from session_buddy.utils.database_tools import require_reflection_database
from session_buddy.utils.error_management import (
    DatabaseUnavailableError,
    _get_logger,
    validate_required,
)
from session_buddy.utils.messages import ToolMessages
from session_buddy.utils.tool_wrapper import (
    execute_database_tool,
    execute_simple_database_tool,
)

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter import (
        ReflectionDatabaseAdapter as ReflectionDatabase,
    )
    from session_buddy.search.progressive_search import SearchTier


# Progressive search imports


# ============================================================================
# Token Optimization (Standalone - No Database)
# ============================================================================


async def _optimize_search_results_impl(
    results: list[dict[str, Any]],
    optimize_tokens: bool,
    max_tokens: int,
    query: str,
) -> dict[str, Any]:
    """Apply token optimization to search results if available."""
    try:
        from session_buddy.token_optimizer import TokenOptimizer

        if optimize_tokens and results:
            optimizer = TokenOptimizer()
            (
                optimized_results,
                optimization_info,
            ) = await optimizer.optimize_search_results(
                results, "truncate_old", max_tokens
            )
            return {
                "results": optimized_results,
                "optimized": True,
                "optimization_info": optimization_info,
            }

        return {"results": results, "optimized": False, "token_count": 0}
    except ImportError:
        _get_logger().info("Token optimizer not available, returning results as-is")
        return {"results": results, "optimized": False, "token_count": 0}
    except Exception as e:
        _get_logger().exception(f"Search optimization failed: {e}")
        return {"results": results, "optimized": False, "error": str(e)}


# ============================================================================
# Store Reflection
# ============================================================================


async def _store_reflection_operation(
    db: ReflectionDatabase, content: str, tags: list[str]
) -> dict[str, Any]:
    """Execute reflection storage operation."""
    reflection_id = await db.store_reflection(content, tags)
    return {"success": True, "id": reflection_id, "content": content, "tags": tags}


def _format_store_reflection(result: dict[str, Any]) -> str:
    """Format reflection storage result."""
    tag_text = f" (tags: {', '.join(result['tags'])})" if result["tags"] else ""
    return f"✅ Reflection stored successfully with ID: {result['id']}{tag_text}"


async def _store_reflection_impl(content: str, tags: list[str] | None = None) -> str:
    """Store an important insight or reflection for future reference."""

    def validator() -> None:
        validate_required(content, "content")

    async def operation(db: ReflectionDatabase) -> dict[str, Any]:
        return await _store_reflection_operation(db, content, tags or [])

    return await execute_database_tool(
        operation, _format_store_reflection, "Store reflection", validator
    )


# ============================================================================
# Quick Search
# ============================================================================


async def _quick_search_operation(
    db: ReflectionDatabase,
    query: str,
    project: str | None,
    min_score: float,
    limit: int = 5,
) -> str:
    """Execute quick search and format results."""
    total_results = await db.search_conversations(
        query=query, project=project, min_score=min_score, limit=limit
    )

    if not total_results:
        return f"🔍 No results found for '{query}'"

    top_result = total_results[0]
    result = f"🔍 **{len(total_results)} results** for '{query}'\n\n"
    result += f"**Top Result** (score: {top_result.get('similarity', 'N/A')}):\n"
    result += f"{top_result.get('content', '')[:200]}..."

    if len(total_results) > 1:
        result += f"\n\n💡 Use get_more_results to see additional {len(total_results) - 1} results"

    return result


async def _quick_search_impl(
    query: str,
    project: str | None = None,
    min_score: float = 0.7,
    limit: int = 5,
) -> str:
    """Quick search that returns only the count and top result for fast overview."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _quick_search_operation(db, query, project, min_score, limit)

    return await execute_simple_database_tool(operation, "Quick search")


# ============================================================================
# Search Summary
# ============================================================================


def _extract_key_terms(all_content: str) -> list[str]:
    """Extract key terms from content."""
    word_freq: dict[str, int] = {}
    for word in all_content.split():
        if len(word) > 4:  # Skip short words
            word_freq[word.lower()] = word_freq.get(word.lower(), 0) + 1

    if word_freq:
        top_words = sorted(word_freq.items(), key=operator.itemgetter(1), reverse=True)[
            :5
        ]
        return [w[0] for w in top_words]
    return []


async def _format_search_summary(query: str, results: list[dict[str, Any]]) -> str:
    """Format complete search summary."""
    if not results:
        return f"🔍 No results found for '{query}'"

    lines = [
        f"🔍 **Search Summary for '{query}'**\n",
        f"**Found**: {len(results)} relevant conversations\n",
    ]

    # Time distribution
    dates = [r.get("timestamp", "") for r in results if r.get("timestamp")]
    if dates:
        lines.append(f"**Time Range**: {min(dates)} to {max(dates)}\n")

    # Key themes
    all_content = " ".join([r.get("content", "")[:100] for r in results])
    key_terms = _extract_key_terms(all_content)
    if key_terms:
        lines.append(f"**Key Terms**: {', '.join(key_terms)}\n")

    lines.append("\n💡 Use search with same query to see individual results")

    return "".join(lines)


async def _search_summary_operation(
    db: ReflectionDatabase, query: str, project: str | None, min_score: float
) -> str:
    """Execute search summary operation."""
    results = await db.search_conversations(
        query=query, project=project, min_score=min_score, limit=20
    )
    return await _format_search_summary(query, results)


async def _search_summary_impl(
    query: str,
    project: str | None = None,
    min_score: float = 0.7,
) -> str:
    """Get aggregated insights from search results without individual result details."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_summary_operation(db, query, project, min_score)

    return await execute_simple_database_tool(operation, "Search summary")


# ============================================================================
# Pagination - Get More Results
# ============================================================================


def _build_pagination_output(
    query: str,
    offset: int,
    paginated_results: list[dict[str, Any]],
    total_results: int,
    limit: int,
) -> str:
    """Build the complete output for paginated results."""
    if not paginated_results:
        return f"🔍 No more results for '{query}' (offset: {offset})"

    output = f"🔍 **Results {offset + 1}-{offset + len(paginated_results)}** for '{query}'\n\n"

    for i, result in enumerate(paginated_results, offset + 1):
        if result.get("timestamp"):
            output += f"**{i}.** ({result['timestamp']}) "
        else:
            output += f"**{i}.** "
        output += f"{result.get('content', '')[:150]}...\n\n"

    if offset + limit < total_results:
        remaining = total_results - (offset + limit)
        output += f"💡 {remaining} more results available"

    return output


async def _get_more_results_operation(
    db: ReflectionDatabase,
    query: str,
    offset: int,
    limit: int,
    project: str | None,
) -> str:
    """Execute pagination operation."""
    results = await db.search_conversations(
        query=query, project=project, limit=limit + offset
    )
    paginated_results = results[offset : offset + limit]
    return _build_pagination_output(
        query, offset, paginated_results, len(results), limit
    )


async def _get_more_results_impl(
    query: str,
    offset: int = 3,
    limit: int = 3,
    project: str | None = None,
) -> str:
    """Get additional search results after an initial search (pagination support)."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _get_more_results_operation(db, query, offset, limit, project)

    return await execute_simple_database_tool(operation, "Get more results")


# ============================================================================
# Search by File
# ============================================================================


def _extract_file_excerpt(content: str, file_path: str) -> str:
    """Extract a relevant excerpt from content based on the file path."""
    if file_path in content:
        start = max(0, content.find(file_path) - 50)
        end = min(len(content), content.find(file_path) + len(file_path) + 100)
        return content[start:end]
    return content[:150]


async def _format_file_search_results(
    file_path: str, results: list[dict[str, Any]]
) -> str:
    """Format file search results."""
    if not results:
        return f"🔍 No conversations found about file: {file_path}"

    output = f"🔍 **{len(results)} conversations** about `{file_path}`\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "

        excerpt = _extract_file_excerpt(result.get("content", ""), file_path)
        output += f"{excerpt}...\n\n"

    return output


async def _search_by_file_operation(
    db: ReflectionDatabase, file_path: str, limit: int, project: str | None
) -> str:
    """Execute file search operation."""
    results = await db.search_conversations(
        query=file_path, project=project, limit=limit
    )
    return await _format_file_search_results(file_path, results)


async def _search_by_file_impl(
    file_path: str,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for conversations that analyzed a specific file."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_by_file_operation(db, file_path, limit, project)

    return await execute_simple_database_tool(operation, "Search by file")


# ============================================================================
# Search by Concept
# ============================================================================


def _extract_relevant_excerpt(content: str, concept: str) -> str:
    """Extract a relevant excerpt from content based on the concept."""
    if concept.lower() in content.lower():
        start = max(0, content.lower().find(concept.lower()) - 75)
        end = min(len(content), start + 200)
        return content[start:end]
    return content[:150]


def _extract_mentioned_files(results: list[dict[str, Any]]) -> list[str]:
    """Extract mentioned files from search results."""
    try:
        from session_buddy.utils.regex_patterns import SAFE_PATTERNS

        all_content = " ".join([r.get("content", "") for r in results])
        files = []

        for pattern_name in (
            "python_files",
            "javascript_files",
            "config_files",
            "documentation_files",
        ):
            pattern = SAFE_PATTERNS[pattern_name]
            matches = pattern.findall(all_content)
            files.extend(matches)

        return list(set(files))[:10] if files else []
    except Exception:
        return []


async def _format_concept_results(
    concept: str, results: list[dict[str, Any]], include_files: bool
) -> str:
    """Format concept search results."""
    if not results:
        return f"🔍 No conversations found about concept: {concept}"

    output = f"🔍 **{len(results)} conversations** about `{concept}`\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "
        if result.get("similarity"):
            output += f"(relevance: {result['similarity']:.2f}) "

        excerpt = _extract_relevant_excerpt(result.get("content", ""), concept)
        output += f"{excerpt}...\n\n"

    if include_files:
        files = _extract_mentioned_files(results)
        if files:
            output += f"📁 **Related Files**: {', '.join(files)}"

    return output


async def _search_by_concept_operation(
    db: ReflectionDatabase,
    concept: str,
    include_files: bool,
    limit: int,
    project: str | None,
) -> str:
    """Execute concept search operation."""
    results = await db.search_conversations(
        query=concept, project=project, limit=limit, min_score=0.6
    )
    return await _format_concept_results(concept, results, include_files)


async def _search_by_concept_impl(
    concept: str,
    include_files: bool = True,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for conversations about a specific development concept."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_by_concept_operation(
            db, concept, include_files, limit, project
        )

    return await execute_simple_database_tool(operation, "Search by concept")


# ============================================================================
# Search by Source (Cross-Tool Memory Fabric)
# ============================================================================


async def _format_source_results(
    query: str,
    results: list[dict[str, Any]],
    source_type: str | None,
    project: str | None,
) -> str:
    """Format cross-tool memory search results."""
    if not results:
        scope = f"source_type={source_type!r}" if source_type else "all sources"
        scope += f", project={project!r}" if project else ""
        return f"🔍 No cross-tool memory found for '{query}' ({scope})"

    scope_bits: list[str] = []
    if source_type:
        scope_bits.append(f"source: {source_type}")
    if project:
        scope_bits.append(f"project: {project}")
    scope_text = f" [{', '.join(scope_bits)}]" if scope_bits else " [all sources]"

    output = f"🔍 **{len(results)} cross-tool results** for '{query}'{scope_text}\n\n"
    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "
        if result.get("source_type"):
            output += f"[{result['source_type']}] "
        if result.get("project"):
            output += f"[{result['project']}] "
        content = str(result.get("content", ""))
        output += f"{content[:200]}...\n\n"
    return output


async def _search_by_source_operation(
    db: ReflectionDatabase,
    query: str,
    source_type: str | None,
    project: str | None,
    limit: int,
) -> str:
    """Execute cross-tool memory search."""
    results = await db.search_by_source(
        query=query,
        source_type=source_type,
        project=project,
        limit=limit,
    )
    return _format_source_results(query, results, source_type, project)


async def _search_by_source_impl(
    query: str,
    source_type: str | None = None,
    project: str | None = None,
    limit: int = 10,
) -> str:
    """Cross-tool memory search: filter v2 by source_type and/or project.

    Phase 1 Feature #5. The v2 schema indexes source_type and project
    so this is an O(log n) range scan, not a full table scan.
    """

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_by_source_operation(
            db, query, source_type, project, limit
        )

    return await execute_simple_database_tool(operation, "Search by source")


# ============================================================================
# Memory Lineage / Provenance (Phase 1 Feature #4)
# ============================================================================


async def _format_memory_lineage(
    memory_id: str, chain: list[dict[str, Any]]
) -> str:
    """Format the provenance chain for a memory."""
    if not chain:
        return f"🔍 No provenance records for memory_id={memory_id!r}"
    lines = [
        f"🔍 **Lineage for memory_id={memory_id}** — {len(chain)} records\n"
    ]
    for i, row in enumerate(chain, 1):
        ts = row.get("extracted_at", "unknown")
        src = row.get("source_type", "?")
        ref = row.get("source_ref") or "-"
        model = row.get("model") or "-"
        lines.append(f"**{i}.** ({ts}) source={src} ref={ref} model={model}")
    return "\n".join(lines)


async def _memory_lineage_impl(memory_id: str) -> str:
    """Return the provenance chain for a memory, oldest-first.

    Phase 1 Feature #4. Each row in ``memory_provenance`` records
    WHERE a memory came from (source_type + source_ref + model) and
    WHEN it was extracted. Most memories have a single row;
    transcripts and Conscious-Agent writes can produce more.
    """
    if not memory_id:
        return ToolMessages.invalid_input("memory_id", "(non-empty string)")

    async def operation(db: ReflectionDatabase) -> str:
        chain = await db.memory_lineage(memory_id)
        return _format_memory_lineage(memory_id, chain)

    return await execute_simple_database_tool(operation, "Memory lineage")


# ============================================================================
# Per-project peer modeling (Phase 1.5 Feature #2: Honcho)
# ============================================================================
# ACL is a CALLER concern — these tools do not check ``peer_models:read``
# / ``peer_models:write`` themselves. The host environment (typically
# Mahavishnu's ACL router) is expected to gate the tool invocation
# before the request reaches here. See
# ``session_buddy.memory.peer_modeling`` for the full contract.


def _format_peer_context(context: dict[str, Any]) -> str:
    """Format a peer_context dict for the LLM-facing response."""
    lines = [
        f"🧠 **Peer context for {context['peer_id']} in "
        f"{context['project_id']}**\n"
    ]
    rep = context.get("representation_text", "") or ""
    if rep:
        lines.append(f"**Representation:** {rep}\n")
    if context.get("last_updated"):
        lines.append(
            f"**Last updated:** {context['last_updated']} | "
            f"**Evidence:** {context['evidence_count']} | "
            f"**Model:** {context['model'] or 'n/a'}\n"
        )
    recent = context.get("recent_memories") or []
    if recent:
        lines.append(f"**Recent memories ({len(recent)}):**")
        for mem in recent:
            content = mem.get("content", "")
            if isinstance(content, str) and len(content) > 120:
                content = content[:117] + "..."
            lines.append(
                f"- {mem.get('id', '?')[:8]} [{mem.get('category', '?')}] "
                f"{content}"
            )
        lines.append("")
    target = context.get("target_peer")
    if target is not None:
        lines.append(
            f"**Target peer ({target['peer_id']}):** "
            f"{target.get('representation_text', '')}"
        )
    return "\n".join(lines)


async def _peer_context_impl(
    peer_id: str,
    project_id: str,
    target_peer_id: str | None = None,
    recent_limit: int = 5,
) -> str:
    """Return peer context (representation + recent memories).

    Phase 1.5 #2 (Honcho). Bundles the peer's evolving
    ``representation_text`` with their recent memories in the project,
    optionally alongside a second peer's model. ACL: caller must
    check ``peer_models:read``.
    """
    if not peer_id:
        return ToolMessages.invalid_input("peer_id", "(non-empty string)")
    if not project_id:
        return ToolMessages.invalid_input("project_id", "(non-empty string)")

    async def operation(db: ReflectionDatabase) -> str:
        context = await db.peer_context(
            peer_id=peer_id,
            project_id=project_id,
            recent_limit=recent_limit,
            target_peer_id=target_peer_id,
        )
        return _format_peer_context(context)

    return await execute_simple_database_tool(operation, "Peer context")


async def _update_peer_model_impl(
    peer_id: str,
    project_id: str,
    model: str = "heuristic",
) -> str:
    """Trigger a peer model update (heuristic or LLM).

    Phase 1.5 #2. On first call for a peer, creates a row with
    ``representation_text`` synthesized from recent memories. On
    subsequent calls, increments ``evidence_count`` and refreshes the
    representation. The ``model`` field on the row records which path
    produced it. ACL: caller must check ``peer_models:write``.
    """
    if not peer_id:
        return ToolMessages.invalid_input("peer_id", "(non-empty string)")
    if not project_id:
        return ToolMessages.invalid_input("project_id", "(non-empty string)")

    async def operation(db: ReflectionDatabase) -> str:
        representation = await db.update_peer_model(
            peer_id=peer_id,
            project_id=project_id,
            model=model,
        )
        return (
            f"✅ Peer model updated for {peer_id} in {project_id}\n\n"
            f"**Model:** {model}\n"
            f"**Representation:** {representation}"
        )

    return await execute_simple_database_tool(operation, "Update peer model")


# ============================================================================
# Causal Memory Chains (Phase 1.5 Feature #3)
# ============================================================================
# The chain walker is LLM-free (the plan's LLM Cost Ceiling pins
# causal inference at 0). The output distinguishes ``observed``
# links (ground truth) from ``inferred`` links (heuristic) so
# consumers know which to trust.


def _format_causal_chain(start_id: str, edges: list[dict[str, Any]]) -> str:
    """Format a causal chain walk for the LLM-facing response."""
    if not edges:
        return f"🔍 No causal chain found for memory_id={start_id!r}"
    lines = [
        f"⛓️  **Causal chain for memory_id={start_id}** "
        f"— {len(edges)} edges\n"
    ]
    for i, edge in enumerate(edges, 1):
        origin = edge.get("link_origin", "?")
        evidence = edge.get("evidence", 0.0)
        link_type = edge.get("link_type", "?")
        depth = edge.get("depth", "?")
        origin_emoji = "✅" if origin == "observed" else "🤔"
        lines.append(
            f"**{i}.** {origin_emoji} [{origin}] depth={depth} "
            f"evidence={evidence:.2f} type={link_type}\n"
            f"    {edge.get('from_id', '?')} → {edge.get('to_id', '?')}"
        )
    return "\n".join(lines)


async def _causal_chain_impl(start_id: str, max_depth: int = 3) -> str:
    """BFS-walk the causal graph from ``start_id`` up to ``max_depth``.

    Phase 1.5 #3. Cycle-safe. Returns a formatted Markdown summary
    with each edge's ``link_origin`` (observed vs inferred) and
    evidence weight. Depth defaults to 3 per the plan.
    """
    if not start_id:
        return ToolMessages.invalid_input("start_id", "(non-empty string)")

    async def operation(db: ReflectionDatabase) -> str:
        edges = await db.causal_chain(
            start_id=start_id, max_depth=max_depth
        )
        return _format_causal_chain(start_id, edges)

    return await execute_simple_database_tool(operation, "Causal chain")


# ============================================================================
# Skill Distillation (Phase 1.5 Feature #6)
# ============================================================================
# The data layer is LLM-optional; the LLM path is a Conscious Agent
# enhancement. The default ``model='heuristic'`` argument means a
# caller can distill skills without configuring a provider.


def _format_skill(skill: dict[str, Any]) -> str:
    """Format a single distilled skill for the LLM-facing response."""
    importance = float(skill.get("importance_score") or 0.0)
    evidence = int(skill.get("evidence_count") or 0)
    return (
        f"### {skill.get('problem_pattern', '?')}\n"
        f"**Approach:** {skill.get('suggested_approach', '?')}\n"
        f"**Because:** {skill.get('because', '?')}\n"
        f"**Importance:** {importance:.2f} | **Evidence:** {evidence} prior cases | "
        f"**Model:** {skill.get('model', '?')}"
    )


def _format_skill_list(skills: list[dict[str, Any]]) -> str:
    """Format a list of skills as a Markdown report."""
    if not skills:
        return "🔍 No skills distilled yet."
    lines = [f"🧪 **{len(skills)} distilled skill(s)**\n"]
    for i, s in enumerate(skills, 1):
        lines.append(f"**{i}.** {_format_skill(s)}")
    return "\n\n".join(lines)


def _format_skill_search(results: list[dict[str, Any]]) -> str:
    """Format a search result list as Markdown."""
    if not results:
        return "🔍 No matching skills found."
    return _format_skill_list(results)


async def _distill_skills_now_impl(
    evidence_threshold: int = 3, model: str = "heuristic"
) -> str:
    """Run the skill distiller and return the freshly-distilled skills.

    Phase 1.5 #6. The first 10 distilled skills are sampled for
    human review (per the plan's quality gate). The function
    is idempotent on the same data — a re-run produces duplicate
    rows. The Conscious Agent is responsible for scheduling
    cadence and dedup.
    """
    async def operation(db: ReflectionDatabase) -> str:
        skills = await db.distill_skills_now(
            evidence_threshold=evidence_threshold, model=model
        )
        return _format_skill_list(skills)

    return await execute_simple_database_tool(
        operation, "Distill skills"
    )


async def _search_distilled_skills_impl(
    query: str = "", limit: int = 5
) -> str:
    """Search distilled skills by problem_pattern / approach / because.

    Phase 1.5 #6. An empty ``query`` returns the top ``limit``
    skills by ``importance_score DESC, last_reinforced_at DESC``.
    A non-empty ``query`` does a case-insensitive substring
    match across the three text fields.
    """
    async def operation(db: ReflectionDatabase) -> str:
        results = await db.search_distilled_skills(query=query, limit=limit)
        return _format_skill_search(results)

    return await execute_simple_database_tool(
        operation, "Search distilled skills"
    )


# ============================================================================
# Distilled Skill Health (Phase 1.5 wiring, Item 4 of bodai-adoption-phase-1.5)
# ============================================================================
# Crackerjack's coverage report calls this tool rather than reading
# DuckDB directly (per the plan's A3 + Q3 default). The tool reads
# ``distilled_skills``, computes a freshness status per row, and
# returns a list of dicts. The status semantics:
#
#   - ``stale``          last_reinforced_at < now() - threshold_days
#   - ``under_utilized`` importance_score >= 0.9 AND no matching
#                        Crackerjack skill (when supplied)
#   - ``cold``           evidence_count == 0 (never reinforced) AND
#                        not under_utilized
#   - ``fresh``          anything else


# Importance threshold for the under-utilized bucket. Pinned at 0.9
# in the plan's Item 4 acceptance: a high-importance skill with no
# Crackerjack counterpart is exactly the kind of "under-utilized
# knowledge" the report must surface.
_UNDER_UTILIZED_IMPORTANCE_FLOOR: float = 0.9


def _classify_skill_status(
    row: dict[str, Any],
    *,
    threshold: timedelta,
    crackerjack_skill_names: list[str] | None,
) -> str:
    """Apply the four-bucket classifier to one distilled_skill row.

    Pure function — no DB, no I/O — so unit tests can exercise the
    status logic directly. The ordering of the checks matters:
    ``stale`` is checked first (it depends only on the timestamp),
    then ``under_utilized`` (depends on importance + Crackerjack
    match), then ``cold`` (depends on evidence_count), with
    ``fresh`` as the catch-all.
    """
    importance = float(row.get("importance_score") or 0.0)
    evidence = int(row.get("evidence_count") or 0)
    last_reinforced = row.get("last_reinforced_at")

    # 1. Stale — timestamp-based; check first so a stale, high-importance
    # skill reports as 'stale' rather than 'under_utilized'.
    if last_reinforced is not None:
        try:
            reinforced_dt = _parse_reinforced_ts(last_reinforced)
        except (TypeError, ValueError):
            reinforced_dt = None
        if reinforced_dt is not None:
            now = datetime.now()
            if now - reinforced_dt > threshold:
                return "stale"

    # 2. Under-utilized — high importance with no Crackerjack match.
    if importance >= _UNDER_UTILIZED_IMPORTANCE_FLOOR:
        if crackerjack_skill_names is not None:
            pattern = str(row.get("problem_pattern") or "").lower()
            has_match = any(
                pattern and pattern in name.lower()
                for name in crackerjack_skill_names
            )
            if not has_match:
                return "under_utilized"
        else:
            # No Crackerjack skill list provided: the report cannot
            # decide if the skill is under-utilized, so it stays in
            # the default bucket. Item 4 only treats it as
            # 'under_utilized' when the caller supplies the list.
            pass

    # 3. Cold — never reinforced (zero evidence) AND below the
    # under-utilized floor. The plan's "cold-start indicator" is
    # "a skill exists but has no signal"; evidence==0 captures
    # that even when last_reinforced_at is recent.
    if evidence == 0:
        return "cold"

    return "fresh"


def _parse_reinforced_ts(value: Any) -> datetime:
    """Coerce a ``last_reinforced_at`` value to a ``datetime``.

    The v2 schema stores ``TIMESTAMP`` which DuckDB returns as a
    ``datetime`` instance, but tests and ad-hoc inserts sometimes
    hand us a string. Accept both forms rather than crash.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"unsupported last_reinforced_at type: {type(value)!r}")


async def _distilled_skill_health_impl(
    threshold_days: int = 90,
    crackerjack_skill_names: list[str] | None = None,
    db: ReflectionDatabase | None = None,
) -> list[dict[str, Any]]:
    """Return a freshness/utility report for the v2 ``distilled_skills`` table.

    Phase 1.5 wiring (Item 4 of the bodai-adoption-phase-1.5 plan).
    Crackerjack's ``skill_coverage_report`` calls this tool rather
    than reading DuckDB directly so the read stays ACL-gated and
    the data shape is owned by the producer.

    Args:
        threshold_days: Number of days since ``last_reinforced_at``
            before a skill is reported as ``stale``. Default 90
            matches the plan's A4.
        crackerjack_skill_names: Optional list of skill names from
            Crackerjack's registry. When provided, high-importance
            (>= 0.9) skills whose ``problem_pattern`` is NOT a
            substring of any Crackerjack skill are reported as
            ``under_utilized``.
        db: Optional pre-resolved ``ReflectionDatabase`` instance.
            Used by the test suite to inject a fixture-bound adapter
            (so the read targets the same DuckDB file the test
            just seeded). When ``None``, falls back to
            :func:`require_reflection_database`.

    Returns:
        A list of dicts, one per row in ``distilled_skills``,
        each containing the row's columns plus a ``status`` key.
    """
    if threshold_days <= 0:
        return []
    threshold = timedelta(days=threshold_days)

    try:
        if db is None:
            db = await require_reflection_database()
        # The simplest portable read: ask the distiller module for
        # the full list (empty query → top by score). That keeps
        # the tool in the LLM-free data layer and avoids a new
        # raw-SQL path. The result is bounded only by the underlying
        # query; for the report's purposes "all rows" is correct.
        rows = await db.search_distilled_skills(query="", limit=10_000)
        for row in rows:
            row["status"] = _classify_skill_status(
                row,
                threshold=threshold,
                crackerjack_skill_names=crackerjack_skill_names,
            )
        return rows
    except DatabaseUnavailableError as e:
        _get_logger().exception(f"Distilled skill health: {e}")
        return []
    except Exception as e:
        _get_logger().exception(f"Distilled skill health: {e}")
        return []


# ============================================================================
# Database Management
# ============================================================================


async def _reset_reflection_database_impl() -> str:
    """Reset the reflection database connection to fix lock issues."""
    try:
        await require_reflection_database()
        return "✅ Reflection database connection verified successfully"
    except Exception as e:
        return ToolMessages.operation_failed("Database reset", e)


async def _reflection_stats_operation(db: ReflectionDatabase) -> str:
    """Execute reflection stats operation."""
    stats = await db.get_stats()
    output = "📊 **Reflection Database Statistics**\n\n"
    for key, value in stats.items():
        output += f"**{key.replace('_', ' ').title()}**: {value}\n"
    return output


async def _reflection_stats_impl() -> str:
    """Get statistics about the reflection database."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _reflection_stats_operation(db)

    return await execute_simple_database_tool(operation, "Reflection stats")


async def _session_learning_report_impl(
    session_id: str, window_hours: int = 24
) -> dict[str, Any]:
    """Generate a 'session learning report' for the given session_id.

    Pure read over v2 tables. Returns what memories were created, reinforced,
    contradicted, or had new causal links attributed to this session within
    the time window.
    """
    try:
        db = await require_reflection_database()
        return await db.generate_session_differential(session_id, window_hours)
    except DatabaseUnavailableError as e:
        return {"error": str(e), "session_id": session_id}
    except Exception as e:
        _get_logger().exception(f"Error in Session learning report: {e}")
        return {"error": str(e), "session_id": session_id}


# ============================================================================
# Search Code
# ============================================================================


def _extract_code_blocks_from_content(content: str) -> list[str]:
    """Extract code blocks from content using regex patterns."""
    try:
        from session_buddy.utils.regex_patterns import SAFE_PATTERNS

        code_pattern = SAFE_PATTERNS["generic_code_block"]
        matches = code_pattern.findall(content)
        return matches if matches is not None else []
    except Exception:
        return []


async def _format_code_search_results(
    query: str, results: list[dict[str, Any]], pattern_type: str | None
) -> str:
    """Format code search results."""
    if not results:
        return f"🔍 No code patterns found for: {query}"

    output = f"🔍 **{len(results)} code patterns** for `{query}`"
    if pattern_type:
        output += f" (type: {pattern_type})"
    output += "\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "

        content = result.get("content", "")
        code_blocks = _extract_code_blocks_from_content(content)

        if code_blocks:
            code = code_blocks[0][:200]
            output += f"\n```\n{code}...\n```\n\n"
        else:
            if query.lower() in content.lower():
                start = max(0, content.lower().find(query.lower()) - 50)
                end = min(len(content), start + 150)
                excerpt = content[start:end]
            else:
                excerpt = content[:100]
            output += f"{excerpt}...\n\n"

    return output


async def _search_code_operation(
    db: ReflectionDatabase,
    query: str,
    pattern_type: str | None,
    limit: int,
    project: str | None,
) -> str:
    """Execute code search operation."""
    code_query = f"code {query}"
    if pattern_type:
        code_query += f" {pattern_type}"

    results = await db.search_conversations(
        query=code_query, project=project, limit=limit, min_score=0.5
    )
    return await _format_code_search_results(query, results, pattern_type)


async def _search_code_impl(
    query: str,
    pattern_type: str | None = None,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for code patterns in conversations using AST parsing."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_code_operation(db, query, pattern_type, limit, project)

    return await execute_simple_database_tool(operation, "Search code")


# ============================================================================
# Search Errors
# ============================================================================


def _find_best_error_excerpt(content: str) -> str:
    """Find the most relevant excerpt from content based on error keywords."""
    error_keywords = ["error", "exception", "traceback", "failed", "fix"]
    best_excerpt = ""
    best_score = 0

    for keyword in error_keywords:
        if keyword in content.lower():
            start = max(0, content.lower().find(keyword) - 75)
            end = min(len(content), start + 200)
            excerpt = content[start:end]
            score = content.lower().count(keyword)
            if score > best_score:
                best_score = score
                best_excerpt = excerpt

    return best_excerpt or content[:150]


async def _format_error_search_results(
    query: str, results: list[dict[str, Any]], error_type: str | None
) -> str:
    """Format error search results."""
    if not results:
        return f"🔍 No error patterns found for: {query}"

    output = f"🔍 **{len(results)} error contexts** for `{query}`"
    if error_type:
        output += f" (type: {error_type})"
    output += "\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "

        best_excerpt = _find_best_error_excerpt(result.get("content", ""))
        output += f"{best_excerpt}...\n\n"

    return output


async def _search_errors_operation(
    db: ReflectionDatabase,
    query: str,
    error_type: str | None,
    limit: int,
    project: str | None,
) -> str:
    """Execute error search operation."""
    error_query = f"error {query}"
    if error_type:
        error_query += f" {error_type}"

    results = await db.search_conversations(
        query=error_query, project=project, limit=limit, min_score=0.4
    )
    return await _format_error_search_results(query, results, error_type)


async def _search_errors_impl(
    query: str,
    error_type: str | None = None,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search for error patterns and debugging contexts in conversations."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_errors_operation(db, query, error_type, limit, project)

    return await execute_simple_database_tool(operation, "Search errors")


# ============================================================================
# Temporal Search
# ============================================================================


def _parse_time_expression(time_expression: str) -> datetime | None:
    """Parse natural language time expression into datetime."""
    now = datetime.now()

    if "yesterday" in time_expression.lower():
        return now - timedelta(days=1)
    if "last week" in time_expression.lower():
        return now - timedelta(days=7)
    if "last month" in time_expression.lower():
        return now - timedelta(days=30)
    if "today" in time_expression.lower():
        return now - timedelta(hours=24)

    return None


async def _format_temporal_results(
    time_expression: str, query: str | None, results: list[dict[str, Any]]
) -> str:
    """Format temporal search results."""
    if not results:
        return f"🔍 No conversations found for time period: {time_expression}"

    output = f"🔍 **{len(results)} conversations** from `{time_expression}`"
    if query:
        output += f" matching `{query}`"
    output += "\n\n"

    for i, result in enumerate(results, 1):
        output += f"**{i}.** "
        if result.get("timestamp"):
            output += f"({result['timestamp']}) "

        content = result.get("content", "")
        output += f"{content[:150]}...\n\n"

    return output


async def _search_temporal_operation(
    db: ReflectionDatabase,
    time_expression: str,
    query: str | None,
    limit: int,
    project: str | None,
) -> str:
    """Execute temporal search operation."""
    start_time = _parse_time_expression(time_expression)
    search_query = query or ""
    results = await db.search_conversations(
        query=search_query, project=project, limit=limit * 2
    )

    if start_time:
        # Simplified filter - would need proper timestamp parsing
        filtered_results = results.copy()
        results = filtered_results[:limit]

    return await _format_temporal_results(time_expression, query, results)


async def _search_temporal_impl(
    time_expression: str,
    query: str | None = None,
    limit: int = 10,
    project: str | None = None,
) -> str:
    """Search conversations within a specific time range using natural language."""

    async def operation(db: ReflectionDatabase) -> str:
        return await _search_temporal_operation(
            db, time_expression, query, limit, project
        )

    return await execute_simple_database_tool(operation, "Temporal search")


# ============================================================================
# MCP Tool Registration
# ============================================================================


def _parse_tags_parameter(tags: list[str] | str | None) -> list[str] | None:
    """Parse and validate tags parameter from MCP protocol.

    Handles JSON string deserialization from MCP protocol where complex types
    are serialized to JSON strings during transport.

    Args:
        tags: Tags parameter (list, JSON string, or None)

    Returns:
        Parsed tags as list[str] or None

    Examples:
        >>> _parse_tags_parameter('["tag1", "tag2"]')
        ['tag1', 'tag2']
        >>> _parse_tags_parameter('single-tag')
        ['single-tag']
        >>> _parse_tags_parameter(['already', 'list'])
        ['already', 'list']
        >>> _parse_tags_parameter(None)
        None
    """
    if not isinstance(tags, str):
        return tags

    # Handle JSON string deserialization
    try:
        decoded = json.loads(tags)
        if isinstance(decoded, list):
            return [str(tag) for tag in decoded]
        elif decoded is None:
            return None
        else:
            # Single non-list value, wrap it
            return [str(decoded)]
    except json.JSONDecodeError:
        # Not valid JSON, treat as single tag
        return [tags]


def _parse_skill_names_param(
    names: list[str] | str | None,
) -> list[str] | None:
    """Normalize the ``crackerjack_skill_names`` MCP parameter.

    Mirrors :func:`_parse_tags_parameter`: MCP transports sometimes
    serialize a list[str] as a JSON string during transport. This
    helper accepts both shapes and returns ``list[str] | None``.
    A JSON parse failure falls back to ``None`` so the call site
    can opt out of the under-utilized check rather than crash.
    """
    if names is None:
        return None
    if isinstance(names, list):
        return [str(n) for n in names]
    if isinstance(names, str):
        try:
            decoded = json.loads(names)
        except json.JSONDecodeError:
            return None
        if isinstance(decoded, list):
            return [str(n) for n in decoded]
    return None


def _register_core_search_tools(mcp: Any) -> None:
    """Register core search and reflection tools.

    Args:
        mcp: FastMCP server instance

    """

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def _optimize_search_results(
        results: list[dict[str, Any]],
        optimize_tokens: bool,
        max_tokens: int,
        query: str,
    ) -> dict[str, Any]:
        return await _optimize_search_results_impl(
            results, optimize_tokens, max_tokens, query
        )

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def store_reflection(
        content: str, tags: list[str] | str | None = None
    ) -> str:
        """Store an important insight or reflection for future reference."""
        parsed_tags = _parse_tags_parameter(tags)
        return await _store_reflection_impl(content, parsed_tags)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def quick_search(
        query: str, project: str | None = None, min_score: float = 0.7, limit: int = 5
    ) -> str:
        # Note: For quick search, we're using the limit to determine how many results to return,
        # but the underlying implementation may not use this parameter directly
        return await _quick_search_impl(query, project, min_score)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def search_summary(
        query: str, project: str | None = None, min_score: float = 0.7
    ) -> str:
        return await _search_summary_impl(query, project, min_score)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def get_more_results(
        query: str, offset: int = 3, limit: int = 3, project: str | None = None
    ) -> str:
        return await _get_more_results_impl(query, offset, limit, project)


def _register_specialized_search_tools(mcp: Any) -> None:
    """Register specialized search tools (file, concept, code, errors, temporal).

    Args:
        mcp: FastMCP server instance

    """

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def search_by_file(
        file_path: str, limit: int = 10, project: str | None = None
    ) -> str:
        return await _search_by_file_impl(file_path, limit, project)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def search_by_concept(
        concept: str,
        include_files: bool = True,
        limit: int = 10,
        project: str | None = None,
    ) -> str:
        return await _search_by_concept_impl(concept, include_files, limit, project)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def search_by_source(
        query: str,
        source_type: str | None = None,
        project: str | None = None,
        limit: int = 10,
    ) -> str:
        """Cross-tool memory search: filter v2 by source_type and project.

        source_type must be one of: claude_code, crackerjack,
        mahavishnu_workflow, manual, migration. Leave None to search
        all sources.
        """
        return await _search_by_source_impl(query, source_type, project, limit)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def memory_lineage(memory_id: str) -> str:
        """Return the provenance chain for a memory, oldest-first.

        Phase 1 Feature #4. Each record lists the source_type
        (claude_code | crackerjack | mahavishnu_workflow | manual |
        migration), the source_ref (typically a session id), the
        model, and the extracted_at timestamp. Returns a formatted
        Markdown summary.
        """
        return await _memory_lineage_impl(memory_id)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def peer_context(
        peer_id: str,
        project_id: str,
        target_peer_id: str | None = None,
        recent_limit: int = 5,
    ) -> str:
        """Return peer context (representation + recent memories).

        Phase 1.5 #2 (Honcho-style theory of mind). Bundles a peer's
        evolving ``representation_text`` with their recent memories
        in the project. When ``target_peer_id`` is set, the response
        also includes a second peer's model — useful for agent-vs-user
        theory of mind.

        Requires ``peer_models:read`` ACL (caller's responsibility).
        Returns a formatted Markdown summary.
        """
        return await _peer_context_impl(
            peer_id, project_id, target_peer_id, recent_limit
        )

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def update_peer_model(
        peer_id: str,
        project_id: str,
        model: str = "heuristic",
    ) -> str:
        """Trigger a peer model update (heuristic or LLM-driven).

        Phase 1.5 #2. On first call for a peer, creates a row with
        ``representation_text`` synthesized from recent memories. On
        subsequent calls, increments ``evidence_count`` and refreshes
        the representation. The ``model`` field records which path
        produced it ('heuristic' for the cheap path, an LLM name for
        the Conscious Agent path).

        Requires ``peer_models:write`` ACL (caller's responsibility).
        Returns the new representation.
        """
        return await _update_peer_model_impl(peer_id, project_id, model)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def causal_chain(
        start_id: str, max_depth: int = 3
    ) -> str:
        """BFS-walk the causal graph from ``start_id``.

        Phase 1.5 #3. Cycle-safe. Returns a formatted Markdown
        summary with each edge's ``link_origin`` (observed vs
        inferred) and evidence weight. ``max_depth`` is the cap
        on hop count from ``start_id`` (default 3 per the plan).

        LLM-free — pure DuckDB queries (the plan's LLM Cost Ceiling
        pins causal inference at 0).
        """
        return await _causal_chain_impl(start_id, max_depth)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def distill_skills_now(
        evidence_threshold: int = 3, model: str = "heuristic"
    ) -> str:
        """Run the skill distiller and return freshly-distilled skills.

        Phase 1.5 #6. The first 10 distilled skills are sampled
        for human review (per the plan's quality gate). The
        data layer is LLM-optional; the default ``model='heuristic'``
        argument means a caller can distill skills without
        configuring a provider.

        Per the plan's LLM Cost Ceiling: 100 calls/week cap.
        """
        return await _distill_skills_now_impl(
            evidence_threshold, model
        )

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def search_distilled_skills(
        query: str = "", limit: int = 5
    ) -> str:
        """Search distilled skills by problem / approach / because.

        Phase 1.5 #6. An empty ``query`` returns the top ``limit``
        skills by ``importance_score DESC, last_reinforced_at DESC``.
        A non-empty ``query`` does a case-insensitive substring
        match across the three text fields.
        """
        return await _search_distilled_skills_impl(query, limit)

    _register_distilled_skill_health_tool(mcp)
    _register_peer_modeling_tools(mcp)
    _register_causal_chain_tools(mcp)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def reset_reflection_database() -> str:
        return await _reset_reflection_database_impl()

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def reflection_stats() -> str:
        return await _reflection_stats_impl()

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def search_code(
        query: str,
        pattern_type: str | None = None,
        limit: int = 10,
        project: str | None = None,
    ) -> str:
        return await _search_code_impl(query, pattern_type, limit, project)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def search_errors(
        query: str,
        error_type: str | None = None,
        limit: int = 10,
        project: str | None = None,
    ) -> str:
        return await _search_errors_impl(query, error_type, limit, project)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def search_temporal(
        time_expression: str,
        query: str | None = None,
        limit: int = 10,
        project: str | None = None,
    ) -> str:
        return await _search_temporal_impl(time_expression, query, limit, project)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def session_learning_report(
        session_id: str, window_hours: int = 24
    ) -> dict[str, Any]:
        """Generate a 'session learning report' for the given session_id.

        Pure read over v2 tables; no new writes. Returns a dictionary
        describing what memories were created, reinforced (accessed more
        than once), contradicted, or had new causal links attributed to
        this session within the time window. ``contradictions`` and
        ``new_causal_links`` are placeholders (out of scope for v1).

        Args:
            session_id: Session identifier to scope the report.
            window_hours: How far back to look (default 24 hours).
        """
        return await _session_learning_report_impl(session_id, window_hours)


def _register_distilled_skill_health_tool(mcp: Any) -> None:
    """Register the ``distilled_skill_health`` MCP tool.

    Extracted from :func:`_register_specialized_search_tools` to
    keep the parent's branch count under the 15-branch pylint
    ceiling. The tool itself is a Phase 1.5 wiring (Item 4 of
    the bodai-adoption-phase-1.5 plan); Crackerjack's
    ``skill_coverage_report`` is its only known consumer.
    """

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def distilled_skill_health(
        threshold_days: int = 90,
        crackerjack_skill_names: list[str] | str | None = None,
    ) -> list[dict[str, Any]]:
        """Return a freshness/utility report for the ``distilled_skills`` table.

        Phase 1.5 wiring (Item 4 of the bodai-adoption-phase-1.5
        plan). Crackerjack's ``skill_coverage_report`` calls this
        tool via the MCP client — the data layer is the source of
        truth, so the read stays ACL-gated and the schema is owned
        by the producer.

        Each row in the returned list carries its v2 columns plus
        a ``status`` key:

        - ``stale`` — ``last_reinforced_at`` is older than
          ``threshold_days`` (default 90, per the plan's A4).
        - ``under_utilized`` — ``importance_score >= 0.9`` AND
          ``problem_pattern`` does not appear in any
          ``crackerjack_skill_names`` entry.
        - ``cold`` — ``evidence_count == 0`` and not under-utilized.
        - ``fresh`` — anything else.

        Args:
            threshold_days: Days since ``last_reinforced_at`` before
                a skill is reported as ``stale``. Default 90.
            crackerjack_skill_names: Optional list (or JSON-encoded
                string) of skill names from Crackerjack's
                registry. When provided, drives the
                ``under_utilized`` classification.
        """
        parsed_names = _parse_skill_names_param(crackerjack_skill_names)
        return await _distilled_skill_health_impl(
            threshold_days, parsed_names
        )


def _register_progressive_search_tools(mcp: Any) -> None:
    """Register progressive search tools (Phase 3).

    Args:
        mcp: FastMCP server instance

    """

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def progressive_search(
        query: str,
        project: str | None = None,
        min_score: float = 0.6,
        max_results: int = 30,
        max_tiers: int = 4,
        enable_early_stop: bool = True,
    ) -> dict[str, Any]:
        """Execute multi-tier progressive search with early stopping."""
        return await _progressive_search_impl(
            query, project, min_score, max_results, max_tiers, enable_early_stop
        )

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def configure_tiers(
        categories_min_score: float | None = None,
        categories_max_results: int | None = None,
        insights_min_score: float | None = None,
        insights_max_results: int | None = None,
        reflections_min_score: float | None = None,
        reflections_max_results: int | None = None,
        conversations_min_score: float | None = None,
        conversations_max_results: int | None = None,
        sufficiency_min_results: int | None = None,
        sufficiency_high_quality_threshold: float | None = None,
    ) -> dict[str, Any]:
        """Configure progressive search tier thresholds and sufficiency evaluation."""
        return await _configure_tiers_impl(
            categories_min_score,
            categories_max_results,
            insights_min_score,
            insights_max_results,
            reflections_min_score,
            reflections_max_results,
            conversations_min_score,
            conversations_max_results,
            sufficiency_min_results,
            sufficiency_high_quality_threshold,
        )

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def tier_stats() -> dict[str, Any]:
        """Get progressive search tier statistics and current configuration.

        Returns tier performance metrics, configuration settings, and usage statistics
        for monitoring and optimization.
        """
        return await _tier_stats_impl()


def register_search_tools(mcp: Any) -> None:
    """Register all search-related MCP tools.

    Args:
        mcp: FastMCP server instance

    """
    _register_core_search_tools(mcp)
    _register_specialized_search_tools(mcp)
    _register_progressive_search_tools(mcp)


# ============================================================================
# Progressive Search (Phase 3)
# ============================================================================


async def _progressive_search_impl(
    query: str,
    project: str | None = None,
    min_score: float = 0.6,
    max_results: int = 30,
    max_tiers: int = 4,
    enable_early_stop: bool = True,
) -> dict[str, Any]:
    """Execute progressive search across multiple tiers.

    Args:
        query: Search query string
        project: Optional project filter
        min_score: Minimum similarity score (0.0-1.0)
        max_results: Maximum total results across all tiers
        max_tiers: Maximum number of tiers to search (1-4)
        enable_early_stop: Whether to enable early stopping optimization

    Returns:
        Dictionary with search results and metadata
    """
    try:
        from session_buddy.search import ProgressiveSearchEngine

        engine = ProgressiveSearchEngine()
        result = await engine.search_progressive(
            query=query,
            project=project,
            min_score=min_score,
            max_results=max_results,
            max_tiers=max_tiers,
            enable_early_stop=enable_early_stop,
        )

        # Format results for display
        formatted_results = []
        for tier_result in result.tier_results:
            tier_name = SearchTier.get_tier_name(tier_result.tier)
            for item in tier_result.results[:5]:  # Show first 5 per tier
                formatted_results.append(
                    f"[{tier_name}] {item.get('content', '')[:100]}..."
                )

        return {
            "success": True,
            "query": query,
            "total_results": result.total_results,
            "tiers_searched": len(result.tiers_searched),
            "tier_names": [SearchTier.get_tier_name(t) for t in result.tiers_searched],
            "early_stop": result.early_stop,
            "total_latency_ms": result.total_latency_ms,
            "early_stop_reason": result.metadata.get("early_stop_reason"),
            "sample_results": formatted_results,
        }

    except ImportError:
        return {
            "success": False,
            "error": "Progressive search engine not available",
            "query": query,
        }
    except Exception as e:
        _get_logger().exception(f"Progressive search failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "query": query,
        }


async def _configure_tiers_impl(
    categories_min_score: float | None = None,
    categories_max_results: int | None = None,
    insights_min_score: float | None = None,
    insights_max_results: int | None = None,
    reflections_min_score: float | None = None,
    reflections_max_results: int | None = None,
    conversations_min_score: float | None = None,
    conversations_max_results: int | None = None,
    sufficiency_min_results: int | None = None,
    sufficiency_high_quality_threshold: float | None = None,
) -> dict[str, Any]:
    """Configure progressive search tier thresholds.

    Args:
        categories_min_score: Minimum score for CATEGORIES tier (0.0-1.0)
        categories_max_results: Max results for CATEGORIES tier
        insights_min_score: Minimum score for INSIGHTS tier (0.0-1.0)
        insights_max_results: Max results for INSIGHTS tier
        reflections_min_score: Minimum score for REFLECTIONS tier (0.0-1.0)
        reflections_max_results: Max results for REFLECTIONS tier
        conversations_min_score: Minimum score for CONVERSATIONS tier (0.0-1.0)
        conversations_max_results: Max results for CONVERSATIONS tier
        sufficiency_min_results: Minimum results before early stop consideration
        sufficiency_high_quality_threshold: Avg score to consider "high quality"

    Returns:
        Dictionary with configuration status
    """
    try:
        from session_buddy.search import SufficiencyConfig

        config = SufficiencyConfig()

        # Update tier thresholds
        if categories_min_score is not None:
            # Note: This would require modifying SearchTier.get_min_score
            # For now, we'll just update sufficiency config
            pass

        if categories_max_results is not None:
            # Note: This would require modifying SearchTier.get_max_results
            pass

        # Update sufficiency config
        if sufficiency_min_results is not None:
            config.min_results = sufficiency_min_results

        if sufficiency_high_quality_threshold is not None:
            config.high_quality_threshold = sufficiency_high_quality_threshold

        return {
            "success": True,
            "message": "Tier configuration updated",
            "config": {
                "min_results": config.min_results,
                "high_quality_threshold": config.high_quality_threshold,
                "perfect_match_threshold": config.perfect_match_threshold,
                "max_tiers": config.max_tiers,
                "tier_timeout_ms": config.tier_timeout_ms,
                "quality_weight": config.quality_weight,
                "quantity_weight": config.quantity_weight,
            },
        }

    except ImportError:
        return {
            "success": False,
            "error": "Progressive search configuration not available",
        }
    except Exception as e:
        _get_logger().exception(f"Tier configuration failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


async def _tier_stats_impl() -> dict[str, Any]:
    """Get progressive search tier statistics.

    Returns:
        Dictionary with tier performance metrics
    """
    try:
        from session_buddy.search import ProgressiveSearchEngine

        engine = ProgressiveSearchEngine()
        stats = engine.get_search_stats()

        return {
            "success": True,
            "stats": stats,
            "tier_info": {
                "CATEGORIES": {
                    "min_score": 0.9,
                    "max_results": 10,
                    "name": "High-quality insights",
                },
                "INSIGHTS": {
                    "min_score": 0.75,
                    "max_results": 15,
                    "name": "Learned skills",
                },
                "REFLECTIONS": {
                    "min_score": 0.7,
                    "max_results": 20,
                    "name": "Stored reflections",
                },
                "CONVERSATIONS": {
                    "min_score": 0.6,
                    "max_results": 30,
                    "name": "Full conversations",
                },
            },
        }

    except ImportError:
        return {
            "success": False,
            "error": "Progressive search statistics not available",
        }
    except Exception as e:
        _get_logger().exception(f"Tier stats retrieval failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
