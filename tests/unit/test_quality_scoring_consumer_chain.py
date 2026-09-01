from __future__ import annotations

import importlib
import json
import sqlite3
import typing as t
from pathlib import Path

import pytest

from session_buddy.crackerjack_integration import CrackerjackIntegration
from session_buddy.utils import quality_scoring


def _load_crackerjack_integration():
    return importlib.import_module("session_buddy.crackerjack_integration")

pytestmark = pytest.mark.asyncio

_SCORING_KEYS = frozenset(
    {"code_coverage", "lint_score", "security_score", "complexity_score"}
)


@pytest.fixture(autouse=True)
def clear_metrics_cache() -> t.Iterator[None]:
    quality_scoring._metrics_cache.clear()
    yield
    quality_scoring._metrics_cache.clear()


@pytest.fixture
def crackerjack_integration() -> t.Any:
    # tests/unit/test_quality_scoring_helpers.py installs a fake
    # ``session_buddy.crackerjack_integration`` module in sys.modules; if
    # the helpers test ran first, the real module isn't present yet.
    # Re-import through the standard loader to make sure we bind to the
    # real class.
    import sys
    real = _load_crackerjack_integration()
    if not hasattr(real, "CrackerjackIntegration"):
        sys.modules.pop("session_buddy.crackerjack_integration", None)
        real = _load_crackerjack_integration()
    return real


async def _empty_history(*args: object, **kwargs: object) -> list[dict[str, object]]:
    return []


def _force_metric_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quality_scoring, "CRACKERJACK_AVAILABLE", True)
    monkeypatch.setattr(quality_scoring, "get_quality_metrics_history", _empty_history)
    monkeypatch.setattr(quality_scoring, "_read_coverage_json", lambda _path: 0.0)
    monkeypatch.setattr(quality_scoring, "_read_coverage_dotfile", lambda _path: 0.0)


def _read_history_rows(database_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(str(database_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM crackerjack_results ORDER BY timestamp DESC",
        )
        return [dict(row) for row in cursor.fetchall()]


async def test_consumer_chain_invokes_helper_after_coverage_file_miss(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """DB miss + reflection miss + coverage miss invokes the CLI helper."""
    _force_metric_miss(monkeypatch)
    captured: dict[str, object] = {}

    async def fake_helper(*args: object, **kwargs: object) -> dict[str, float]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"lint_score": 80.0}

    monkeypatch.setattr(quality_scoring, "try_crackerjack_cli", fake_helper)

    result = await quality_scoring._get_crackerjack_metrics(tmp_path)

    assert result["lint_score"] == 80.0
    assert captured["args"] == ()
    assert captured["kwargs"] == {
        "project_dir": tmp_path,
        "missing_metrics": _SCORING_KEYS,
        "timeout": 30.0,
        "caller": "consumer_chain",
    }


async def test_consumer_chain_helper_none_falls_through_to_synthesis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    crackerjack_integration: t.Any,
) -> None:
    """A None helper result synthesizes unavailable metrics and writes history."""
    _force_metric_miss(monkeypatch)
    database_path = tmp_path / "crackerjack-history.db"
    real_integration = crackerjack_integration.CrackerjackIntegration
    # Pre-create the schema so the test can read it back after the consumer
    # chain has called _store_result against a fresh DB.
    real_integration(db_path=str(database_path))
    # The consumer chain reads its db_path from the global integration
    # singleton. Repoint the global so the synthesis write lands in
    # ``database_path`` rather than the user's home directory.
    global_integration = crackerjack_integration.get_crackerjack_integration()
    original_db_path = global_integration.db_path
    global_integration.db_path = str(database_path)
    global_integration._init_database()

    async def fake_helper(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(quality_scoring, "try_crackerjack_cli", fake_helper)
    try:
        result = await quality_scoring._get_crackerjack_metrics(tmp_path)
    finally:
        global_integration.db_path = original_db_path

    assert result == {
        "code_coverage": None,
        "lint_score": None,
        "security_score": None,
        "complexity_score": None,
        "unavailable": True,
    }
    history = _read_history_rows(database_path)
    assert any(row["command"] == "<unavailable>" for row in history), (
        f"synthesized row not found in history: {history!r}"
    )
    row = next(row for row in history if row["command"] == "<unavailable>")
    assert row["working_directory"] == str(tmp_path)
    assert row["exit_code"] == -1
    parsed_metrics = json.loads(row["quality_metrics"])
    assert parsed_metrics == result

    synthesized = crackerjack_integration.synthesize_unavailable_result(str(tmp_path))
    assert synthesized.quality_metrics == result
    assert synthesized.fallback_used is False


async def test_consumer_chain_helper_raises_falls_through_to_synthesis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    crackerjack_integration: t.Any,
) -> None:
    """Helper and best-effort history failures cannot crash synthesis."""
    _force_metric_miss(monkeypatch)

    async def fake_helper(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated helper failure")

    def failing_integration(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated history failure")

    monkeypatch.setattr(quality_scoring, "try_crackerjack_cli", fake_helper)
    monkeypatch.setattr(
        crackerjack_integration,
        "CrackerjackIntegration",
        failing_integration,
    )

    result = await quality_scoring._get_crackerjack_metrics(tmp_path)

    assert result["unavailable"] is True
    assert result["lint_score"] is None


async def test_consumer_chain_db_hit_skips_helper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Complete DB metrics return without invoking the CLI helper."""
    history = [
        {"metric_type": "code_coverage", "metric_value": 80.0},
        {"metric_type": "lint_score", "metric_value": 90.0},
        {"metric_type": "security_score", "metric_value": 100.0},
        {"metric_type": "complexity_score", "metric_value": 85.0},
    ]
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def fake_history(
        *args: object,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        return history

    async def fake_helper(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr(quality_scoring, "CRACKERJACK_AVAILABLE", True)
    monkeypatch.setattr(quality_scoring, "get_quality_metrics_history", fake_history)
    monkeypatch.setattr(quality_scoring, "try_crackerjack_cli", fake_helper)

    result = await quality_scoring._get_crackerjack_metrics(tmp_path)

    assert calls == []
    assert result["code_coverage"] == 80.0
    assert result["lint_score"] == 90.0
