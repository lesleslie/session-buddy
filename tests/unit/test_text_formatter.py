from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_UTILS_PACKAGE = types.ModuleType("session_buddy.utils")
_UTILS_PACKAGE.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("session_buddy.utils", _UTILS_PACKAGE)

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "text_formatter.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.text_formatter", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.text_formatter", _MODULE)
_SPEC.loader.exec_module(_MODULE)


def test_statistics_and_search_headers() -> None:
    assert _MODULE._format_statistics_header("alice")[0].endswith("alice**")
    assert _MODULE._format_session_statistics({}) == ["📝 No session data available"]
    assert _MODULE._format_interruption_type_details([]) == []
    assert _MODULE._format_no_data_message("alice")[0].endswith("alice**")
    assert _MODULE._has_statistics_data({}, {}, {}) is False
    assert _MODULE._build_search_header("query", 3) == [
        "🔍 **Search Results for: 'query'**",
        "",
        "📊 Found 3 results",
        "",
    ]
    assert _MODULE._build_search_header("query", 7, {"current_chunk": 2, "total_chunks": 4}) == [
        "🔍 **Search Results for: 'query'**",
        "",
        "📊 Found 7 results (Page 2/4)",
        "",
    ]
    assert _MODULE._format_monitoring_status({"monitoring_active": False})[2].startswith("⏸️")
    assert _MODULE._format_monitoring_status(
        {"monitoring_active": True, "last_check": "2026-01-01", "total_checks": 3}
    ) == [
        "📊 **Current Monitoring Status**",
        "",
        "✅ Quality monitoring is active",
        "• Last check: 2026-01-01",
        "• Checks performed: 3",
        "",
    ]


def test_quality_formatters_and_counts() -> None:
    sessions = {"total": 4, "avg_duration_minutes": 12.5, "max_duration_minutes": 30.0}
    interruptions = {
        "total": 2,
        "avg_per_session": 0.5,
        "peak_hour": 14,
        "by_type": [{"type": "focus", "count": 2}, {"type": "meeting", "count": 1}],
    }
    snapshots = {"total": 2, "successful_restores": 1, "avg_size_kb": 8.5}
    quality_data = {
        "monitoring_active": True,
        "last_check": "2026-01-01",
        "total_checks": 3,
        "trend": {"current_score": 88, "direction": "up", "change": 2.5},
        "alerts": [
            {"severity": "high", "message": "Critical issue"},
            {"severity": "medium", "message": "Watch this"},
            {"severity": "low", "message": "Minor"},
            {"severity": "info", "message": "FYI"},
        ],
        "recommendations": ["Refactor", "Add tests"],
    }

    assert _MODULE._calculate_efficiency_rates(sessions, interruptions, snapshots) == {
        "interruption_rate": 0.5,
        "recovery_rate": 0.5,
        "productivity_score": 90.0,
    }
    assert _MODULE._format_session_statistics(sessions)[0] == "**Session Activity:**"
    assert _MODULE._format_interruption_statistics(interruptions)[0] == "**Interruption Patterns:**"
    assert _MODULE._format_snapshot_statistics(snapshots)[0] == "**Context Snapshots:**"
    assert _MODULE._format_efficiency_metrics(sessions, interruptions, snapshots)[0] == "**Efficiency Metrics:**"
    assert _MODULE._format_quality_trend(quality_data)[0] == "📈 **Quality Trend Analysis**"
    assert _MODULE._format_quality_alerts(quality_data)[0] == "🚨 **Quality Alerts**"
    assert _MODULE._format_proactive_recommendations(quality_data)[0] == "💡 **Proactive Recommendations**"
    assert _MODULE._format_monitor_usage_guidance()[0] == "📖 **Usage Guidance**"
    assert _MODULE._format_search_results(
        [{"content": "hello", "project": "Proj", "timestamp": "now"}]
    ) == [
        "**1. [Proj]** now",
        "   hello",
        "",
    ]


def test_empty_quality_and_search_paths() -> None:
    assert _MODULE._format_interruption_statistics({}) == ["🚫 No interruption data available"]
    assert _MODULE._format_snapshot_statistics({}) == ["💾 No snapshot data available"]
    assert _MODULE._format_quality_trend({}) == ["📈 No trend data available"]
    assert _MODULE._format_quality_alerts({}) == ["✅ No quality alerts"]
    assert _MODULE._format_proactive_recommendations({}) == ["💡 No recommendations at this time"]
    assert _MODULE._format_search_results([]) == ["No results found"]


def test_search_result_truncation_and_type_limit() -> None:
    results = [
        {
            "content": "x" * 400,
            "project": "Proj",
            "timestamp": "later",
        }
    ]
    formatted = _MODULE._format_search_results(results)
    assert formatted[1].endswith("...")
    assert len(formatted[1].strip()) <= 300

    type_lines = _MODULE._format_interruption_type_details(
        [{"type": f"t{i}", "count": i} for i in range(7)]
    )
    assert type_lines[0] == "**Interruption Types:**"
    assert len(type_lines) == 7
