"""Analytics modules for Session-Buddy.

This package provides analytics capabilities for understanding session patterns,
component usage, system performance, and advanced predictive analytics.
"""

# Phase 4: Advanced analytics
from session_buddy.analytics.ab_testing import (
    ABTestAnalysisResult,
    ABTestConfig,
    ABTestFramework,
    ABTestOutcome,
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
    "ABTestAnalysisResult",
    "ABTestConfig",
    "ABTestFramework",
    "ABTestOutcome",
    "ASCIIVisualizer",
    "CollaborativeFilteringEngine",
    "CollaborativeFilteringError",
    "ComponentUsage",
    "HourlyMetrics",
    "RankingWeights",
    "ResultInteraction",
    "SessionAnalytics",
    "SessionContext",
    "SessionStats",
    "SkillSuccessPredictor",
    "TimeSeriesAnalyzer",
    "TrendAnalysis",
    "UsageMetrics",
    "UsageTracker",
    "create_session_summary_report",
    "get_ab_framework",
    "get_analyzer",
    "get_collaborative_engine",
    "get_predictor",
]
