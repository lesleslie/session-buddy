"""Tests for session_buddy.mcp.quality_scorer.

Covers the MCP-layer ``MCPQualityScorer`` (1 class, 3 callable units):

- ``__init__`` sets the permissions-score cache to ``None``
- ``calculate_quality_score`` delegates to ``session_buddy.quality_engine`` and
  returns its payload; falls back to a basic dict on ``ImportError``
- ``get_permissions_score`` resolves trusted operations from already-imported
  server modules, applies the points math (4 per op, capped at 20), caches
  the result, and falls back to 10 when no manager is registered
- ``_resolve_trusted_operations`` walks ``_PERMISSIONS_MODULES`` and returns
  the first ``permissions_manager.trusted_operations`` it finds, or ``None``

Test approach: monkeypatch ``sys.modules`` entries for the candidate server
modules, or patch the imported helpers inside the module. ``asyncio_mode =
auto`` handles the async tests; no ``@pytest.mark.asyncio`` needed.
"""

from __future__ import annotations

import builtins
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock

import pytest

from session_buddy.mcp.quality_scorer import (
    MCPQualityScorer,
    _FALLBACK_PERMISSIONS_SCORE,
    _MAX_PERMISSIONS_SCORE,
    _POINTS_PER_TRUSTED_OPERATION,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scorer() -> MCPQualityScorer:
    """Fresh scorer with no cached permissions score."""
    return MCPQualityScorer()


@pytest.fixture
def clean_server_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove any stale server modules from ``sys.modules`` for isolation."""
    for module_name in ("session_buddy.mcp.server", "session_buddy.server"):
        monkeypatch.delitem(sys.modules, module_name, raising=False)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Sanity checks on the scoring constants — guards against silent
    renames that would change the permissions curve.
    """

    def test_points_per_trusted_operation(self) -> None:
        assert _POINTS_PER_TRUSTED_OPERATION == 4

    def test_max_permissions_score(self) -> None:
        assert _MAX_PERMISSIONS_SCORE == 20

    def test_fallback_permissions_score(self) -> None:
        assert _FALLBACK_PERMISSIONS_SCORE == 10

    def test_max_equals_points_times_five(self) -> None:
        # 5 trusted ops × 4 points each == 20 (the ceiling)
        assert _MAX_PERMISSIONS_SCORE == _POINTS_PER_TRUSTED_OPERATION * 5


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_cache_starts_none(self, scorer: MCPQualityScorer) -> None:
        assert scorer._permissions_score_cache is None

    def test_each_instance_independent(self) -> None:
        a = MCPQualityScorer()
        b = MCPQualityScorer()
        a._permissions_score_cache = 17
        assert b._permissions_score_cache is None


# ---------------------------------------------------------------------------
# calculate_quality_score
# ---------------------------------------------------------------------------


class TestCalculateQualityScore:
    async def test_delegates_to_quality_engine(
        self,
        scorer: MCPQualityScorer,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """When ``session_buddy.quality_engine`` is importable, call it with
        ``project_dir`` as keyword arg and return its payload."""
        fake_engine = ModuleType("session_buddy.quality_engine")
        fake_engine.calculate_quality_score = AsyncMock(
            return_value={"overall": 92, "metrics": {"x": 1}}
        )
        monkeypatch.setitem(sys.modules, "session_buddy.quality_engine", fake_engine)

        result = await scorer.calculate_quality_score(project_dir=tmp_path)

        assert result == {"overall": 92, "metrics": {"x": 1}}
        fake_engine.calculate_quality_score.assert_awaited_once_with(
            project_dir=tmp_path
        )

    async def test_passes_none_project_dir(
        self,
        scorer: MCPQualityScorer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_engine = ModuleType("session_buddy.quality_engine")
        fake_engine.calculate_quality_score = AsyncMock(return_value={"overall": 80})
        monkeypatch.setitem(sys.modules, "session_buddy.quality_engine", fake_engine)

        result = await scorer.calculate_quality_score()

        assert result == {"overall": 80}
        fake_engine.calculate_quality_score.assert_awaited_once_with(project_dir=None)

    async def test_import_error_returns_basic_score(
        self,
        scorer: MCPQualityScorer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When ``session_buddy.quality_engine`` is missing, fall back to the
        static 'basic score' dict rather than raising."""
        # Ensure the engine is NOT importable. Wrap ``builtins.__import__``
        # so the engine module raises ImportError while other imports pass
        # through unchanged.
        original_import = builtins.__import__

        def guarded_import(
            name: str,
            globals: Any = None,
            locals: Any = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> Any:
            if name == "session_buddy.quality_engine" or name.startswith(
                "session_buddy.quality_engine."
            ):
                raise ImportError("simulated missing engine")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", guarded_import)

        result = await scorer.calculate_quality_score(project_dir=Path("/tmp/x"))

        # Fallback payload carries the compatibility key AND the overall score
        assert result["total_score"] == 75
        assert result["overall"] == 75
        assert "metrics" in result
        assert result["metrics"]["coverage"]["coverage_pct"] == 0
        assert result["metrics"]["quality"]["score"] == 75
        assert result["project_health"]["total"] == 75
        assert result["permissions_health"]["score"] == 10
        assert result["session_health"]["status"] == "active"

    async def test_import_error_recommendations_empty(
        self,
        scorer: MCPQualityScorer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original_import = builtins.__import__

        def guarded_import(
            name: str,
            globals: Any = None,
            locals: Any = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> Any:
            if name == "session_buddy.quality_engine":
                raise ImportError("missing")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", guarded_import)

        result = await scorer.calculate_quality_score()
        assert result["recommendations"] == []
        assert result["tool_health"]["count"] == 0


# ---------------------------------------------------------------------------
# _resolve_trusted_operations
# ---------------------------------------------------------------------------


class TestResolveTrustedOperations:
    def test_returns_none_when_no_modules_loaded(
        self,
        clean_server_modules: None,
    ) -> None:
        assert MCPQualityScorer._resolve_trusted_operations() is None

    def test_returns_none_when_module_present_without_manager(
        self,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Module exists but lacks ``permissions_manager``.
        mod = ModuleType("session_buddy.mcp.server")
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mod)
        assert MCPQualityScorer._resolve_trusted_operations() is None

    def test_returns_none_when_manager_lacks_attribute(
        self,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Module has ``permissions_manager`` but it has no ``trusted_operations``.
        mod = ModuleType("session_buddy.mcp.server")
        mod.permissions_manager = object()  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mod)
        assert MCPQualityScorer._resolve_trusted_operations() is None

    def test_returns_trusted_ops_from_mcp_server(
        self,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ops = {"Bash", "Read"}
        mod = ModuleType("session_buddy.mcp.server")
        mod.permissions_manager = type("M", (), {"trusted_operations": ops})()
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mod)

        result = MCPQualityScorer._resolve_trusted_operations()
        assert result is ops

    def test_falls_back_to_legacy_session_buddy_server(
        self,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the MCP-layer module is absent, the legacy module is tried."""
        ops = {"Edit"}
        legacy = ModuleType("session_buddy.server")
        legacy.permissions_manager = type("M", (), {"trusted_operations": ops})()
        monkeypatch.setitem(sys.modules, "session_buddy.server", legacy)

        result = MCPQualityScorer._resolve_trusted_operations()
        assert result is ops

    def test_prefers_mcp_server_over_legacy(
        self,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When both modules expose a manager, the MCP one wins (order in
        ``_PERMISSIONS_MODULES``)."""
        mcp_ops = {"MCP-OPS"}
        legacy_ops = {"LEGACY-OPS"}
        mcp_mod = ModuleType("session_buddy.mcp.server")
        mcp_mod.permissions_manager = type(
            "M", (), {"trusted_operations": mcp_ops}
        )()
        legacy_mod = ModuleType("session_buddy.server")
        legacy_mod.permissions_manager = type(
            "M", (), {"trusted_operations": legacy_ops}
        )()
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mcp_mod)
        monkeypatch.setitem(sys.modules, "session_buddy.server", legacy_mod)

        result = MCPQualityScorer._resolve_trusted_operations()
        assert result is mcp_ops


# ---------------------------------------------------------------------------
# get_permissions_score
# ---------------------------------------------------------------------------


class TestGetPermissionsScore:
    def test_returns_fallback_when_no_manager_loaded(
        self,
        scorer: MCPQualityScorer,
        clean_server_modules: None,
    ) -> None:
        score = scorer.get_permissions_score()
        assert score == _FALLBACK_PERMISSIONS_SCORE

    def test_returns_cached_value_on_second_call(
        self,
        scorer: MCPQualityScorer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Once cached, the resolver is not consulted again."""
        scorer._permissions_score_cache = 16
        # Even with no module loaded, the cache wins.
        score = scorer.get_permissions_score()
        assert score == 16

    def test_zero_trusted_operations_returns_zero(
        self,
        scorer: MCPQualityScorer,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Empty trusted_ops → 0 points → 0 score (no fallback)."""
        mod = ModuleType("session_buddy.mcp.server")
        mod.permissions_manager = type("M", (), {"trusted_operations": set()})()
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mod)

        assert scorer.get_permissions_score() == 0

    @pytest.mark.parametrize(
        "count, expected",
        [
            (1, 4),
            (2, 8),
            (3, 12),
            (4, 16),
            (5, 20),  # boundary — exactly at the cap
            (6, 20),  # above cap → capped
            (10, 20),
        ],
    )
    def test_score_math(
        self,
        scorer: MCPQualityScorer,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
        count: int,
        expected: int,
    ) -> None:
        ops = {f"op{i}" for i in range(count)}
        mod = ModuleType("session_buddy.mcp.server")
        mod.permissions_manager = type("M", (), {"trusted_operations": ops})()
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mod)

        assert scorer.get_permissions_score() == expected

    def test_populates_cache_after_first_call(
        self,
        scorer: MCPQualityScorer,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ops = {"Bash", "Edit"}
        mod = ModuleType("session_buddy.mcp.server")
        mod.permissions_manager = type("M", (), {"trusted_operations": ops})()
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mod)

        assert scorer._permissions_score_cache is None
        scorer.get_permissions_score()
        assert scorer._permissions_score_cache == 8  # 2 ops × 4 pts

    def test_fallback_does_not_populate_cache(
        self,
        scorer: MCPQualityScorer,
        clean_server_modules: None,
    ) -> None:
        """The fallback path is NOT cached — re-resolving after a manager
        appears should pick up the new value."""
        first = scorer.get_permissions_score()
        assert first == _FALLBACK_PERMISSIONS_SCORE
        assert scorer._permissions_score_cache is None

    def test_caches_after_fallback_resolves_manager(
        self,
        scorer: MCPQualityScorer,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After fallback, install a manager and call again — should cache
        the real score this time."""
        # First call → fallback
        scorer.get_permissions_score()
        assert scorer._permissions_score_cache is None

        # Now install a manager with 1 trusted op
        ops = {"Bash"}
        mod = ModuleType("session_buddy.mcp.server")
        mod.permissions_manager = type("M", (), {"trusted_operations": ops})()
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mod)

        assert scorer.get_permissions_score() == 4
        assert scorer._permissions_score_cache == 4

    def test_manager_with_none_trusted_ops_falls_back(
        self,
        scorer: MCPQualityScorer,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``trusted_operations`` attribute is explicitly ``None`` → no
        value found → fallback fires."""
        mod = ModuleType("session_buddy.mcp.server")
        mod.permissions_manager = type("M", (), {"trusted_operations": None})()
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mod)

        assert scorer.get_permissions_score() == _FALLBACK_PERMISSIONS_SCORE


# ---------------------------------------------------------------------------
# Integration: full instance lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_full_lifecycle(
        self,
        scorer: MCPQualityScorer,
        clean_server_modules: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """End-to-end: init → cache unset → resolve → cache set → consistent
        subsequent calls → permission score stable across ``calculate_*``."""
        # Install a manager with 3 trusted ops
        ops = {"op1", "op2", "op3"}
        mod = ModuleType("session_buddy.mcp.server")
        mod.permissions_manager = type("M", (), {"trusted_operations": ops})()
        monkeypatch.setitem(sys.modules, "session_buddy.mcp.server", mod)

        # Also install a fake engine for calculate_quality_score
        fake_engine = ModuleType("session_buddy.quality_engine")
        fake_engine.calculate_quality_score = AsyncMock(
            return_value={"overall": 50}
        )
        monkeypatch.setitem(sys.modules, "session_buddy.quality_engine", fake_engine)

        assert scorer._permissions_score_cache is None
        assert scorer.get_permissions_score() == 12
        assert scorer.get_permissions_score() == 12  # cached

        score_result = await scorer.calculate_quality_score()
        assert score_result == {"overall": 50}

        # Permissions score still 12 after the unrelated async call
        assert scorer.get_permissions_score() == 12
