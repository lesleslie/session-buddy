"""Code formatting implementation for MCP layer.

This module provides the concrete implementation of CodeFormatter that uses
the crackerjack integration from the MCP server.

This implementation is registered in the DI container whenAPHONY the MCP server starts.
"""

from __future__ import annotations

import logging
from pathlib import Path

from session_buddy.core.hooks import CodeFormatter

logger = logging.getLogger(__name__)


class MCPCodeFormatter(CodeFormatter):
    """MCP layer code formatter implementation.

    This class wraps the crackerjack formatting functionality that resides in the
    MCP layer (server.py). By implementing the CodeFormatter interface,
    we allow the core layer to depend on the abstraction rather than
    the concrete MCP layer implementation.

    This breaks the circular dependency:
    - Before: hooks.py → server.run_crackerjack_command()
    - After: hooks.py → CodeFormatter interface ← MCPCodeFormatter
    """

    async def format_file(self, file_path: Path, timeout: int = 30) -> bool:
        """Format a file using crackerjack.

        This method imports and calls the actual run_crackerjack_command
        function from server.py, ensuring we get the full formatting
        functionality while maintaining layer separation.

        Args:
            file_path: Path to the file to format
            timeout: Maximum time to wait for formatting to complete

        Returns:
            True if formatting succeeded, False otherwise
        """
        # Import here to avoid circular dependency at module load time
        # This is safe because we're in the MCP layer
        try:
            from session_buddy.mcp.server import run_crackerjack_command

            await run_crackerjack_command(
                ["lint", "--fix", str(file_path)], timeout=timeout
            )
            return True
        except ImportError:
            logger.warning(
                "MCP server run_crackerjack_command not available, formatting skipped"
            )
            return False
        except Exception as e:
            logger.warning("Code formatting failed for %s: %s", file_path, e)
            return False
