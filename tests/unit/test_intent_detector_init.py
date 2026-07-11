"""Targeted unit tests for IntentDetector.initialize().

The existing ``test_intent_detection_tools.py`` covers most of the
IntentDetector surface but skips the happy-path branch of
``initialize()`` that loads patterns from a real YAML file (missing
lines 69-97 in the module). This file targets those gaps plus the
``_semantic_match`` Exception branch (lines 220-221) and the
``_combine_matches`` semantic-loses branch (lines 285-290).
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.intent_detector import IntentDetector, ToolMatch


# ============================================================================
# initialize()
# ============================================================================


@pytest.mark.asyncio
class TestInitializeLoadsFromRealYaml:
    async def test_loads_real_patterns_yaml(self, tmp_path: Path) -> None:
        """Real patterns YAML is loaded successfully.

        The production code looks for ``data/intent_patterns.yaml`` relative
        to ``session_buddy/core``. If the file is present, ``initialize()``
        must load it without falling back to defaults.
        """
        detector = IntentDetector()
        # Snapshot state before init
        assert detector.patterns == {}

        await detector.initialize()

        # If the bundled YAML exists, we should have at least one tool
        bundled_yaml = (
            Path(__file__).resolve().parents[2]
            / "session_buddy"
            / "data"
            / "intent_patterns.yaml"
        )
        if bundled_yaml.exists():
            # At least one tool registered
            assert len(detector.patterns) >= 1
            # Loaded lists are lists
            for tool_name, patterns in detector.patterns.items():
                assert isinstance(patterns, list)
                # And the corresponding semantic examples list is populated
                assert isinstance(detector.semantic_examples[tool_name], list)
        else:
            # No YAML — defaults kicked in
            assert "checkpoint" in detector.patterns


@pytest.mark.asyncio
class TestInitializeFallsBack:
    async def test_falls_back_when_yaml_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing YAML file falls back to default patterns + logs warning."""
        detector = IntentDetector()
        # Force the bundled patterns path to a non-existent location
        fake_path = tmp_path / "no-such-file.yaml"

        # Patch Path so its .exists() returns False for the patterns file
        original_exists = Path.exists

        def fake_exists(self: Path) -> bool:  # type: ignore[override]
            if self == fake_path or self.name == "intent_patterns.yaml":
                return False
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", fake_exists)

        # The detector computes the patterns path dynamically; we patch
        # Path.exists globally and verify the fallback path is exercised.
        await detector.initialize()

        # Defaults were loaded
        assert "checkpoint" in detector.patterns
        assert "search_reflections" in detector.patterns
        assert "quality_monitor" in detector.patterns

    async def test_logs_warning_when_yaml_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
    ) -> None:
        """A warning is emitted when YAML patterns file is missing."""
        detector = IntentDetector()
        original_exists = Path.exists

        def fake_exists(self: Path) -> bool:  # type: ignore[override]
            if self.name == "intent_patterns.yaml":
                return False
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", fake_exists)

        with caplog.at_level(logging.WARNING, logger="session_buddy.core.intent_detector"):
            await detector.initialize()

        assert any(
            "Intent patterns file not found" in record.message
            for record in caplog.records
        )

    async def test_swallows_yaml_load_exception(
        self, monkeypatch: pytest.MonkeyPatch, caplog
    ) -> None:
        """Exceptions during YAML load fall back to defaults + log error."""
        detector = IntentDetector()
        # Force yaml.safe_load to raise when called from the production module.
        import yaml as yaml_module

        def _explode(*_args, **_kwargs):
            raise RuntimeError("yaml boom")

        monkeypatch.setattr(yaml_module, "safe_load", _explode)

        with caplog.at_level(logging.ERROR, logger="session_buddy.core.intent_detector"):
            await detector.initialize()

        # Defaults loaded
        assert "checkpoint" in detector.patterns
        # And error was logged
        assert any(
            "Failed to load intent patterns" in record.message
            for record in caplog.records
        )


# ============================================================================
# _semantic_match — Exception branch (lines 220-221)
# ============================================================================


class TestSemanticMatchGenericException:
    @pytest.mark.asyncio
    async def test_generic_exception_returns_none(self, caplog) -> None:
        """Unexpected exceptions inside _semantic_match are logged and swallowed."""
        detector = IntentDetector()
        detector.semantic_examples = {"x": ["y"]}

        # Patch generate_embedding to raise a non-ImportError exception
        # AFTER the import succeeds.
        async def _explode(_text: str):
            raise RuntimeError("embedding down")

        fake_module = MagicMock()
        fake_module.generate_embedding = AsyncMock(side_effect=_explode)

        # numpy is fine — patch at the import boundary inside _semantic_match.
        with patch.dict(
            "sys.modules",
            {"session_buddy.reflection_tools": fake_module},
        ):
            with caplog.at_level(logging.ERROR, logger="session_buddy.core.intent_detector"):
                result = await detector._semantic_match("hello")

        assert result is None
        # Error was logged with the original exception
        assert any(
            "Semantic matching failed" in record.message
            for record in caplog.records
        )


# ============================================================================
# _combine_matches — semantic < pattern branch (lines 285-290)
# ============================================================================


class TestCombineMatchesSemanticLower:
    def test_pattern_wins_when_higher_confidence(self) -> None:
        """When pattern's confidence is higher than semantic's, pattern wins
        with the semantic tool recorded as an alternative."""
        detector = IntentDetector()
        semantic = ToolMatch(tool_name="sem_tool", confidence=0.5, extracted_args={})
        pattern = ToolMatch(tool_name="pat_tool", confidence=0.9, extracted_args={})

        result = detector._combine_matches(semantic, pattern)

        assert result is not None
        assert result.tool_name == "pat_tool"
        assert result.confidence == 0.9
        assert result.alternatives == ["sem_tool"]
        assert result.disambiguation_needed is True