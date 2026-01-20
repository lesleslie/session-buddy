# MemU-Inspired Features Implementation Plan

> **Source Analysis**: [NevaMind-AI/memU](https://github.com/NevaMind-AI/memU)
> **Created**: January 19, 2026
> **Status**: Planning Phase

## Executive Summary

This document outlines the implementation plan for three key features inspired by the MemU agentic memory framework that would enhance session-buddy's memory and retrieval capabilities:

1. **LLM-Based Query Rewriting** - Context-aware query enhancement using conversation history
2. **Progressive Hierarchical Search** - Multi-tier search with early stopping
3. **Self-Evolving Category Structure** - Dynamic subcategory generation via clustering

These features maintain session-buddy's core principles:
- **Privacy-first**: Local processing where possible, optional LLM enhancement
- **Graceful degradation**: Features work without LLM, just with reduced capability
- **Backward compatibility**: Existing APIs unchanged, new features are additive

---

## Feature 1: LLM-Based Query Rewriting

### Overview

Enable conversational memory queries like "What did I say about that?" by automatically expanding ambiguous queries using recent conversation context.

### Current State

```python
# Current: Direct embedding search
query_embedding = await self._generate_embedding(query)
results = cosine_similarity_search(query_embedding)
```

### Target State

```python
# Enhanced: Query rewriting before embedding
expanded_query = await query_rewriter.expand(
    query="What did he mention about that?",
    conversation_context=recent_messages
)
# Returns: "What did John mention about the database migration issue?"
query_embedding = await self._generate_embedding(expanded_query)
results = cosine_similarity_search(query_embedding)
```

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Query Processing Pipeline                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Query ──► Ambiguity Detection ──► LLM Rewrite ──► Search  │
│       │              │                      │              │     │
│       │              ▼                      ▼              │     │
│       │        Skip if clear          Expand pronouns      │     │
│       │        (fast path)            Resolve "that"       │     │
│       │                               Add context          │     │
│       │                                    │               │     │
│       └────────────────────────────────────┴───────────────┘     │
│                              │                                   │
│                              ▼                                   │
│                    Embedding Generation                          │
│                              │                                   │
│                              ▼                                   │
│                    Vector Similarity Search                      │
│                              │                                   │
│                              ▼                                   │
│                    Results + Rewrite Metadata                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Details

#### File: `session_buddy/memory/query_rewriter.py`

```python
"""Context-aware query rewriting for conversational memory search.

Expands ambiguous queries using recent conversation context to resolve
pronouns, demonstratives, and implicit references.
"""

from __future__ import annotations

import re
import typing as t
from dataclasses import dataclass, field
from datetime import UTC, datetime

if t.TYPE_CHECKING:
    from session_buddy.tools.llm_tools import LLMProvider


@dataclass
class QueryRewriteResult:
    """Result of query rewriting operation."""

    original_query: str
    expanded_query: str
    was_rewritten: bool
    confidence: float  # 0.0-1.0 confidence in the rewrite
    resolved_references: list[str] = field(default_factory=list)
    context_used: int = 0  # Number of context messages used
    rewrite_reason: str | None = None
    latency_ms: float = 0.0


class AmbiguityDetector:
    """Detect whether a query contains ambiguous references."""

    # Pronouns that might refer to people or things
    PRONOUNS = {
        "he", "she", "they", "it", "him", "her", "them",
        "his", "hers", "theirs", "its"
    }

    # Demonstratives that need context
    DEMONSTRATIVES = {
        "this", "that", "these", "those", "here", "there"
    }

    # Temporal references needing context
    TEMPORAL_REFS = {
        "earlier", "before", "previously", "last time",
        "yesterday", "recently", "just now", "again"
    }

    # Implicit references
    IMPLICIT_REFS = {
        "the same", "similar", "like before", "as usual",
        "the other", "another one", "the issue", "the problem",
        "the error", "the bug", "the feature"
    }

    def detect(self, query: str) -> tuple[bool, list[str]]:
        """Detect ambiguous references in query.

        Args:
            query: The user's search query

        Returns:
            Tuple of (is_ambiguous, list of ambiguous tokens found)
        """
        query_lower = query.lower()
        words = set(re.findall(r'\b\w+\b', query_lower))

        ambiguous_tokens = []

        # Check pronouns
        pronoun_matches = words & self.PRONOUNS
        ambiguous_tokens.extend(pronoun_matches)

        # Check demonstratives
        demo_matches = words & self.DEMONSTRATIVES
        ambiguous_tokens.extend(demo_matches)

        # Check temporal references (phrase matching)
        for ref in self.TEMPORAL_REFS:
            if ref in query_lower:
                ambiguous_tokens.append(ref)

        # Check implicit references (phrase matching)
        for ref in self.IMPLICIT_REFS:
            if ref in query_lower:
                ambiguous_tokens.append(ref)

        return len(ambiguous_tokens) > 0, ambiguous_tokens


class QueryRewriter:
    """Rewrites ambiguous queries using conversation context.

    Uses a fast LLM (Haiku recommended) to expand queries that contain
    pronouns, demonstratives, or other ambiguous references.

    Example:
        >>> rewriter = QueryRewriter(llm_provider)
        >>> result = await rewriter.rewrite(
        ...     query="What did he say about that?",
        ...     context=[
        ...         {"role": "user", "content": "Ask John about the migration"},
        ...         {"role": "assistant", "content": "John mentioned the DB migration..."}
        ...     ]
        ... )
        >>> print(result.expanded_query)
        "What did John say about the database migration?"
    """

    REWRITE_PROMPT = '''You are a query expansion assistant. Given a search query and recent conversation context, expand any ambiguous references (pronouns, "that", "this", etc.) into explicit terms.

RULES:
1. Only expand ambiguous references - keep everything else unchanged
2. Use ONLY information from the provided context
3. If you can't resolve a reference, keep the original term
4. Output ONLY the expanded query, nothing else
5. Maintain the original query intent and structure

CONTEXT (most recent first):
{context}

ORIGINAL QUERY: {query}

AMBIGUOUS TOKENS DETECTED: {tokens}

EXPANDED QUERY:'''

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        max_context_messages: int = 10,
        confidence_threshold: float = 0.7,
        enable_fallback: bool = True,
    ) -> None:
        """Initialize query rewriter.

        Args:
            llm_provider: LLM provider for rewriting (optional)
            max_context_messages: Max messages to include in context
            confidence_threshold: Min confidence to use rewritten query
            enable_fallback: Whether to fall back to original on errors
        """
        self.llm_provider = llm_provider
        self.max_context_messages = max_context_messages
        self.confidence_threshold = confidence_threshold
        self.enable_fallback = enable_fallback
        self.detector = AmbiguityDetector()

    async def rewrite(
        self,
        query: str,
        context: list[dict[str, str]] | None = None,
        force_rewrite: bool = False,
    ) -> QueryRewriteResult:
        """Rewrite query to expand ambiguous references.

        Args:
            query: Original search query
            context: Recent conversation messages [{"role": "...", "content": "..."}]
            force_rewrite: Force LLM rewrite even if no ambiguity detected

        Returns:
            QueryRewriteResult with expanded query and metadata
        """
        start_time = datetime.now(UTC)

        # Fast path: no context provided
        if not context:
            return QueryRewriteResult(
                original_query=query,
                expanded_query=query,
                was_rewritten=False,
                confidence=1.0,
                rewrite_reason="No context provided",
            )

        # Detect ambiguity
        is_ambiguous, tokens = self.detector.detect(query)

        # Fast path: query is clear
        if not is_ambiguous and not force_rewrite:
            return QueryRewriteResult(
                original_query=query,
                expanded_query=query,
                was_rewritten=False,
                confidence=1.0,
                rewrite_reason="Query is unambiguous",
            )

        # No LLM provider - return original with low confidence
        if not self.llm_provider:
            return QueryRewriteResult(
                original_query=query,
                expanded_query=query,
                was_rewritten=False,
                confidence=0.5,
                resolved_references=[],
                rewrite_reason="No LLM provider configured",
            )

        # Prepare context string
        context_str = self._format_context(context)

        # Call LLM for rewriting
        try:
            expanded = await self._call_llm(query, context_str, tokens)
            latency = (datetime.now(UTC) - start_time).total_seconds() * 1000

            # Validate rewrite
            confidence = self._calculate_confidence(query, expanded, tokens)

            if confidence < self.confidence_threshold:
                return QueryRewriteResult(
                    original_query=query,
                    expanded_query=query,
                    was_rewritten=False,
                    confidence=confidence,
                    rewrite_reason=f"Low confidence rewrite ({confidence:.2f})",
                    latency_ms=latency,
                )

            return QueryRewriteResult(
                original_query=query,
                expanded_query=expanded,
                was_rewritten=True,
                confidence=confidence,
                resolved_references=tokens,
                context_used=min(len(context), self.max_context_messages),
                rewrite_reason="Successfully expanded references",
                latency_ms=latency,
            )

        except Exception as e:
            if self.enable_fallback:
                return QueryRewriteResult(
                    original_query=query,
                    expanded_query=query,
                    was_rewritten=False,
                    confidence=0.5,
                    rewrite_reason=f"LLM error, using original: {e}",
                )
            raise

    def _format_context(self, context: list[dict[str, str]]) -> str:
        """Format conversation context for prompt."""
        recent = context[-self.max_context_messages:]
        lines = []
        for msg in reversed(recent):  # Most recent first
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")[:500]  # Truncate long messages
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

    async def _call_llm(
        self,
        query: str,
        context_str: str,
        tokens: list[str]
    ) -> str:
        """Call LLM to rewrite query."""
        prompt = self.REWRITE_PROMPT.format(
            context=context_str,
            query=query,
            tokens=", ".join(tokens) if tokens else "none detected",
        )

        # Use fast model (Haiku) for low latency
        response = await self.llm_provider.generate(
            prompt=prompt,
            max_tokens=200,
            temperature=0.1,  # Low temperature for consistency
        )

        # Clean up response
        expanded = response.strip().strip('"').strip("'")
        return expanded if expanded else query

    def _calculate_confidence(
        self,
        original: str,
        expanded: str,
        tokens: list[str]
    ) -> float:
        """Calculate confidence score for rewrite quality."""
        if original == expanded:
            return 0.0  # No change made

        # Check that ambiguous tokens were resolved
        expanded_lower = expanded.lower()
        resolved_count = sum(1 for t in tokens if t not in expanded_lower)

        if not tokens:
            return 0.8  # Force rewrite with no tokens

        resolution_ratio = resolved_count / len(tokens)

        # Check expansion is reasonable length
        length_ratio = len(expanded) / len(original) if original else 1.0
        length_score = 1.0 if 1.0 <= length_ratio <= 3.0 else 0.5

        return min(1.0, resolution_ratio * 0.7 + length_score * 0.3)
```

#### Integration Point: `session_buddy/adapters/reflection_adapter_oneiric.py`

```python
# Add to search_conversations method

async def search_conversations(
    self,
    query: str,
    limit: int = 10,
    min_score: float = 0.7,
    project: str | None = None,
    *,
    enable_query_rewrite: bool = True,
    conversation_context: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Search conversations with optional query rewriting.

    Args:
        query: Search query
        limit: Max results
        min_score: Min similarity score
        project: Filter by project
        enable_query_rewrite: Whether to expand ambiguous queries
        conversation_context: Recent messages for context-aware rewriting

    Returns:
        List of matching conversations with metadata
    """
    rewrite_result = None
    effective_query = query

    # Attempt query rewriting if enabled
    if enable_query_rewrite and self._query_rewriter:
        rewrite_result = await self._query_rewriter.rewrite(
            query=query,
            context=conversation_context,
        )
        effective_query = rewrite_result.expanded_query

    # Generate embedding for effective query
    query_embedding = await self._generate_embedding(effective_query)

    # ... existing search logic ...

    # Include rewrite metadata in results
    if rewrite_result and rewrite_result.was_rewritten:
        for result in results:
            result["_query_rewrite"] = {
                "original": rewrite_result.original_query,
                "expanded": rewrite_result.expanded_query,
                "confidence": rewrite_result.confidence,
            }

    return results
```

### Configuration

```python
# session_buddy/adapters/settings.py

@dataclass
class QueryRewriteSettings:
    """Settings for query rewriting."""

    enabled: bool = True
    llm_provider: str = "haiku"  # Fast model for low latency
    max_context_messages: int = 10
    confidence_threshold: float = 0.7
    cache_rewrites: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
```

### Testing Strategy

```python
# tests/unit/test_query_rewriter.py

class TestAmbiguityDetector:
    def test_detects_pronouns(self):
        detector = AmbiguityDetector()
        is_ambiguous, tokens = detector.detect("What did he say?")
        assert is_ambiguous
        assert "he" in tokens

    def test_clear_query_not_ambiguous(self):
        detector = AmbiguityDetector()
        is_ambiguous, tokens = detector.detect("How to implement authentication?")
        assert not is_ambiguous
        assert len(tokens) == 0

    def test_detects_demonstratives(self):
        detector = AmbiguityDetector()
        is_ambiguous, tokens = detector.detect("Tell me more about that")
        assert is_ambiguous
        assert "that" in tokens


class TestQueryRewriter:
    async def test_rewrites_pronoun_query(self, mock_llm):
        mock_llm.generate.return_value = "What did John say about the migration?"

        rewriter = QueryRewriter(llm_provider=mock_llm)
        result = await rewriter.rewrite(
            query="What did he say about that?",
            context=[
                {"role": "user", "content": "Ask John about the database migration"}
            ]
        )

        assert result.was_rewritten
        assert "John" in result.expanded_query
        assert result.confidence > 0.7

    async def test_skips_clear_queries(self):
        rewriter = QueryRewriter()
        result = await rewriter.rewrite(
            query="How to implement OAuth2 authentication?",
            context=[{"role": "user", "content": "Some context"}]
        )

        assert not result.was_rewritten
        assert result.original_query == result.expanded_query

    async def test_fallback_on_no_llm(self):
        rewriter = QueryRewriter(llm_provider=None)
        result = await rewriter.rewrite(
            query="What did he say?",
            context=[{"role": "user", "content": "Talk to John"}]
        )

        assert not result.was_rewritten
        assert result.confidence == 0.5
```

### Rollout Plan

| Phase | Duration | Scope |
|-------|----------|-------|
| 1. Core Implementation | 3 days | `QueryRewriter` class, `AmbiguityDetector` |
| 2. Integration | 2 days | Hook into `search_conversations`, `search_reflections` |
| 3. Testing | 2 days | Unit tests, integration tests, benchmark |
| 4. Configuration | 1 day | Settings, feature flag |
| 5. Documentation | 1 day | Update CLAUDE.md, add examples |

**Total: ~9 days**

---

## Feature 2: Progressive Hierarchical Search

### Overview

Implement multi-tier search that flows through Categories → Items → Resources, stopping early when sufficient information is found.

### Current State

```python
# Current: Single-tier search across all content
results = await search_all_conversations(query, limit=20)
```

### Target State

```python
# Enhanced: Progressive multi-tier search
results = await progressive_search(
    query=query,
    tiers=["categories", "insights", "reflections", "conversations"],
    stop_when_sufficient=True,
    sufficiency_threshold=3,  # Stop after 3 high-quality matches
)
```

### Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    Progressive Search Pipeline                      │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Query ───► Tier 1: Categories    ───► Sufficient? ───► Return     │
│                  │                          │                       │
│                  │ No                       │ No                    │
│                  ▼                          │                       │
│             Tier 2: Insights      ◄─────────┘                       │
│                  │                                                  │
│                  │ Not sufficient                                   │
│                  ▼                                                  │
│             Tier 3: Reflections                                     │
│                  │                                                  │
│                  │ Not sufficient                                   │
│                  ▼                                                  │
│             Tier 4: Conversations (full search)                     │
│                  │                                                  │
│                  ▼                                                  │
│             Merge & Deduplicate Results                             │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### Implementation Details

#### File: `session_buddy/memory/progressive_search.py`

```python
"""Progressive hierarchical search with early stopping.

Searches through memory tiers from most abstract to most detailed,
stopping when sufficient high-quality results are found.
"""

from __future__ import annotations

import typing as t
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

if t.TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter_oneiric import (
        ReflectionDatabaseAdapterOneiric,
    )


class SearchTier(str, Enum):
    """Memory tiers in order of abstraction (high to low)."""

    CATEGORIES = "categories"      # Highest level summaries
    INSIGHTS = "insights"          # Extracted patterns and learnings
    REFLECTIONS = "reflections"    # Session reflections
    CONVERSATIONS = "conversations" # Raw conversation data


@dataclass
class TierSearchResult:
    """Result from searching a single tier."""

    tier: SearchTier
    results: list[dict[str, t.Any]]
    search_time_ms: float
    total_in_tier: int
    matched_count: int


@dataclass
class ProgressiveSearchResult:
    """Result from progressive multi-tier search."""

    query: str
    results: list[dict[str, t.Any]]
    tiers_searched: list[SearchTier]
    stopped_early: bool
    stop_reason: str | None
    tier_results: list[TierSearchResult] = field(default_factory=list)
    total_search_time_ms: float = 0.0

    @property
    def result_count(self) -> int:
        return len(self.results)


@dataclass
class SufficiencyConfig:
    """Configuration for determining search sufficiency."""

    min_results: int = 3
    min_avg_score: float = 0.8
    min_tier_coverage: int = 1  # At least results from N tiers
    max_tiers_to_search: int = 4


class SufficiencyEvaluator:
    """Evaluates whether search results are sufficient to stop early."""

    def __init__(self, config: SufficiencyConfig | None = None) -> None:
        self.config = config or SufficiencyConfig()

    def is_sufficient(
        self,
        results: list[dict[str, t.Any]],
        tiers_searched: list[SearchTier],
    ) -> tuple[bool, str]:
        """Determine if results are sufficient to stop searching.

        Args:
            results: Accumulated results so far
            tiers_searched: Tiers that have been searched

        Returns:
            Tuple of (is_sufficient, reason)
        """
        # Check minimum results
        if len(results) < self.config.min_results:
            return False, f"Need {self.config.min_results} results, have {len(results)}"

        # Check average score
        scores = [r.get("score", r.get("similarity", 0)) for r in results]
        avg_score = sum(scores) / len(scores) if scores else 0

        if avg_score < self.config.min_avg_score:
            return False, f"Avg score {avg_score:.2f} below threshold {self.config.min_avg_score}"

        # Check tier coverage
        unique_tiers = len(set(r.get("_tier") for r in results if r.get("_tier")))
        if unique_tiers < self.config.min_tier_coverage:
            return False, f"Only {unique_tiers} tiers covered, need {self.config.min_tier_coverage}"

        # Check if we've searched all tiers
        if len(tiers_searched) >= self.config.max_tiers_to_search:
            return True, "All tiers searched"

        # Sufficient!
        return True, f"Found {len(results)} results with avg score {avg_score:.2f}"


class ProgressiveSearchEngine:
    """Multi-tier search engine with early stopping.

    Searches through memory tiers from most abstract (categories) to most
    detailed (conversations), stopping early when sufficient results are found.

    Benefits:
        - Faster searches for simple queries matching high-level summaries
        - Reduced compute for queries that don't need full conversation search
        - Better result quality by prioritizing curated insights

    Example:
        >>> engine = ProgressiveSearchEngine(adapter)
        >>> result = await engine.search(
        ...     query="authentication patterns",
        ...     sufficiency_config=SufficiencyConfig(min_results=5)
        ... )
        >>> print(f"Found {result.result_count} in {len(result.tiers_searched)} tiers")
    """

    # Default tier order (most abstract to most detailed)
    DEFAULT_TIERS = [
        SearchTier.CATEGORIES,
        SearchTier.INSIGHTS,
        SearchTier.REFLECTIONS,
        SearchTier.CONVERSATIONS,
    ]

    def __init__(
        self,
        adapter: ReflectionDatabaseAdapterOneiric,
        default_limit_per_tier: int = 10,
    ) -> None:
        """Initialize progressive search engine.

        Args:
            adapter: Database adapter for searches
            default_limit_per_tier: Default max results per tier
        """
        self.adapter = adapter
        self.default_limit_per_tier = default_limit_per_tier

    async def search(
        self,
        query: str,
        tiers: list[SearchTier] | None = None,
        limit_per_tier: int | None = None,
        total_limit: int = 20,
        min_score: float = 0.6,
        sufficiency_config: SufficiencyConfig | None = None,
        stop_when_sufficient: bool = True,
        project: str | None = None,
    ) -> ProgressiveSearchResult:
        """Perform progressive multi-tier search.

        Args:
            query: Search query
            tiers: Tiers to search (default: all in order)
            limit_per_tier: Max results per tier
            total_limit: Max total results across all tiers
            min_score: Minimum similarity score
            sufficiency_config: Config for early stopping
            stop_when_sufficient: Whether to stop when sufficient results found
            project: Optional project filter

        Returns:
            ProgressiveSearchResult with results and metadata
        """
        start_time = datetime.now(UTC)
        tiers = tiers or self.DEFAULT_TIERS
        limit_per_tier = limit_per_tier or self.default_limit_per_tier
        evaluator = SufficiencyEvaluator(sufficiency_config)

        all_results: list[dict[str, t.Any]] = []
        tier_results: list[TierSearchResult] = []
        tiers_searched: list[SearchTier] = []
        stop_reason: str | None = None
        stopped_early = False

        for tier in tiers:
            tier_start = datetime.now(UTC)

            # Search this tier
            tier_matches = await self._search_tier(
                tier=tier,
                query=query,
                limit=limit_per_tier,
                min_score=min_score,
                project=project,
            )

            tier_time = (datetime.now(UTC) - tier_start).total_seconds() * 1000

            # Tag results with tier
            for result in tier_matches:
                result["_tier"] = tier.value

            # Record tier results
            tier_result = TierSearchResult(
                tier=tier,
                results=tier_matches,
                search_time_ms=tier_time,
                total_in_tier=len(tier_matches),
                matched_count=len(tier_matches),
            )
            tier_results.append(tier_result)
            tiers_searched.append(tier)

            # Accumulate results
            all_results.extend(tier_matches)

            # Check sufficiency
            if stop_when_sufficient:
                is_sufficient, reason = evaluator.is_sufficient(
                    all_results, tiers_searched
                )
                if is_sufficient:
                    stopped_early = True
                    stop_reason = reason
                    break

            # Check total limit
            if len(all_results) >= total_limit:
                stopped_early = True
                stop_reason = f"Reached total limit of {total_limit}"
                break

        # Deduplicate and sort by score
        unique_results = self._deduplicate_results(all_results)
        sorted_results = sorted(
            unique_results,
            key=lambda r: r.get("score", r.get("similarity", 0)),
            reverse=True,
        )[:total_limit]

        total_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return ProgressiveSearchResult(
            query=query,
            results=sorted_results,
            tiers_searched=tiers_searched,
            stopped_early=stopped_early,
            stop_reason=stop_reason,
            tier_results=tier_results,
            total_search_time_ms=total_time,
        )

    async def _search_tier(
        self,
        tier: SearchTier,
        query: str,
        limit: int,
        min_score: float,
        project: str | None,
    ) -> list[dict[str, t.Any]]:
        """Search a specific tier."""
        if tier == SearchTier.CATEGORIES:
            return await self._search_categories(query, limit, min_score, project)
        elif tier == SearchTier.INSIGHTS:
            return await self.adapter.search_insights(
                query=query, limit=limit, min_score=min_score
            )
        elif tier == SearchTier.REFLECTIONS:
            return await self.adapter.search_reflections(query=query, limit=limit)
        elif tier == SearchTier.CONVERSATIONS:
            return await self.adapter.search_conversations(
                query=query, limit=limit, min_score=min_score, project=project
            )
        return []

    async def _search_categories(
        self,
        query: str,
        limit: int,
        min_score: float,
        project: str | None,
    ) -> list[dict[str, t.Any]]:
        """Search category-level summaries.

        Categories are high-level aggregations that don't exist as a
        separate table yet. This searches insights with high importance
        scores as a proxy for category-level content.
        """
        # Use high-importance insights as category proxies
        return await self.adapter.search_insights(
            query=query,
            limit=limit,
            min_score=min_score,
            min_quality_score=0.8,  # Only high-quality as categories
        )

    def _deduplicate_results(
        self, results: list[dict[str, t.Any]]
    ) -> list[dict[str, t.Any]]:
        """Remove duplicate results based on content similarity."""
        seen_ids: set[str] = set()
        unique: list[dict[str, t.Any]] = []

        for result in results:
            result_id = result.get("id", "")
            if result_id and result_id not in seen_ids:
                seen_ids.add(result_id)
                unique.append(result)

        return unique
```

#### MCP Tool Integration

```python
# session_buddy/tools/search_tools.py

@mcp.tool()
async def progressive_search(
    query: str,
    stop_when_sufficient: bool = True,
    min_results: int = 3,
    min_score: float = 0.7,
    project: str | None = None,
) -> dict[str, Any]:
    """Search memory using progressive multi-tier strategy.

    Searches through memory tiers from most abstract (categories, insights)
    to most detailed (conversations), stopping early when sufficient
    high-quality results are found.

    Benefits:
        - Faster for queries matching high-level summaries
        - Better results by prioritizing curated insights
        - Reduced compute for simple queries

    Args:
        query: Search query
        stop_when_sufficient: Stop when enough good results found
        min_results: Minimum results before stopping
        min_score: Minimum similarity score (0.0-1.0)
        project: Optional project filter

    Returns:
        Search results with tier metadata
    """
    from session_buddy.memory.progressive_search import (
        ProgressiveSearchEngine,
        SufficiencyConfig,
    )

    adapter = await get_reflection_adapter()
    engine = ProgressiveSearchEngine(adapter)

    config = SufficiencyConfig(
        min_results=min_results,
        min_avg_score=min_score,
    )

    result = await engine.search(
        query=query,
        sufficiency_config=config,
        stop_when_sufficient=stop_when_sufficient,
        project=project,
    )

    return {
        "success": True,
        "query": result.query,
        "results": result.results,
        "result_count": result.result_count,
        "tiers_searched": [t.value for t in result.tiers_searched],
        "stopped_early": result.stopped_early,
        "stop_reason": result.stop_reason,
        "search_time_ms": result.total_search_time_ms,
    }
```

### Rollout Plan

| Phase | Duration | Scope |
|-------|----------|-------|
| 1. Core Implementation | 2 days | `ProgressiveSearchEngine`, `SufficiencyEvaluator` |
| 2. Tier Search Methods | 2 days | Implement each tier's search logic |
| 3. MCP Tool | 1 day | `progressive_search` tool |
| 4. Testing | 2 days | Unit tests, performance benchmarks |
| 5. Migration | 1 day | Optional: make default search strategy |

**Total: ~8 days**

---

## Feature 3: Self-Evolving Category Structure

### Overview

Enable dynamic subcategory creation based on clustering frequently co-occurring topics within the fixed top-level categories.

### Current State

```python
# Fixed categories in MemoryCategory enum
class MemoryCategory(str, Enum):
    FACTS = "facts"
    PREFERENCES = "preferences"
    SKILLS = "skills"
    RULES = "rules"
    CONTEXT = "context"
```

### Target State

```python
# Dynamic subcategories within fixed categories
categories = {
    "facts": ["database_schema", "api_endpoints", "team_structure"],
    "skills": ["python_patterns", "testing_strategies", "git_workflows"],
    "preferences": ["code_style", "tool_preferences", "communication"],
}
```

### Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    Category Evolution System                        │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  New Memory ───► Extract Keywords ───► Find Cluster ───► Assign    │
│                        │                    │                       │
│                        ▼                    │                       │
│                   [python, async,           │                       │
│                    patterns, code]          │                       │
│                        │                    │                       │
│                        ▼                    ▼                       │
│                   Cluster Engine ◄──── Existing Clusters            │
│                        │                                            │
│                        ├──► Match existing cluster                  │
│                        │         └──► skills/python_patterns        │
│                        │                                            │
│                        └──► Create new cluster                      │
│                                  └──► skills/new_cluster_42         │
│                                              │                      │
│                                              ▼                      │
│                                      Name via LLM                   │
│                                              │                      │
│                                              ▼                      │
│                                   skills/async_programming          │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘

Background Process:
┌────────────────────────────────────────────────────────────────────┐
│                    Periodic Reorganization                          │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Every N hours:                                                     │
│    1. Collect all memories by category                              │
│    2. Generate embeddings for content                               │
│    3. Run clustering (HDBSCAN/K-means)                              │
│    4. Name clusters via LLM or keyword extraction                   │
│    5. Update subcategory assignments                                │
│    6. Merge small/similar clusters                                  │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### Implementation Details

#### File: `session_buddy/memory/category_evolution.py`

```python
"""Self-evolving category structure via clustering.

Automatically creates and manages subcategories within the fixed
top-level memory categories based on content clustering.
"""

from __future__ import annotations

import re
import typing as t
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import numpy as np

if t.TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter_oneiric import (
        ReflectionDatabaseAdapterOneiric,
    )


class TopLevelCategory(str, Enum):
    """Fixed top-level memory categories."""

    FACTS = "facts"
    PREFERENCES = "preferences"
    SKILLS = "skills"
    RULES = "rules"
    CONTEXT = "context"


@dataclass
class Subcategory:
    """A dynamically created subcategory."""

    id: str
    parent_category: TopLevelCategory
    name: str  # Human-readable name
    keywords: list[str]  # Keywords that map to this subcategory
    centroid: list[float] | None = None  # Cluster centroid embedding
    memory_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def full_path(self) -> str:
        """Get full category path like 'skills/python_patterns'."""
        return f"{self.parent_category.value}/{self.name}"


@dataclass
class CategoryAssignment:
    """Assignment of a memory to a category/subcategory."""

    memory_id: str
    category: TopLevelCategory
    subcategory: str | None
    confidence: float
    keywords_matched: list[str]


class KeywordExtractor:
    """Extract keywords from memory content for clustering."""

    # Common stop words to ignore
    STOP_WORDS = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall",
        "can", "need", "dare", "ought", "used", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "above", "below", "between", "under",
        "again", "further", "then", "once", "here", "there", "when",
        "where", "why", "how", "all", "each", "few", "more", "most",
        "other", "some", "such", "no", "nor", "not", "only", "own",
        "same", "so", "than", "too", "very", "just", "also", "now",
        "i", "you", "he", "she", "it", "we", "they", "what", "which",
        "this", "that", "these", "those", "am", "and", "but", "if",
        "or", "because", "until", "while", "although", "though",
    }

    # Technical terms to prioritize
    TECH_TERMS = {
        "python", "javascript", "typescript", "rust", "go", "java",
        "api", "database", "sql", "nosql", "redis", "postgres",
        "docker", "kubernetes", "aws", "gcp", "azure", "terraform",
        "git", "github", "gitlab", "ci", "cd", "pipeline",
        "test", "testing", "pytest", "unittest", "mock",
        "async", "await", "concurrent", "parallel", "thread",
        "cache", "memory", "performance", "optimization",
        "security", "authentication", "authorization", "oauth",
        "frontend", "backend", "fullstack", "microservice",
        "react", "vue", "angular", "fastapi", "django", "flask",
    }

    def extract(
        self,
        content: str,
        max_keywords: int = 10
    ) -> list[str]:
        """Extract keywords from content.

        Args:
            content: Text content to extract from
            max_keywords: Maximum keywords to return

        Returns:
            List of keywords ordered by relevance
        """
        # Tokenize and clean
        words = re.findall(r'\b[a-z_][a-z0-9_]*\b', content.lower())

        # Filter stop words
        words = [w for w in words if w not in self.STOP_WORDS and len(w) > 2]

        # Count frequencies
        counter = Counter(words)

        # Boost technical terms
        for word in counter:
            if word in self.TECH_TERMS:
                counter[word] *= 2

        # Return top keywords
        return [word for word, _ in counter.most_common(max_keywords)]


class SubcategoryClusterer:
    """Cluster memories within a category to form subcategories."""

    def __init__(
        self,
        min_cluster_size: int = 5,
        max_clusters_per_category: int = 10,
        similarity_threshold: float = 0.7,
    ) -> None:
        """Initialize clusterer.

        Args:
            min_cluster_size: Min memories to form a subcategory
            max_clusters_per_category: Max subcategories per category
            similarity_threshold: Min similarity to join cluster
        """
        self.min_cluster_size = min_cluster_size
        self.max_clusters_per_category = max_clusters_per_category
        self.similarity_threshold = similarity_threshold
        self.keyword_extractor = KeywordExtractor()

    def cluster_memories(
        self,
        memories: list[dict[str, t.Any]],
        existing_subcategories: list[Subcategory] | None = None,
    ) -> list[Subcategory]:
        """Cluster memories into subcategories.

        Args:
            memories: List of memories with embeddings
            existing_subcategories: Existing subcategories to update

        Returns:
            List of subcategories (new and updated)
        """
        if not memories:
            return existing_subcategories or []

        # Extract embeddings
        embeddings = []
        valid_memories = []
        for mem in memories:
            emb = mem.get("embedding")
            if emb is not None:
                embeddings.append(emb)
                valid_memories.append(mem)

        if not embeddings:
            return existing_subcategories or []

        embeddings_array = np.array(embeddings)

        # Simple clustering: assign to existing or create new
        subcategories = list(existing_subcategories) if existing_subcategories else []
        unassigned = []

        for i, mem in enumerate(valid_memories):
            embedding = embeddings_array[i]
            assigned = False

            # Try to assign to existing subcategory
            for subcat in subcategories:
                if subcat.centroid is not None:
                    similarity = self._cosine_similarity(
                        embedding, np.array(subcat.centroid)
                    )
                    if similarity >= self.similarity_threshold:
                        subcat.memory_count += 1
                        subcat.updated_at = datetime.now(UTC)
                        # Update centroid (running average)
                        subcat.centroid = self._update_centroid(
                            subcat.centroid, embedding.tolist(), subcat.memory_count
                        )
                        assigned = True
                        break

            if not assigned:
                unassigned.append((mem, embedding))

        # Create new subcategories from unassigned if enough
        if len(unassigned) >= self.min_cluster_size:
            new_subcats = self._create_new_subcategories(unassigned)
            subcategories.extend(new_subcats)

        return subcategories

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def _update_centroid(
        self,
        current: list[float],
        new: list[float],
        count: int
    ) -> list[float]:
        """Update centroid with running average."""
        current_arr = np.array(current)
        new_arr = np.array(new)
        # Incremental mean update
        updated = current_arr + (new_arr - current_arr) / count
        return updated.tolist()

    def _create_new_subcategories(
        self,
        unassigned: list[tuple[dict[str, t.Any], np.ndarray]],
    ) -> list[Subcategory]:
        """Create new subcategories from unassigned memories."""
        import uuid

        # Simple approach: create one subcategory from all unassigned
        # More sophisticated: use k-means or HDBSCAN

        if len(unassigned) < self.min_cluster_size:
            return []

        # Extract keywords from all unassigned
        all_content = " ".join(mem["content"] for mem, _ in unassigned)
        keywords = self.keyword_extractor.extract(all_content, max_keywords=5)

        # Calculate centroid
        embeddings = np.array([emb for _, emb in unassigned])
        centroid = np.mean(embeddings, axis=0).tolist()

        # Generate name from keywords
        name = "_".join(keywords[:3]) if keywords else f"cluster_{uuid.uuid4().hex[:8]}"

        # Determine parent category from first memory
        parent = TopLevelCategory(
            unassigned[0][0].get("category", "context")
        )

        return [Subcategory(
            id=str(uuid.uuid4()),
            parent_category=parent,
            name=name,
            keywords=keywords,
            centroid=centroid,
            memory_count=len(unassigned),
        )]


class CategoryEvolutionEngine:
    """Manages the evolution of category structure over time.

    Periodically analyzes stored memories and creates/updates
    subcategories based on content clustering.

    Example:
        >>> engine = CategoryEvolutionEngine(adapter)
        >>> await engine.evolve_category(TopLevelCategory.SKILLS)
        >>> subcats = await engine.get_subcategories(TopLevelCategory.SKILLS)
        >>> print([s.name for s in subcats])
        ['python_patterns', 'testing_strategies', 'git_workflows']
    """

    def __init__(
        self,
        adapter: ReflectionDatabaseAdapterOneiric,
        clusterer: SubcategoryClusterer | None = None,
    ) -> None:
        """Initialize evolution engine.

        Args:
            adapter: Database adapter for memory access
            clusterer: Clusterer for subcategory generation
        """
        self.adapter = adapter
        self.clusterer = clusterer or SubcategoryClusterer()
        self._subcategories: dict[TopLevelCategory, list[Subcategory]] = {}

    async def evolve_category(
        self,
        category: TopLevelCategory,
        force_recluster: bool = False,
    ) -> list[Subcategory]:
        """Evolve subcategories for a top-level category.

        Args:
            category: Category to evolve
            force_recluster: Force complete reclustering

        Returns:
            Updated list of subcategories
        """
        # Load existing subcategories
        existing = [] if force_recluster else self._subcategories.get(category, [])

        # Get all memories for this category
        memories = await self._get_category_memories(category)

        # Cluster and update
        updated = self.clusterer.cluster_memories(memories, existing)

        # Store updated subcategories
        self._subcategories[category] = updated
        await self._persist_subcategories(category, updated)

        return updated

    async def assign_subcategory(
        self,
        memory: dict[str, t.Any],
    ) -> CategoryAssignment:
        """Assign a memory to the best matching subcategory.

        Args:
            memory: Memory with content and embedding

        Returns:
            CategoryAssignment with category and subcategory
        """
        category = TopLevelCategory(memory.get("category", "context"))
        subcategories = self._subcategories.get(category, [])

        embedding = memory.get("embedding")
        if embedding is None or not subcategories:
            return CategoryAssignment(
                memory_id=memory.get("id", ""),
                category=category,
                subcategory=None,
                confidence=1.0,
                keywords_matched=[],
            )

        # Find best matching subcategory
        best_subcat = None
        best_similarity = 0.0

        embedding_arr = np.array(embedding)

        for subcat in subcategories:
            if subcat.centroid:
                similarity = self._cosine_similarity(
                    embedding_arr, np.array(subcat.centroid)
                )
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_subcat = subcat

        # Also check keyword matches
        keywords_matched = []
        if best_subcat:
            content_lower = memory.get("content", "").lower()
            keywords_matched = [k for k in best_subcat.keywords if k in content_lower]

        return CategoryAssignment(
            memory_id=memory.get("id", ""),
            category=category,
            subcategory=best_subcat.name if best_subcat else None,
            confidence=best_similarity,
            keywords_matched=keywords_matched,
        )

    async def get_subcategories(
        self,
        category: TopLevelCategory | None = None,
    ) -> dict[str, list[Subcategory]]:
        """Get all subcategories, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            Dict mapping category names to subcategory lists
        """
        if category:
            return {category.value: self._subcategories.get(category, [])}
        return {k.value: v for k, v in self._subcategories.items()}

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity."""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    async def _get_category_memories(
        self,
        category: TopLevelCategory,
    ) -> list[dict[str, t.Any]]:
        """Get all memories for a category."""
        # Query adapter for memories with this category
        # This would be implemented based on actual schema
        return []

    async def _persist_subcategories(
        self,
        category: TopLevelCategory,
        subcategories: list[Subcategory],
    ) -> None:
        """Persist subcategories to database."""
        # Store in a subcategories table
        # This would be implemented based on actual schema
        pass
```

#### Database Schema Addition

```sql
-- New table for subcategories
CREATE TABLE IF NOT EXISTS memory_subcategories (
    id TEXT PRIMARY KEY,
    parent_category TEXT NOT NULL,  -- facts, preferences, skills, rules, context
    name TEXT NOT NULL,
    keywords TEXT[],  -- Array of associated keywords
    centroid FLOAT[384],  -- Cluster centroid embedding
    memory_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(parent_category, name)
);

-- Add subcategory column to existing tables
ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS subcategory TEXT;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS subcategory TEXT;

-- Index for subcategory queries
CREATE INDEX IF NOT EXISTS idx_conv_subcategory
    ON conversations_v2(category, subcategory);
CREATE INDEX IF NOT EXISTS idx_refl_subcategory
    ON reflections_v2(category, subcategory);
```

### Rollout Plan

| Phase | Duration | Scope |
|-------|----------|-------|
| 1. Schema Migration | 1 day | Add subcategory table and columns |
| 2. Core Classes | 3 days | `KeywordExtractor`, `SubcategoryClusterer`, `CategoryEvolutionEngine` |
| 3. Integration | 2 days | Hook into memory storage, add assignment logic |
| 4. Background Job | 1 day | Periodic evolution task |
| 5. MCP Tools | 1 day | Tools to view/manage subcategories |
| 6. Testing | 2 days | Unit tests, evolution simulation |

**Total: ~10 days**

---

## Summary & Timeline

### Total Estimated Effort

| Feature | Days | Priority | Value |
|---------|------|----------|-------|
| Query Rewriting | 9 | High | Enables conversational memory |
| Progressive Search | 8 | Medium | Performance optimization |
| Category Evolution | 10 | Medium | Organization improvement |
| **Total** | **27 days** | | |

### Recommended Implementation Order

1. **Query Rewriting** (9 days) - Highest user-facing impact
2. **Progressive Search** (8 days) - Natural extension, uses same infrastructure
3. **Category Evolution** (10 days) - Background improvement

### Dependencies

```
Query Rewriting
    └── LLM Provider (existing)
    └── Conversation Context (existing)

Progressive Search
    └── Query Rewriting (optional, but beneficial)
    └── Tiered storage (insights table exists)

Category Evolution
    └── Embedding infrastructure (existing)
    └── Schema migration
    └── Background task runner
```

### Success Metrics

| Feature | Metric | Target |
|---------|--------|--------|
| Query Rewriting | Ambiguous query resolution rate | >80% |
| Query Rewriting | Search latency increase | <200ms |
| Progressive Search | Avg tiers searched | <2.5 |
| Progressive Search | Search time reduction | >30% |
| Category Evolution | Subcategories per category | 3-10 |
| Category Evolution | Memory assignment accuracy | >75% |

### Feature Flags

```python
# session_buddy/settings.py

class MemoryEnhancementSettings:
    # Query Rewriting
    enable_query_rewriting: bool = True
    query_rewrite_llm_provider: str = "haiku"
    query_rewrite_max_context: int = 10

    # Progressive Search
    enable_progressive_search: bool = True
    progressive_search_default: bool = False  # Make default after testing
    sufficiency_min_results: int = 3

    # Category Evolution
    enable_category_evolution: bool = True
    evolution_interval_hours: int = 6
    min_cluster_size: int = 5
    max_subcategories_per_category: int = 10
```

---

## References

- [MemU GitHub Repository](https://github.com/NevaMind-AI/memU)
- Session-buddy existing architecture: `session_buddy/adapters/reflection_adapter_oneiric.py`
- Memory categories: `session_buddy/memory/schema_v2.py`
- Existing summarization: `session_buddy/memory_optimizer.py`
