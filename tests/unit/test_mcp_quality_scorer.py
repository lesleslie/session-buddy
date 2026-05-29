from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_mcp_quality_scorer_success_and_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.quality_scorer import MCPQualityScorer

    scorer = MCPQualityScorer()

    async def fake_calculate_quality_score(project_dir=None):
        return {"total_score": 91, "breakdown": {"code_quality": 40}}

    monkeypatch.setattr(
        "session_buddy.quality_engine.calculate_quality_score",
        fake_calculate_quality_score,
    )

    result = await scorer.calculate_quality_score()
    assert result["total_score"] == 91
    assert result["breakdown"]["code_quality"] == 40

    monkeypatch.setitem(
        __import__("sys").modules,
        "session_buddy.quality_engine",
        SimpleNamespace(),
    )
    fallback = await scorer.calculate_quality_score()
    assert fallback["total_score"] == 75
    assert fallback["metrics"]["quality"]["score"] == 75


def test_mcp_quality_scorer_permissions_score_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.mcp.quality_scorer import MCPQualityScorer

    scorer = MCPQualityScorer()

    monkeypatch.setitem(
        __import__("sys").modules,
        "session_buddy.mcp.server",
        SimpleNamespace(
            permissions_manager=SimpleNamespace(trusted_operations=[1, 2, 3])
        ),
    )

    assert scorer.get_permissions_score() == 12

    monkeypatch.setitem(
        __import__("sys").modules,
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
    from session_buddy.mcp.quality_scorer import MCPQualityScorer

    scorer = MCPQualityScorer()

    monkeypatch.setitem(
        __import__("sys").modules,
        "session_buddy.mcp.server",
        SimpleNamespace(
            permissions_manager=SimpleNamespace(
                trusted_operations=list(range(10))
            )
        ),
    )

    assert scorer.get_permissions_score() == 20


def test_mcp_quality_scorer_permissions_score_fallback_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test fallback score when permissions_manager is missing trusted ops."""
    from session_buddy.mcp.quality_scorer import MCPQualityScorer

    scorer = MCPQualityScorer()

    monkeypatch.setitem(
        __import__("sys").modules,
        "session_buddy.mcp.server",
        SimpleNamespace(permissions_manager=SimpleNamespace()),
    )

    assert scorer.get_permissions_score() == 10


def test_mcp_quality_scorer_permissions_score_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test fallback score when the MCP server import fails."""
    from session_buddy.mcp.quality_scorer import MCPQualityScorer

    scorer = MCPQualityScorer()

    monkeypatch.delitem(__import__("sys").modules, "session_buddy.mcp.server", raising=False)

    assert scorer.get_permissions_score() == 10
