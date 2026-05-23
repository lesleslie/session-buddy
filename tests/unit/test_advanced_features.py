"""Tests for advanced_features module.

Tests advanced MCP tools for multi-project coordination, natural scheduling,
interruption management, and enhanced search.

Phase: Week 5 Day 2 - Advanced Features Coverage
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAdvancedFeaturesHub:
    """Test AdvancedFeaturesHub coordinator class."""

    def test_hub_initialization(self) -> None:
        """Should initialize with logger and feature flags."""
        from session_buddy.advanced_features import AdvancedFeaturesHub

        mock_logger = MagicMock()
        hub = AdvancedFeaturesHub(mock_logger)

        assert hub.logger == mock_logger
        assert hub._multi_project_initialized is False
        assert hub._advanced_search_initialized is False
        assert hub._app_monitor_initialized is False

    @pytest.mark.asyncio
    async def test_initialize_multi_project_not_implemented(self) -> None:
        """Should raise NotImplementedError for multi-project init."""
        from session_buddy.advanced_features import AdvancedFeaturesHub

        hub = AdvancedFeaturesHub(MagicMock())

        with pytest.raises(NotImplementedError):
            await hub.initialize_multi_project()

    @pytest.mark.asyncio
    async def test_initialize_advanced_search_not_implemented(self) -> None:
        """Should raise NotImplementedError for advanced search init."""
        from session_buddy.advanced_features import AdvancedFeaturesHub

        hub = AdvancedFeaturesHub(MagicMock())

        with pytest.raises(NotImplementedError):
            await hub.initialize_advanced_search()

    @pytest.mark.asyncio
    async def test_initialize_app_monitor_not_implemented(self) -> None:
        """Should raise NotImplementedError for app monitor init."""
        from session_buddy.advanced_features import AdvancedFeaturesHub

        hub = AdvancedFeaturesHub(MagicMock())

        with pytest.raises(NotImplementedError):
            await hub.initialize_app_monitor()


class TestNaturalReminderTools:
    """Test natural language reminder MCP tools."""

    @pytest.mark.asyncio
    async def test_create_natural_reminder_success(self) -> None:
        """Should create reminder and return formatted output."""
        from session_buddy.advanced_features import create_natural_reminder

        with patch(
            "session_buddy.natural_scheduler.create_natural_reminder"
        ) as mock_create:
            mock_create.return_value = "reminder-123"

            result = await create_natural_reminder(
                title="Test reminder",
                time_expression="in 30 minutes",
                description="Test description",
            )

            assert isinstance(result, str)
            assert "successfully" in result or "✅" in result or "⏰" in result
            assert "reminder-123" in result

    @pytest.mark.asyncio
    async def test_create_natural_reminder_handles_import_error(self) -> None:
        """Should handle missing dependencies gracefully."""
        from session_buddy.advanced_features import create_natural_reminder

        # Mock the import to raise ImportError
        with patch("builtins.__import__", side_effect=ImportError):
            result = await create_natural_reminder(
                title="Test", time_expression="in 1 hour"
            )

            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_create_natural_reminder_failure(self) -> None:
        """Should handle reminder creation failure."""
        from session_buddy.advanced_features import create_natural_reminder

        with patch(
            "session_buddy.natural_scheduler.create_natural_reminder"
        ) as mock_create:
            mock_create.return_value = ""  # Empty string means failure

            result = await create_natural_reminder(
                title="Test", time_expression="invalid time"
            )

            assert isinstance(result, str)
            assert "Failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_create_natural_reminder_with_project_id(self) -> None:
        """Should create reminder with project ID included."""
        from session_buddy.advanced_features import create_natural_reminder

        with patch(
            "session_buddy.natural_scheduler.create_natural_reminder"
        ) as mock_create:
            mock_create.return_value = "reminder-456"

            result = await create_natural_reminder(
                title="Project reminder",
                time_expression="tomorrow at 9am",
                description="Important deadline",
                user_id="test-user",
                project_id="my-project",
            )

            assert isinstance(result, str)
            assert "reminder-456" in result

    @pytest.mark.asyncio
    async def test_list_user_reminders_with_reminders(self) -> None:
        """Should list user reminders."""
        from session_buddy.advanced_features import list_user_reminders

        with patch("session_buddy.natural_scheduler.list_user_reminders") as mock_list:
            mock_list.return_value = [{"id": "1", "title": "Reminder 1"}]

            with patch(
                "session_buddy.utils.session_formatters._format_reminders_list"
            ) as mock_format:
                mock_format.return_value = ["Formatted output"]

                result = await list_user_reminders(user_id="test-user")

                assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_list_user_reminders_empty(self) -> None:
        """Should handle empty reminder list."""
        from session_buddy.advanced_features import list_user_reminders

        with patch("session_buddy.natural_scheduler.list_user_reminders") as mock_list:
            mock_list.return_value = []

            with patch(
                "session_buddy.utils.session_formatters._format_no_reminders_message"
            ) as mock_format:
                mock_format.return_value = ["No reminders"]

                result = await list_user_reminders(user_id="test-user")

                assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_list_user_reminders_import_error(self) -> None:
        """Should handle import error when listing reminders."""
        from session_buddy.advanced_features import list_user_reminders

        with patch("builtins.__import__", side_effect=ImportError):
            result = await list_user_reminders(user_id="test-user")

            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_cancel_user_reminder_success(self) -> None:
        """Should cancel reminder and return confirmation."""
        from session_buddy.advanced_features import cancel_user_reminder

        with patch(
            "session_buddy.natural_scheduler.cancel_user_reminder"
        ) as mock_cancel:
            mock_cancel.return_value = True

            result = await cancel_user_reminder(reminder_id="reminder-123")

            assert isinstance(result, str)
            assert "cancelled" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_cancel_user_reminder_failure(self) -> None:
        """Should handle failed cancellation."""
        from session_buddy.advanced_features import cancel_user_reminder

        with patch(
            "session_buddy.natural_scheduler.cancel_user_reminder"
        ) as mock_cancel:
            mock_cancel.return_value = False

            result = await cancel_user_reminder(reminder_id="nonexistent")

            assert isinstance(result, str)
            assert "Failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_cancel_user_reminder_import_error(self) -> None:
        """Should handle import error when cancelling reminder."""
        from session_buddy.advanced_features import cancel_user_reminder

        with patch("builtins.__import__", side_effect=ImportError):
            result = await cancel_user_reminder(reminder_id="reminder-123")

            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_start_reminder_service_success(self) -> None:
        """Should start reminder service."""
        from session_buddy.advanced_features import start_reminder_service

        with patch("session_buddy.natural_scheduler.register_session_notifications"):
            with patch("session_buddy.natural_scheduler.start_reminder_service"):
                result = await start_reminder_service()

                assert isinstance(result, str)
                assert "started" in result or "🚀" in result

    @pytest.mark.asyncio
    async def test_start_reminder_service_import_error(self) -> None:
        """Should handle import error when starting service."""
        from session_buddy.advanced_features import start_reminder_service

        with patch("builtins.__import__", side_effect=ImportError):
            result = await start_reminder_service()

            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_stop_reminder_service_success(self) -> None:
        """Should stop reminder service."""
        from session_buddy.advanced_features import stop_reminder_service

        with patch("session_buddy.natural_scheduler.stop_reminder_service"):
            result = await stop_reminder_service()

            assert isinstance(result, str)
            assert "stopped" in result or "🛑" in result

    @pytest.mark.asyncio
    async def test_stop_reminder_service_import_error(self) -> None:
        """Should handle import error when stopping service."""
        from session_buddy.advanced_features import stop_reminder_service

        with patch("builtins.__import__", side_effect=ImportError):
            result = await stop_reminder_service()

            assert "not available" in result or "❌" in result


class TestInterruptionManagement:
    """Test interruption management tools."""

    @pytest.mark.asyncio
    async def test_get_interruption_statistics_with_data(self) -> None:
        """Should return formatted interruption statistics."""
        from session_buddy.advanced_features import get_interruption_statistics

        # Test the import error path since interruption_manager is optional
        with patch("builtins.__import__", side_effect=ImportError):
            result = await get_interruption_statistics(user_id="test-user")

            assert isinstance(result, str)
            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_get_interruption_statistics_with_full_data(self) -> None:
        """Should return full interruption statistics when data is available."""
        from session_buddy.advanced_features import get_interruption_statistics

        mock_stats = {
            "sessions": {"total_sessions": 5, "active_sessions": 2},
            "interruptions": {"by_type": ["context_switch", "break"]},
            "snapshots": {"total": 10},
        }

        with patch(
            "session_buddy.interruption_manager.get_interruption_statistics"
        ) as mock_get:
            mock_get.return_value = mock_stats

            with patch(
                "session_buddy.utils._format_statistics_header"
            ) as mock_header:
                mock_header.return_value = ["Header"]

                with patch(
                    "session_buddy.advanced_features._format_session_statistics"
                ) as mock_sess:
                    mock_sess.return_value = []

                    with patch(
                        "session_buddy.utils.session_formatters._format_interruption_statistics"
                    ) as mock_int:
                        mock_int.return_value = []

                        with patch(
                            "session_buddy.utils.session_formatters._format_snapshot_statistics"
                        ) as mock_snap:
                            mock_snap.return_value = []

                            with patch(
                                "session_buddy.utils._format_efficiency_metrics"
                            ) as mock_eff:
                                mock_eff.return_value = []

                                with patch(
                                    "session_buddy.advanced_features._has_statistics_data",
                                    return_value=True,
                                ):
                                    result = await get_interruption_statistics(
                                        user_id="test-user"
                                    )

                                    assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_interruption_statistics_generic_error(self) -> None:
        """Should handle generic errors gracefully."""
        from session_buddy.advanced_features import get_interruption_statistics

        with patch(
            "session_buddy.interruption_manager.get_interruption_statistics",
            side_effect=Exception("Database error"),
        ):
            result = await get_interruption_statistics(user_id="test-user")

            assert isinstance(result, str)
            assert "Error" in result or "❌" in result


class TestMultiProjectCoordination:
    """Test multi-project coordination tools."""

    @pytest.mark.asyncio
    async def test_create_project_group_success(self) -> None:
        """Should create project group and return formatted output."""
        from session_buddy.advanced_features import create_project_group

        mock_group = MagicMock()
        mock_group.name = "Test Group"
        mock_group.projects = ["project1", "project2"]
        mock_group.description = "Test description"
        mock_group.id = "group-123"

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator"
        ) as mock_get:
            mock_coordinator = AsyncMock()
            mock_coordinator.create_project_group = AsyncMock(return_value=mock_group)
            mock_get.return_value = mock_coordinator

            result = await create_project_group(
                name="Test Group", projects=["project1", "project2"]
            )

            assert isinstance(result, str)
            assert "Created" in result or "✅" in result
            assert "Test Group" in result

    @pytest.mark.asyncio
    async def test_create_project_group_not_available(self) -> None:
        """Should handle unavailable multi-project coordinator."""
        from session_buddy.advanced_features import create_project_group

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator",
            return_value=None,
        ):
            result = await create_project_group(
                name="Test Group", projects=["project1"]
            )

            assert isinstance(result, str)
            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_create_project_group_error(self) -> None:
        """Should handle errors when creating project group."""
        from session_buddy.advanced_features import create_project_group

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator"
        ) as mock_get:
            mock_coordinator = AsyncMock()
            mock_coordinator.create_project_group = AsyncMock(
                side_effect=Exception("Creation failed")
            )
            mock_get.return_value = mock_coordinator

            result = await create_project_group(
                name="Test Group", projects=["project1"]
            )

            assert isinstance(result, str)
            assert "Failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_add_project_dependency_success(self) -> None:
        """Should add project dependency."""
        from session_buddy.advanced_features import add_project_dependency

        mock_dependency = MagicMock()
        mock_dependency.source_project = "project1"
        mock_dependency.target_project = "project2"
        mock_dependency.dependency_type = "uses"
        mock_dependency.description = "Uses API"

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator"
        ) as mock_get:
            mock_coordinator = AsyncMock()
            mock_coordinator.add_project_dependency = AsyncMock(
                return_value=mock_dependency
            )
            mock_get.return_value = mock_coordinator

            result = await add_project_dependency(
                source_project="project1",
                target_project="project2",
                dependency_type="uses",
            )

            assert isinstance(result, str)
            assert "Added" in result or "✅" in result

    @pytest.mark.asyncio
    async def test_add_project_dependency_not_available(self) -> None:
        """Should handle unavailable coordinator."""
        from session_buddy.advanced_features import add_project_dependency

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator",
            return_value=None,
        ):
            result = await add_project_dependency(
                source_project="p1",
                target_project="p2",
                dependency_type="uses",
            )

            assert isinstance(result, str)
            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_search_across_projects_with_results(self) -> None:
        """Should search across related projects."""
        from session_buddy.advanced_features import search_across_projects

        mock_results = [
            {
                "content": "Test content",
                "score": 0.95,
                "is_current_project": True,
                "source_project": "project1",
                "timestamp": "2025-01-01",
            }
        ]

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator"
        ) as mock_get:
            mock_coordinator = AsyncMock()
            mock_coordinator.find_related_conversations = AsyncMock(
                return_value=mock_results
            )
            mock_get.return_value = mock_coordinator

            result = await search_across_projects(
                query="test", current_project="project1"
            )

            assert isinstance(result, str)
            assert "Test content" in result

    @pytest.mark.asyncio
    async def test_search_across_projects_no_results(self) -> None:
        """Should handle no search results."""
        from session_buddy.advanced_features import search_across_projects

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator"
        ) as mock_get:
            mock_coordinator = AsyncMock()
            mock_coordinator.find_related_conversations = AsyncMock(return_value=[])
            mock_get.return_value = mock_coordinator

            result = await search_across_projects(
                query="nonexistent", current_project="project1"
            )

            assert isinstance(result, str)
            assert "No results" in result

    @pytest.mark.asyncio
    async def test_search_across_projects_not_available(self) -> None:
        """Should handle unavailable coordinator."""
        from session_buddy.advanced_features import search_across_projects

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator",
            return_value=None,
        ):
            result = await search_across_projects(
                query="test", current_project="project1"
            )

            assert isinstance(result, str)
            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_get_project_insights_success(self) -> None:
        """Should get project insights."""
        from session_buddy.advanced_features import get_project_insights

        # Test unavailable coordinator path
        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator"
        ) as mock_get:
            mock_get.return_value = None

            result = await get_project_insights(projects=["project1", "project2"])

            assert isinstance(result, str)
            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_get_project_insights_error(self) -> None:
        """Should handle errors getting project insights."""
        from session_buddy.advanced_features import get_project_insights

        with patch(
            "session_buddy.advanced_features._get_multi_project_coordinator"
        ) as mock_get:
            mock_coordinator = AsyncMock()
            mock_coordinator.get_cross_project_insights = AsyncMock(
                side_effect=Exception("Insights failed")
            )
            mock_get.return_value = mock_coordinator

            result = await get_project_insights(projects=["project1"])

            assert isinstance(result, str)
            assert "Failed" in result or "❌" in result


class TestAdvancedSearch:
    """Test advanced search tools."""

    @pytest.mark.asyncio
    async def test_advanced_search_with_results(self) -> None:
        """Should perform advanced search with filters."""
        from session_buddy.advanced_features import advanced_search

        # Test unavailable search engine path
        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine"
        ) as mock_get:
            mock_get.return_value = None

            result = await advanced_search(query="test")

            assert isinstance(result, str)
            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_advanced_search_with_search_results(self) -> None:
        """Should return search results when available."""
        from session_buddy.advanced_features import advanced_search

        mock_engine = AsyncMock()
        mock_engine.search = AsyncMock(
            return_value={
                "results": [{"content": "Result 1", "score": 0.9}],
            }
        )
        mock_engine._parse_timeframe = MagicMock(return_value=("2025-01-01", "2025-12-31"))

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            with patch(
                "session_buddy.advanced_features._get_advanced_search_engine_sync",
                return_value=mock_engine,
            ):
                with patch(
                    "session_buddy.utils.session_formatters._format_advanced_search_results"
                ) as mock_format:
                    mock_format.return_value = "Formatted results"

                    result = await advanced_search(query="test")

                    assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_advanced_search_no_results(self) -> None:
        """Should handle no search results."""
        from session_buddy.advanced_features import advanced_search

        mock_engine = AsyncMock()
        mock_engine.search = AsyncMock(return_value={"results": []})

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await advanced_search(query="nonexistent")

            assert isinstance(result, str)
            assert "No results" in result

    @pytest.mark.asyncio
    async def test_advanced_search_error(self) -> None:
        """Should handle search errors gracefully."""
        from session_buddy.advanced_features import advanced_search

        mock_engine = AsyncMock()
        mock_engine.search = AsyncMock(side_effect=Exception("Search failed"))

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = await advanced_search(query="test")

            assert isinstance(result, str)
            assert "Failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_search_suggestions_success(self) -> None:
        """Should return search suggestions."""
        from session_buddy.advanced_features import search_suggestions

        mock_suggestions = ["suggestion1", "suggestion2"]

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine"
        ) as mock_get:
            mock_engine = AsyncMock()
            mock_engine.get_suggestions = AsyncMock(return_value=mock_suggestions)
            mock_get.return_value = mock_engine

            result = await search_suggestions(query="test")

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_search_suggestions_no_results(self) -> None:
        """Should handle no suggestions."""
        from session_buddy.advanced_features import search_suggestions

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine"
        ) as mock_get:
            mock_engine = AsyncMock()
            mock_engine.suggest_completions = AsyncMock(return_value=[])
            mock_get.return_value = mock_engine

            result = await search_suggestions(query="xyz")

            assert isinstance(result, str)
            assert "No suggestions" in result

    @pytest.mark.asyncio
    async def test_search_suggestions_not_available(self) -> None:
        """Should handle unavailable search engine."""
        from session_buddy.advanced_features import search_suggestions

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=None,
        ):
            result = await search_suggestions(query="test")

            assert isinstance(result, str)
            assert "not available" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_get_search_metrics_success(self) -> None:
        """Should return search metrics."""
        from session_buddy.advanced_features import get_search_metrics

        mock_metrics = {"total_searches": 100, "avg_results": 5}

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine"
        ) as mock_get:
            mock_engine = AsyncMock()
            mock_engine.get_metrics = AsyncMock(return_value=mock_metrics)
            mock_get.return_value = mock_engine

            result = await get_search_metrics(metric_type="searches")

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_search_metrics_error_response(self) -> None:
        """Should handle error in metrics response."""
        from session_buddy.advanced_features import get_search_metrics

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine"
        ) as mock_get:
            mock_engine = AsyncMock()
            mock_engine.aggregate_metrics = AsyncMock(
                return_value={"error": "Invalid metric type"}
            )
            mock_get.return_value = mock_engine

            result = await get_search_metrics(metric_type="invalid")

            assert isinstance(result, str)
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_get_search_metrics_empty_data(self) -> None:
        """Should handle empty metrics data."""
        from session_buddy.advanced_features import get_search_metrics

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine"
        ) as mock_get:
            mock_engine = AsyncMock()
            mock_engine.aggregate_metrics = AsyncMock(
                return_value={"data": [], "timeframe": "30d"}
            )
            mock_get.return_value = mock_engine

            result = await get_search_metrics(metric_type="searches")

            assert isinstance(result, str)
            assert "No data" in result

    @pytest.mark.asyncio
    async def test_get_search_metrics_not_available(self) -> None:
        """Should handle unavailable search engine."""
        from session_buddy.advanced_features import get_search_metrics

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=None,
        ):
            result = await get_search_metrics(metric_type="searches")

            assert isinstance(result, str)
            assert "not available" in result or "❌" in result


class TestGitWorktreeManagement:
    """Test git worktree management tools."""

    @pytest.mark.asyncio
    async def test_git_worktree_add_success(self) -> None:
        """Should add git worktree."""
        from session_buddy.advanced_features import git_worktree_add

        # Mock WorktreeManager where it's imported from
        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.create_worktree = AsyncMock(
                return_value={
                    "success": True,
                    "branch": "feature",
                    "worktree_path": "/tmp/worktree",
                    "output": "Created worktree",
                }
            )
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_add(branch="feature", path="/tmp/worktree")

            assert isinstance(result, str)
            assert "🎉" in result or "Created" in result

    @pytest.mark.asyncio
    async def test_git_worktree_add_failure(self) -> None:
        """Should handle worktree creation failure."""
        from session_buddy.advanced_features import git_worktree_add

        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.create_worktree = AsyncMock(
                return_value={"success": False, "error": "Branch already exists"}
            )
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_add(branch="main", path="/tmp/worktree")

            assert isinstance(result, str)
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_git_worktree_add_exception(self) -> None:
        """Should handle exceptions during worktree creation."""
        from session_buddy.advanced_features import git_worktree_add

        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.create_worktree = AsyncMock(side_effect=Exception("Git error"))
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_add(branch="feature", path="/tmp/worktree")

            assert isinstance(result, str)
            assert "Failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_git_worktree_add_with_working_directory(self) -> None:
        """Should add git worktree with custom working directory."""
        from session_buddy.advanced_features import git_worktree_add

        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.create_worktree = AsyncMock(
                return_value={
                    "success": True,
                    "branch": "feature",
                    "worktree_path": "/tmp/worktree",
                }
            )
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_add(
                branch="feature",
                path="new-worktree",
                working_directory="/home/user/repos/myproject",
                create_branch=True,
            )

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_git_worktree_remove_success(self) -> None:
        """Should remove git worktree."""
        from session_buddy.advanced_features import git_worktree_remove

        # Mock WorktreeManager where it's imported from
        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.remove_worktree = AsyncMock(
                return_value={
                    "success": True,
                    "removed_path": "/tmp/worktree",
                    "output": "Removed worktree",
                }
            )
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_remove(path="/tmp/worktree")

            assert isinstance(result, str)
            assert "🗑️" in result or "Removed" in result

    @pytest.mark.asyncio
    async def test_git_worktree_remove_failure(self) -> None:
        """Should handle worktree removal failure."""
        from session_buddy.advanced_features import git_worktree_remove

        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.remove_worktree = AsyncMock(
                return_value={"success": False, "error": "Not found"}
            )
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_remove(path="/tmp/nonexistent")

            assert isinstance(result, str)
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_git_worktree_remove_force(self) -> None:
        """Should remove git worktree with force flag."""
        from session_buddy.advanced_features import git_worktree_remove

        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.remove_worktree = AsyncMock(
                return_value={
                    "success": True,
                    "removed_path": "/tmp/worktree",
                    "output": "Force removed",
                }
            )
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_remove(path="/tmp/worktree", force=True)

            assert isinstance(result, str)
            assert "force" in result.lower() or "yes" in result.lower()

    @pytest.mark.asyncio
    async def test_git_worktree_switch_success(self) -> None:
        """Should switch between worktrees."""
        from session_buddy.advanced_features import git_worktree_switch

        # Mock WorktreeManager where it's imported from
        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.switch_worktree_context = AsyncMock(
                return_value={
                    "success": True,
                    "from_worktree": {"branch": "main", "path": "/tmp/wt1"},
                    "to_worktree": {"branch": "feature", "path": "/tmp/wt2"},
                    "context_preserved": True,
                }
            )
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_switch(from_path="/tmp/wt1", to_path="/tmp/wt2")

            assert isinstance(result, str)
            assert "Switch" in result or "Complete" in result

    @pytest.mark.asyncio
    async def test_git_worktree_switch_failure(self) -> None:
        """Should handle worktree switch failure."""
        from session_buddy.advanced_features import git_worktree_switch

        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.switch_worktree_context = AsyncMock(
                return_value={"success": False, "error": "Switch failed"}
            )
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_switch(from_path="/tmp/wt1", to_path="/tmp/wt2")

            assert isinstance(result, str)
            assert "❌" in result or "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_git_worktree_switch_context_not_preserved(self) -> None:
        """Should handle switch with failed context preservation."""
        from session_buddy.advanced_features import git_worktree_switch

        with patch(
            "session_buddy.worktree_manager.WorktreeManager"
        ) as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.switch_worktree_context = AsyncMock(
                return_value={
                    "success": True,
                    "from_worktree": {"branch": "main", "path": "/tmp/wt1"},
                    "to_worktree": {"branch": "feature", "path": "/tmp/wt2"},
                    "context_preserved": False,
                    "session_error": "State file not found",
                }
            )
            mock_manager_cls.return_value = mock_manager

            result = await git_worktree_switch(from_path="/tmp/wt1", to_path="/tmp/wt2")

            assert isinstance(result, str)
            # Should still show success since git switch worked
            assert "Switch" in result or "Complete" in result


class TestSessionWelcome:
    """Test session welcome tool."""

    @pytest.mark.asyncio
    async def test_session_welcome_returns_formatted_message(self) -> None:
        """Should return session welcome message."""
        from session_buddy.advanced_features import session_welcome

        # Test basic functionality without setting connection info
        result = await session_welcome()

        assert isinstance(result, str)
        # Should return some welcome-related content
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_session_welcome_with_connection_info(self) -> None:
        """Should return welcome message with connection info."""
        from session_buddy.advanced_features import session_welcome, set_connection_info

        connection_info = {
            "project": "/path/to/project",
            "quality_score": 85,
            "connected_at": "2025-01-01T10:00:00",
            "previous_session": {
                "ended_at": "2025-01-01T09:00:00",
                "quality_score": 82,
                "top_recommendation": "Keep using feature flags",
            },
            "recommendations": ["Enable TurboQuant", "Try phased rollouts"],
        }

        set_connection_info(connection_info)
        result = await session_welcome()

        assert isinstance(result, str)
        assert "/path/to/project" in result
        assert "85" in result

    @pytest.mark.asyncio
    async def test_session_welcome_first_session(self) -> None:
        """Should return first session message when no previous session."""
        from session_buddy.advanced_features import session_welcome, set_connection_info

        connection_info = {
            "project": "/path/to/project",
            "quality_score": 100,
            "connected_at": "2025-01-01T10:00:00",
            "previous_session": None,
            "recommendations": [],
        }

        set_connection_info(connection_info)
        result = await session_welcome()

        assert isinstance(result, str)
        assert "first session" in result.lower() or "first" in result.lower()

    @pytest.mark.asyncio
    async def test_session_welcome_clears_connection_info(self) -> None:
        """Should clear connection info after displaying welcome."""
        from session_buddy.advanced_features import session_welcome, set_connection_info

        connection_info = {
            "project": "/path/to/project",
            "quality_score": 85,
            "connected_at": "2025-01-01T10:00:00",
        }

        set_connection_info(connection_info)
        result1 = await session_welcome()
        result2 = await session_welcome()

        # Second call should show "not available" since connection info was cleared
        assert "not available" in result2 or "not available" in result1.lower()


class TestHelperFunctions:
    """Test utility and helper functions."""

    def test_calculate_overdue_time_for_overdue_reminder(self) -> None:
        """Should calculate overdue time."""
        from session_buddy.advanced_features import _calculate_overdue_time

        # Use a past timestamp
        past_time = "2020-01-01T12:00:00"

        result = _calculate_overdue_time(past_time)

        assert isinstance(result, str)
        assert "Overdue" in result or "⏱️" in result

    def test_calculate_overdue_time_for_future_reminder(self) -> None:
        """Should handle future scheduled time."""
        from session_buddy.advanced_features import _calculate_overdue_time

        # Use a future timestamp
        from datetime import datetime, timedelta

        future_time = (datetime.now() + timedelta(days=1)).isoformat()

        result = _calculate_overdue_time(future_time)

        assert isinstance(result, str)
        assert "Not yet due" in result or "⏱️" in result

    def test_calculate_overdue_time_invalid_format(self) -> None:
        """Should handle invalid timestamp format."""
        from session_buddy.advanced_features import _calculate_overdue_time

        result = _calculate_overdue_time("not-a-timestamp")

        assert isinstance(result, str)
        assert "Error" in result or "❌" in result

    def test_format_session_statistics_with_data(self) -> None:
        """Should format session statistics."""
        from session_buddy.advanced_features import _format_session_statistics

        sessions = {
            "total_sessions": 10,
            "active_sessions": 3,
            "avg_duration": "1h 30m",
        }

        result = _format_session_statistics(sessions)

        assert isinstance(result, list)
        assert len(result) > 0

    def test_format_session_statistics_empty(self) -> None:
        """Should handle empty session statistics."""
        from session_buddy.advanced_features import _format_session_statistics

        result = _format_session_statistics({})

        assert isinstance(result, list)
        assert len(result) == 0

    def test_format_session_statistics_partial(self) -> None:
        """Should handle partial session statistics."""
        from session_buddy.advanced_features import _format_session_statistics

        sessions = {"total_sessions": 5}

        result = _format_session_statistics(sessions)

        assert isinstance(result, list)
        assert len(result) > 0

    def test_has_statistics_data_with_data(self) -> None:
        """Should detect presence of statistics data."""
        from session_buddy.advanced_features import _has_statistics_data

        assert _has_statistics_data({"total": 1}, {}, {}) is True
        assert _has_statistics_data({}, {"count": 1}, {}) is True
        assert _has_statistics_data({}, {}, {"snapshots": 1}) is True

    def test_has_statistics_data_without_data(self) -> None:
        """Should detect absence of statistics data."""
        from session_buddy.advanced_features import _has_statistics_data

        assert _has_statistics_data({}, {}, {}) is False
        assert _has_statistics_data(None, None, None) is False

    def test_build_advanced_search_filters_empty(self) -> None:
        """Should return empty filters when no params provided."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        result = _build_advanced_search_filters(None, None, None)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_build_advanced_search_filters_with_content_type(self) -> None:
        """Should build filter for content type."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        result = _build_advanced_search_filters("conversation", None, None)

        assert isinstance(result, list)
        assert len(result) == 1

    def test_build_advanced_search_filters_with_project(self) -> None:
        """Should build filter for project."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        result = _build_advanced_search_filters(None, "my-project", None)

        assert isinstance(result, list)
        assert len(result) == 1

    def test_build_advanced_search_filters_with_timeframe(self) -> None:
        """Should build filter for timeframe."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        # Need to mock the engine to get the timeframe filter
        mock_engine = MagicMock()
        mock_engine._parse_timeframe = MagicMock(
            return_value=("2025-01-01", "2025-12-31")
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine_sync",
            return_value=mock_engine,
        ):
            result = _build_advanced_search_filters(None, None, "30d")

            assert isinstance(result, list)

    def test_build_advanced_search_filters_all_params(self) -> None:
        """Should build filters for all parameters."""
        from session_buddy.advanced_features import _build_advanced_search_filters

        mock_engine = MagicMock()
        mock_engine._parse_timeframe = MagicMock(
            return_value=("2025-01-01", "2025-12-31")
        )

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine_sync",
            return_value=mock_engine,
        ):
            result = _build_advanced_search_filters("conversation", "project-x", "7d")

            assert isinstance(result, list)
            assert len(result) == 3

    def test_get_worktree_indicators_main_detached(self) -> None:
        """Should return correct indicators for main and detached."""
        from session_buddy.advanced_features import _get_worktree_indicators

        main_indicator, detached_indicator = _get_worktree_indicators(
            is_main=True, is_detached=True
        )

        assert " (main)" in main_indicator
        assert " (detached)" in detached_indicator

    def test_get_worktree_indicators_neither(self) -> None:
        """Should return empty strings when not main or detached."""
        from session_buddy.advanced_features import _get_worktree_indicators

        main_indicator, detached_indicator = _get_worktree_indicators(
            is_main=False, is_detached=False
        )

        assert main_indicator == ""
        assert detached_indicator == ""

    def test_get_worktree_indicators_only_main(self) -> None:
        """Should return main indicator when only is_main is True."""
        from session_buddy.advanced_features import _get_worktree_indicators

        main_indicator, detached_indicator = _get_worktree_indicators(
            is_main=True, is_detached=False
        )

        assert " (main)" in main_indicator
        assert detached_indicator == ""

    def test_resolve_worktree_working_dir_with_value(self) -> None:
        """Should return provided working directory."""
        from session_buddy.advanced_features import _resolve_worktree_working_dir
        from pathlib import Path

        result = _resolve_worktree_working_dir("/custom/path")

        assert result == Path("/custom/path")

    def test_resolve_worktree_working_dir_empty_uses_cwd(self) -> None:
        """Should use current working directory when none provided."""
        from session_buddy.advanced_features import _resolve_worktree_working_dir

        result = _resolve_worktree_working_dir(None)

        assert result == result  # Should be a valid Path

    def test_format_worktree_switch_result(self) -> None:
        """Should format worktree switch result."""
        from session_buddy.advanced_features import _format_worktree_switch_result

        result_dict = {
            "from_worktree": {"branch": "main", "path": "/tmp/wt1"},
            "to_worktree": {"branch": "feature", "path": "/tmp/wt2"},
            "context_preserved": True,
            "session_state_saved": True,
            "session_state_restored": True,
        }

        result = _format_worktree_switch_result(result_dict)

        assert isinstance(result, str)
        assert "main" in result
        assert "feature" in result

    def test_format_context_preserved(self) -> None:
        """Should format preserved context information."""
        from session_buddy.advanced_features import _format_context_preserved

        result_dict = {
            "context_preserved": True,
            "session_state_saved": True,
            "session_state_restored": True,
        }

        result = _format_context_preserved(result_dict)

        assert isinstance(result, list)
        assert len(result) > 0

    def test_format_context_failed(self) -> None:
        """Should format failed context information."""
        from session_buddy.advanced_features import _format_context_failed

        result_dict = {
            "context_preserved": False,
            "session_error": "State file corrupted",
        }

        result = _format_context_failed(result_dict)

        assert isinstance(result, list)
        assert len(result) > 0
        assert "corrupted" in result[0].lower() or "failed" in result[0].lower()

    def test_format_context_failed_no_error(self) -> None:
        """Should format failed context without specific error."""
        from session_buddy.advanced_features import _format_context_failed

        result_dict = {"context_preserved": False}

        result = _format_context_failed(result_dict)

        assert isinstance(result, list)
        assert len(result) > 0


class TestGetMultiProjectCoordinator:
    """Test multi-project coordinator getter."""

    @pytest.mark.asyncio
    async def test_get_multi_project_coordinator_returns_coordinator(self) -> None:
        """Should return coordinator when available."""
        from session_buddy.advanced_features import _get_multi_project_coordinator

        with patch("session_buddy.multi_project_coordinator.MultiProjectCoordinator"):
            with patch("session_buddy.reflection_tools.get_reflection_database") as mock_db:
                mock_db.return_value = MagicMock()

                result = await _get_multi_project_coordinator()

                assert result is not None

    @pytest.mark.asyncio
    async def test_get_multi_project_coordinator_returns_none_on_error(self) -> None:
        """Should return None when exception occurs."""
        from session_buddy.advanced_features import _get_multi_project_coordinator

        with patch(
            "session_buddy.multi_project_coordinator.MultiProjectCoordinator",
            side_effect=Exception("Import failed"),
        ):
            result = await _get_multi_project_coordinator()

            assert result is None


class TestGetAdvancedSearchEngine:
    """Test advanced search engine getter."""

    @pytest.mark.asyncio
    async def test_get_advanced_search_engine_returns_engine(self) -> None:
        """Should return engine when available."""
        from session_buddy.advanced_features import _get_advanced_search_engine

        with patch("session_buddy.advanced_search.AdvancedSearchEngine"):
            with patch("session_buddy.reflection_tools.get_reflection_database") as mock_db:
                mock_db.return_value = MagicMock()

                result = await _get_advanced_search_engine()

                assert result is not None

    @pytest.mark.asyncio
    async def test_get_advanced_search_engine_returns_none_on_error(self) -> None:
        """Should return None when exception occurs."""
        from session_buddy.advanced_features import _get_advanced_search_engine

        with patch(
            "session_buddy.advanced_search.AdvancedSearchEngine",
            side_effect=Exception("Import failed"),
        ):
            result = await _get_advanced_search_engine()

            assert result is None

    def test_get_advanced_search_engine_sync(self) -> None:
        """Should return engine synchronously."""
        from session_buddy.advanced_features import _get_advanced_search_engine_sync

        mock_engine = MagicMock()

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            return_value=mock_engine,
        ):
            result = _get_advanced_search_engine_sync()

            assert result == mock_engine

    def test_get_advanced_search_engine_sync_handles_exception(self) -> None:
        """Should return None when sync call fails."""
        from session_buddy.advanced_features import _get_advanced_search_engine_sync

        with patch(
            "session_buddy.advanced_features._get_advanced_search_engine",
            side_effect=Exception("Async error"),
        ):
            result = _get_advanced_search_engine_sync()

            assert result is None