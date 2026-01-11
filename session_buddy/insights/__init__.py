"""
Insights Capture & Extraction System.

This package provides automatic extraction of educational insights from
explanatory mode conversations, with semantic embeddings for intelligent retrieval.

Components:
- extractor: Rule-based insight extraction from conversation context
- models: Pydantic data models with security validation

Example:
    ```python
    from session_buddy.insights.extractor import extract_insights_from_context

    insights = await extract_insights_from_context(
        context=session_context, project="session-buddy"
    )

    for insight in insights:
        print(f"Found: {insight.content} (confidence: {insight.confidence})")
    ```

"""

from session_buddy.insights.extractor import (
    calculate_confidence_score,
    detect_insight_type,
    extract_insights_from_context,
    extract_insights_from_response,
    extract_topics,
    filter_duplicate_insights,
    generate_insight_hash,
    normalize_insight_content,
)

__all__ = [
    "calculate_confidence_score",
    "detect_insight_type",
    "extract_insights_from_context",
    "extract_insights_from_response",
    "extract_topics",
    "filter_duplicate_insights",
    "generate_insight_hash",
    "normalize_insight_content",
]
