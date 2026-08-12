from __future__ import annotations

import importlib.util
import inspect
import sys
import types
from pathlib import Path


def _load_quality_scoring_module():
    package_name = "session_buddy.utils"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [
            str(Path(__file__).resolve().parents[2] / "session_buddy" / "utils"),
        ]  # type: ignore[attr-defined]
        sys.modules[package_name] = package

    parser_module = types.ModuleType("session_buddy.utils.quality_score_parser")
    parser_module._extract_quality_scores = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    parser_module._generate_quality_trend_recommendations = (  # type: ignore[attr-defined]
        lambda *args, **kwargs: []
    )
    sys.modules["session_buddy.utils.quality_score_parser"] = parser_module

    crackerjack_module = types.ModuleType("session_buddy.crackerjack_integration")

    async def get_quality_metrics_history(*args, **kwargs):
        return []

    crackerjack_module.get_quality_metrics_history = get_quality_metrics_history  # type: ignore[attr-defined]
    sys.modules["session_buddy.crackerjack_integration"] = crackerjack_module

    module_path = (
        Path(__file__).resolve().parents[2]
        / "session_buddy"
        / "utils"
        / "quality_scoring.py"
    )
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.quality_scoring",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


qs = _load_quality_scoring_module()


def test_synthesis_replacement_emits_none_values() -> None:
    """Synthesis emits explicit unavailable markers, never perfect scores."""
    result = qs._create_fallback_metrics()
    assert result["code_coverage"] is None
    assert result["lint_score"] is None
    assert result["security_score"] is None
    assert result["complexity_score"] is None
    assert result["unavailable"] is True


def test_synthesis_replacement_does_not_emit_perfect_scores() -> None:
    """Regression guard: no key synthesizes 100."""
    result = qs._create_fallback_metrics()
    for key in ("code_coverage", "lint_score", "security_score", "complexity_score"):
        assert result[key] != 100, f"{key} unexpectedly synthesized as 100"


def test_synthesis_drops_coverage_pct_parameter() -> None:
    """API cleanup: legacy coverage_pct parameter is removed."""
    sig = inspect.signature(qs._create_fallback_metrics)
    assert "coverage_pct" not in sig.parameters
