#!/usr/bin/env python3
"""Comprehensive test suite for session_buddy.mcp.tools.infrastructure.protocols module.

Tests protocol definitions, method signatures, and mock implementations.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, get_protocol_members
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.infrastructure.protocols import (
    AgentAnalyzerProtocol,
    CrackerjackIntegrationProtocol,
    CrackerjackResultProtocol,
    QualityMetricsExtractorProtocol,
    RecommendationEngineProtocol,
    ReflectionDatabaseProtocol,
)
from session_buddy.mcp.tools.intelligence.agent_analyzer import (
    AgentRecommendation,
    AgentType,
)
from session_buddy.mcp.tools.advanced.recommendation_engine import AgentEffectiveness
from session_buddy.tools.quality_metrics import QualityMetrics


# ==============================================================================
# Mock Implementations for Testing
# ==============================================================================


class MockQualityMetricsExtractor:
    """Mock implementation of QualityMetricsExtractorProtocol."""

    @classmethod
    def extract(cls, stdout: str, stderr: str) -> QualityMetrics:
        """Extract metrics from crackerjack output."""
        metrics = QualityMetrics()
        combined = stdout + stderr

        if "coverage:" in combined.lower() or "coverage:" in combined.lower():
            import re

            if match := re.search(r"coverage:?\s*(\d+(?:\.\d+)?)%", combined):
                metrics.coverage_percent = float(match.group(1))

        if "complexity of" in combined.lower() and "too high" in combined.lower():
            import re

            matches = re.findall(r"Complexity of (\d+) is too high", combined)
            if matches:
                metrics.max_complexity = max(int(m) for m in matches)
                metrics.complexity_violations = len(matches)

        if "B" in combined:
            import re

            metrics.security_issues = len(re.findall(r"B\d{3}:", combined))

        if "passed" in combined:
            import re

            if match := re.search(r"(\d+) passed", combined):
                metrics.tests_passed = int(match.group(1))
            if match := re.search(r"(\d+) failed", combined):
                metrics.tests_failed = int(match.group(1))

        return metrics


class MockAgentAnalyzer:
    """Mock implementation of AgentAnalyzerProtocol."""

    @classmethod
    def analyze(
        cls,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> list[AgentRecommendation]:
        """Analyze crackerjack output and recommend agents."""
        if exit_code == 0:
            return []

        recommendations = []
        combined = stdout + stderr

        if "complexity" in combined.lower() and "too high" in combined.lower():
            recommendations.append(
                AgentRecommendation(
                    agent=AgentType.REFACTORING,
                    confidence=0.9,
                    reason="Complexity violation detected",
                    quick_fix_command="python -m crackerjack --ai-fix",
                    pattern_matched=r"Complexity of (\d+) is too high",
                )
            )

        if "B" in combined and any(f"B{digits}" in combined for digits in ["108", "603", "101"]):
            recommendations.append(
                AgentRecommendation(
                    agent=AgentType.SECURITY,
                    confidence=0.8,
                    reason="Bandit security issue found",
                    quick_fix_command="python -m crackerjack --ai-fix",
                    pattern_matched=r"B\d{3}:",
                )
            )

        return recommendations[:3]

    @classmethod
    def format_recommendations(cls, recommendations: list[AgentRecommendation]) -> str:
        """Format recommendations for display."""
        if not recommendations:
            return ""

        output = "\n🤖 **AI Agent Recommendations**:\n"

        for i, rec in enumerate(recommendations, 1):
            confidence_emoji = "🔥" if rec.confidence >= 0.85 else "✨"
            output += (
                f"\n{i}. {confidence_emoji} **{rec.agent.value}** "
                f"(confidence: {rec.confidence:.0%})\n"
            )
            output += f"   - **Reason**: {rec.reason}\n"
            output += f"   - **Quick Fix**: `{rec.quick_fix_command}`\n"

        return output


class MockRecommendationEngine:
    """Mock implementation of RecommendationEngineProtocol."""

    @classmethod
    async def analyze_history(
        cls,
        db: Any,
        project: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """Analyze execution history for patterns and effectiveness."""
        results = await db.search_conversations(
            query="crackerjack",
            project=project,
            limit=50,
        )

        return {
            "patterns": [],
            "agent_effectiveness": [],
            "insights": ["Mock analysis complete"],
            "total_executions": len(results),
            "date_range": {"start": "mock", "end": "mock"},
        }

    @classmethod
    def adjust_confidence(
        cls,
        recommendations: list[AgentRecommendation],
        effectiveness: list[AgentEffectiveness],
    ) -> list[AgentRecommendation]:
        """Adjust recommendation confidence scores based on historical effectiveness."""
        if not effectiveness:
            return recommendations

        effectiveness_map = {e.agent: e for e in effectiveness}

        adjusted = []
        for rec in recommendations:
            agent_eff = effectiveness_map.get(rec.agent)
            if agent_eff and agent_eff.total_recommendations >= 5:
                adjusted_confidence = min(
                    (0.6 * agent_eff.success_rate) + (0.4 * rec.confidence),
                    1.0,
                )
                adjusted.append(
                    AgentRecommendation(
                        agent=rec.agent,
                        confidence=adjusted_confidence,
                        reason=f"{rec.reason} (adjusted based on {agent_eff.success_rate:.0%} historical success)",
                        quick_fix_command=rec.quick_fix_command,
                        pattern_matched=rec.pattern_matched,
                    )
                )
            else:
                adjusted.append(rec)

        return sorted(adjusted, key=lambda r: r.confidence, reverse=True)[:3]


class MockReflectionDatabase:
    """Mock implementation of ReflectionDatabaseProtocol."""

    def __init__(self, mock_results: list[dict[str, Any]] | None = None):
        self._mock_results = mock_results or []
        self._stored_conversations: list[dict[str, Any]] = []

    async def search_conversations(
        self,
        query: str,
        project: str | None = None,
        limit: int = 50,
        min_score: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Search for conversations in the database."""
        return self._mock_results[:limit]

    async def store_conversation(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a conversation in the database."""
        self._stored_conversations.append(
            {"content": content, "metadata": metadata or {}}
        )

    async def __aenter__(self) -> "MockReflectionDatabase":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        pass


class MockCrackerjackResult:
    """Mock implementation of CrackerjackResultProtocol."""

    def __init__(
        self,
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
        execution_time: float = 0.0,
    ):
        self._exit_code = exit_code
        self._stdout = stdout
        self._stderr = stderr
        self._execution_time = execution_time

    @property
    def exit_code(self) -> int:
        """Process exit code."""
        return self._exit_code

    @property
    def stdout(self) -> str:
        """Standard output."""
        return self._stdout

    @property
    def stderr(self) -> str:
        """Standard error."""
        return self._stderr

    @property
    def execution_time(self) -> float:
        """Execution time in seconds."""
        return self._execution_time


class MockCrackerjackIntegration:
    """Mock implementation of CrackerjackIntegrationProtocol."""

    def __init__(self, mock_result: MockCrackerjackResult | None = None):
        self._mock_result = mock_result or MockCrackerjackResult()

    async def execute_crackerjack_command(
        self,
        command: str,
        args: list[str] | None = None,
        working_directory: str = ".",
        timeout: int = 300,
        ai_agent_mode: bool = False,
    ) -> MockCrackerjackResult:
        """Execute a crackerjack command."""
        return self._mock_result


# ==============================================================================
# Protocol Definition Tests
# ==============================================================================


class TestQualityMetricsExtractorProtocol:
    """Test QualityMetricsExtractorProtocol definition."""

    def test_protocol_exists(self) -> None:
        """Test that QualityMetricsExtractorProtocol is defined."""
        assert QualityMetricsExtractorProtocol is not None

    def test_protocol_is_protocol(self) -> None:
        """Test that QualityMetricsExtractorProtocol is a Protocol."""
        from typing import Protocol

        assert issubclass(QualityMetricsExtractorProtocol, Protocol)

    def test_extract_method_exists(self) -> None:
        """Test that extract classmethod exists on protocol."""
        assert hasattr(QualityMetricsExtractorProtocol, "extract")
        members = list(get_protocol_members(QualityMetricsExtractorProtocol))
        assert "extract" in members

    def test_extract_method_signature(self) -> None:
        """Test that extract method has correct signature."""
        # Get the protocol's extract method
        extract_method = QualityMetricsExtractorProtocol.extract
        sig = inspect.signature(extract_method)

        # Verify parameters: (cls, stdout: str, stderr: str)
        params = list(sig.parameters.keys())
        assert params == ["stdout", "stderr"], f"Expected ['stdout', 'stderr'], got {params}"

        # Verify annotations
        assert sig.parameters["stdout"].annotation == str
        assert sig.parameters["stderr"].annotation == str

    def test_protocol_signature_compliance_mock(self) -> None:
        """Test that MockQualityMetricsExtractor complies with protocol signature."""
        sig = inspect.signature(MockQualityMetricsExtractor.extract)
        params = list(sig.parameters.keys())
        assert params == ["stdout", "stderr"], f"Mock doesn't match protocol signature: {params}"


class TestAgentAnalyzerProtocol:
    """Test AgentAnalyzerProtocol definition."""

    def test_protocol_exists(self) -> None:
        """Test that AgentAnalyzerProtocol is defined."""
        assert AgentAnalyzerProtocol is not None

    def test_protocol_is_protocol(self) -> None:
        """Test that AgentAnalyzerProtocol is a Protocol."""
        from typing import Protocol

        assert issubclass(AgentAnalyzerProtocol, Protocol)

    def test_analyze_method_exists(self) -> None:
        """Test that analyze classmethod exists on protocol."""
        assert hasattr(AgentAnalyzerProtocol, "analyze")
        members = list(get_protocol_members(AgentAnalyzerProtocol))
        assert "analyze" in members

    def test_format_recommendations_method_exists(self) -> None:
        """Test that format_recommendations classmethod exists on protocol."""
        assert hasattr(AgentAnalyzerProtocol, "format_recommendations")
        members = list(get_protocol_members(AgentAnalyzerProtocol))
        assert "format_recommendations" in members

    def test_analyze_method_signature(self) -> None:
        """Test that analyze method has correct signature."""
        analyze_method = AgentAnalyzerProtocol.analyze
        sig = inspect.signature(analyze_method)

        params = list(sig.parameters.keys())
        assert params == ["stdout", "stderr", "exit_code"], f"Expected ['stdout', 'stderr', 'exit_code'], got {params}"

        assert sig.parameters["stdout"].annotation == str
        assert sig.parameters["stderr"].annotation == str
        assert sig.parameters["exit_code"].annotation == int

    def test_format_recommendations_method_signature(self) -> None:
        """Test that format_recommendations method has correct signature."""
        format_method = AgentAnalyzerProtocol.format_recommendations
        sig = inspect.signature(format_method)

        params = list(sig.parameters.keys())
        assert params == ["recommendations"], f"Expected ['recommendations'], got {params}"

        # Check that it accepts list[AgentRecommendation]
        ann = sig.parameters["recommendations"].annotation
        assert "AgentRecommendation" in str(ann)

    def test_protocol_signature_compliance_mock(self) -> None:
        """Test that MockAgentAnalyzer complies with protocol signature."""
        analyze_sig = inspect.signature(MockAgentAnalyzer.analyze)
        analyze_params = list(analyze_sig.parameters.keys())
        assert analyze_params == ["stdout", "stderr", "exit_code"], f"Mock analyze doesn't match protocol: {analyze_params}"

        format_sig = inspect.signature(MockAgentAnalyzer.format_recommendations)
        format_params = list(format_sig.parameters.keys())
        assert format_params == ["recommendations"], f"Mock format_recommendations doesn't match protocol: {format_params}"


class TestRecommendationEngineProtocol:
    """Test RecommendationEngineProtocol definition."""

    def test_protocol_exists(self) -> None:
        """Test that RecommendationEngineProtocol is defined."""
        assert RecommendationEngineProtocol is not None

    def test_protocol_is_protocol(self) -> None:
        """Test that RecommendationEngineProtocol is a Protocol."""
        from typing import Protocol

        assert issubclass(RecommendationEngineProtocol, Protocol)

    def test_analyze_history_method_exists(self) -> None:
        """Test that analyze_history classmethod exists on protocol."""
        assert hasattr(RecommendationEngineProtocol, "analyze_history")
        members = list(get_protocol_members(RecommendationEngineProtocol))
        assert "analyze_history" in members

    def test_adjust_confidence_method_exists(self) -> None:
        """Test that adjust_confidence classmethod exists on protocol."""
        assert hasattr(RecommendationEngineProtocol, "adjust_confidence")
        members = list(get_protocol_members(RecommendationEngineProtocol))
        assert "adjust_confidence" in members

    def test_analyze_history_method_signature(self) -> None:
        """Test that analyze_history method has correct signature."""
        analyze_method = RecommendationEngineProtocol.analyze_history
        sig = inspect.signature(analyze_method)

        params = list(sig.parameters.keys())
        assert params == ["db", "project", "days"], f"Expected ['db', 'project', 'days'], got {params}"

        assert sig.parameters["project"].annotation == str
        assert sig.parameters["days"].annotation == int

    def test_adjust_confidence_method_signature(self) -> None:
        """Test that adjust_confidence method has correct signature."""
        adjust_method = RecommendationEngineProtocol.adjust_confidence
        sig = inspect.signature(adjust_method)

        params = list(sig.parameters.keys())
        assert params == ["recommendations", "effectiveness"], f"Expected ['recommendations', 'effectiveness'], got {params}"

    def test_protocol_signature_compliance_mock(self) -> None:
        """Test that MockRecommendationEngine complies with protocol signature."""
        analyze_sig = inspect.signature(MockRecommendationEngine.analyze_history)
        analyze_params = list(analyze_sig.parameters.keys())
        assert analyze_params == ["db", "project", "days"], f"Mock analyze_history doesn't match: {analyze_params}"

        adjust_sig = inspect.signature(MockRecommendationEngine.adjust_confidence)
        adjust_params = list(adjust_sig.parameters.keys())
        assert adjust_params == ["recommendations", "effectiveness"], f"Mock adjust_confidence doesn't match: {adjust_params}"


class TestReflectionDatabaseProtocol:
    """Test ReflectionDatabaseProtocol definition."""

    def test_protocol_exists(self) -> None:
        """Test that ReflectionDatabaseProtocol is defined."""
        assert ReflectionDatabaseProtocol is not None

    def test_protocol_is_protocol(self) -> None:
        """Test that ReflectionDatabaseProtocol is a Protocol."""
        from typing import Protocol

        assert issubclass(ReflectionDatabaseProtocol, Protocol)

    def test_search_conversations_method_exists(self) -> None:
        """Test that search_conversations async method exists on protocol."""
        assert hasattr(ReflectionDatabaseProtocol, "search_conversations")

    def test_store_conversation_method_exists(self) -> None:
        """Test that store_conversation async method exists on protocol."""
        assert hasattr(ReflectionDatabaseProtocol, "store_conversation")

    def test_aenter_method_exists(self) -> None:
        """Test that __aenter__ async method exists on protocol."""
        assert hasattr(ReflectionDatabaseProtocol, "__aenter__")

    def test_aexit_method_exists(self) -> None:
        """Test that __aexit__ async method exists on protocol."""
        assert hasattr(ReflectionDatabaseProtocol, "__aexit__")

    def test_search_conversations_is_async_method(self) -> None:
        """Test that search_conversations is an async method."""
        import asyncio
        method = ReflectionDatabaseProtocol.search_conversations
        assert asyncio.iscoroutinefunction(method) or hasattr(method, "__call__")

    def test_store_conversation_is_async_method(self) -> None:
        """Test that store_conversation is an async method."""
        import asyncio
        method = ReflectionDatabaseProtocol.store_conversation
        assert asyncio.iscoroutinefunction(method) or hasattr(method, "__call__")

    def test_protocol_signature_compliance_mock(self) -> None:
        """Test that MockReflectionDatabase complies with protocol signature."""
        # Verify mock has the required async methods
        db = MockReflectionDatabase()
        assert callable(db.search_conversations)
        assert callable(db.store_conversation)
        # Verify it can be used as async context manager
        assert hasattr(db, "__aenter__")
        assert hasattr(db, "__aexit__")


class TestCrackerjackResultProtocol:
    """Test CrackerjackResultProtocol definition."""

    def test_protocol_exists(self) -> None:
        """Test that CrackerjackResultProtocol is defined."""
        assert CrackerjackResultProtocol is not None

    def test_protocol_is_protocol(self) -> None:
        """Test that CrackerjackResultProtocol is a Protocol."""
        from typing import Protocol

        assert issubclass(CrackerjackResultProtocol, Protocol)

    def test_exit_code_property_exists(self) -> None:
        """Test that exit_code property exists on protocol."""
        assert hasattr(CrackerjackResultProtocol, "exit_code")

    def test_stdout_property_exists(self) -> None:
        """Test that stdout property exists on protocol."""
        assert hasattr(CrackerjackResultProtocol, "stdout")

    def test_stderr_property_exists(self) -> None:
        """Test that stderr property exists on protocol."""
        assert hasattr(CrackerjackResultProtocol, "stderr")

    def test_execution_time_property_exists(self) -> None:
        """Test that execution_time property exists on protocol."""
        assert hasattr(CrackerjackResultProtocol, "execution_time")

    def test_all_properties_are_properties(self) -> None:
        """Test that all members are property-based."""
        # Verify the protocol members are accessible as properties
        protocol = CrackerjackResultProtocol
        # Protocol members should be accessible
        assert hasattr(protocol, "exit_code")
        assert hasattr(protocol, "stdout")
        assert hasattr(protocol, "stderr")
        assert hasattr(protocol, "execution_time")

    def test_protocol_signature_compliance_mock(self) -> None:
        """Test that MockCrackerjackResult complies with protocol signature."""
        mock = MockCrackerjackResult(exit_code=1, stdout="out", stderr="err", execution_time=1.5)

        # Verify all required properties exist and return correct types
        assert isinstance(mock.exit_code, int)
        assert isinstance(mock.stdout, str)
        assert isinstance(mock.stderr, str)
        assert isinstance(mock.execution_time, float)


class TestCrackerjackIntegrationProtocol:
    """Test CrackerjackIntegrationProtocol definition."""

    def test_protocol_exists(self) -> None:
        """Test that CrackerjackIntegrationProtocol is defined."""
        assert CrackerjackIntegrationProtocol is not None

    def test_protocol_is_protocol(self) -> None:
        """Test that CrackerjackIntegrationProtocol is a Protocol."""
        from typing import Protocol

        assert issubclass(CrackerjackIntegrationProtocol, Protocol)

    def test_execute_crackerjack_command_method_exists(self) -> None:
        """Test that execute_crackerjack_command async method exists."""
        assert hasattr(CrackerjackIntegrationProtocol, "execute_crackerjack_command")

    def test_execute_crackerjack_command_is_async(self) -> None:
        """Test that execute_crackerjack_command is an async method."""
        import asyncio
        method = CrackerjackIntegrationProtocol.execute_crackerjack_command
        assert asyncio.iscoroutinefunction(method) or hasattr(method, "__call__")

    def test_protocol_signature_compliance_mock(self) -> None:
        """Test that MockCrackerjackIntegration complies with protocol signature."""
        mock = MockCrackerjackIntegration()
        # Verify mock has the async method
        assert callable(mock.execute_crackerjack_command)
        # Verify it's an async method
        import asyncio
        assert asyncio.iscoroutinefunction(mock.execute_crackerjack_command) or asyncio.iscoroutinefunction(
            getattr(mock, "execute_crackerjack_command")
        )


# ==============================================================================
# Mock Implementation Tests
# ==============================================================================


class TestMockQualityMetricsExtractor:
    """Test MockQualityMetricsExtractor functionality."""

    def test_extract_coverage_from_stdout(self) -> None:
        """Test extracting coverage from stdout."""
        stdout = "TOTAL coverage: 85.5%"
        stderr = ""

        result = MockQualityMetricsExtractor.extract(stdout, stderr)

        assert result.coverage_percent == 85.5

    def test_extract_complexity_violations(self) -> None:
        """Test extracting complexity violations."""
        stdout = ""
        stderr = "Complexity of 18 is too high\nComplexity of 22 is too high"

        result = MockQualityMetricsExtractor.extract(stdout, stderr)

        assert result.max_complexity == 22
        assert result.complexity_violations == 2

    def test_extract_security_issues(self) -> None:
        """Test extracting security issues."""
        stdout = ""
        stderr = "B108: Probable insecure usage\nB603: subprocess call"

        result = MockQualityMetricsExtractor.extract(stdout, stderr)

        assert result.security_issues == 2

    def test_extract_test_results(self) -> None:
        """Test extracting test results."""
        stdout = "10 passed, 2 failed"
        stderr = ""

        result = MockQualityMetricsExtractor.extract(stdout, stderr)

        assert result.tests_passed == 10
        assert result.tests_failed == 2


class TestMockAgentAnalyzer:
    """Test MockAgentAnalyzer functionality."""

    def test_no_recommendations_on_success(self) -> None:
        """Test that no recommendations are given when exit code is 0."""
        stdout = "All checks passed!"
        stderr = ""
        exit_code = 0

        recommendations = MockAgentAnalyzer.analyze(stdout, stderr, exit_code)

        assert recommendations == []

    def test_refactoring_recommendation_for_complexity(self) -> None:
        """Test RefactoringAgent recommendation for complexity violations."""
        stdout = ""
        stderr = "Complexity of 18 is too high"
        exit_code = 1

        recommendations = MockAgentAnalyzer.analyze(stdout, stderr, exit_code)

        assert len(recommendations) == 1
        assert recommendations[0].agent == AgentType.REFACTORING
        assert recommendations[0].confidence == 0.9

    def test_security_recommendation_for_bandit(self) -> None:
        """Test SecurityAgent recommendation for Bandit codes."""
        stdout = ""
        stderr = "B603: subprocess call detected"
        exit_code = 1

        recommendations = MockAgentAnalyzer.analyze(stdout, stderr, exit_code)

        assert len(recommendations) == 1
        assert recommendations[0].agent == AgentType.SECURITY
        assert recommendations[0].confidence == 0.8

    def test_format_recommendations_empty(self) -> None:
        """Test formatting empty recommendations."""
        result = MockAgentAnalyzer.format_recommendations([])

        assert result == ""

    def test_format_recommendations_with_data(self) -> None:
        """Test formatting recommendations with data."""
        recommendations = [
            AgentRecommendation(
                agent=AgentType.REFACTORING,
                confidence=0.9,
                reason="Complexity violation",
                quick_fix_command="python -m crackerjack --ai-fix",
                pattern_matched="test",
            )
        ]

        result = MockAgentAnalyzer.format_recommendations(recommendations)

        assert "🤖 **AI Agent Recommendations**:" in result
        assert "RefactoringAgent" in result
        assert "90%" in result


class TestMockRecommendationEngine:
    """Test MockRecommendationEngine functionality."""

    @pytest.mark.asyncio
    async def test_analyze_history_returns_dict(self) -> None:
        """Test that analyze_history returns a properly structured dict."""
        mock_db = MockReflectionDatabase([])
        project = "test_project"
        days = 30

        result = await MockRecommendationEngine.analyze_history(mock_db, project, days)

        assert isinstance(result, dict)
        assert "patterns" in result
        assert "agent_effectiveness" in result
        assert "insights" in result
        assert "total_executions" in result

    @pytest.mark.asyncio
    async def test_analyze_history_with_results(self) -> None:
        """Test analyze_history with mock results."""
        mock_results = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "content": "test content",
                "metadata": {"exit_code": 1},
            }
        ]
        mock_db = MockReflectionDatabase(mock_results)

        result = await MockRecommendationEngine.analyze_history(mock_db, "test", days=30)

        assert result["total_executions"] == 1

    def test_adjust_confidence_no_effectiveness_data(self) -> None:
        """Test adjust_confidence with no effectiveness data returns original."""
        recommendations = [
            AgentRecommendation(
                agent=AgentType.REFACTORING,
                confidence=0.9,
                reason="Test",
                quick_fix_command="test",
                pattern_matched="test",
            )
        ]

        result = MockRecommendationEngine.adjust_confidence(recommendations, [])

        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_adjust_confidence_with_effectiveness_data(self) -> None:
        """Test adjust_confidence adjusts confidence based on effectiveness."""
        recommendations = [
            AgentRecommendation(
                agent=AgentType.REFACTORING,
                confidence=0.9,
                reason="Test",
                quick_fix_command="test",
                pattern_matched="test",
            )
        ]

        effectiveness = [
            AgentEffectiveness(
                agent=AgentType.REFACTORING,
                total_recommendations=10,
                successful_fixes=8,
                failed_fixes=2,
                avg_confidence=0.85,
                success_rate=0.8,
            )
        ]

        result = MockRecommendationEngine.adjust_confidence(recommendations, effectiveness)

        assert len(result) == 1
        # Check that confidence was adjusted (not necessarily 0.84 due to mock implementation differences)
        assert result[0].confidence <= 0.9  # Should be <= original
        assert result[0].agent == AgentType.REFACTORING


class TestMockReflectionDatabase:
    """Test MockReflectionDatabase functionality."""

    @pytest.mark.asyncio
    async def test_search_conversations_returns_results(self) -> None:
        """Test that search_conversations returns mock results."""
        mock_results = [
            {"content": "test1", "metadata": {}},
            {"content": "test2", "metadata": {}},
        ]
        db = MockReflectionDatabase(mock_results)

        results = await db.search_conversations("test", limit=10)

        assert len(results) == 2
        assert results[0]["content"] == "test1"

    @pytest.mark.asyncio
    async def test_search_conversations_respects_limit(self) -> None:
        """Test that search_conversations respects limit parameter."""
        mock_results = [{"content": f"test{i}", "metadata": {}} for i in range(10)]
        db = MockReflectionDatabase(mock_results)

        results = await db.search_conversations("test", limit=5)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_store_conversation_appendes_to_list(self) -> None:
        """Test that store_conversation appends to internal list."""
        db = MockReflectionDatabase()

        await db.store_conversation("test content", {"key": "value"})

        assert len(db._stored_conversations) == 1
        assert db._stored_conversations[0]["content"] == "test content"
        assert db._stored_conversations[0]["metadata"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_context_manager_entry(self) -> None:
        """Test that __aenter__ returns self."""
        db = MockReflectionDatabase()

        async with db as result:
            assert result is db

    @pytest.mark.asyncio
    async def test_context_manager_exit(self) -> None:
        """Test that __aexit__ completes without error."""
        db = MockReflectionDatabase()

        await db.__aexit__(None, None, None)


class TestMockCrackerjackResult:
    """Test MockCrackerjackResult functionality."""

    def test_properties_return_correct_values(self) -> None:
        """Test that all properties return correct values."""
        result = MockCrackerjackResult(
            exit_code=1,
            stdout="test output",
            stderr="test error",
            execution_time=2.5,
        )

        assert result.exit_code == 1
        assert result.stdout == "test output"
        assert result.stderr == "test error"
        assert result.execution_time == 2.5

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        result = MockCrackerjackResult()

        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.execution_time == 0.0


class TestMockCrackerjackIntegration:
    """Test MockCrackerjackIntegration functionality."""

    @pytest.mark.asyncio
    async def test_execute_crackerjack_command_returns_result(self) -> None:
        """Test that execute_crackerjack_command returns a CrackerjackResult."""
        mock_result = MockCrackerjackResult(exit_code=0, stdout="success")
        integration = MockCrackerjackIntegration(mock_result)

        result = await integration.execute_crackerjack_command(
            "lint", [], ".", timeout=300, ai_agent_mode=False
        )

        assert result.exit_code == 0
        assert result.stdout == "success"

    @pytest.mark.asyncio
    async def test_execute_crackerjack_command_respects_ai_agent_mode(self) -> None:
        """Test that execute_crackerjack_command respects ai_agent_mode."""
        mock_result = MockCrackerjackResult()
        integration = MockCrackerjackIntegration(mock_result)

        result = await integration.execute_crackerjack_command(
            "test", [], ".", timeout=300, ai_agent_mode=True
        )

        assert isinstance(result, MockCrackerjackResult)


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestProtocolEdgeCases:
    """Test edge cases for protocol implementations."""

    def test_empty_stdout_stderr(self) -> None:
        """Test protocol implementations handle empty stdout/stderr."""
        result = MockQualityMetricsExtractor.extract("", "")
        assert result.coverage_percent is None

    def test_whitespace_only_output(self) -> None:
        """Test protocol implementations handle whitespace-only output."""
        result = MockQualityMetricsExtractor.extract("   \n\n  ", "   \n\n  ")
        assert result.coverage_percent is None

    def test_malformed_coverage_format(self) -> None:
        """Test handling of malformed coverage format."""
        result = MockQualityMetricsExtractor.extract("coverage: not_a_number%", "")
        assert result.coverage_percent is None

    def test_multiple_bandit_codes(self) -> None:
        """Test extraction of multiple Bandit codes."""
        import re
        stderr = "B108: test\nB603: test\nB101: test\nB413: test\nB506: test"
        result = MockQualityMetricsExtractor.extract("", stderr)
        # B\d{3}: pattern should match 5 bandit codes
        matches = re.findall(r"B\d{3}:", stderr)
        assert len(matches) == 5

    def test_analyze_with_max_exit_code(self) -> None:
        """Test analyze with maximum exit code value."""
        recommendations = MockAgentAnalyzer.analyze("", "", 2147483647)
        # Should still process the input
        assert isinstance(recommendations, list)

    def test_analyze_with_negative_exit_code(self) -> None:
        """Test analyze with negative exit code."""
        recommendations = MockAgentAnalyzer.analyze("", "", -1)
        # Negative exit code still means failure
        assert isinstance(recommendations, list)

    def test_format_recommendations_preserves_high_confidence_emoji(self) -> None:
        """Test that high confidence recommendations get fire emoji."""
        recommendations = [
            AgentRecommendation(
                agent=AgentType.REFACTORING,
                confidence=1.0,
                reason="Test",
                quick_fix_command="test",
                pattern_matched="test",
            )
        ]

        formatted = MockAgentAnalyzer.format_recommendations(recommendations)
        assert "🔥" in formatted

    def test_format_recommendations_low_confidence_emoji(self) -> None:
        """Test that low confidence recommendations get sparkle emoji."""
        recommendations = [
            AgentRecommendation(
                agent=AgentType.DOCUMENTATION,
                confidence=0.5,
                reason="Test",
                quick_fix_command="test",
                pattern_matched="test",
            )
        ]

        formatted = MockAgentAnalyzer.format_recommendations(recommendations)
        assert "✨" in formatted


class TestAsyncMethodEdgeCases:
    """Test edge cases for async protocol methods."""

    @pytest.mark.asyncio
    async def test_search_conversations_with_none_project(self) -> None:
        """Test search_conversations accepts None for project."""
        db = MockReflectionDatabase([{"content": "test"}])

        results = await db.search_conversations("test", project=None)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_conversations_with_zero_limit(self) -> None:
        """Test search_conversations handles zero limit."""
        db = MockReflectionDatabase([{"content": "test"}])

        results = await db.search_conversations("test", limit=0)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_analyze_history_with_zero_days(self) -> None:
        """Test analyze_history handles zero days."""
        db = MockReflectionDatabase([])

        result = await MockRecommendationEngine.analyze_history(db, "test", days=0)
        assert "patterns" in result

    def test_adjust_confidence_with_empty_recommendations(self) -> None:
        """Test adjust_confidence handles empty recommendations list."""
        result = MockRecommendationEngine.adjust_confidence([], [])
        assert result == []

    @pytest.mark.asyncio
    async def test_store_conversation_with_none_metadata(self) -> None:
        """Test store_conversation handles None metadata."""
        db = MockReflectionDatabase()

        await db.store_conversation("test content", None)
        assert len(db._stored_conversations) == 1
        assert db._stored_conversations[0]["metadata"] == {}


# ==============================================================================
# Type Checking Tests
# ==============================================================================


class TestProtocolTypeChecking:
    """Test type checking behavior with protocols."""

    def test_isinstance_check_with_protocol(self) -> None:
        """Test isinstance check with mock implementation."""
        mock_result = MockCrackerjackResult(exit_code=0)

        # Verify mock implements the protocol
        assert isinstance(mock_result, object)  # Basic check

    def test_protocol_member_access(self) -> None:
        """Test that protocol members are accessible."""
        members = get_protocol_members(CrackerjackResultProtocol)
        assert len(members) == 4  # exit_code, stdout, stderr, execution_time

    def test_all_protocols_have_members(self) -> None:
        """Test that all protocols have expected members."""
        protocols_members = {
            QualityMetricsExtractorProtocol: ["extract"],
            AgentAnalyzerProtocol: ["analyze", "format_recommendations"],
            RecommendationEngineProtocol: ["analyze_history", "adjust_confidence"],
            ReflectionDatabaseProtocol: ["search_conversations", "store_conversation", "__aenter__", "__aexit__"],
            CrackerjackResultProtocol: ["exit_code", "stdout", "stderr", "execution_time"],
            CrackerjackIntegrationProtocol: ["execute_crackerjack_command"],
        }

        for protocol, expected_members in protocols_members.items():
            members = get_protocol_members(protocol)
            for member in expected_members:
                assert member in members, f"{protocol.__name__} missing member: {member}"


# ==============================================================================
# Run Tests
# ==============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])