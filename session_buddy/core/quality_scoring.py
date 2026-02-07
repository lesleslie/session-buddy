"""Quality scoring interface for session-buddy.

This module defines the abstract interface for quality scoring, following
the Dependency Inversion Principle. The core layer depends on this interface,
not on concrete implementations from the MCP layer.

This breaks the circular dependency between session_manager.py (core) and
server.py (MCP layer).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class QualityScorer(ABC):
    """Abstract interface for quality scoring.

    This interface defines the contract for quality scoring implementations.
    The core layer depends on this interface, not on concrete implementations.

    Implementations can be provided from any layer (MCP, infrastructure, etc.)
    via dependency injection.

    Example:
        >>> from session_buddy.core.quality_scoring import QualityScorer
        >>>
        >>> class MyQualityScorer(QualityScorer):
        ...     async def calculate_quality_score(self, project_dir):
        ...         return {"overall": 85}
    """

    @abstractmethod
    async def calculate_quality_score(
        self,
        project_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Calculate project quality score.

        Args:
            project_dir: Path to the project directory. If not provided, will use current directory.

        Returns:
            Dict with quality metrics including:
            - overall: Overall quality score (0-100)
            - metrics: Detailed breakdown (coverage, quality, type_hints, security)
            - recommendations: List of improvement recommendations

        Raises:
            Exception: If scoring fails (implementations should handle gracefully)

        Example:
            >>> scorer = MyQualityScorer()
            >>> score = await scorer.calculate_quality_score(Path("/path/to/project"))
            >>> print(f"Quality: {score['overall']}/100")
        """
        pass

    @abstractmethod
    def get_permissions_score(self) -> int:
        """Get permissions health score (0-20).

        Returns:
            Permissions score based on trusted operations count.
            Max 20 points (4 points per trusted operation).

        Example:
            >>> scorer = MyQualityScorer()
            >>> score = scorer.get_permissions_score()
            >>> print(f"Permissions: {score}/20")
        """
        pass


class DefaultQualityScorer(QualityScorer):
    """Default quality scorer implementation.

    Provides a fallback implementation when no specialized scorer is available.
    This scorer uses basic heuristics without requiring MCP layer dependencies.
    """

    async def calculate_quality_score(
        self,
        project_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Calculate basic quality score without MCP dependencies.

        Args:
            project_dir: Path to the project directory

        Returns:
            Dict with basic quality metrics
        """
        if project_dir is None:
            project_dir = Path.cwd()

        # Basic scoring without full analysis
        return {
            "overall": 75,  # Default moderate score
            "metrics": {
                "coverage": {"coverage_pct": 0},
                "quality": {"score": 75},
                "type_hints": {"coverage_pct": 80},
                "security": {"test_count": 0},
            },
            "recommendations": [],
        }

    def get_permissions_score(self) -> int:
        """Get default permissions score.

        Returns:
            Default moderate permissions score
        """
        return 10  # Basic score when permissions unavailable


# Global scorer instance (can be overridden via DI)
_default_scorer: QualityScorer | None = None


def get_quality_scorer() -> QualityScorer:
    """Get the quality scorer instance.

    Returns:
        QualityScorer instance (default or injected via DI)

    Example:
        >>> from session_buddy.core.quality_scoring import get_quality_scorer
        >>>
        >>> scorer = get_quality_scorer()
        >>> score = await scorer.calculate_quality_score()
    """
    global _default_scorer

    if _default_scorer is None:
        _default_scorer = DefaultQualityScorer()

    return _default_scorer


def set_quality_scorer(scorer: QualityScorer) -> None:
    """Set the quality scorer instance (for DI injection).

    Args:
        scorer: QualityScorer instance to use

    Example:
        >>> from session_buddy.core.quality_scoring import set_quality_scorer, QualityScorer
        >>>
        >>> class MyScorer(QualityScorer):
        ...     # ... implementation ...
        >>>
        >>> set_quality_scorer(MyScorer())
    """
    global _default_scorer
    _default_scorer = scorer
