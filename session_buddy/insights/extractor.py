"""
Rule-based insight extraction from conversations.

This module implements pattern-based extraction of educational insights from
explanatory mode conversations, using heuristics and keyword matching.

Key Features:
- Detects insights marked with special delimiters (★ Insight)
- Extracts topics using keyword matching
- Calculates confidence scores based on multiple signals
- Supports both full conversation and single-response extraction

Design Philosophy:
- Rule-based over AI extraction (deterministic, testable)
- Conservative extraction (better to miss than to hallucinate)
- High-signal insights only (quality over quantity)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

# Constants
INSIGHT_DELIMITER_START: Final[str] = "`★ Insight ─────────────────────────────────────"
INSIGHT_DELIMITER_END: Final[str] = "`─────────────────────────────────────────────────"
MIN_INSIGHT_LENGTH: Final[int] = 30  # Minimum characters to qualify
MAX_INSIGHT_LENGTH: Final[int] = 10000  # Maximum characters (security limit)

# Topic keyword mappings for classification
TOPIC_KEYWORDS: Final[dict[str, list[str]]] = {
    "async": ["async", "await", "asyncio", "coroutine", "future", "task"],
    "database": ["database", "sql", "query", "transaction", "orm", "duckdb"],
    "testing": ["test", "pytest", "mock", "fixture", "assert", "coverage"],
    "api": ["api", "endpoint", "http", "rest", "graphql", "request", "response"],
    "security": [
        "security",
        "authentication",
        "authorization",
        "csrf",
        "xss",
        "injection",
    ],
    "performance": ["performance", "optimization", "caching", "latency", "throughput"],
    "python": ["python", "pip", "virtualenv", "package", "module", "import"],
    "architecture": [
        "architecture",
        "design",
        "pattern",
        "structure",
        "layer",
        "component",
    ],
    "error-handling": ["error", "exception", "try", "except", "raise", "catch"],
    "logging": ["log", "logger", "debug", "info", "warn", "error"],
    "type-safety": ["type", "hint", "annotation", "pydantic", "validation"],
    "async-patterns": ["async/await", "async def", "awaitable", "concurrent"],
}

# Insight type patterns for classification
INSIGHT_TYPE_PATTERNS: Final[dict[str, list[str]]] = {
    "pattern": [
        r"pattern",
        r"approach",
        r"strategy",
        r"idiom",
        r"best practice",
    ],
    "architecture": [
        r"architecture",
        r"design",
        r"structure",
        r"component",
        r"layer",
    ],
    "best_practice": [
        r"should",
        r"recommend",
        r"avoid",
        r"prefer",
        r"best practice",
    ],
    "gotcha": [
        r"gotcha",
        r"pitfall",
        r"common mistake",
        r"watch out",
        r"be careful",
    ],
    "general": [],  # Default fallback
}


@dataclass
class ExtractedInsight:
    """
    Represents an insight extracted from conversation content.

    Attributes:
        content: The insight text (educational pattern or best practice)
        insight_type: Category (pattern, architecture, best_practice, gotcha, general)
        topics: Topic tags for categorization
        confidence: Extraction confidence score (0.0 to 1.0)
        source_conversation_id: ID of conversation that generated this insight
        source_reflection_id: ID of reflection that generated this insight
        quality_score: Estimated quality score (0.0 to 1.0)
        extracted_at: Timestamp when insight was extracted

    """

    content: str
    insight_type: str = "general"
    topics: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source_conversation_id: str | None = None
    source_reflection_id: str | None = None
    quality_score: float = 0.5
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate insight after construction."""
        # Trim whitespace from content
        if self.content:
            object.__setattr__(self, "content", self.content.strip())

        # Validate content length
        if not (MIN_INSIGHT_LENGTH <= len(self.content) <= MAX_INSIGHT_LENGTH):
            msg = (
                f"Insight content length must be between {MIN_INSIGHT_LENGTH} "
                f"and {MAX_INSIGHT_LENGTH} characters (got {len(self.content)})"
            )
            raise ValueError(msg)

        # Validate scores
        if not (0.0 <= self.confidence <= 1.0):
            msg = f"Confidence must be 0.0-1.0 (got {self.confidence})"
            raise ValueError(msg)

        if not (0.0 <= self.quality_score <= 1.0):
            msg = f"Quality score must be 0.0-1.0 (got {self.quality_score})"
            raise ValueError(msg)


def extract_insights_from_response(
    response_content: str,
    conversation_id: str | None = None,
    reflection_id: str | None = None,
    min_confidence: float = 0.3,
) -> list[ExtractedInsight]:
    """
    Extract insights from a single assistant response.

    This is the core extraction function that parses response content for
    insights marked with special delimiters (★ Insight).

    Args:
        response_content: The assistant's response text to parse
        conversation_id: Optional source conversation ID for tracking
        reflection_id: Optional source reflection ID for tracking
        min_confidence: Minimum confidence threshold for extraction (0.0-1.0)

    Returns:
        List of extracted insights (empty if none found or below threshold)

    Example:
        ```python
        response = '''
        Some explanation text.

        `★ Insight ─────────────────────────────────────`
        Always use async/await for database operations to prevent blocking
        `─────────────────────────────────────────────────`

        More text here.
        '''

        insights = extract_insights_from_response(response)
        assert len(insights) == 1
        assert "async/await" in insights[0].content
        ```

    """
    insights: list[ExtractedInsight] = []

    # Split response by insight delimiter patterns
    # Pattern matches both start and end delimiters
    pattern = (
        re.escape(INSIGHT_DELIMITER_START) + r"(.*?)" + re.escape(INSIGHT_DELIMITER_END)
    )
    matches = re.findall(pattern, response_content, re.DOTALL)

    for match in matches:
        # Extract insight content
        content = match.strip()

        # Skip if too short (likely false positive)
        if len(content) < MIN_INSIGHT_LENGTH:
            continue

        # Skip if too long (security limit)
        if len(content) > MAX_INSIGHT_LENGTH:
            continue

        # Detect insight type
        insight_type = detect_insight_type(content)

        # Extract topics
        topics = extract_topics(content)

        # Calculate confidence score
        confidence = calculate_confidence_score(content, insight_type, topics)

        # Apply minimum confidence threshold
        if confidence < min_confidence:
            continue

        # Estimate quality score (conservative estimate)
        quality_score = estimate_quality_score(content, topics, confidence)

        # Create extracted insight
        insight = ExtractedInsight(
            content=content,
            insight_type=insight_type,
            topics=topics,
            confidence=confidence,
            source_conversation_id=conversation_id,
            source_reflection_id=reflection_id,
            quality_score=quality_score,
        )

        insights.append(insight)

    return insights


def _extract_conversation_insights(
    conversation_history: list[object],
    conversation_id: object,
    min_confidence: float,
) -> list[ExtractedInsight]:
    """Extract insights from conversation history entries.

    Args:
        conversation_history: List of conversation entries
        conversation_id: Session conversation identifier
        min_confidence: Minimum confidence threshold

    Returns:
        List of insights extracted from conversation entries

    """
    insights: list[ExtractedInsight] = []

    for entry in conversation_history:
        if not isinstance(entry, dict):
            continue

        if entry.get("role") != "assistant":
            continue

        response_content = entry.get("content", "")
        if not isinstance(response_content, str):
            continue

        conv_id = str(conversation_id) if conversation_id is not None else None
        entry_insights = extract_insights_from_response(
            response_content=response_content,
            conversation_id=conv_id,
            min_confidence=min_confidence,
        )
        insights.extend(entry_insights)

    return insights


def _extract_reflection_insights(
    recent_reflections: list[object],
    conversation_id: object,
    min_confidence: float,
) -> list[ExtractedInsight]:
    """Extract insights from recent reflections.

    Args:
        recent_reflections: List of reflection entries
        conversation_id: Session conversation identifier
        min_confidence: Minimum confidence threshold

    Returns:
        List of insights extracted from reflections

    """
    insights: list[ExtractedInsight] = []

    for reflection in recent_reflections:
        if not isinstance(reflection, dict):
            continue

        reflection_content = reflection.get("content", "")
        if not isinstance(reflection_content, str):
            continue

        conv_id = str(conversation_id) if conversation_id is not None else None
        reflection_insights = extract_insights_from_response(
            response_content=reflection_content,
            conversation_id=conv_id,
            reflection_id=reflection.get("id"),
            min_confidence=min_confidence,
        )
        insights.extend(reflection_insights)

    return insights


def _deduplicate_insights(
    insights: list[ExtractedInsight],
) -> list[ExtractedInsight]:
    """Remove duplicate insights by content.

    Args:
        insights: List of insights to deduplicate

    Returns:
        List of unique insights (first occurrence kept)

    """
    seen_content: set[str] = set()
    unique_insights: list[ExtractedInsight] = []

    for insight in insights:
        content_normalized = insight.content.lower().strip()
        if content_normalized not in seen_content:
            seen_content.add(content_normalized)
            unique_insights.append(insight)

    return unique_insights


def extract_insights_from_context(
    context: dict[str, object],
    project: str | None = None,
    min_confidence: float = 0.3,
) -> list[ExtractedInsight]:
    """
    Extract insights from full session context.

    This function extracts insights from the complete session context,
    including conversation history and recent reflections.

    Args:
        context: Session context dictionary from session_manager
        project: Optional project name for filtering/project association
        min_confidence: Minimum confidence threshold for extraction (0.0-1.0)

    Returns:
        List of extracted insights from all context sources

    Example:
        ```python
        from session_buddy.core.session_manager import SessionManager

        async with SessionManager() as manager:
            context = manager.session_context

            insights = await extract_insights_from_context(
                context=context, project="session-buddy"
            )

            print(f"Extracted {len(insights)} insights")
        ```

    """
    all_insights: list[ExtractedInsight] = []

    # Extract from conversation history
    conversation_history = context.get("conversation_history", [])
    if isinstance(conversation_history, list):
        conversation_id = context.get("conversation_id")
        insights = _extract_conversation_insights(
            conversation_history, conversation_id, min_confidence
        )
        all_insights.extend(insights)

    # Extract from recent reflections
    recent_reflections = context.get("recent_reflections", [])
    if isinstance(recent_reflections, list):
        conversation_id = context.get("conversation_id")
        insights = _extract_reflection_insights(
            recent_reflections, conversation_id, min_confidence
        )
        all_insights.extend(insights)

    # Deduplicate insights by content
    return _deduplicate_insights(all_insights)


def detect_insight_type(content: str) -> str:
    """
    Detect the type of insight based on content patterns.

    Uses keyword matching to classify insights into categories:
    - pattern: Reusable approaches and strategies
    - architecture: Design and structure guidance
    - best_practice: Recommendations and guidelines
    - gotcha: Common pitfalls and mistakes
    - general: Default fallback

    Args:
        content: Insight content to classify

    Returns:
        Detected insight type (default: "general")

    Example:
        ```python
        detect_insight_type("Use async/await for I/O operations")
        # Returns: "pattern"

        detect_insight_type("Watch out for this common mistake")
        # Returns: "gotcha"
        ```

    """
    content_lower = content.lower()

    # Check each insight type pattern with flexible matching
    for insight_type, patterns in INSIGHT_TYPE_PATTERNS.items():
        for pattern in patterns:
            # Use word boundaries for single words, substring for phrases
            if " " in pattern:
                # Phrase matching (contains, not word boundary)
                if pattern in content_lower:
                    return insight_type
            # Single word matching with word boundary
            elif re.search(r"\b" + pattern + r"\b", content_lower):
                return insight_type

    # Default to general if no patterns match
    return "general"


def extract_topics(content: str) -> list[str]:
    """
    Extract topic tags from insight content using keyword matching.

    Identifies relevant topics based on keyword presence:
    - async, database, testing, api, security
    - performance, python, architecture, error-handling
    - logging, type-safety, async-patterns

    Args:
        content: Insight content to analyze

    Returns:
        List of detected topics (sorted by relevance)

    Example:
        ```python
        extract_topics("Use async/await for database operations")
        # Returns: ["async", "database"]
        ```

    """
    content_lower = content.lower()
    detected_topics: list[str] = []

    # Check each topic category
    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword in content_lower:
                detected_topics.append(topic)
                break  # Only add each topic once

    return detected_topics


def calculate_confidence_score(
    content: str,
    insight_type: str,
    topics: list[str],
) -> float:
    """
    Calculate confidence score for extracted insight.

    Higher confidence indicates:
    - Clear educational structure (imperative verbs, explanations)
    - Good topic coverage (relevant keywords present)
    - Strong signal patterns (not generic advice)

    Confidence Score Factors:
    - Base score: 0.3 (all insights start with minimum confidence)
    - Topic coverage: +0.1 per topic (max +0.3)
    - Strong patterns: +0.2 for clear imperatives ("always", "never", "use")
    - Length factor: +0.1 for good length (50-500 chars)
    - Type specificity: +0.1 for specific types (pattern, architecture)

    Args:
        content: Insight content to score
        insight_type: Detected insight type
        topics: Detected topics

    Returns:
        Confidence score (0.0 to 1.0)

    Example:
        ```python
        calculate_confidence_score(
            content="Always use async/await for database operations",
            insight_type="pattern",
            topics=["async", "database"],
        )
        # Returns: ~0.8 (high confidence)
        ```

    """
    confidence = 0.3  # Base score

    # Topic coverage bonus (max +0.3)
    topic_bonus = min(len(topics) * 0.1, 0.3)
    confidence += topic_bonus

    # Strong pattern bonus (+0.2)
    strong_patterns = ["always", "never", "use", "avoid", "should", "recommend"]
    content_lower = content.lower()
    if any(pattern in content_lower for pattern in strong_patterns):
        confidence += 0.2

    # Length factor (+0.1)
    if 50 <= len(content) <= 500:
        confidence += 0.1

    # Type specificity bonus (+0.1)
    if insight_type in ("pattern", "architecture", "best_practice"):
        confidence += 0.1

    # Cap at 1.0
    return min(confidence, 1.0)


def estimate_quality_score(
    content: str,
    topics: list[str],
    confidence: float,
) -> float:
    """
    Estimate quality score for extracted insight.

    Quality is estimated conservatively based on available signals:
    - Content structure (clear explanations vs vague advice)
    - Topic relevance (specific vs generic)
    - Confidence score (extraction certainty)

    This is a rough estimate - true quality emerges from usage over time.

    Args:
        content: Insight content to evaluate
        topics: Detected topics
        confidence: Extraction confidence score

    Returns:
        Estimated quality score (0.0 to 1.0)

    """
    quality = 0.5  # Base score

    # Topic relevance bonus
    if len(topics) >= 2:
        quality += 0.2  # Good topic coverage

    # Content structure bonus
    if "because" in content.lower() or "reason" in content.lower():
        quality += 0.1  # Provides reasoning

    # Confidence factor
    quality += (confidence - 0.5) * 0.2  # Slight boost from high confidence

    # Cap at 1.0, floor at 0.3
    return max(0.3, min(quality, 1.0))


def normalize_insight_content(content: str) -> str:
    """
    Normalize insight content for deduplication hashing.

    Normalization includes:
    - Convert to lowercase
    - Strip leading/trailing whitespace
    - Remove extra whitespace within content
    - Remove common punctuation

    This helps catch near-duplicates with minor formatting differences.

    Args:
        content: Raw insight content to normalize

    Returns:
        Normalized content string suitable for hashing

    Example:
        ```python
        normalize_insight_content("Use async/await for I/O!")
        # Returns: "use asyncawait for io"
        ```

    """
    # Convert to lowercase
    normalized = content.lower()

    # Remove common punctuation (keep word structure)
    # Remove: .,!?;:"'()[]{}<>-/ (hyphen at end to avoid range)
    normalized = re.sub(r'[.,!?;:"\'()\[\]{}<>/-]', "", normalized)

    # Normalize whitespace (collapse multiple spaces to single space)
    normalized = re.sub(r"\s+", " ", normalized)

    # Strip leading/trailing whitespace
    return normalized.strip()


def generate_insight_hash(content: str) -> str:
    """
    Generate SHA-256 hash for insight deduplication.

    Uses normalized content to ensure near-duplicates are caught.

    Args:
        content: Raw insight content to hash

    Returns:
        Hexadecimal SHA-256 hash string

    Example:
        ```python
        hash1 = generate_insight_hash("Use async/await for I/O")
        hash2 = generate_insight_hash("Use async/await for I/O!")  # Same hash
        assert hash1 == hash2
        ```

    """
    normalized = normalize_insight_content(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def filter_duplicate_insights(
    insights: list[ExtractedInsight],
    seen_hashes: set[str] | None = None,
) -> tuple[list[ExtractedInsight], set[str]]:
    """
    Filter out duplicate insights based on content hashes.

    Maintains a set of seen hashes to prevent duplicates across multiple
    extraction calls during a session.

    Args:
        insights: List of extracted insights to filter
        seen_hashes: Optional set of previously seen hashes (for multi-call deduplication)

    Returns:
        Tuple of (unique_insights, updated_seen_hashes)

    Example:
        ```python
        insights = [insight1, insight2, insight3]
        unique_insights, seen_hashes = filter_duplicate_insights(insights)

        # Later in same session:
        more_insights = [insight4, insight1_duplicate]
        unique_more, updated_hashes = filter_duplicate_insights(
            more_insights, seen_hashes=seen_hashes
        )
        # unique_more contains only insight4 (insight1_duplicate filtered out)
        ```

    """
    if seen_hashes is None:
        seen_hashes = set()

    unique_insights: list[ExtractedInsight] = []

    for insight in insights:
        # Generate hash for this insight
        content_hash = generate_insight_hash(insight.content)

        # Skip if we've seen this content before
        if content_hash in seen_hashes:
            continue

        # Add to unique list and track hash
        unique_insights.append(insight)
        seen_hashes.add(content_hash)

    return unique_insights, seen_hashes
