"""Quality scoring implementation for MCP layer.

This module provides the concrete implementation of QualityScorer that uses
the full quality scoring logic from the MCP server.

This implementation is registered in the DI container when the MCP server starts,
breaking the circular dependency between core and MCP layers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from session_buddy.core.quality_scoring import QualityScorer

logger = logging.getLogger(__name__)


class MCPQualityScorer(QualityScorer):
    """MCP layer quality scorer implementation.

    This class wraps the actual quality scoring logic that resides in the
    MCP layer (server.py). By implementing the QualityScorer interface,
    we allow the core layer to depend on the abstraction rather than
    the concrete MCP layer implementation.

    This breaks the circular dependency:
    - Before: session_manager.py → server.calculate_quality_score()
    - After: session_manager.py → QualityScorer interface ← MCPQualityScorer
    """

    def __init__(self) -> None:
        """Initialize MCP quality scorer."""
        self._permissions_score_cache: int | None = None

    async def calculate_quality_score(
        self,
        project_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Calculate project quality score using MCP server logic.

        This method imports and calls the actual calculate_quality_score
        function from server.py, ensuring we get the full quality analysis
        while maintaining layer separation.

        Args:
            project_dir: Path to the project directory

        Returns:
            Dict with quality metrics
        """
        # Import here to avoid circular dependency at module load time
        # This is safe because we're in the MCP layer
        try:
            from session_buddy.mcp.server import calculate_quality_score

            return await calculate_quality_score(project_dir=project_dir)
        except ImportError:
            logger.warning(
                "MCP server calculate_quality_score not available, using fallback"
            )
            # Return basic score if MCP server not available
            return {
                "overall": 75,
                "metrics": {
                    "coverage": {"coverage_pct": 0},
                    "quality": {"score": 75},
                    "type_hints": {"coverage_pct": 80},
                    "security": {"test_count": 0},
                },
                "recommendations": [],
            }

    def get_permissions_score(self) -> int:
        """Get permissions score from MCP server.

        Returns:
            Permissions score based on trusted operations count

        """
        if self._permissions_score_cache is not None:
            return self._permissions_score_cache

        try:
            from session_buddy.mcp.server import permissions_manager

            if hasattr(permissions_manager, "trusted_operations"):
                trusted_count = len(permissions_manager.trusted_operations)
                score = min(
                    trusted_count * 4, 20
                )  # 4 points per trusted operation, max 20
                self._permissions_score_cache = score
                return score
            return 10  # Basic score if we can't access trusted operations
        except ImportError:
            logger.warning(
                "MCP server permissions_manager not available, using fallback"
            )
            return 10  # Fallback score
