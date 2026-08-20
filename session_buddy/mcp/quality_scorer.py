"""Quality scoring implementation for MCP layer.

This module provides the concrete implementation of QualityScorer that uses
the full quality scoring logic from the MCP server.

This implementation is registered in the DI container when the MCP server starts,
breaking the circular dependency between core and MCP layers.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from session_buddy.core.quality_scoring import QualityScorer

logger = logging.getLogger(__name__)

# Modules that may expose a live ``permissions_manager``. The MCP layer's own
# server module wins; ``session_buddy.server`` is kept as a legacy fallback.
_PERMISSIONS_MODULES = ("session_buddy.mcp.server", "session_buddy.server")

# Points awarded per trusted operation and the ceiling for the resulting score.
_POINTS_PER_TRUSTED_OPERATION = 4
_MAX_PERMISSIONS_SCORE = 20
_FALLBACK_PERMISSIONS_SCORE = 10


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
            from session_buddy.quality_engine import calculate_quality_score

            return await calculate_quality_score(project_dir=project_dir)
        except ImportError:
            logger.warning(
                "MCP server calculate_quality_score not available, using fallback"
            )
            # Return basic score if MCP server not available
            return {
                "total_score": 75,  # Add missing key for compatibility
                "overall": 75,
                "metrics": {
                    "coverage": {"coverage_pct": 0},
                    "quality": {"score": 75},
                    "type_hints": {"coverage_pct": 80},
                    "security": {"test_count": 0},
                },
                "recommendations": [],
                "project_health": {"total": 75},
                "permissions_health": {"score": 10},
                "session_health": {"status": "active"},
                "tool_health": {"count": 0},
            }

    def get_permissions_score(self) -> int:
        """Get permissions score from MCP server.

        Returns:
            Permissions score based on trusted operations count

        """
        if self._permissions_score_cache is not None:
            return self._permissions_score_cache

        trusted_operations = self._resolve_trusted_operations()
        if trusted_operations is None:
            logger.warning(
                "MCP server permissions_manager not available, using fallback"
            )
            return _FALLBACK_PERMISSIONS_SCORE

        score = min(
            len(trusted_operations) * _POINTS_PER_TRUSTED_OPERATION,
            _MAX_PERMISSIONS_SCORE,
        )
        self._permissions_score_cache = score
        return score

    @staticmethod
    def _resolve_trusted_operations() -> Any | None:
        """Locate the trusted operations of a live permissions manager.

        The permissions manager is owned by the running MCP server, so it is
        resolved from already-imported modules rather than by importing the
        server (which would re-run tool registration). ``None`` is returned
        when no server module exposes a usable manager.
        """
        for module_name in _PERMISSIONS_MODULES:
            module = sys.modules.get(module_name)
            if module is None:
                continue

            manager = getattr(module, "permissions_manager", None)
            trusted_operations = getattr(manager, "trusted_operations", None)
            if trusted_operations is not None:
                return trusted_operations

        return None
