"""PyCharm MCP Tools for Session-Buddy.

Provides enhanced code analysis capabilities by integrating PyCharm's IDE
indexing with Session-Buddy's session management system.
"""

from __future__ import annotations

import json
import logging
import re
import time
import typing as t
from dataclasses import dataclass

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerState:
    """Circuit breaker for fault tolerance."""

    failure_count: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False
    failure_threshold: int = 3
    recovery_timeout: float = 60.0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def can_execute(self) -> bool:
        if not self.is_open:
            return True

        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.recovery_timeout:
            logger.info("Circuit breaker entering half-open state")
            return True
        return False


@dataclass
class SearchResult:
    """Search result from PyCharm index."""

    file_path: str
    line_number: int
    column: int
    match_text: str
    repo_path: str | None = None
    context_before: str | None = None
    context_after: str | None = None


class PyCharmMCPAdapter:
    """Adapter for PyCharm MCP integration with circuit breaker and caching.

    Provides:
    - IDE diagnostics via `get_file_problems`
    - Code search via `search_regex`
    - Symbol info via `get_symbol_info`
    - Usage tracking via `find_usages`
    - Health monitoring via `health_check`
    """

    def __init__(
        self,
        mcp_client: t.Any | None = None,
        timeout: float = 30.0,
        max_results: int = 100,
    ) -> None:
        self._mcp = mcp_client
        self._timeout = timeout
        self._max_results = max_results
        self._circuit_breaker = CircuitBreakerState()
        self._cache: dict[str, t.Any] = {}
        self._cache_ttl: dict[str, float] = {}
        self._available = mcp_client is not None
        self._logger = logging.getLogger(__name__)

    async def search_regex(
        self,
        pattern: str,
        file_pattern: str | None = None,
    ) -> list[SearchResult]:
        """Search for regex pattern across indexed files.

        Uses PyCharm's file index for fast, accurate regex searches.
        Results are cached for 60 seconds.

        Args:
            pattern: Regex pattern to search for
            file_pattern: Optional file glob filter (e.g., "*.py")

        Returns:
            List of SearchResult objects with file, line, column, and context.
        """
        sanitized_pattern = self._sanitize_regex(pattern)
        if not sanitized_pattern:
            self._logger.warning(f"Invalid regex pattern rejected: {pattern[:50]}")
            return []

        cache_key = f"search:{sanitized_pattern}:{file_pattern}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        results = await self._execute_with_circuit_breaker(
            self._search_regex_impl,
            sanitized_pattern,
            file_pattern,
        )

        self._set_cached(cache_key, results, ttl=60.0)
        return results

    async def get_file_problems(
        self,
        file_path: str,
        errors_only: bool = False,
    ) -> list[dict[str, t.Any]]:
        """Get IDE diagnostics for a file.

        Retrieves problems from PyCharm's inspections including:
        - Syntax errors
        - Type checking issues
        - Code style violations
        - Potential bugs

        Args:
            file_path: Path to the file (relative to project root)
            errors_only: If True, only return errors (not warnings or info)

        Returns:
            List of problem dictionaries with:
            - severity: "ERROR", "WARNING", "INFO"
            - line: Line number
            - message: Problem description
            - category: Problem category
        """
        if not self._is_safe_path(file_path):
            return []

        cache_key = f"problems:{file_path}:{errors_only}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        problems = await self._execute_with_circuit_breaker(
            self._get_file_problems_impl,
            file_path,
            errors_only,
        )

        self._set_cached(cache_key, problems, ttl=10.0)
        return problems

    async def get_symbol_info(self, symbol_name: str) -> dict[str, t.Any] | None:
        """Get information about a symbol.

        Args:
            symbol_name: Name of the symbol to look up

        Returns:
            Symbol information or None if not found
        """
        if not self._mcp:
            return None

        try:
            result = await self._mcp.get_symbol_info(symbol_name=symbol_name)
            return result
        except Exception as e:
            self._logger.error(f"Failed to get symbol info: {e}")
            return None

    async def find_usages(self, symbol_name: str) -> list[dict[str, t.Any]]:
        """Find all usages of a symbol.

        Args:
            symbol_name: Name of the symbol to find usages for

        Returns:
            List of usage locations
        """
        if not self._mcp:
            return []

        cache_key = f"usages:{symbol_name}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        usages = await self._execute_with_circuit_breaker(
            self._find_usages_impl,
            symbol_name,
        )

        self._set_cached(cache_key, usages, ttl=30.0)
        return usages

    async def health_check(self) -> dict[str, t.Any]:
        """Check health of PyCharm integration.

        Returns:
            Dictionary with health status including:
            - mcp_available: Whether MCP client is connected
            - circuit_breaker_open: Whether circuit breaker is tripped
            - failure_count: Number of consecutive failures
            - cache_size: Number of cached items
        """
        return {
            "mcp_available": self._available,
            "circuit_breaker_open": self._circuit_breaker.is_open,
            "failure_count": self._circuit_breaker.failure_count,
            "cache_size": len(self._cache),
        }

    # Private methods

    async def _search_regex_impl(
        self,
        pattern: str,
        file_pattern: str | None,
    ) -> list[SearchResult]:
        if not self._mcp:
            return self._fallback_search(pattern, file_pattern)

        try:
            results = await self._mcp.search_regex(
                pattern=pattern,
                file_pattern=file_pattern,
            )
            search_results = []
            for item in results[: self._max_results]:
                search_results.append(
                    SearchResult(
                        file_path=item.get("file_path", ""),
                        line_number=item.get("line", 0),
                        column=item.get("column", 0),
                        match_text=item.get("match", ""),
                        context_before=item.get("context_before"),
                        context_after=item.get("context_after"),
                    )
                )
            return search_results

        except TimeoutError:
            self._logger.warning(f"Search timed out for pattern: {pattern[:50]}")
            return []
        except Exception as e:
            self._logger.error(f"Search failed: {e}")
            return []

    async def _get_file_problems_impl(
        self,
        file_path: str,
        errors_only: bool,
    ) -> list[dict[str, t.Any]]:
        if not self._mcp:
            return []

        try:
            problems = await self._mcp.get_file_problems(
                file_path=file_path,
                errors_only=errors_only,
            )
            return list(problems) if problems else []
        except Exception as e:
            self._logger.error(f"Failed to get file problems: {e}")
            return []

    async def _find_usages_impl(self, symbol_name: str) -> list[dict[str, t.Any]]:
        if not self._mcp:
            return []

        try:
            usages = await self._mcp.find_usages(symbol_name=symbol_name)
            return list(usages) if usages else []
        except Exception as e:
            self._logger.error(f"Failed to find usages: {e}")
            return []

    def _fallback_search(
        self,
        pattern: str,
        file_pattern: str | None,
    ) -> list[SearchResult]:
        """Fallback search using grep when MCP is not available."""
        import subprocess

        results = []
        try:
            cmd = ["grep", "-rn", "-E", pattern]
            if file_pattern:
                cmd.extend(["--include", file_pattern])
            cmd.append(".")

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            for line in proc.stdout.split("\n")[: self._max_results]:
                if ":" in line:
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        results.append(
                            SearchResult(
                                file_path=parts[0],
                                line_number=int(parts[1]),
                                column=0,
                                match_text=parts[2],
                            )
                        )

        except Exception as e:
            self._logger.debug(f"Fallback search failed: {e}")

        return results

    def _sanitize_regex(self, pattern: str) -> str:
        """Sanitize regex pattern to prevent ReDoS attacks."""
        if len(pattern) > 500:
            return ""

        # Block dangerous patterns that could cause catastrophic backtracking
        dangerous_patterns = [
            r"\(\.\*\)\+",
            r"\(\.\+\)\+",
            r"\(\.\*\)\*",
            r"\(\.\+\)\*",
            r"\(\.\*\)\{",
            r"\(\.\+\)\{",
        ]

        for dangerous in dangerous_patterns:
            if re.search(dangerous, pattern):
                return ""

        try:
            re.compile(pattern)
            return pattern
        except re.error:
            return ""

    def _is_safe_path(self, file_path: str) -> bool:
        """Check if file path is safe to resolve."""
        if not file_path:
            return False

        # Prevent path traversal
        if ".." in file_path:
            return False

        # Prevent null bytes
        if "\x00" in file_path:
            return False

        return True

    async def _execute_with_circuit_breaker(
        self,
        func: t.Callable[..., t.Awaitable[t.Any]],
        *args: t.Any,
        **kwargs: t.Any,
    ) -> t.Any:
        """Execute a function with circuit breaker protection."""
        if not self._circuit_breaker.can_execute():
            self._logger.debug("Circuit breaker is open, skipping operation")
            return []

        try:
            result = await func(*args, **kwargs)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            self._logger.error(f"Operation failed (circuit breaker): {e}")
            raise

    def _get_cached(self, key: str) -> t.Any | None:
        """Get cached result if not expired."""
        if key in self._cache:
            expiry = self._cache_ttl.get(key, 0)
            if time.time() < expiry:
                return self._cache[key]
            else:
                del self._cache[key]
                self._cache_ttl.pop(key, None)
        return None

    def _set_cached(self, key: str, value: t.Any, ttl: float = 60.0) -> None:
        """Cache a result with TTL."""
        self._cache[key] = value
        self._cache_ttl[key] = time.time() + ttl

    def clear_cache(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._cache_ttl.clear()


# Global adapter instance
_pycharm_adapter: PyCharmMCPAdapter | None = None


def get_pycharm_adapter() -> PyCharmMCPAdapter:
    """Get or create the global PyCharm adapter instance."""
    global _pycharm_adapter
    if _pycharm_adapter is None:
        _pycharm_adapter = PyCharmMCPAdapter()
    return _pycharm_adapter


def register_ide_tools(mcp: FastMCP) -> None:
    """Register PyCharm IDE integration tools.

    Args:
        mcp: FastMCP application instance
    """
    adapter = get_pycharm_adapter()

    @mcp.tool()
    async def get_ide_diagnostics(
        file_path: str,
        errors_only: bool = False,
    ) -> str:
        """Get IDE-level diagnostics for a file from PyCharm."""
        try:
            problems = await adapter.get_file_problems(file_path, errors_only)

            # Convert to ToolIssue-compatible format
            issues = []
            for prob in problems:
                issues.append(
                    {
                        "file_path": file_path,
                        "line_number": prob.get("line", 0),
                        "column": prob.get("column", 0),
                        "message": prob.get("message", ""),
                        "severity": prob.get("severity", "ERROR").upper(),
                        "category": prob.get("category", "GENERAL"),
                    }
                )

            return json.dumps(
                {
                    "success": True,
                    "file_path": file_path,
                    "count": len(issues),
                    "issues": issues,
                }
            )

        except Exception as e:
            logger.error(f"Failed to get IDE diagnostics: {e}")
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "file_path": file_path,
                }
            )

    @mcp.tool()
    async def search_code_patterns(
        pattern: str,
        file_pattern: str | None = None,
    ) -> str:
        """Search for code patterns across all indexed files."""
        try:
            results = await adapter.search_regex(pattern, file_pattern)

            # Convert to serializable format
            matches = []
            for result in results:
                matches.append(
                    {
                        "file_path": result.file_path,
                        "line_number": result.line_number,
                        "column": result.column,
                        "match_text": result.match_text,
                        "context_before": result.context_before,
                        "context_after": result.context_after,
                    }
                )

            return json.dumps(
                {
                    "success": True,
                    "pattern": pattern,
                    "count": len(matches),
                    "results": matches,
                }
            )

        except Exception as e:
            logger.error(f"Failed to search code patterns: {e}")
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "pattern": pattern,
                }
            )

    @mcp.tool()
    async def get_symbol_info(symbol_name: str) -> str:
        """Get information about a code symbol."""
        try:
            info = await adapter.get_symbol_info(symbol_name)
            if info:
                return json.dumps(
                    {
                        "success": True,
                        "symbol_name": symbol_name,
                        **info,
                    }
                )
            return json.dumps(
                {
                    "success": False,
                    "error": f"Symbol '{symbol_name}' not found",
                }
            )

        except Exception as e:
            logger.error(f"Failed to get symbol info: {e}")
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                }
            )

    @mcp.tool()
    async def find_usages(symbol_name: str) -> str:
        """Find all usages of a symbol across the codebase."""
        try:
            usages = await adapter.find_usages(symbol_name)

            # Convert to serializable format
            usage_list = []
            for usage in usages:
                usage_list.append(
                    {
                        "file_path": usage.get("file_path", ""),
                        "line_number": usage.get("line", 0),
                        "column": usage.get("column", 0),
                        "type": usage.get("type", "reference"),
                        "symbol": usage.get("symbol", symbol_name),
                    }
                )

            return json.dumps(
                {
                    "success": True,
                    "symbol_name": symbol_name,
                    "count": len(usage_list),
                    "usages": usage_list,
                }
            )

        except Exception as e:
            logger.error(f"Failed to find usages: {e}")
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                }
            )

    @mcp.tool()
    async def pycharm_health() -> str:
        """Check health of PyCharm MCP integration."""
        try:
            health = await adapter.health_check()
            return json.dumps(
                {
                    "success": True,
                    "healthy": health["mcp_available"],
                    **health,
                }
            )

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                }
            )

    logger.info("PyCharm IDE tools registered successfully")


__all__ = [
    "register_ide_tools",
    "PyCharmMCPAdapter",
    "get_pycharm_adapter",
]
