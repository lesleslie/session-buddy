from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module
    return module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_ensure_package("session_buddy", PROJECT_ROOT / "session_buddy")
_ensure_package("session_buddy.core", PROJECT_ROOT / "session_buddy" / "core")
_ensure_package("session_buddy.mcp", PROJECT_ROOT / "session_buddy" / "mcp")

core_quality_scoring = _load_module(
    "session_buddy.core.quality_scoring",
    PROJECT_ROOT / "session_buddy" / "core" / "quality_scoring.py",
)
mcp_quality_scorer = _load_module(
    "session_buddy.mcp.quality_scorer",
    PROJECT_ROOT / "session_buddy" / "mcp" / "quality_scorer.py",
)

MCPQualityScorer = mcp_quality_scorer.MCPQualityScorer


@pytest.mark.asyncio
async def test_mcp_quality_scorer_success_and_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorer = MCPQualityScorer()

    async def fake_calculate_quality_score(project_dir=None):
        return {"total_score": 91, "breakdown": {"code_quality": 40}}

    quality_engine_stub = SimpleNamespace(
        calculate_quality_score=fake_calculate_quality_score
    )
    monkeypatch.setitem(sys.modules, "session_buddy.quality_engine", quality_engine_stub)

    result = await scorer.calculate_quality_score()
    assert result["total_score"] == 91
    assert result["breakdown"]["code_quality"] == 40

    monkeypatch.setitem(
        sys.modules,
        "session_buddy.quality_engine",
        SimpleNamespace(),
    )
    fallback = await scorer.calculate_quality_score()
    assert fallback["total_score"] == 75
    assert fallback["metrics"]["quality"]["score"] == 75


def test_mcp_quality_scorer_permissions_score_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorer = MCPQualityScorer()

    monkeypatch.setitem(
        sys.modules,
        "session_buddy.mcp.server",
        SimpleNamespace(
            permissions_manager=SimpleNamespace(trusted_operations=[1, 2, 3])
        ),
    )

    assert scorer.get_permissions_score() == 12

    monkeypatch.setitem(
        sys.modules,
        "session_buddy.mcp.server",
        SimpleNamespace(
            permissions_manager=SimpleNamespace(
                trusted_operations=[1, 2, 3, 4, 5, 6, 7]
            )
        ),
    )
    assert scorer.get_permissions_score() == 12


def test_mcp_quality_scorer_permissions_score_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that permissions score is capped at 20."""
    scorer = MCPQualityScorer()

    monkeypatch.setitem(
        sys.modules,
        "session_buddy.mcp.server",
        SimpleNamespace(
            permissions_manager=SimpleNamespace(trusted_operations=list(range(10)))
        ),
    )

    assert scorer.get_permissions_score() == 20


def test_mcp_quality_scorer_permissions_score_fallback_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test fallback score when permissions_manager is missing trusted ops."""
    scorer = MCPQualityScorer()

    monkeypatch.setitem(
        sys.modules,
        "session_buddy.mcp.server",
        SimpleNamespace(permissions_manager=SimpleNamespace()),
    )

    assert scorer.get_permissions_score() == 10


def test_mcp_quality_scorer_permissions_score_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test fallback score when the MCP server import fails."""
    scorer = MCPQualityScorer()

    monkeypatch.delitem(sys.modules, "session_buddy.mcp.server", raising=False)

    assert scorer.get_permissions_score() == 10
