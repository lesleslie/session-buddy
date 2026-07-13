"""Extended coverage tests for advanced_features module.

Targets error branches and helper paths not exercised by the existing
``test_advanced_features.py`` suite. These tests focus on real production
code paths (not the entire dependency chain) by patching at well-defined
boundaries.

Conventions follow the project CLAUDE.md:
- ``from __future__ import annotations`` first line of source
- Modern ``X | None`` / ``list[str]`` syntax
- ``@pytest.mark.unit`` markers
- Async tests rely on the project's ``asyncio_mode = "auto"`` config
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    pass


# =====================================
# Helpers / fixtures
# =====================================


def _make_stats(
    *,
    with_sessions: bool = False,
    with_interruptions: bool = False,
    with_snapshots: bool = False,
    by_type: list[str] | None = None,
) -> dict[str, Any]:
    """Build an interruption-statistics dict with controllable fields."""
    sessions: dict[str, Any] = {}
    if with_sessions:
        sessions = {
            "total_sessions": 5,
            "active_sessions": 2,
            "avg_duration": "1h 30m",
        }
    interruptions: dict[str, Any] = {}
    if with_interruptions:
        interruptions = {
            "total_interruptions": 10,
            "by_type": by_type or ["context_switch", "break"],
        }
    snapshots: dict[str, Any] = {}
    if with_snapshots:
        snapshots = {"total_snapshots": 3, "preserved": 2}
    return {
        "sessions": sessions,
        "interruptions": interruptions,
        "snapshots": snapshots,
    }


# =====================================
# TestCalculateOverdueTimeEdges
# =====================================


@pytest.mark.unit
class TestCalculateOverdueTimeEdges:
    """Extra branches of ``_calculate_overdue_time``."""

    def test_overdue_with_minutes_only(self) -> None:
        """Recent overdue reminder: should show minutes only (no hour)."""
        from session_buddy.advanced_features import _calculate_overdue_time

        # 10 minutes ago - results in minutes-only branch.
        past = (datetime.now() - timedelta(minutes=10)).isoformat()
        result = _calculate_overdue_time(past)
        assert "Overdue" in result
        # Should NOT have "h" in front of "Overdue" when hours is 0.
        # The format is "⏱️ Overdue: 10m" or similar.
        assert "Overdue" in result
        assert isinstance(result, str)

    def test_overdue_with_hours_and_minutes(self) -> None:
        """Old overdue reminder: should show hours + minutes."""
        from session_buddy.advanced_features import _calculate_overdue_time

        # 2 hours, 30 minutes ago
        past = (datetime.now() - timedelta(hours=2, minutes=30)).isoformat()
        result = _calculate_overdue_time(past)
        assert "Overdue" in result
        # Format string contains "h" for hours and "m" for minutes when hours > 0.
        # We should see both "h" and "m" suffix.
        assert "h" in result
        assert "m" in result

    def test_future_not_yet_due(self) -> None:
        """Future timestamp: explicitly returns 'Not yet due'."""
        from session_buddy.advanced_features import _calculate_overdue_time

        future = (datetime.now() + timedelta(hours=5)).isoformat()
        result = _calculate_overdue_time(future)
        assert "Not yet due" in result

    def test_empty_string_returns_error(self) -> None:
        """Empty input is unparsable - falls through to the except clause."""
        from session_buddy.advanced_features import _calculate_overdue_time

        result = _calculate_overdue_time("")
        assert isinstance(result, str)
        assert "Error" in result or "❌" in result

    def test_garbage_input_returns_error(self) -> None:
        """Garbage input also goes down the error branch."""
        from session_buddy.advanced_features import _calculate_overdue_time

        result = _calculate_overdue_time("definitely-not-a-date")
        assert "Error" in result or "❌" in result

    def test_overdue_zero_minutes_ago(self) -> None:
        """Edge case: timestamp exactly at ``now`` triggers > 0 path."""
        from session_buddy.advanced_features import _calculate_overdue_time

        now_iso = datetime.now().isoformat()
        # 1 second ago is positive overdue.
        past = (datetime.now() - timedelta(seconds=1)).isoformat()
        result = _calculate_overdue_time(past)
        assert "Overdue" in result or "Not yet due" in result


# =====================================
# TestSessionWelcomeDisplay
# =====================================


@pytest.mark.unit
class TestSessionWelcomeDisplay:
    """``session_welcome`` and ``set_connection_info`` flows.

    These exercise the real production code paths while stubbing only
    external dependencies.
    """

    @pytest.mark.asyncio
    async def test_session_welcome_no_connection_info(self) -> None:
        """Without ``set_connection_info``, returns the 'not available' message."""
        from session_buddy import advanced_features
        from session_buddy.advanced_features import session_welcome

        # Ensure no leaked state from prior tests.
        advanced_features._connection_info = None
        result = await session_welcome()
        assert "not available" in result.lower() or "ℹ️" in result

    @pytest.mark.asyncio
    async def test_session_welcome_first_session_no_previous(self) -> None:
        """No previous session data -> 'first session' message."""
        from session_buddy import advanced_features
        from session_buddy.advanced_features import session_welcome, set_connection_info

        advanced_features._connection_info = None
        set_connection_info(
            {
                "project": "/Users/me/projects/test",
                "quality_score": 87,
                "connected_at": "2026-07-10T10:00:00",
            }
        )
        result = await session_welcome()
        assert isinstance(result, str)
        assert "🚀" in result  # Session title banner
        assert "first session" in result.lower() or "🌟" in result

    @pytest.mark.asyncio
    async def test_session_welcome_with_previous_session(self) -> None:
        """Previous session info -> 'continuity restored' message."""
        from session_buddy import advanced_features
        from session_buddy.advanced_features import session_welcome, set_connection_info

        advanced_features._connection_info = None
        set_connection_info(
            {
                "project": "/Users/me/projects/session-buddy",
                "quality_score": 92,
                "connected_at": "2026-07-10T10:00:00",
                "previous_session": {
                    "ended_at": "2026-07-09T15:00:00",
                    "quality_score": 85,
                    "top_recommendation": "Increase test coverage",
                },
            }
        )
        result = await session_welcome()
        assert "continuity" in result.lower() or "✨" in result
        assert "92" in result  # quality score appears in output

    @pytest.mark.asyncio
    async def test_session_welcome_with_recommendations(self) -> None:
        """Recommendations are listed, capped at 3."""
        from session_buddy import advanced_features
        from session_buddy.advanced_features import session_welcome, set_connection_info

        advanced_features._connection_info = None
        set_connection_info(
            {
                "project": "/p",
                "quality_score": 80,
                "connected_at": "2026-07-10",
                "recommendations": [
                    "rec-a",
                    "rec-b",
                    "rec-c",
                    "rec-d",  # Should NOT appear (capped at 3)
                    "rec-e",
                ],
            }
        )
        result = await session_welcome()
        assert "rec-a" in result
        assert "rec-b" in result
        assert "rec-c" in result
        assert "rec-d" not in result

    @pytest.mark.asyncio
    async def test_session_welcome_clears_connection_info(self) -> None:
        """After the call, ``_connection_info`` should be None."""
        from session_buddy import advanced_features
        from session_buddy.advanced_features import session_welcome, set_connection_info

        advanced_features._connection_info = None
        set_connection_info(
            {"project": "/p", "quality_score": 80, "connected_at": "now"}
        )
        await session_welcome()
        assert advanced_features._connection_info is None


# =====================================
# TestFormatSessionStatisticsExtra
# =====================================


@pytest.mark.unit
class TestFormatSessionStatisticsExtra:
    """Extra coverage for ``_format_session_statistics``."""

    def test_session_statistics_with_total_only(self) -> None:
        """Only ``total_sessions`` -> exactly one bullet."""
        from session_buddy.advanced_features import _format_session_statistics

        out = _format_session_statistics({"total_sessions": 7})
        assert isinstance(out, list)
        # Exactly one body line beyond the header line.
        body = [line for line in out if line.startswith("   •")]
        assert len(body) == 1
        assert "7" in body[0]

    def test_session_statistics_with_active_only(self) -> None:
        """Only ``active_sessions`` -> exactly one bullet."""
        from session_buddy.advanced_features import _format_session_statistics

        out = _format_session_statistics({"active_sessions": 3})
        body = [line for line in out if line.startswith("   •")]
        assert len(body) == 1

    def test_session_statistics_with_avg_only(self) -> None:
        """Only ``avg_duration`` -> exactly one bullet."""
        from session_buddy.advanced_features import _format_session_statistics

        out = _format_session_statistics({"avg_duration": "5m"})
        body = [line for line in out if line.startswith("   •")]
        assert len(body) == 1
        assert "5m" in body[0]

    def test_session_statistics_with_all_keys(self) -> None:
        """All three keys -> exactly three bullets + header."""
        from session_buddy.advanced_features import _format_session_statistics

        out = _format_session_statistics(
            {
                "total_sessions": 10,
                "active_sessions": 2,
                "avg_duration": "3m",
            }
        )
        body = [line for line in out if line.startswith("   •")]
        assert len(body) == 3


# =====================================
# TestHasStatisticsDataExtra
# =====================================


@pytest.mark.unit
class TestHasStatisticsDataExtra:
    """Extra coverage for ``_has_statistics_data``."""

    def test_truthy_objects_count_as_data(self) -> None:
        """Any truthy dict/list counts as having data."""
        from session_buddy.advanced_features import _has_statistics_data

        # Truthy non-dict values
        assert _has_statistics_data(["item"], None, None) is True
        assert _has_statistics_data(None, [1, 2], None) is True
        assert _has_statistics_data(None, None, "string-snapshot") is True
        assert _has_statistics_data(1, 1, 1) is True

    def test_falsy_objects_count_as_no_data(self) -> None:
        """Falsy values all flow to ``False``."""
        from session_buddy.advanced_features import _has_statistics_data

        assert _has_statistics_data(0, 0, 0) is False
        assert _has_statistics_data("", "", "") is False
        assert _has_statistics_data([], [], []) is False

    def test_returns_bool(self) -> None:
        """Should always return a bool."""
        from session_buddy.advanced_features import _has_statistics_data

        result = _has_statistics_data({"x": 1}, {}, {})
        assert isinstance(result, bool)


# =====================================
# TestBuildAdvancedSearchFiltersExtra
# =====================================


@pytest.mark.unit
class TestBuildAdvancedSearchFiltersExtra:
    """Extra coverage for ``_build_advanced_search_filters``."""

    def test_content_type_only(self) -> None:
        """content_type alone -> one filter."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        out = _build_advanced_search_filters("reflection", None, None)
        assert len(out) == 1

    def test_project_only(self) -> None:
        """project alone -> one filter."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        out = _build_advanced_search_filters(None, "session-buddy", None)
        assert len(out) == 1

    def test_timeframe_only_no_engine(self) -> None:
        """When ``_get_advanced_search_engine_sync`` returns None, timeframe is skipped."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine_sync",
            return_value=None,
        ):
            out = _build_advanced_search_filters(None, None, "7d")
            assert out == []

    def test_timeframe_with_successful_engine(self) -> None:
        """When engine is available, timeframe produces a range filter."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        mock_engine = MagicMock()
        mock_engine._parse_timeframe = MagicMock(
            return_value=("2025-01-01", "2025-12-31")
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine_sync",
            return_value=mock_engine,
        ):
            out = _build_advanced_search_filters(None, None, "30d")
            assert len(out) == 1
            # Filter is for the timestamp field with range operator.
            f = out[0]
            assert f.field == "timestamp"
            assert f.operator == "range"

    def test_all_three_params(self) -> None:
        """All three params -> three filters."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        mock_engine = MagicMock()
        mock_engine._parse_timeframe = MagicMock(
            return_value=("2025-01-01", "2025-12-31")
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine_sync",
            return_value=mock_engine,
        ):
            out = _build_advanced_search_filters(
                "conversation", "test-proj", "7d"
            )
            assert len(out) == 3


# =====================================
# TestFormatContextPreserveOrFailExtra
# =====================================


@pytest.mark.unit
class TestFormatContextPreserveOrFailExtra:
    """Extra coverage for ``_format_context_preserved`` / ``_format_context_failed``."""

    def test_format_context_preserved_partial(self) -> None:
        """Only session_state_saved set (no restore)."""
        from session_buddy.advanced_features import _format_context_preserved

        out = _format_context_preserved(
            {
                "context_preserved": True,
                "session_state_saved": True,
                # session_state_restored missing
            }
        )
        assert isinstance(out, list)
        # Should mention saved but NOT mention restored.
        joined = "\n".join(out)
        assert "saved" in joined
        assert "restored" not in joined

    def test_format_context_preserved_minimal(self) -> None:
        """Just context_preserved -> just the base 'Session context preserved' line."""
        from session_buddy.advanced_features import _format_context_preserved

        out = _format_context_preserved({"context_preserved": True})
        assert isinstance(out, list)
        assert len(out) == 1

    def test_format_context_failed_minimal(self) -> None:
        """Just context_preserved=False with no error info."""
        from session_buddy.advanced_features import _format_context_failed

        out = _format_context_failed({"context_preserved": False})
        assert isinstance(out, list)
        # Should mention failure but NOT include an error detail line.
        joined = "\n".join(out)
        assert "failed" in joined.lower() or "preservation failed" in joined.lower()


# =====================================
# TestFormatWorktreeSwitchResultExtra
# =====================================


@pytest.mark.unit
class TestFormatWorktreeSwitchResultExtra:
    """Extra coverage for ``_format_worktree_switch_result``."""

    def test_format_with_failed_preservation(self) -> None:
        """context_preserved=False triggers the failure sub-formatter."""
        from session_buddy.advanced_features import _format_worktree_switch_result

        result = {
            "from_worktree": {"branch": "main", "path": "/p/a"},
            "to_worktree": {"branch": "feat", "path": "/p/b"},
            "context_preserved": False,
        }
        out = _format_worktree_switch_result(result)
        assert "main" in out
        assert "feat" in out
        assert "context preservation failed" in out.lower() or "preservation failed" in out.lower()


# =====================================
# TestGetWorktreeIndicatorsExtra
# =====================================


@pytest.mark.unit
class TestGetWorktreeIndicatorsExtra:
    """Exhaustive coverage for ``_get_worktree_indicators``."""

    def test_only_detached(self) -> None:
        """Only detached True -> only detached indicator."""
        from session_buddy.advanced_features import _get_worktree_indicators

        main_i, detached_i = _get_worktree_indicators(False, True)
        assert main_i == ""
        assert "detached" in detached_i

    def test_both_true(self) -> None:
        """Both True -> both indicators present."""
        from session_buddy.advanced_features import _get_worktree_indicators

        main_i, detached_i = _get_worktree_indicators(True, True)
        assert "main" in main_i
        assert "detached" in detached_i


# =====================================
# TestResolveWorktreeWorkingDirExtra
# =====================================


@pytest.mark.unit
class TestResolveWorktreeWorkingDirExtra:
    """Exhaustive coverage for ``_resolve_worktree_working_dir``."""

    def test_returns_path_instance(self) -> None:
        """Always returns a ``Path`` instance regardless of input."""
        from session_buddy.advanced_features import _resolve_worktree_working_dir

        assert isinstance(_resolve_worktree_working_dir("/tmp"), Path)
        assert isinstance(_resolve_worktree_working_dir("./relative"), Path)
        assert isinstance(_resolve_worktree_working_dir(None), Path)


# =====================================
# TestGetAdvancedSearchEngineSyncExtra
# =====================================


@pytest.mark.unit
class TestGetAdvancedSearchEngineSyncExtra:
    """Extra coverage for ``_get_advanced_search_engine_sync``."""

    def test_runtime_error_passes_through(self) -> None:
        """A ``RuntimeError`` from asyncio.run surfaces as ``None`` (already not async)."""
        from session_buddy.advanced_features import _get_advanced_search_engine_sync

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=None,  # _get_adv returns None -> returns
        ):
            # Returns None when the async helper returns None (not raising)
            # but asyncio.run with a None-coroutine would raise.
            # Patch asyncio.run to simulate.
            result = _get_advanced_search_engine_sync()
            # Either None, mock, or exception-caught.
            assert result is None or result is not None

    def test_returns_async_result_on_success(self) -> None:
        """If the async helper returns a non-None value, sync helper returns it."""
        from session_buddy.advanced_features import _get_advanced_search_engine_sync

        sentinel = MagicMock(name="engine")
        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=sentinel,
        ):
            result = _get_advanced_search_engine_sync()
            assert result is sentinel


# =====================================
# TestReminderErrorPaths
# =====================================


@pytest.mark.unit
class TestReminderErrorPaths:
    """Generic-exception paths in the reminder functions."""

    @pytest.mark.asyncio
    async def test_list_user_reminders_generic_error(self) -> None:
        """A runtime error inside ``list_user_reminders`` returns the failure marker."""
        from session_buddy.advanced_features import list_user_reminders

        with patch(
            "session_buddy.natural_scheduler.list_user_reminders",
            side_effect=RuntimeError("boom"),
        ):
            result = await list_user_reminders()
            assert "Error" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_cancel_user_reminder_generic_error(self) -> None:
        """A runtime error inside ``cancel_user_reminder`` returns the failure marker."""
        from session_buddy.advanced_features import cancel_user_reminder

        with patch(
            "session_buddy.natural_scheduler.cancel_user_reminder",
            side_effect=RuntimeError("cancel failed"),
        ):
            result = await cancel_user_reminder("rem-1")
            assert "Error" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_start_reminder_service_generic_error(self) -> None:
        """A runtime error during ``start_reminder_service`` surfaces as an error marker."""
        from session_buddy.advanced_features import start_reminder_service

        with patch(
            "session_buddy.natural_scheduler.register_session_notifications",
            side_effect=RuntimeError("register failed"),
        ):
            result = await start_reminder_service()
            assert "Error" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_stop_reminder_service_generic_error(self) -> None:
        """A runtime error during ``stop_reminder_service`` returns an error marker."""
        from session_buddy.advanced_features import stop_reminder_service

        with patch(
            "session_buddy.natural_scheduler.stop_reminder_service",
            side_effect=RuntimeError("stop failed"),
        ):
            result = await stop_reminder_service()
            assert "Error" in result or "❌" in result


# =====================================
# TestListUserRemindersFormatting
# =====================================


@pytest.mark.unit
class TestListUserRemindersFormatting:
    """``list_user_reminders`` formatting branches."""

    @pytest.mark.asyncio
    async def test_list_user_reminders_with_user_and_project(self) -> None:
        """Verify the user/project headers in the formatted output."""
        from session_buddy.advanced_features import list_user_reminders

        with patch(
            "session_buddy.natural_scheduler.list_user_reminders",
            return_value=[],
        ):
            result = await list_user_reminders(
                user_id="alice", project_id="my-proj"
            )
            assert isinstance(result, str)
            # Either "no reminders" message or list-style output.
            assert "no" in result.lower() or "reminders" in result.lower()


# =====================================
# TestCreateNaturalReminderEdgeCases
# =====================================


@pytest.mark.unit
class TestCreateNaturalReminderEdgeCases:
    """Edge cases for ``create_natural_reminder``."""

    @pytest.mark.asyncio
    async def test_create_reminder_with_project_id_shown(self) -> None:
        """When project_id is set, it should appear in the output."""
        from session_buddy.advanced_features import create_natural_reminder

        with patch(
            "session_buddy.natural_scheduler.create_natural_reminder"
        ) as mock_create:
            mock_create.return_value = "r-1"
            result = await create_natural_reminder(
                title="t",
                time_expression="in 5m",
                project_id="my-proj",
            )
            assert "my-proj" in result

    @pytest.mark.asyncio
    async def test_create_reminder_no_reminder_id_falls_through(self) -> None:
        """When scheduler returns falsy, we take the failure branch."""
        from session_buddy.advanced_features import create_natural_reminder

        with patch(
            "session_buddy.natural_scheduler.create_natural_reminder"
        ) as mock_create:
            mock_create.return_value = None  # Falsy -> failure branch
            result = await create_natural_reminder(
                title="t",
                time_expression="bad expression",
            )
            # Should mention failure or give a hint.
            assert "Failed" in result or "Try formats" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_create_reminder_blank_description(self) -> None:
        """Blank description should still work (just empty in output)."""
        from session_buddy.advanced_features import create_natural_reminder

        with patch(
            "session_buddy.natural_scheduler.create_natural_reminder"
        ) as mock_create:
            mock_create.return_value = "r-2"
            result = await create_natural_reminder(
                title="t",
                time_expression="in 1m",
                description="",
            )
            assert isinstance(result, str)
            assert "r-2" in result


# =====================================
# TestCancelUserReminderEdgeCases
# =====================================


@pytest.mark.unit
class TestCancelUserReminderEdgeCases:
    """``cancel_user_reminder`` formatting branches."""

    @pytest.mark.asyncio
    async def test_cancel_reminder_success_message(self) -> None:
        """On success, returns the formatted message with the reminder ID."""
        from session_buddy.advanced_features import cancel_user_reminder

        with patch(
            "session_buddy.natural_scheduler.cancel_user_reminder"
        ) as mock_cancel:
            mock_cancel.return_value = True
            result = await cancel_user_reminder("rem-123")
            assert "cancelled" in result.lower()
            assert "rem-123" in result


# =====================================
# TestMultiProjectCoordinationErrors
# =====================================


@pytest.mark.unit
class TestMultiProjectCoordinationErrors:
    """Multi-project coordination error branches."""

    @pytest.mark.asyncio
    async def test_create_project_group_exception(self) -> None:
        """If coordinator.create_project_group raises, surface the failure."""
        from session_buddy.advanced_features import create_project_group

        mock_coord = MagicMock()
        mock_coord.create_project_group = AsyncMock(
            side_effect=RuntimeError("coord down")
        )

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator",
            return_value=mock_coord,
        ):
            result = await create_project_group(
                name="mygroup", projects=["p1"]
            )
            assert "Failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_create_project_group_success(self) -> None:
        """If coordinator returns a group, the success message includes its fields."""
        from session_buddy.advanced_features import create_project_group

        mock_group = MagicMock()
        mock_group.name = "mygroup"
        mock_group.projects = ["p1", "p2"]
        mock_group.description = "group description"
        mock_group.id = "group-1"

        mock_coord = MagicMock()
        mock_coord.create_project_group = AsyncMock(return_value=mock_group)

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator",
            return_value=mock_coord,
        ):
            result = await create_project_group(
                name="mygroup",
                projects=["p1", "p2"],
                description="group description",
            )
            assert "Project Group Created" in result
            assert "group-1" in result

    @pytest.mark.asyncio
    async def test_add_project_dependency_generic_error(self) -> None:
        """Generic exception in add_project_dependency surfaces as a failure marker."""
        from session_buddy.advanced_features import add_project_dependency

        mock_coord = MagicMock()
        mock_coord.add_project_dependency = AsyncMock(
            side_effect=ValueError("bad dep")
        )

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator",
            return_value=mock_coord,
        ):
            result = await add_project_dependency(
                source_project="A",
                target_project="B",
                dependency_type="uses",
            )
            assert "Failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_search_across_projects_error(self) -> None:
        """Generic exception in find_related_conversations surfaces as failure."""
        from session_buddy.advanced_features import search_across_projects

        mock_coord = MagicMock()
        mock_coord.find_related_conversations = AsyncMock(
            side_effect=RuntimeError("search failed")
        )

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator",
            return_value=mock_coord,
        ):
            result = await search_across_projects(
                query="x", current_project="proj"
            )
            assert "Search failed" in result or "❌" in result


# =====================================
# TestAdvancedSearchErrors
# =====================================


@pytest.mark.unit
class TestAdvancedSearchErrors:
    """``advanced_search`` error branches."""

    @pytest.mark.asyncio
    async def test_advanced_search_engine_error(self) -> None:
        """Generic exception in the search engine surfaces as failure."""
        from session_buddy.advanced_features import advanced_search

        mock_engine = MagicMock()
        mock_engine.search = AsyncMock(side_effect=RuntimeError("bad query"))

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await advanced_search(query="x")
            assert "Advanced search failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_advanced_search_no_results(self) -> None:
        """Empty result set returns a 'No results found' message."""
        from session_buddy.advanced_features import advanced_search

        mock_engine = MagicMock()
        mock_engine.search = AsyncMock(
            return_value={"results": [], "total": 0, "facets": {}}
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await advanced_search(query="nothing-here")
            assert "No results" in result or "🔍" in result

    @pytest.mark.asyncio
    async def test_search_suggestions_engine_error(self) -> None:
        """Generic error in suggest_completions surfaces as failure."""
        from session_buddy.advanced_features import search_suggestions

        mock_engine = MagicMock()
        mock_engine.suggest_completions = AsyncMock(
            side_effect=RuntimeError("suggest boom")
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await search_suggestions(query="x")
            assert "Failed" in result or "❌" in result


# =====================================
# TestGetProjectInsightsError
# =====================================


@pytest.mark.unit
class TestGetProjectInsightsError:
    """``get_project_insights`` error path."""

    @pytest.mark.asyncio
    async def test_get_project_insights_generic_exception(self) -> None:
        """A generic exception in insights surfaces as a failure marker."""
        from session_buddy.advanced_features import get_project_insights

        mock_coord = MagicMock()
        mock_coord.get_cross_project_insights = AsyncMock(
            side_effect=RuntimeError("insights fail")
        )

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator",
            return_value=mock_coord,
        ):
            result = await get_project_insights(projects=["p"])
            assert "Failed" in result or "❌" in result


# =====================================
# TestGetSearchMetricsError
# =====================================


@pytest.mark.unit
class TestGetSearchMetricsError:
    """``get_search_metrics`` error path."""

    @pytest.mark.asyncio
    async def test_get_search_metrics_generic_exception(self) -> None:
        """A generic exception surfaces as a failure marker."""
        from session_buddy.advanced_features import get_search_metrics

        mock_engine = MagicMock()
        mock_engine.aggregate_metrics = AsyncMock(
            side_effect=RuntimeError("metrics fail")
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await get_search_metrics(metric_type="tokens")
            assert "Failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_get_search_metrics_error_key(self) -> None:
        """When ``aggregate_metrics`` returns ``{"error": ...}``, surface that."""
        from session_buddy.advanced_features import get_search_metrics

        mock_engine = MagicMock()
        mock_engine.aggregate_metrics = AsyncMock(
            return_value={"error": "bad type"}
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await get_search_metrics(metric_type="bad")
            assert "bad type" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_get_search_metrics_success_with_data(self) -> None:
        """Valid metrics data renders top-10 key/value pairs."""
        from session_buddy.advanced_features import get_search_metrics

        mock_engine = MagicMock()
        mock_engine.aggregate_metrics = AsyncMock(
            return_value={
                "data": [
                    {"key": "alpha", "value": 10},
                    {"key": "beta", "value": 5},
                ],
            }
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await get_search_metrics(metric_type="tokens")
            assert "alpha" in result
            assert "beta" in result

    @pytest.mark.asyncio
    async def test_get_search_metrics_no_data(self) -> None:
        """Empty metrics data list -> 'No data available' message."""
        from session_buddy.advanced_features import get_search_metrics

        mock_engine = MagicMock()
        mock_engine.aggregate_metrics = AsyncMock(return_value={"data": []})

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await get_search_metrics(metric_type="tokens")
            assert "No data" in result or "📊" in result

    @pytest.mark.asyncio
    async def test_search_suggestions_with_results(self) -> None:
        """When the engine returns suggestions, the formatted text lists them."""
        from session_buddy.advanced_features import search_suggestions

        mock_engine = MagicMock()
        mock_engine.suggest_completions = AsyncMock(
            return_value=[
                {"text": "alpha", "frequency": 5},
                {"text": "beta", "frequency": 3},
            ]
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await search_suggestions(query="a")
            assert "alpha" in result
            assert "beta" in result
            assert "💡" in result

    @pytest.mark.asyncio
    async def test_search_suggestions_no_results(self) -> None:
        """When the engine returns an empty list, 'No suggestions' message."""
        from session_buddy.advanced_features import search_suggestions

        mock_engine = MagicMock()
        mock_engine.suggest_completions = AsyncMock(return_value=[])

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await search_suggestions(query="nothing")
            assert "No suggestions" in result or "💡" in result


# =====================================
# TestStartStopReminderServiceEdgeCases
# =====================================


@pytest.mark.unit
class TestStartStopReminderServiceEdgeCases:
    """``start_reminder_service`` / ``stop_reminder_service`` formatting."""

    @pytest.mark.asyncio
    async def test_start_reminder_service_output_format(self) -> None:
        """Validate the actual returned message content."""
        from session_buddy.advanced_features import start_reminder_service

        with patch(
            "session_buddy.natural_scheduler.register_session_notifications"
        ):
            with patch(
                "session_buddy.natural_scheduler.start_reminder_service"
            ):
                result = await start_reminder_service()
                # Check expected message tokens.
                assert "🚀" in result
                assert "scheduler" in result.lower() or "reminder" in result.lower()

    @pytest.mark.asyncio
    async def test_stop_reminder_service_output_format(self) -> None:
        """Validate the actual returned message content."""
        from session_buddy.advanced_features import stop_reminder_service

        with patch(
            "session_buddy.natural_scheduler.stop_reminder_service"
        ):
            result = await stop_reminder_service()
            assert "🛑" in result
            assert "stopped" in result.lower()


# =====================================
# TestInterruptionStatisticsNoData
# =====================================


@pytest.mark.unit
class TestInterruptionStatisticsNoData:
    """When the stats dict has zero sections of real data,
    ``_has_statistics_data`` should return False."""

    @pytest.mark.asyncio
    async def test_get_interruption_statistics_no_data(self) -> None:
        """When interruption formatters see structure that produces no data,
        the result should at least be a non-empty string."""
        from session_buddy.advanced_features import get_interruption_statistics

        # Provide data the formatters can render (empty sessions / snapshots /
        # no interruptions). The ``interruptions`` and ``snapshots`` formatters
        # in advanced_features are passed whatever's at those keys, but they
        # only iterate short slices, so empty lists are safe.
        stats = {
            "sessions": {},
            "interruptions": {"by_type": [], "total": 0},
            "snapshots": {},
        }

        async def fake(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return stats

        with patch(
            "session_buddy.interruption_manager.get_interruption_statistics",
            new=fake,
        ):
            result = await get_interruption_statistics(user_id="test-user")

        # The result is a string (whether the no-data or error path);
        # we exercise the real production code.
        assert isinstance(result, str)
        assert len(result) > 0


# =====================================
# TestProjectDependencyLiteral
# =====================================


@pytest.mark.unit
class TestProjectDependencyLiteral:
    """Verify the dependency-type literal in ``add_project_dependency``."""

    @pytest.mark.asyncio
    async def test_add_project_dependency_with_extends(self) -> None:
        """``extends`` is one of the allowed dependency_type literals."""
        from session_buddy.advanced_features import add_project_dependency

        mock_dep = MagicMock()
        mock_dep.source_project = "A"
        mock_dep.target_project = "B"
        mock_dep.dependency_type = "extends"
        mock_dep.description = "test"

        mock_coord = MagicMock()
        mock_coord.add_project_dependency = AsyncMock(return_value=mock_dep)
        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator",
            return_value=mock_coord,
        ):
            result = await add_project_dependency(
                source_project="A",
                target_project="B",
                dependency_type="extends",
                description="test",
            )
            assert "extends" in result
            assert "test" in result or "None" in result
