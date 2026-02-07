"""Recommendation engine for learning from crackerjack execution history."""

import re
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .agent_analyzer import AgentRecommendation, AgentType


@dataclass
class FailurePattern:
    """Detected failure pattern from historical executions."""

    pattern_signature: str  # Unique identifier for the pattern
    occurrences: int
    last_seen: datetime
    successful_fixes: list[AgentType]  # Agents that successfully fixed this pattern
    failed_fixes: list[AgentType]  # Agents that failed to fix this pattern
    avg_fix_time: float  # Average time to fix in seconds


@dataclass
class AgentEffectiveness:
    """Track effectiveness of an agent over time."""

    agent: AgentType
    total_recommendations: int
    successful_fixes: int
    failed_fixes: int
    avg_confidence: float
    success_rate: float  # 0.0-1.0


class RecommendationEngine:
    """Learn from execution history to improve recommendations."""

    @classmethod
    async def _get_cached_result(cls, project: str, days: int) -> dict[str, Any] | None:
        """Get cached analysis result if available."""
        from .history_cache import get_cache

        cache = get_cache()
        return await cache.get(project, days)

    @classmethod
    def _filter_results_by_date(
        cls,
        results: list[dict[str, Any]],
        start_date: datetime,
    ) -> list[dict[str, Any]]:
        """Filter results by date range."""
        filtered_results = []
        for result in results:
            timestamp_str = result.get("timestamp")
            if timestamp_str:
                try:
                    if isinstance(timestamp_str, str):
                        result_date = datetime.fromisoformat(timestamp_str)
                    else:
                        result_date = timestamp_str
                    if result_date >= start_date:
                        filtered_results.append(result)
                except (ValueError, AttributeError):
                    filtered_results.append(result)

        return filtered_results

    @classmethod
    async def _cache_result(
        cls,
        project: str,
        days: int,
        result: dict[str, Any],
    ) -> None:
        """Cache analysis result."""
        from .history_cache import get_cache

        cache = get_cache()
        await cache.set(project, days, result)

    @classmethod
    async def analyze_history(
        cls,
        db: Any,  # ReflectionDatabase
        project: str,
        days: int = 30,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Analyze execution history for patterns and effectiveness.

        Args:
            db: ReflectionDatabase instance
            project: Project name
            days: Number of days to analyze
            use_cache: Whether to use cached results (default: True)

        Returns:
            Dictionary with patterns, agent effectiveness, and insights

        """
        # Check cache first
        if use_cache:
            if cached_result := await cls._get_cached_result(project, days):
                return cached_result

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Search for crackerjack executions with agent recommendations
        results = await db.search_conversations(
            query="crackerjack agent_recommendations",
            project=project,
            limit=100,
        )

        # Filter by date
        filtered_results = cls._filter_results_by_date(results, start_date)

        # Extract patterns and effectiveness
        patterns = cls._extract_patterns(filtered_results)
        effectiveness = cls._calculate_agent_effectiveness(filtered_results)
        insights = cls._generate_insights(patterns, effectiveness)

        analysis_result: dict[str, Any] = {
            "patterns": patterns,
            "agent_effectiveness": effectiveness,
            "insights": insights,
            "total_executions": len(filtered_results),
            "date_range": {"start": start_date, "end": end_date},
        }

        # Cache the result
        if use_cache:
            await cls._cache_result(project, days, analysis_result)

        return analysis_result

    @classmethod
    def _update_timestamp(
        cls,
        pattern_data: dict[str, dict[str, Any]],
        signature: str,
        timestamp_str: str | None,
    ) -> None:
        """Update last seen timestamp for pattern."""
        if not timestamp_str:
            return

        with suppress(ValueError, AttributeError):  # FURB107
            timestamp = (
                datetime.fromisoformat(timestamp_str)
                if isinstance(timestamp_str, str)
                else timestamp_str
            )
            if (
                not pattern_data[signature]["last_seen"]
                or timestamp > pattern_data[signature]["last_seen"]
            ):
                pattern_data[signature]["last_seen"] = timestamp

    @classmethod
    def _track_agent_fixes(
        cls,
        pattern_data: dict[str, dict[str, Any]],
        signature: str,
        recommendations: list[dict[str, Any]],
        next_metadata: dict[str, Any],
    ) -> None:
        """Track agent recommendation success/failure."""
        next_exit_code = next_metadata.get("exit_code", 1)

        for rec in recommendations:
            agent_name = rec.get("agent")
            if not agent_name:
                continue

            with suppress(ValueError):  # FURB107
                agent = AgentType(agent_name)
                if next_exit_code == 0:
                    pattern_data[signature]["successful_fixes"].append(agent)
                    if exec_time := next_metadata.get("execution_time"):
                        pattern_data[signature]["fix_times"].append(exec_time)
                else:
                    pattern_data[signature]["failed_fixes"].append(agent)

    @classmethod
    def _extract_patterns(cls, results: list[dict[str, Any]]) -> list[FailurePattern]:
        """Extract failure patterns from execution history."""
        pattern_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "occurrences": 0,
                "last_seen": None,
                "successful_fixes": [],
                "failed_fixes": [],
                "fix_times": [],
            },
        )

        for i, result in enumerate(results):
            metadata = result.get("metadata", {})
            content = result.get("content", "")

            signature = cls._generate_signature(content, metadata)
            if not signature:
                continue

            pattern_data[signature]["occurrences"] += 1
            cls._update_timestamp(pattern_data, signature, result.get("timestamp"))

            recommendations = metadata.get("agent_recommendations", [])
            if recommendations and i + 1 < len(results):
                next_metadata = results[i + 1].get("metadata", {})
                cls._track_agent_fixes(
                    pattern_data,
                    signature,
                    recommendations,
                    next_metadata,
                )

        # Convert to FailurePattern objects
        patterns = [
            FailurePattern(
                pattern_signature=signature,
                occurrences=data["occurrences"],
                last_seen=data["last_seen"] or datetime.now(),
                successful_fixes=data["successful_fixes"],
                failed_fixes=data["failed_fixes"],
                avg_fix_time=(
                    sum(data["fix_times"]) / len(data["fix_times"])
                    if data["fix_times"]
                    else 0.0
                ),
            )
            for signature, data in pattern_data.items()
        ]

        return sorted(patterns, key=lambda p: p.occurrences, reverse=True)

    @classmethod
    def _process_recommendation(
        cls,
        rec: dict[str, Any],
        next_exit_code: int,
        agent_stats: dict[AgentType, dict[str, Any]],
    ) -> None:
        """Process a single recommendation and update stats."""
        agent_name = rec.get("agent")
        if not agent_name:
            return

        with suppress(ValueError):  # FURB107
            agent = AgentType(agent_name)
            agent_stats[agent]["total_recommendations"] += 1
            agent_stats[agent]["confidences"].append(rec.get("confidence", 0.0))

            if next_exit_code == 0:
                agent_stats[agent]["successful_fixes"] += 1
            else:
                agent_stats[agent]["failed_fixes"] += 1

    @classmethod
    def _create_effectiveness(
        cls,
        agent: AgentType,
        stats: dict[str, Any],
    ) -> AgentEffectiveness | None:
        """Create AgentEffectiveness from stats dict."""
        total = stats["total_recommendations"]
        if total == 0:
            return None

        successful = stats["successful_fixes"]
        success_rate = successful / total
        avg_confidence = (
            sum(stats["confidences"]) / len(stats["confidences"])
            if stats["confidences"]
            else 0.0
        )

        return AgentEffectiveness(
            agent=agent,
            total_recommendations=total,
            successful_fixes=successful,
            failed_fixes=stats["failed_fixes"],
            avg_confidence=avg_confidence,
            success_rate=success_rate,
        )

    @classmethod
    def _calculate_agent_effectiveness(
        cls,
        results: list[dict[str, Any]],
    ) -> list[AgentEffectiveness]:
        """Calculate effectiveness metrics for each agent."""
        agent_stats: dict[AgentType, dict[str, Any]] = defaultdict(
            lambda: {
                "total_recommendations": 0,
                "successful_fixes": 0,
                "failed_fixes": 0,
                "confidences": [],
            },
        )

        for i, result in enumerate(results):
            metadata = result.get("metadata", {})
            recommendations = metadata.get("agent_recommendations", [])

            if recommendations and i + 1 < len(results):
                next_exit_code = results[i + 1].get("metadata", {}).get("exit_code", 1)
                for rec in recommendations:
                    cls._process_recommendation(rec, next_exit_code, agent_stats)

        # Convert to AgentEffectiveness objects
        effectiveness = [
            eff
            for agent, stats in agent_stats.items()
            if (eff := cls._create_effectiveness(agent, stats)) is not None
        ]

        return sorted(effectiveness, key=lambda e: e.success_rate, reverse=True)

    @classmethod
    def _generate_signature(cls, content: str, metadata: dict[str, Any]) -> str:
        """Generate unique signature for a failure pattern."""
        # Extract key error indicators
        exit_code = metadata.get("exit_code", 0)
        if exit_code == 0:
            return ""  # Not a failure

        metrics = metadata.get("metrics", {})

        # Build signature from error characteristics
        signature_parts = []

        # Complexity violations
        if metrics.get("complexity_violations", 0) > 0:
            signature_parts.append(f"complexity:{metrics['max_complexity']}")

        # Security issues
        if metrics.get("security_issues", 0) > 0:
            signature_parts.append(f"security:{metrics['security_issues']}")

        # Test failures
        if metrics.get("tests_failed", 0) > 0:
            signature_parts.append(f"test_failures:{metrics['tests_failed']}")

        # Type errors
        if metrics.get("type_errors", 0) > 0:
            signature_parts.append(f"type_errors:{metrics['type_errors']}")

        # Formatting issues
        if metrics.get("formatting_issues", 0) > 0:
            signature_parts.append("formatting")

        # Extract specific error patterns from content
        error_patterns = [
            r"B\d{3}",  # Bandit codes
            r"E\d{3}",  # Ruff codes
            r"F\d{3}",  # Pyflakes codes
        ]

        for pattern in error_patterns:
            matches = re.findall(  # REGEX OK: error code extraction from patterns
                pattern,
                content,
            )
            if matches:
                signature_parts.extend(sorted(set(matches))[:3])  # Top 3 unique codes

        return "|".join(signature_parts) if signature_parts else "unknown_failure"

    @classmethod
    def _get_pattern_insights(cls, patterns: list[FailurePattern]) -> list[str]:
        """Generate insights from failure patterns."""
        if not patterns:
            return []

        insights = []
        most_common = patterns[0]
        insights.append(
            f"🔄 Most common failure: '{most_common.pattern_signature}' "
            f"({most_common.occurrences} occurrences)",
        )

        recent_patterns = [
            p for p in patterns if (datetime.now() - p.last_seen).days <= 7
        ]
        if len(recent_patterns) > 3:
            insights.append(
                f"⚠️ {len(recent_patterns)} different failure patterns in last 7 days - "
                f"consider addressing root causes",
            )

        return insights

    @classmethod
    def _get_effectiveness_insights(
        cls,
        effectiveness: list[AgentEffectiveness],
    ) -> list[str]:
        """Generate insights from agent effectiveness."""
        if not effectiveness:
            return []

        insights = []
        top_agent = effectiveness[0]
        if top_agent.success_rate >= 0.8:
            insights.append(
                f"⭐ {top_agent.agent.value} has {top_agent.success_rate:.0%} success rate - "
                f"highly effective!",
            )

        low_performers = [e for e in effectiveness if e.success_rate < 0.3]
        if low_performers:
            agents = ", ".join(e.agent.value for e in low_performers[:2])
            insights.append(
                f"📉 Low success rate for: {agents} - "
                f"review recommendations or patterns",
            )

        return insights

    @classmethod
    def _get_cross_pattern_insights(
        cls,
        patterns: list[FailurePattern],
        effectiveness: list[AgentEffectiveness],
    ) -> list[str]:
        """Generate insights from pattern-effectiveness correlation."""
        if not (patterns and effectiveness):
            return []

        reliable_fixes = [
            p
            for p in patterns
            if p.successful_fixes and not p.failed_fixes and p.occurrences >= 2
        ]

        if reliable_fixes:
            return [
                f"✅ {len(reliable_fixes)} patterns have consistent successful fixes - "
                f"good agent-pattern matching",
            ]
        return []

    @classmethod
    def _generate_insights(
        cls,
        patterns: list[FailurePattern],
        effectiveness: list[AgentEffectiveness],
    ) -> list[str]:
        """Generate actionable insights from patterns and effectiveness data."""
        insights = (
            cls._get_pattern_insights(patterns)
            + cls._get_effectiveness_insights(effectiveness)
            + cls._get_cross_pattern_insights(patterns, effectiveness)
        )

        if not insights:
            insights.append(
                "📊 Insufficient data - continue using AI mode to build history",
            )

        return insights

    @classmethod
    def _adjust_single_recommendation(
        cls,
        rec: AgentRecommendation,
        agent_eff: AgentEffectiveness | None,
    ) -> AgentRecommendation:
        """Adjust a single recommendation based on effectiveness data."""
        if not agent_eff or agent_eff.total_recommendations < 5:
            return rec  # Not enough data

        # Blend original and learned confidence (60% learned, 40% original)
        adjusted_confidence = min(
            (0.6 * agent_eff.success_rate) + (0.4 * rec.confidence),
            1.0,
        )

        return AgentRecommendation(
            agent=rec.agent,
            confidence=adjusted_confidence,
            reason=f"{rec.reason} (adjusted based on {agent_eff.success_rate:.0%} historical success)",
            quick_fix_command=rec.quick_fix_command,
            pattern_matched=rec.pattern_matched,
        )

    @classmethod
    def adjust_confidence(
        cls,
        recommendations: list[AgentRecommendation],
        effectiveness: list[AgentEffectiveness],
    ) -> list[AgentRecommendation]:
        """Adjust recommendation confidence scores based on historical effectiveness.

        Args:
            recommendations: Original recommendations from AgentAnalyzer
            effectiveness: Historical effectiveness data

        Returns:
            Recommendations with adjusted confidence scores

        """
        effectiveness_map = {e.agent: e for e in effectiveness}

        adjusted = [
            cls._adjust_single_recommendation(rec, effectiveness_map.get(rec.agent))
            for rec in recommendations
        ]

        return sorted(adjusted, key=lambda r: r.confidence, reverse=True)[:3]
