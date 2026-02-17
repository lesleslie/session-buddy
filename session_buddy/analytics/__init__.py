"""Analytics modules for Session-Buddy.

This package provides analytics capabilities for understanding session patterns,
component usage, system performance, and advanced predictive analytics.
"""

# Phase 4: Advanced analytics
from session_buddy.analytics.ab_testing import (
    ABTestConfig,
    ABTestFramework,
    TestAnalysisResult,
    TestOutcome,
    get_ab_framework,
)
from session_buddy.analytics.collaborative_filtering import (
    CollaborativeFilteringEngine,
    CollaborativeFilteringError,
    get_collaborative_engine,
)
from session_buddy.analytics.predictive import (
    SessionContext,
    SkillSuccessPredictor,
    get_predictor,
)
from session_buddy.analytics.session_analytics import (
    ASCIIVisualizer,
    ComponentUsage,
    SessionAnalytics,
    SessionStats,
    create_session_summary_report,
)
from session_buddy.analytics.time_series import (
    HourlyMetrics,
    TimeSeriesAnalyzer,
    TrendAnalysis,
    get_analyzer,
)
from session_buddy.analytics.usage_tracker import (
    RankingWeights,
    ResultInteraction,
    UsageMetrics,
    UsageTracker,
)

__all__ = [
    # Session analytics
    "SessionAnalytics",
    "SessionStats",
    "ComponentUsage",
    "ASCIIVisualizer",
    "create_session_summary_report",
    # Usage tracking
    "UsageTracker",
    "UsageMetrics",
    "ResultInteraction",
    "RankingWeights",
    # Phase 4: Predictive analytics
    "SkillSuccessPredictor",
    "SessionContext",
    "get_predictor",
    # Phase 4: A/B testing
    "ABTestFramework",
    "ABTestConfig",
    "TestOutcome",
    "TestAnalysisResult",
    "get_ab_framework",
    # Phase 4: Time-series analysis
    "TimeSeriesAnalyzer",
    "HourlyMetrics",
    "TrendAnalysis",
    "get_analyzer",
    # Phase 4: Collaborative filtering
    "CollaborativeFilteringEngine",
    "CollaborativeFilteringError",
    "get_collaborative_engine",
]
