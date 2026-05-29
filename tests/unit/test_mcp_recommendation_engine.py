from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from session_buddy.mcp.tools.advanced.recommendation_engine import (
    AgentEffectiveness,
    FailurePattern,
    RecommendationEngine,
)
from session_buddy.mcp.tools.intelligence.agent_analyzer import (
    AgentRecommendation,
    AgentType,
)


def test_mcp_recommendation_engine_filters_dates_and_tracks_agents() -> None:
    start_date = datetime(2026, 1, 10, 0, 0, 0)
    results = [
        {"timestamp": "2026-01-09T23:59:59", "content": "old"},
        {"timestamp": "2026-01-10T00:00:00", "content": "boundary"},
        {"timestamp": datetime(2026, 1, 11, 12, 0, 0), "content": "datetime"},
        {"timestamp": "not-a-date", "content": "invalid"},
    ]
    filtered = RecommendationEngine._filter_results_by_date(results, start_date)
    assert [item["content"] for item in filtered] == [
        "boundary",
        "datetime",
        "invalid",
    ]

    pattern_data = defaultdict(
        lambda: {
            "occurrences": 0,
            "last_seen": None,
            "successful_fixes": [],
            "failed_fixes": [],
            "fix_times": [],
        }
    )
    signature = "sig-1"
    pattern_data[signature]["last_seen"] = datetime(2026, 1, 1, 0, 0, 0)

    RecommendationEngine._update_timestamp(
        pattern_data, signature, "2026-01-02T00:00:00"
    )
    RecommendationEngine._track_agent_fixes(
        pattern_data,
        signature,
        [
            {"agent": AgentType.REFACTORING.value, "confidence": 0.8},
            {"confidence": 0.1},
            {"agent": "not-real", "confidence": 0.2},
        ],
        {"exit_code": 0, "execution_time": 13.5},
    )
    RecommendationEngine._track_agent_fixes(
        pattern_data,
        signature,
        [{"agent": AgentType.REFACTORING.value, "confidence": 0.8}],
        {"exit_code": 1},
    )

    assert pattern_data[signature]["last_seen"] == datetime(2026, 1, 2, 0, 0, 0)
    assert pattern_data[signature]["successful_fixes"] == [AgentType.REFACTORING]
    assert pattern_data[signature]["failed_fixes"] == [AgentType.REFACTORING]
    assert pattern_data[signature]["fix_times"] == [13.5]


def test_mcp_recommendation_engine_pattern_and_effectiveness_insights() -> None:
    now = datetime.now()
    patterns = [
        FailurePattern(
            pattern_signature="complexity:18",
            occurrences=4,
            last_seen=now - timedelta(days=1),
            successful_fixes=[AgentType.REFACTORING],
            failed_fixes=[],
            avg_fix_time=12.0,
        ),
        FailurePattern(
            pattern_signature="security:1",
            occurrences=3,
            last_seen=now - timedelta(days=2),
            successful_fixes=[AgentType.SECURITY],
            failed_fixes=[],
            avg_fix_time=0.0,
        ),
        FailurePattern(
            pattern_signature="test_failures:3",
            occurrences=2,
            last_seen=now - timedelta(days=3),
            successful_fixes=[],
            failed_fixes=[],
            avg_fix_time=0.0,
        ),
        FailurePattern(
            pattern_signature="type_errors:2",
            occurrences=2,
            last_seen=now - timedelta(days=4),
            successful_fixes=[],
            failed_fixes=[],
            avg_fix_time=0.0,
        ),
    ]
    effectiveness = [
        AgentEffectiveness(
            agent=AgentType.REFACTORING,
            total_recommendations=10,
            successful_fixes=9,
            failed_fixes=1,
            avg_confidence=0.9,
            success_rate=0.9,
        ),
        AgentEffectiveness(
            agent=AgentType.SECURITY,
            total_recommendations=6,
            successful_fixes=1,
            failed_fixes=5,
            avg_confidence=0.6,
            success_rate=0.1666667,
        ),
    ]

    pattern_insights = RecommendationEngine._get_pattern_insights(patterns)
    effectiveness_insights = RecommendationEngine._get_effectiveness_insights(
        effectiveness
    )
    cross_insights = RecommendationEngine._get_cross_pattern_insights(
        patterns, effectiveness
    )
    combined = RecommendationEngine._generate_insights(patterns, effectiveness)

    assert any("most common failure" in item.lower() for item in pattern_insights)
    assert any("different failure patterns" in item.lower() for item in pattern_insights)
    assert any("highly effective" in item.lower() for item in effectiveness_insights)
    assert any("low success rate" in item.lower() for item in effectiveness_insights)
    assert cross_insights == [
        "✅ 2 patterns have consistent successful fixes - good agent-pattern matching",
    ]
    assert combined[: len(pattern_insights)] == pattern_insights


def test_mcp_recommendation_engine_adjusts_confidence_and_signatures() -> None:
    recommendations = [
        AgentRecommendation(
            agent=AgentType.REFACTORING,
            confidence=0.75,
            reason="complexity",
            quick_fix_command="fix",
            pattern_matched="complexity",
        ),
        AgentRecommendation(
            agent=AgentType.SECURITY,
            confidence=0.7,
            reason="security",
            quick_fix_command="fix",
            pattern_matched="security",
        ),
    ]
    effectiveness = [
        AgentEffectiveness(
            agent=AgentType.REFACTORING,
            total_recommendations=10,
            successful_fixes=9,
            failed_fixes=1,
            avg_confidence=0.9,
            success_rate=0.9,
        )
    ]

    adjusted = RecommendationEngine.adjust_confidence(recommendations, effectiveness)
    assert adjusted[0].confidence >= adjusted[1].confidence
    assert "historical success" in adjusted[0].reason

    assert RecommendationEngine._generate_signature("ignored", {"exit_code": 0}) == ""
    assert RecommendationEngine._generate_signature(
        "B603 E501 F401",
        {
            "exit_code": 1,
            "metrics": {
                "complexity_violations": 1,
                "max_complexity": 18,
                "security_issues": 1,
                "tests_failed": 3,
                "type_errors": 2,
                "formatting_issues": 1,
            },
        },
    ).startswith("complexity:18")
