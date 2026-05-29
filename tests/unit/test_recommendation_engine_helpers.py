from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from session_buddy.tools.agent_analyzer import AgentRecommendation, AgentType
from session_buddy.tools.recommendation_engine import (
    AgentEffectiveness,
    FailurePattern,
    RecommendationEngine,
)


def test_filter_results_by_date_keeps_invalid_and_recent_entries() -> None:
    start_date = datetime(2026, 1, 10, 0, 0, 0)
    results = [
        {"timestamp": "2026-01-09T23:59:59", "content": "old"},
        {"timestamp": "2026-01-10T00:00:00", "content": "boundary"},
        {"timestamp": datetime(2026, 1, 11, 12, 0, 0), "content": "datetime"},
        {"timestamp": "not-a-date", "content": "invalid"},
        {"content": "missing"},
    ]

    filtered = RecommendationEngine._filter_results_by_date(results, start_date)

    assert [item["content"] for item in filtered] == [
        "boundary",
        "datetime",
        "invalid",
    ]


def test_update_timestamp_and_track_agent_fixes_cover_branches() -> None:
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
        pattern_data,
        signature,
        "2026-01-02T00:00:00",
    )
    RecommendationEngine._update_timestamp(pattern_data, signature, "bad-timestamp")
    RecommendationEngine._update_timestamp(pattern_data, signature, None)

    assert pattern_data[signature]["last_seen"] == datetime(2026, 1, 2, 0, 0, 0)

    recommendations = [
        {"agent": AgentType.REFACTORING.value, "confidence": 0.8},
        {"agent": "not-a-real-agent", "confidence": 0.2},
        {"confidence": 0.1},
    ]
    RecommendationEngine._track_agent_fixes(
        pattern_data,
        signature,
        recommendations,
        {"exit_code": 0, "execution_time": 12.5},
    )
    RecommendationEngine._track_agent_fixes(
        pattern_data,
        signature,
        recommendations,
        {"exit_code": 1},
    )

    assert pattern_data[signature]["successful_fixes"] == [AgentType.REFACTORING]
    assert pattern_data[signature]["failed_fixes"] == [AgentType.REFACTORING]
    assert pattern_data[signature]["fix_times"] == [12.5]


def test_extract_patterns_and_effectiveness_and_signatures() -> None:
    results = [
        {
            "timestamp": "2026-01-01T00:00:00",
            "content": "B603 security issue found",
            "metadata": {
                "exit_code": 1,
                "metrics": {
                    "security_issues": 1,
                    "tests_failed": 3,
                    "type_errors": 2,
                },
                "agent_recommendations": [
                    {
                        "agent": AgentType.SECURITY.value,
                        "confidence": 0.9,
                        "reason": "security",
                        "quick_fix_command": "fix",
                        "pattern_matched": "B603",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-01-02T00:00:00",
            "content": "F401 import issue",
            "metadata": {
                "exit_code": 0,
                "execution_time": 7.5,
                "metrics": {"formatting_issues": 1},
                "agent_recommendations": [
                    {
                        "agent": AgentType.DRY.value,
                        "confidence": 0.6,
                        "reason": "formatting",
                        "quick_fix_command": "fix",
                        "pattern_matched": "F401",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-01-03T00:00:00",
            "content": "clean run",
            "metadata": {"exit_code": 0, "execution_time": 7.5},
        },
    ]

    patterns = RecommendationEngine._extract_patterns(results)
    effectiveness = RecommendationEngine._calculate_agent_effectiveness(results)
    insights = RecommendationEngine._generate_insights(patterns, effectiveness)

    assert len(patterns) == 1
    assert patterns[0].pattern_signature.startswith("security:1")
    assert patterns[0].occurrences == 1
    assert patterns[0].successful_fixes == [AgentType.SECURITY]
    assert patterns[0].avg_fix_time == 7.5

    assert len(effectiveness) == 2
    assert {item.agent for item in effectiveness} == {
        AgentType.SECURITY,
        AgentType.DRY,
    }
    assert any("most common failure" in item.lower() for item in insights)

    assert RecommendationEngine._generate_signature("ignored", {"exit_code": 0}) == ""
    assert RecommendationEngine._generate_signature(
        "unknown",
        {"exit_code": 1, "metrics": {}},
    ) == "unknown_failure"


def test_pattern_and_effectiveness_insights_and_adjustment() -> None:
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
            last_seen=now - timedelta(days=1),
            successful_fixes=[AgentType.SECURITY],
            failed_fixes=[AgentType.SECURITY],
            avg_fix_time=0.0,
        ),
        FailurePattern(
            pattern_signature="test_failures:3",
            occurrences=2,
            last_seen=now - timedelta(days=2),
            successful_fixes=[],
            failed_fixes=[],
            avg_fix_time=0.0,
        ),
        FailurePattern(
            pattern_signature="type_errors:2",
            occurrences=2,
            last_seen=now - timedelta(days=3),
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

    assert any("most common failure" in item.lower() for item in pattern_insights)
    assert any("different failure patterns" in item.lower() for item in pattern_insights)
    assert any("highly effective" in item.lower() for item in effectiveness_insights)
    assert any("low success rate" in item.lower() for item in effectiveness_insights)
    assert cross_insights == [
        "✅ 1 patterns have consistent successful fixes - good agent-pattern matching",
    ]

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

    adjusted = RecommendationEngine.adjust_confidence(recommendations, effectiveness)
    assert adjusted[0].confidence >= adjusted[1].confidence
    assert "historical success" in adjusted[0].reason

    unchanged = RecommendationEngine._adjust_single_recommendation(
        recommendations[0],
        AgentEffectiveness(
            agent=AgentType.REFACTORING,
            total_recommendations=3,
            successful_fixes=3,
            failed_fixes=0,
            avg_confidence=0.8,
            success_rate=1.0,
        ),
    )
    assert unchanged.confidence == recommendations[0].confidence
