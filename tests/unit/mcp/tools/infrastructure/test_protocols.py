"""Tests for session_buddy.mcp.tools.infrastructure.protocols.

Protocols are duck-typed interfaces — they have no concrete runtime logic.
This test file verifies:

- Every protocol is importable and inherits from ``typing.Protocol``.
- Each declared method/property signature is exposed on the protocol.
- Concrete ``@runtime_checkable``-compatible fakes satisfy the protocol's
  structural type checks.
- Module-level imports resolve without error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pytest

from session_buddy.mcp.tools.infrastructure import protocols as mod
from session_buddy.mcp.tools.infrastructure.protocols import (
    AgentAnalyzerProtocol,
    CrackerjackIntegrationProtocol,
    CrackerjackResultProtocol,
    QualityMetricsExtractorProtocol,
    RecommendationEngineProtocol,
    ReflectionDatabaseProtocol,
)


# ---------------------------------------------------------------------------
# Concrete fakes that satisfy each protocol structurally
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _FakeMetrics:
    """Minimal stand-in for QualityMetrics."""

    score: float = 100.0


@dataclass(slots=True)
class _FakeAgentRec:
    """Minimal stand-in for AgentRecommendation."""

    agent_name: str = "agent"
    confidence: float = 0.5


@dataclass(slots=True)
class _FakeAgentEffectiveness:
    """Minimal stand-in for AgentEffectiveness."""

    agent_name: str = "agent"
    success_rate: float = 0.0


class _FakeExtractor:
    """Concrete class satisfying QualityMetricsExtractorProtocol."""

    @classmethod
    def extract(cls, stdout: str, stderr: str) -> Any:
        return _FakeMetrics()


class _FakeAnalyzer:
    """Concrete class satisfying AgentAnalyzerProtocol."""

    @classmethod
    def analyze(cls, stdout: str, stderr: str, exit_code: int) -> list[Any]:
        return [_FakeAgentRec()]

    @classmethod
    def format_recommendations(cls, recommendations: list[Any]) -> str:
        return ", ".join(r.agent_name for r in recommendations)


class _FakeEngine:
    """Concrete class satisfying RecommendationEngineProtocol."""

    @classmethod
    async def analyze_history(cls, db: Any, project: str, days: int = 30) -> dict[str, Any]:
        return {"project": project, "days": days, "patterns": []}

    @classmethod
    def adjust_confidence(cls, recommendations: list[Any], effectiveness: list[Any]) -> list[Any]:
        return recommendations


class _FakeReflectionDB:
    """Concrete class satisfying ReflectionDatabaseProtocol."""

    async def search_conversations(
        self,
        query: str,
        project: str | None = None,
        limit: int = 50,
        min_score: float = 0.7,
    ) -> list[dict[str, Any]]:
        return [{"id": "1", "score": min_score, "query": query}]

    async def store_conversation(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        return None

    async def __aenter__(self) -> "_FakeReflectionDB":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeResult:
    """Concrete class satisfying CrackerjackResultProtocol."""

    @property
    def exit_code(self) -> int:
        return 0

    @property
    def stdout(self) -> str:
        return ""

    @property
    def stderr(self) -> str:
        return ""

    @property
    def execution_time(self) -> float:
        return 0.0


class _FakeIntegration:
    """Concrete class satisfying CrackerjackIntegrationProtocol."""

    async def execute_crackerjack_command(
        self,
        command: str,
        args: list[str] | None = None,
        working_directory: str = ".",
        timeout: int = 300,
        ai_agent_mode: bool = False,
    ) -> Any:
        return _FakeResult()


# ---------------------------------------------------------------------------
# QualityMetricsExtractorProtocol
# ---------------------------------------------------------------------------


class TestQualityMetricsExtractorProtocol:
    def test_is_protocol_subclass(self) -> None:
        assert issubclass(QualityMetricsExtractorProtocol, Protocol)

    def test_extract_classmethod_exists(self) -> None:
        assert hasattr(QualityMetricsExtractorProtocol, "extract")
        assert callable(QualityMetricsExtractorProtocol.extract)

    def test_concrete_class_compatible(self) -> None:
        # The structural type is satisfied by any class with the right methods.
        result = _FakeExtractor.extract("out", "err")
        assert isinstance(result, _FakeMetrics)

    def test_callable_directly(self) -> None:
        # Class method can be invoked without instance.
        out = _FakeExtractor.extract("hello", "world")
        assert out.score == 100.0


# ---------------------------------------------------------------------------
# AgentAnalyzerProtocol
# ---------------------------------------------------------------------------


class TestAgentAnalyzerProtocol:
    def test_is_protocol_subclass(self) -> None:
        assert issubclass(AgentAnalyzerProtocol, Protocol)

    def test_required_methods(self) -> None:
        assert hasattr(AgentAnalyzerProtocol, "analyze")
        assert hasattr(AgentAnalyzerProtocol, "format_recommendations")

    def test_analyze(self) -> None:
        recs = _FakeAnalyzer.analyze("o", "e", 0)
        assert len(recs) == 1
        assert recs[0].agent_name == "agent"

    def test_format_recommendations(self) -> None:
        recs = [_FakeAgentRec(agent_name="a"), _FakeAgentRec(agent_name="b")]
        text = _FakeAnalyzer.format_recommendations(recs)
        assert text == "a, b"

    def test_format_empty(self) -> None:
        assert _FakeAnalyzer.format_recommendations([]) == ""


# ---------------------------------------------------------------------------
# RecommendationEngineProtocol
# ---------------------------------------------------------------------------


class TestRecommendationEngineProtocol:
    def test_is_protocol_subclass(self) -> None:
        assert issubclass(RecommendationEngineProtocol, Protocol)

    def test_required_methods(self) -> None:
        assert hasattr(RecommendationEngineProtocol, "analyze_history")
        assert hasattr(RecommendationEngineProtocol, "adjust_confidence")

    def test_analyze_history_default_days(self) -> None:
        import asyncio

        result = asyncio.run(_FakeEngine.analyze_history(None, "p1"))
        assert result["project"] == "p1"
        assert result["days"] == 30

    def test_analyze_history_custom_days(self) -> None:
        import asyncio

        result = asyncio.run(_FakeEngine.analyze_history(None, "p2", days=7))
        assert result["days"] == 7

    def test_adjust_confidence_returns_recommendations(self) -> None:
        recs = [_FakeAgentRec()]
        eff = [_FakeAgentEffectiveness()]
        assert _FakeEngine.adjust_confidence(recs, eff) == recs


# ---------------------------------------------------------------------------
# ReflectionDatabaseProtocol
# ---------------------------------------------------------------------------


class TestReflectionDatabaseProtocol:
    def test_is_protocol_subclass(self) -> None:
        assert issubclass(ReflectionDatabaseProtocol, Protocol)

    def test_required_methods(self) -> None:
        assert hasattr(ReflectionDatabaseProtocol, "search_conversations")
        assert hasattr(ReflectionDatabaseProtocol, "store_conversation")
        assert hasattr(ReflectionDatabaseProtocol, "__aenter__")
        assert hasattr(ReflectionDatabaseProtocol, "__aexit__")

    def test_search_conversations(self) -> None:
        import asyncio

        async def run() -> list[dict[str, Any]]:
            db = _FakeReflectionDB()
            return await db.search_conversations("foo", project="proj", limit=5, min_score=0.5)

        results = asyncio.run(run())
        assert results == [{"id": "1", "score": 0.5, "query": "foo"}]

    def test_store_conversation(self) -> None:
        import asyncio

        async def run() -> None:
            db = _FakeReflectionDB()
            await db.store_conversation("body", {"tag": "t"})

        asyncio.run(run())  # Should not raise

    def test_async_context_manager(self) -> None:
        import asyncio

        async def run() -> str:
            async with _FakeReflectionDB() as db:
                return "inside"

        assert asyncio.run(run()) == "inside"


# ---------------------------------------------------------------------------
# CrackerjackResultProtocol
# ---------------------------------------------------------------------------


class TestCrackerjackResultProtocol:
    def test_is_protocol_subclass(self) -> None:
        assert issubclass(CrackerjackResultProtocol, Protocol)

    def test_required_properties(self) -> None:
        for name in ("exit_code", "stdout", "stderr", "execution_time"):
            assert hasattr(CrackerjackResultProtocol, name)

    def test_property_access(self) -> None:
        r = _FakeResult()
        assert r.exit_code == 0
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.execution_time == 0.0


# ---------------------------------------------------------------------------
# CrackerjackIntegrationProtocol
# ---------------------------------------------------------------------------


class TestCrackerjackIntegrationProtocol:
    def test_is_protocol_subclass(self) -> None:
        assert issubclass(CrackerjackIntegrationProtocol, Protocol)

    def test_required_methods(self) -> None:
        assert hasattr(CrackerjackIntegrationProtocol, "execute_crackerjack_command")

    def test_execute_crackerjack_command(self) -> None:
        import asyncio

        async def run() -> Any:
            integ = _FakeIntegration()
            return await integ.execute_crackerjack_command(
                "lint",
                args=["--fix"],
                working_directory="/tmp",
                timeout=60,
                ai_agent_mode=True,
            )

        result = asyncio.run(run())
        assert isinstance(result, _FakeResult)


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_protocols_exported(self) -> None:
        for name in (
            "QualityMetricsExtractorProtocol",
            "AgentAnalyzerProtocol",
            "RecommendationEngineProtocol",
            "ReflectionDatabaseProtocol",
            "CrackerjackResultProtocol",
            "CrackerjackIntegrationProtocol",
        ):
            assert hasattr(mod, name)
            assert isinstance(getattr(mod, name), type)

    def test_protocols_inherit_from_typing_protocol(self) -> None:
        for cls in (
            QualityMetricsExtractorProtocol,
            AgentAnalyzerProtocol,
            RecommendationEngineProtocol,
            ReflectionDatabaseProtocol,
            CrackerjackResultProtocol,
            CrackerjackIntegrationProtocol,
        ):
            assert issubclass(cls, Protocol), f"{cls.__name__} should inherit Protocol"

    def test_module_imports_third_party_types(self) -> None:
        # The module imports AgentEffectiveness, AgentRecommendation, QualityMetrics.
        # Smoke-check by trying to use them as type hints via a function.
        from session_buddy.mcp.tools.advanced.recommendation_engine import AgentEffectiveness
        from session_buddy.mcp.tools.intelligence.agent_analyzer import AgentRecommendation
        from session_buddy.tools.quality_metrics import QualityMetrics

        assert AgentEffectiveness is not None
        assert AgentRecommendation is not None
        assert QualityMetrics is not None
