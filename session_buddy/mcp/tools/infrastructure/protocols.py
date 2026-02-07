"""Protocol definitions for crackerjack workflow components.

These protocols define interfaces for dependency injection and testing.
"""

from typing import Any, Protocol

from .agent_analyzer import AgentRecommendation
from .quality_metrics import QualityMetrics
from .recommendation_engine import AgentEffectiveness


class QualityMetricsExtractorProtocol(Protocol):
    """Protocol for extracting quality metrics from crackerjack output."""

    @classmethod
    def extract(cls, stdout: str, stderr: str) -> QualityMetrics:
        """Extract metrics from crackerjack output.

        Args:
            stdout: Standard output from crackerjack execution
            stderr: Standard error from crackerjack execution

        Returns:
            QualityMetrics object with extracted values

        """
        ...


class AgentAnalyzerProtocol(Protocol):
    """Protocol for analyzing failures and recommending agents."""

    @classmethod
    def analyze(
        cls,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> list[AgentRecommendation]:
        """Analyze crackerjack output and recommend agents.

        Args:
            stdout: Standard output from crackerjack
            stderr: Standard error from crackerjack
            exit_code: Process exit code

        Returns:
            List of agent recommendations sorted by confidence

        """
        ...

    @classmethod
    def format_recommendations(cls, recommendations: list[AgentRecommendation]) -> str:
        """Format recommendations for display.

        Args:
            recommendations: List of agent recommendations

        Returns:
            Formatted string for user display

        """
        ...


class RecommendationEngineProtocol(Protocol):
    """Protocol for learning from execution history."""

    @classmethod
    async def analyze_history(
        cls,
        db: Any,
        project: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """Analyze execution history for patterns and effectiveness.

        Args:
            db: ReflectionDatabase instance
            project: Project name
            days: Number of days to analyze

        Returns:
            Dictionary with patterns, agent effectiveness, and insights

        """
        ...

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
        ...


class ReflectionDatabaseProtocol(Protocol):
    """Protocol for reflection database operations."""

    async def search_conversations(
        self,
        query: str,
        project: str | None = None,
        limit: int = 50,
        min_score: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Search for conversations in the database.

        Args:
            query: Search query text
            project: Optional project filter
            limit: Maximum number of results
            min_score: Minimum similarity score

        Returns:
            List of conversation results

        """
        ...

    async def store_conversation(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a conversation in the database.

        Args:
            content: Conversation content
            metadata: Optional metadata dictionary

        """
        ...

    async def __aenter__(self) -> "ReflectionDatabaseProtocol":
        """Async context manager entry."""
        ...

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        ...


class CrackerjackResultProtocol(Protocol):
    """Protocol for crackerjack execution results."""

    @property
    def exit_code(self) -> int:
        """Process exit code."""
        ...

    @property
    def stdout(self) -> str:
        """Standard output."""
        ...

    @property
    def stderr(self) -> str:
        """Standard error."""
        ...

    @property
    def execution_time(self) -> float:
        """Execution time in seconds."""
        ...


class CrackerjackIntegrationProtocol(Protocol):
    """Protocol for crackerjack integration."""

    async def execute_crackerjack_command(
        self,
        command: str,
        args: list[str] | None = None,
        working_directory: str = ".",
        timeout: int = 300,
        ai_agent_mode: bool = False,
    ) -> CrackerjackResultProtocol:
        """Execute a crackerjack command.

        Args:
            command: Command to execute
            args: Optional command arguments
            working_directory: Working directory
            timeout: Timeout in seconds
            ai_agent_mode: Whether to enable AI agent mode

        Returns:
            CrackerjackResult with execution details

        """
        ...
