"""
Console output utilities for insights extraction and injection.

Provides user-friendly console feedback during insight operations.
"""

import logging
from typing import Final

# ANSI color codes for terminal output
COLOR_GREEN: Final[str] = "\033[92m"  # Green
COLOR_BLUE: Final[str] = "\033[94m"  # Blue
COLOR_YELLOW: Final[str] = "\033[93m"  # Yellow
COLOR_RESET: Final[str] = "\033[0m"  # Reset

logger = logging.getLogger(__name__)


def log_insights_captured(count: int, source: str = "response") -> None:
    """
    Log when insights are extracted from a conversation.

    Args:
        count: Number of insights captured
        source: Source of insights (default: "response")

    Example:
        >>> log_insights_captured(3, "checkpoint")
        ✅ Captured 3 insights from checkpoint

    """
    if count > 0:
        source_str = f" from {source}" if source else ""
        print(
            f"{COLOR_GREEN}✅ Captured {count} insight{'' if count == 1 else 's'}{source_str}{COLOR_RESET}"
        )
        logger.info(f"Captured {count} insights from {source}")
    else:
        logger.debug(f"No insights captured from {source}")


def log_insights_injected(count: int, query: str = "") -> None:
    """
    Log when insights are injected into context.

    Args:
        count: Number of insights injected
        query: Original query that triggered injection

    Example:
        >>> log_insights_injected(2, "async patterns")
        💡 Injected 2 relevant insights from past sessions

    """
    if count > 0:
        query_str = (
            f" for '{query[:40]}{'...' if len(query) > 40 else ''}'" if query else ""
        )
        print(
            f"{COLOR_BLUE}💡 Injected {count} relevant insight{'' if count == 1 else 's'} from past sessions{query_str}{COLOR_RESET}"
        )
        logger.info(f"Injected {count} insights for query")
    else:
        print(
            f"{COLOR_YELLOW}💭 No relevant insights found for this query{COLOR_RESET}"
        )
        logger.info("No insights injected - none found")


def log_insights_pruned(count: int, reason: str = "") -> None:
    """
    Log when insights are pruned during maintenance.

    Args:
        count: Number of insights pruned
        reason: Reason for pruning (age, quality, etc.)

    Example:
        >>> log_insights_pruned(5, "low quality and unused")
        🗑️ Pruned 5 stale insights (low quality and unused)

    """
    if count > 0:
        reason_str = f" ({reason})" if reason else ""
        print(
            f"{COLOR_YELLOW}🗑️ Pruned {count} stale insight{'' if count == 1 else 's'}{reason_str}{COLOR_RESET}"
        )
        logger.info(f"Pruned {count} insights: {reason}")
    else:
        logger.debug("No insights pruned")


def log_insight_statistics(stats: dict[str, int]) -> None:
    """
    Log insight statistics summary.

    Args:
        stats: Dictionary with stats (total, avg_quality, etc.)

    Example:
        >>> log_insight_statistics({"total": 100, "avg_quality": 0.75})
        📊 Insights: 100 total, quality: 75%, avg usage: 3.2

    """
    total = stats.get("total", 0)
    avg_quality = stats.get("avg_quality", 0.0)
    avg_usage = stats.get("avg_usage", 0.0)

    quality_pct = int(avg_quality * 100)
    print(
        f"{COLOR_BLUE}📊 Insights: {total} total, quality: {quality_pct}%, avg usage: {avg_usage:.1f}{COLOR_RESET}"
    )
    logger.info(
        f"Insight stats: {total} total, quality {quality_pct}%, usage {avg_usage:.1f}"
    )


def log_extraction_error(error: str, details: str | None = None) -> None:
    """
    Log when insight extraction fails (graceful degradation).

    Args:
        error: Error message
        details: Optional additional details

    Example:
        >>> log_extraction_error("Embedding generation failed", "Model not loaded")
        ⚠️ Insight extraction failed (continuing): Embedding generation failed

    """
    details_str = f": {details}" if details else ""
    print(
        f"{COLOR_YELLOW}⚠️ Insight extraction failed (continuing){details_str}{COLOR_RESET}"
    )
    logger.warning(f"Insight extraction error: {error}{details_str}")


def log_search_error(error: str) -> None:
    """
    Log when insight search fails (graceful degradation).

    Args:
        error: Error message

    Example:
        >>> log_search_error("Database connection failed")
        ⚠️ Failed to load insights (database error)

    """
    print(f"{COLOR_YELLOW}⚠️ Failed to load insights ({error}){COLOR_RESET}")
    logger.warning(f"Insight search error: {error}")


# Convenience wrappers for common scenarios


def log_manual_capture(topic: str) -> None:
    """Log when user manually captures an insight via MCP tool."""
    print(f"{COLOR_GREEN}✅ Manually captured insight: {topic}{COLOR_RESET}")
    logger.info(f"Manual insight capture: {topic}")


def log_auto_capture_detected(count: int) -> None:
    """Log when insights are auto-detected during extraction."""
    if count > 0:
        print(
            f"{COLOR_GREEN}🔍 Auto-detected {count} insight{'' if count == 1 else 's'} in this response{COLOR_RESET}"
        )
        logger.info(f"Auto-detected {count} insights")


def log_no_insights_found(query: str = "") -> None:
    """Log when no insights are found for a query."""
    query_str = (
        f" for '{query[:30]}...'"
        if len(query) > 30
        else f" for '{query}'"
        if query
        else ""
    )
    print(f"{COLOR_YELLOW}💭 No relevant insights found{query_str}{COLOR_RESET}")
    logger.info(f"No insights found{query_str}")
