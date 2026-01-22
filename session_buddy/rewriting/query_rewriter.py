"""Query rewriting system for Session Buddy (Phase 2).

This module implements intelligent query expansion using LLM to resolve ambiguous
queries with pronoun resolution and contextual information, then caches rewritten queries
for fast reuse.

Architecture:
    AmbiguityDetector → QueryRewriter → Cached Rewritten Queries
         ↓                        ↓                  ↓
    Pattern Matching     LLM Expansion       Fast Lookup

Usage:
    >>> detector = AmbiguityDetector()
    >>> rewriter = QueryRewriter()
    >>> is_ambiguous = detector.detect_ambiguity("what did I learn about async?")
    >>> if is_ambiguous:
    ...     rewritten = await rewriter.rewrite_query(
    ...         query="what did I learn about async?",
    ...         context=conversation_history
    ...     )
    ...     # Use expanded query for search
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class AmbiguityType(str, Enum):
    """Types of query ambiguity to detect."""

    # Pronouns that require resolution
    PRONOUN_I = "pronoun_i"  # "what did I learn"
    PRONOUN_IT = "pronoun_it"  # "fix the bug"
    PRONOUN_THIS = "pronoun_this"  # "update this code"
    PRONOUN_THAT = "pronoun_that"  # "that function from last week"

    # Demonstratives requiring context
    DEMONSTRATIVE_TEMPORAL = "demonstrative_temporal"  # "the bug from yesterday"
    DEMONSTRATIVE_SPATIAL = "demonstrative_spatial"  # "the class in that file"

    # Query structure issues
    TOO_SHORT = "too_short"  # < 5 words
    TOO_VAGUE = "too_vague"  # "help me", "how to", "something"
    MISSING_CONTEXT = "missing_context"  # "the method" without class context

    # Referential ambiguity
    REFERS_TO_PREVIOUS = "refers_to_previous"  # "last time", "previously"
    REFERS_TO_RECENT = "refers_to_recent"  # "recent changes", "latest update"


@dataclass
class AmbiguityDetection:
    """Result of ambiguity detection on a query."""

    is_ambiguous: bool
    ambiguity_types: list[AmbiguityType]
    confidence: float  # 0.0 to 1.0
    matched_patterns: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class AmbiguityDetector:
    """Detect ambiguous queries that require context expansion.

    Uses regex patterns and heuristics to identify queries that would benefit
    from LLM-powered context expansion.

    Patterns detected:
        - Pronouns: "I", "my", "it", "this", "that"
        - Temporal references: "yesterday", "last week", "recent"
        - Spatial references: "that file", "the class"
        - Short queries: <2 words (single word queries)
        - Vague queries: "help", "how to", "something"
    """

    # Pronoun patterns
    PRONOUN_PATTERNS = {
        AmbiguityType.PRONOUN_I: [
            r"\bwhat did i\b",
            r"\bhow do i\b",
            r"\bwhere did i\b",
            r"\bmy (?:code|file|project|app|bug|error|issue)",
            r"\bour (?:code|implementation|approach)\b",
        ],
        AmbiguityType.PRONOUN_IT: [
            r"\bfix it\b",
            r"\btest it\b",
            r"\bupdate it\b",
            r"\bremove it\b",
            r"\bdelete it\b",
        ],
        AmbiguityType.PRONOUN_THIS: [
            r"\bthis (?:code|method|function|class|file)\b",
            r"\bcheck this\b",
            r"\breview this\b",
            r"\bupdate this\b",
        ],
        AmbiguityType.PRONOUN_THAT: [
            r"\bthat (?:function|method|class|variable)\b",
            r"\bthat (?:bug|error|issue)\b",
            r"\bthat (?:file|path)\b",
        ],
    }

    # Temporal demonstrative patterns
    TEMPORAL_PATTERNS = {
        AmbiguityType.DEMONSTRATIVE_TEMPORAL: [
            r"\b(?:yesterday|last (?:week|month|time)|recently|lately)\b",
            r"\bthe (?:previous|last|past)\b",
            r"\b(?:earlier|before)\b",
        ],
    }

    # Spatial demonstrative patterns
    SPATIAL_PATTERNS = {
        AmbiguityType.DEMONSTRATIVE_SPATIAL: [
            r"\bthat (?:file|path|directory|folder)\b",
            r"\bthe (?:other|previous|different)\b (?:file|class|method)\b",
            r"\b(?:in|from) (?:that|the)\b",
        ],
    }

    # Query structure patterns
    STRUCTURE_PATTERNS = {
        AmbiguityType.TOO_SHORT: [
            r"^(?:\S+\s+){0,1}\S+\s*$",  # <2 words (1 word or empty)
        ],
        AmbiguityType.TOO_VAGUE: [
            r"\b(?:help|assist|guide|explain|describe)\b",
            r"\bhow do (?:i|you)\b",
            r"\bwhat (?:is|are|should)\b",
            r"\b(?:find|search|look for|show)\b\s+(?:me|us)?\s*$",
        ],
        AmbiguityType.MISSING_CONTEXT: [
            r"\bthe (?:method|function|class|variable)\b(?!\s+in)",
            r"\b(?:call|use|invoke)\b\s+the\b",
            r"\b(?:in|on|at)\b\s+that\b",
        ],
    }

    # Referential patterns
    REFERENTIAL_PATTERNS = {
        AmbiguityType.REFERS_TO_PREVIOUS: [
            r"\b(?:before|earlier|previously|last time)\b",
            r"\b(?:continue|ongoing|following)\b",
        ],
        AmbiguityType.REFERS_TO_RECENT: [
            r"\b(?:just|recently|lately|currently)\b",
            r"\b(?:new|latest|most recent)\b",
        ],
    }

    def __init__(self) -> None:
        """Initialize ambiguity detector with compiled regex patterns."""
        self._all_patterns: dict[AmbiguityType, list[re.Pattern[str]]] = {}

        # Compile all patterns for performance
        all_pattern_groups = [
            self.PRONOUN_PATTERNS,
            self.TEMPORAL_PATTERNS,
            self.SPATIAL_PATTERNS,
            self.STRUCTURE_PATTERNS,
            self.REFERENTIAL_PATTERNS,
        ]

        for group in all_pattern_groups:
            for ambiguity_type, patterns in group.items():
                self._all_patterns[ambiguity_type] = [
                    re.compile(pattern, re.IGNORECASE) for pattern in patterns
                ]

        logger.info(
            "AmbiguityDetector initialized with %d pattern groups",
            len(self._all_patterns),
        )

    def detect_ambiguity(
        self,
        query: str,
        min_confidence: float = 0.5,
    ) -> AmbiguityDetection:
        """Detect if a query contains ambiguous references.

        Args:
            query: The search query to analyze
            min_confidence: Minimum confidence threshold (0.0-1.0)

        Returns:
            AmbiguityDetection result with types and confidence
        """
        query_lower = query.lower().strip()
        detected_types: list[AmbiguityType] = []
        matched_patterns: list[str] = []

        # Check each pattern group
        for ambiguity_type, patterns in self._all_patterns.items():
            for pattern in patterns:
                if pattern.search(query_lower):
                    if ambiguity_type not in detected_types:
                        detected_types.append(ambiguity_type)
                        matched_patterns.append(pattern.pattern)

        # Calculate confidence based on number and severity of ambiguities
        confidence = self._calculate_confidence(detected_types, query, min_confidence)

        # Generate suggestions for resolution
        suggestions = self._generate_suggestions(detected_types, query)

        return AmbiguityDetection(
            is_ambiguous=len(detected_types) > 0 and confidence >= min_confidence,
            ambiguity_types=detected_types,
            confidence=confidence,
            matched_patterns=matched_patterns,
            suggestions=suggestions,
        )

    def _calculate_confidence(
        self,
        detected_types: list[AmbiguityType],
        query: str,
        min_confidence: float,
    ) -> float:
        """Calculate confidence score for ambiguity detection.

        Higher confidence for:
            - Multiple ambiguity types present
            - Pronoun ambiguity (highest priority)
            - Short queries with ambiguity

        Args:
            detected_types: List of detected ambiguity types
            query: Original query string
            min_confidence: Minimum confidence threshold

        Returns:
            Confidence score 0.0-1.0
        """
        if not detected_types:
            return 0.0

        confidence = 0.5  # Base confidence for any ambiguity

        # Increase confidence for pronoun ambiguity (high priority)
        pronoun_types = [
            AmbiguityType.PRONOUN_I,
            AmbiguityType.PRONOUN_IT,
            AmbiguityType.PRONOUN_THIS,
            AmbiguityType.PRONOUN_THAT,
        ]
        if any(t in detected_types for t in pronoun_types):
            confidence += 0.3

        # Increase confidence for very short queries (< 5 words)
        word_count = len(query.split())
        if word_count < 5:
            confidence += 0.2

        # Cap at 1.0
        return min(confidence, 1.0)

    def _generate_suggestions(
        self,
        detected_types: list[AmbiguityType],
        query: str,
    ) -> list[str]:
        """Generate suggestions for resolving ambiguity.

        Args:
            detected_types: List of detected ambiguity types
            query: Original query string

        Returns:
            List of suggestion strings
        """
        suggestions = []

        for ambiguity_type in detected_types:
            if ambiguity_type == AmbiguityType.PRONOUN_I:
                suggestions.append(
                    "Add conversation context: 'What did I learn about async in our previous discussion about error handling?'"
                )
            elif ambiguity_type == AmbiguityType.PRONOUN_IT:
                suggestions.append(
                    "Be specific: 'Fix the bug in authentication service where JWT validation fails'"
                )
            elif ambiguity_type == AmbiguityType.DEMONSTRATIVE_TEMPORAL:
                suggestions.append(
                    "Add time context: 'What changes did I make to the database schema yesterday during the migration?'"
                )
            elif ambiguity_type == AmbiguityType.TOO_SHORT:
                suggestions.append(
                    f"Expand query: '{query}' → '{query} in the context of our current project'"
                )
            elif ambiguity_type == AmbiguityType.TOO_VAGUE:
                suggestions.append(
                    "Be specific about what you need: 'Help me understand how to implement OAuth2 authentication in Python'"
                )

        return suggestions


@dataclass
class QueryRewriteResult:
    """Result of query rewriting operation."""

    original_query: str
    rewritten_query: str
    was_rewritten: bool
    confidence: float  # 0.0 to 1.0
    llm_provider: str | None
    latency_ms: float
    context_used: bool
    cache_hit: bool = False


@dataclass
class RewriteContext:
    """Context information for query rewriting."""

    query: str
    recent_conversations: list[dict[str, Any]] = field(default_factory=list)
    project: str | None = None
    recent_files: list[str] = field(default_factory=list)
    session_context: dict[str, Any] = field(default_factory=dict)


class QueryRewriter:
    """Use LLM to expand ambiguous queries with contextual information.

    The rewriter:
    1. Detects ambiguous queries (delegates to AmbiguityDetector)
    2. Checks cache for existing rewrites
    3. Uses LLM to generate expanded query with context
    4. Caches rewritten queries for fast reuse
    5. Gracefully degrades when LLM unavailable

    Integration:
        - Called via PRE_SEARCH_QUERY hooks (priority: 100)
        - Rewritten queries cached in rewritten_queries table
        - Statistics tracked for monitoring
    """

    def __init__(self) -> None:
        """Initialize query rewriter."""
        self.detector = AmbiguityDetector()
        self._cache: dict[str, QueryRewriteResult] = {}
        self._stats = {
            "total_rewrites": 0,
            "cache_hits": 0,
            "llm_failures": 0,
            "avg_latency_ms": 0.0,
        }
        logger.info("QueryRewriter initialized")

    def detect_ambiguity(
        self, query: str, min_confidence: float = 0.5
    ) -> AmbiguityDetection:
        """Detect if query is ambiguous (wrapper for AmbiguityDetector).

        Args:
            query: Query to analyze
            min_confidence: Minimum confidence threshold

        Returns:
            AmbiguityDetection result
        """
        return self.detector.detect_ambiguity(query, min_confidence)

    async def rewrite_query(
        self,
        query: str,
        context: RewriteContext,
        force_rewrite: bool = False,
    ) -> QueryRewriteResult:
        """Rewrite an ambiguous query using LLM and context.

        Args:
            query: Original query string
            context: Context information (conversations, project, files)
            force_rewrite: Force rewrite even if cached version exists

        Returns:
            QueryRewriteResult with rewritten query and metadata

        Raises:
            RuntimeError: If LLM is unavailable and cache miss occurs
        """
        import time

        start_time = time.perf_counter()

        # Check cache first (unless forced)
        cache_key = self._compute_cache_key(query, context.project)
        if not force_rewrite and cache_key in self._cache:
            cached = self._cache[cache_key]
            cached.cache_hit = True
            logger.debug(f"Cache hit for query: '{query[:50]}...'")
            self._stats["cache_hits"] += 1
            return cached

        # Detect ambiguity
        detection = self.detector.detect_ambiguity(query)
        if not detection.is_ambiguous:
            # Query is clear, return as-is
            latency_ms = (time.perf_counter() - start_time) * 1000
            return QueryRewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                confidence=0.0,
                llm_provider=None,
                latency_ms=latency_ms,
                context_used=False,
                cache_hit=False,
            )

        # LLM-based query expansion
        try:
            rewritten_query = await self._llm_expand_query(query, context)
            llm_provider = await self._get_llm_provider()
            was_rewritten = True
            confidence = detection.confidence
            context_used = True

            # Update statistics
            self._stats["total_rewrites"] += 1
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._stats["avg_latency_ms"] = (
                self._stats["avg_latency_ms"] * (self._stats["total_rewrites"] - 1)
                + latency_ms
            ) / self._stats["total_rewrites"]

            # Create result
            result = QueryRewriteResult(
                original_query=query,
                rewritten_query=rewritten_query,
                was_rewritten=was_rewritten,
                confidence=confidence,
                llm_provider=llm_provider,
                latency_ms=latency_ms,
                context_used=context_used,
                cache_hit=False,
            )

            # Cache the result
            self._cache[cache_key] = result

            return result

        except Exception as e:
            self._stats["llm_failures"] += 1
            logger.error(f"LLM query rewrite failed: {e}")

            # Fallback: return original query
            latency_ms = (time.perf_counter() - start_time) * 1000
            return QueryRewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                confidence=0.0,
                llm_provider=None,
                latency_ms=latency_ms,
                context_used=False,
                cache_hit=False,
            )

    async def _llm_expand_query(self, query: str, context: RewriteContext) -> str:
        """Use LLM to expand query with contextual information.

        Args:
            query: Original ambiguous query
            context: Context information

        Returns:
            Expanded query string

        Raises:
            RuntimeError: If LLM provider is not available
        """
        # Build context prompt for LLM
        context_prompt = self._build_context_prompt(query, context)

        # Get LLM provider and generate expansion
        try:
            llm_provider = await self._get_llm_provider()
            if not llm_provider:
                raise RuntimeError("No LLM provider available")

            # Call LLM
            from session_buddy.di import depends

            llm = depends.get_sync("LLMManager")

            # Generate rewritten query using LLM
            messages = [
                {
                    "role": "system",
                    "content": "You are a search query expansion assistant. Your task is to expand ambiguous search queries by adding relevant context from conversation history.",
                },
                {
                    "role": "user",
                    "content": context_prompt,
                },
            ]

            response = await llm.call_llm(
                provider=llm_provider,
                messages=messages,
                temperature=0.3,  # Lower temperature for more focused rewrites
                max_tokens=150,
            )

            # Extract rewritten query from response
            rewritten_query = self._extract_rewritten_query(response)

            return rewritten_query

        except Exception as e:
            logger.error(f"LLM expansion failed: {e}")
            raise RuntimeError(f"LLM query expansion failed: {e}")

    def _build_context_prompt(self, query: str, context: RewriteContext) -> str:
        """Build context prompt for LLM query expansion.

        Args:
            query: Original query
            context: Context information

        Returns:
            Context prompt string
        """
        prompt_parts = [
            f"Original query: '{query}'",
            "",
            "Relevant context:",
        ]

        # Add recent conversation context
        if context.recent_conversations:
            prompt_parts.append("Recent conversations:")
            for i, conv in enumerate(
                context.recent_conversations[:3]
            ):  # Last 3 conversations
                content_preview = conv.get("content", "")[:200]
                prompt_parts.append(f"  {i + 1}. {content_preview}...")

        # Add project context
        if context.project:
            prompt_parts.append(f"Project: {context.project}")

        # Add recent files context
        if context.recent_files:
            prompt_parts.append(f"Recent files: {', '.join(context.recent_files[:5])}")

        prompt_parts.extend(
            [
                "",
                "Task: Expand the original query to be more specific by incorporating relevant context from the conversation history.",
                "The expanded query should:",
                "  - Be self-contained (no pronouns like 'it', 'this', 'that' without clear antecedents)",
                "  - Include relevant project/file names if applicable",
                "  - Maintain the original intent of the query",
                "  - Be concise but descriptive",
                "",
                "Return only the expanded query text, no explanation.",
            ]
        )

        return "\n".join(prompt_parts)

    def _extract_rewritten_query(self, llm_response: str) -> str:
        """Extract rewritten query from LLM response.

        Args:
            llm_response: Raw LLM response

        Returns:
            Cleaned rewritten query string
        """
        # Remove common prefixes/suffixes
        response = llm_response.strip()

        # Remove quotes if present
        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1]
        elif response.startswith("'") and response.endswith("'"):
            response = response[1:-1]

        # Remove explanatory prefixes
        prefixes_to_remove = [
            "Expanded query:",
            "Rewritten query:",
            "The expanded query is:",
            "Query:",
        ]

        for prefix in prefixes_to_remove:
            if response.lower().startswith(prefix.lower()):
                response = response[len(prefix) :].strip()
                break

        return response

    def _compute_cache_key(self, query: str, project: str | None) -> str:
        """Compute cache key for rewritten query.

        Args:
            query: Original query string
            project: Optional project filter

        Returns:
            Cache key string
        """
        import hashlib

        key_string = f"{query}|{project or ''}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    async def _get_llm_provider(self) -> str | None:
        """Get available LLM provider.

        Returns:
            LLM provider name or None if unavailable
        """
        try:
            from session_buddy.di import depends

            llm = depends.get_sync("LLMManager")
            if not llm:
                return None

            # Get available providers
            providers = llm.list_providers()
            if providers and len(providers) > 0:
                # Return first available provider
                provider = providers[0]
                return str(provider) if provider is not None else None

            return None

        except Exception as e:
            logger.warning(f"Failed to get LLM provider: {e}")
            return None

    def get_stats(self) -> dict[str, Any]:
        """Get query rewriting statistics.

        Returns:
            Dictionary with rewriting metrics
        """
        cache_size = len(self._cache)

        return {
            "total_rewrites": self._stats["total_rewrites"],
            "cache_hits": self._stats["cache_hits"],
            "cache_hit_rate": (
                self._stats["cache_hits"] / self._stats["total_rewrites"]
                if self._stats["total_rewrites"] > 0
                else 0.0
            ),
            "llm_failures": self._stats["llm_failures"],
            "avg_latency_ms": self._stats["avg_latency_ms"],
            "cache_size": cache_size,
        }

    def clear_cache(self) -> None:
        """Clear rewrite cache."""
        self._cache.clear()
        logger.info("Rewrite cache cleared")
