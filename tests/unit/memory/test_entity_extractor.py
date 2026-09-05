from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from session_buddy.memory.entity_extractor import (
    EntityExtractionEngine,
    EntityExtractionResult,
    EntityRelationship,
    LLMEntityExtractor,
    PatternBasedExtractor,
    ProcessedMemory,
    ExtractedEntity,
)


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------


class TestExtractedEntity:
    """Tests for ExtractedEntity Pydantic model."""

    def test_minimal_required_fields(self) -> None:
        e = ExtractedEntity(entity_type="person", entity_value="Alice")
        assert e.entity_type == "person"
        assert e.entity_value == "Alice"
        assert e.confidence == 1.0

    def test_confidence_must_be_in_range(self) -> None:
        ExtractedEntity(
            entity_type="person", entity_value="Alice", confidence=0.0
        )
        ExtractedEntity(
            entity_type="person", entity_value="Alice", confidence=1.0
        )
        with pytest.raises(ValidationError):
            ExtractedEntity(
                entity_type="person", entity_value="Alice", confidence=-0.1
            )
        with pytest.raises(ValidationError):
            ExtractedEntity(
                entity_type="person", entity_value="Alice", confidence=1.1
            )


class TestEntityRelationship:
    """Tests for EntityRelationship Pydantic model."""

    def test_default_values(self) -> None:
        r = EntityRelationship(
            from_entity="A",
            to_entity="B",
            relationship_type="uses",
        )
        assert r.strength == 1.0

    def test_strength_validation(self) -> None:
        with pytest.raises(ValidationError):
            EntityRelationship(
                from_entity="A",
                to_entity="B",
                relationship_type="uses",
                strength=2.0,
            )


class TestProcessedMemory:
    """Tests for ProcessedMemory Pydantic model."""

    def test_minimal_required_fields(self) -> None:
        m = ProcessedMemory(
            category="facts",
            importance_score=0.5,
            summary="short",
            searchable_content="full content",
            reasoning="because",
        )
        assert m.category == "facts"
        assert m.importance_score == 0.5
        assert m.entities == []
        assert m.relationships == []
        assert m.tags == []
        assert m.suggested_tier == "long_term"
        assert m.subcategory is None

    def test_importance_score_validation(self) -> None:
        with pytest.raises(ValidationError):
            ProcessedMemory(
                category="facts",
                importance_score=1.5,
                summary="x",
                searchable_content="y",
                reasoning="z",
            )
        with pytest.raises(ValidationError):
            ProcessedMemory(
                category="facts",
                importance_score=-0.1,
                summary="x",
                searchable_content="y",
                reasoning="z",
            )

    def test_round_trip_via_model_dump(self) -> None:
        m = ProcessedMemory(
            category="skills",
            subcategory="python",
            importance_score=0.7,
            summary="summary",
            searchable_content="content",
            reasoning="because",
            entities=[ExtractedEntity(entity_type="tech", entity_value="python")],
            relationships=[
                EntityRelationship(
                    from_entity="x",
                    to_entity="y",
                    relationship_type="uses",
                )
            ],
            suggested_tier="long_term",
            tags=["t1", "t2"],
        )
        data = m.model_dump()
        # Re-validate from the dumped dict.
        rebuilt = ProcessedMemory.model_validate(data)
        assert rebuilt.category == "skills"
        assert rebuilt.subcategory == "python"
        assert len(rebuilt.entities) == 1
        assert rebuilt.entities[0].entity_value == "python"
        assert rebuilt.tags == ["t1", "t2"]


# ------------------------------------------------------------------
# EntityExtractionResult dataclass
# ------------------------------------------------------------------


class TestEntityExtractionResult:
    """Tests for EntityExtractionResult dataclass."""

    def test_minimal_construction(self) -> None:
        m = ProcessedMemory(
            category="facts",
            importance_score=0.5,
            summary="s",
            searchable_content="c",
            reasoning="r",
        )
        r = EntityExtractionResult(
            processed_memory=m,
            entities_count=0,
            relationships_count=0,
            extraction_time_ms=10.0,
            llm_provider="openai",
        )
        assert r.entities_count == 0
        assert r.relationships_count == 0
        assert r.extraction_time_ms == 10.0


# ------------------------------------------------------------------
# PatternBasedExtractor
# ------------------------------------------------------------------


class TestPatternBasedExtractor:
    """Tests for PatternBasedExtractor."""

    @pytest.fixture
    def extractor(self) -> PatternBasedExtractor:
        return PatternBasedExtractor()

    async def test_extract_returns_processed_memory(self, extractor) -> None:
        result = await extractor.extract_entities(
            user_input="hello world",
            ai_output="hi there",
        )
        assert isinstance(result, ProcessedMemory)
        assert result.summary == "Conversation recorded"
        assert result.searchable_content == "hello world\nhi there"
        assert result.suggested_tier == "long_term"

    @pytest.mark.parametrize(
        ("user_input", "ai_output", "expected_category"),
        [
            ("I prefer dark mode", "noted", "preferences"),
            ("I like Python", "got it", "preferences"),
            ("Avoid sugary drinks", "ok", "preferences"),
            ("I learned Rust", "good", "skills"),
            ("I'm skilled at cooking", "ok", "skills"),
            ("Follow the rule: no yelling", "noted", "rules"),
            ("Today's context is busy", "ok", "context"),
            ("Random fact about something", "noted", "facts"),
        ],
    )
    async def test_categorize_keyword_branches(
        self, extractor, user_input: str, ai_output: str, expected_category: str
    ) -> None:
        result = await extractor.extract_entities(user_input, ai_output)
        assert result.category == expected_category
        # Tag list reflects the category (single tag, the category itself).
        assert result.tags == [expected_category]


# ------------------------------------------------------------------
# LLMEntityExtractor
# ------------------------------------------------------------------


class TestLLMEntityExtractorInit:
    """Tests for LLMEntityExtractor construction (no LLM calls)."""

    def test_default_construction_uses_openai(self, monkeypatch) -> None:
        # Clear environment vars so the constructor doesn't pick up local URLs.
        monkeypatch.delenv("BIFROST_OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("BIFROST_API_KEY", raising=False)

        ext = LLMEntityExtractor()
        assert ext.llm_provider == "openai"
        # Default model preserved when env not set.
        assert ext.model == "gpt-4o-mini"
        assert ext.base_url is None
        assert ext.api_key is None

    def test_bifrost_url_triggers_default_model_replacement(self, monkeypatch) -> None:
        monkeypatch.setenv("BIFROST_OPENAI_BASE_URL", "http://localhost:9999")
        monkeypatch.setenv("BIFROST_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

        ext = LLMEntityExtractor()
        # When BIFROST_OPENAI_BASE_URL is set, the default model is replaced.
        assert ext.model == "zai-openai/glm-5-turbo"
        assert ext.api_key == "test-key"
        assert ext.base_url == "http://localhost:9999"

    def test_openai_default_model_env_wins(self, monkeypatch) -> None:
        monkeypatch.delenv("BIFROST_OPENAI_BASE_URL", raising=False)
        monkeypatch.setenv("OPENAI_DEFAULT_MODEL", "custom-model")
        ext = LLMEntityExtractor()
        assert ext.model == "custom-model"


class TestLLMEntityExtractorExtract:
    """Tests for LLMEntityExtractor.extract_entities with mocked OpenAI client."""

    async def test_extract_entities_success(self, monkeypatch) -> None:
        monkeypatch.delenv("BIFROST_OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("BIFROST_API_KEY", raising=False)

        ext = LLMEntityExtractor()

        # Build a fake OpenAI response.
        fake_payload = ProcessedMemory(
            category="facts",
            subcategory="python",
            importance_score=0.9,
            summary="LL wrote this",
            searchable_content="content",
            reasoning="because",
            entities=[
                ExtractedEntity(
                    entity_type="technology", entity_value="python", confidence=0.95
                )
            ],
            relationships=[
                EntityRelationship(
                    from_entity="python",
                    to_entity="ai",
                    relationship_type="uses",
                    strength=0.8,
                )
            ],
            tags=["python", "ai"],
        )
        fake_response = MagicMock()
        fake_response.choices = [MagicMock()]
        fake_response.choices[0].message.content = (
            fake_payload.model_dump_json()
        )

        fake_client = MagicMock()
        fake_client.chat = MagicMock()
        fake_client.chat.completions = MagicMock()
        fake_client.chat.completions.create = AsyncMock(
            return_value=fake_response
        )
        ext._client = fake_client

        result = await ext.extract_entities(
            user_input="Tell me about Python",
            ai_output="Python is a language",
        )

        assert isinstance(result, EntityExtractionResult)
        assert result.processed_memory.category == "facts"
        assert result.entities_count == 1
        assert result.relationships_count == 1
        assert result.llm_provider == "openai"
        assert result.extraction_time_ms >= 0
        fake_client.chat.completions.create.assert_awaited_once()

    async def test_extract_entities_falls_back_on_exception(
        self, monkeypatch
    ) -> None:
        monkeypatch.delenv("BIFROST_OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("BIFROST_API_KEY", raising=False)

        ext = LLMEntityExtractor()

        fake_client = MagicMock()
        fake_client.chat = MagicMock()
        fake_client.chat.completions = MagicMock()
        fake_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        ext._client = fake_client

        result = await ext.extract_entities(
            user_input="hi", ai_output="hello"
        )
        # Fallback path yields a ProcessedMemory with category=context
        # and importance=0.5.
        assert result.processed_memory.category == "context"
        assert result.entities_count == 0
        assert result.relationships_count == 0
        assert result.extraction_time_ms >= 0

    async def test_initialize_is_idempotent(self, monkeypatch) -> None:
        monkeypatch.delenv("BIFROST_OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("BIFROST_API_KEY", raising=False)

        ext = LLMEntityExtractor()
        with patch("openai.AsyncOpenAI") as mock_openai_cls:
            mock_openai_cls.return_value = MagicMock(name="FakeClient")
            await ext.initialize()
            first_client = ext._client
            # Second call must not replace the client.
            await ext.initialize()
            assert ext._client is first_client
            # AsyncOpenAI was only called once.
            mock_openai_cls.assert_called_once()

    async def test_unsupported_provider_initialize_raises(self) -> None:
        ext = LLMEntityExtractor(llm_provider="anthropic")
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            await ext.initialize()


# ------------------------------------------------------------------
# EntityExtractionEngine — pattern fallback happy path
# ------------------------------------------------------------------


class TestEntityExtractionEngineFallback:
    """Tests for EntityExtractionEngine.extract_entities fallback path."""

    async def test_engine_falls_back_to_pattern_when_no_manager(self) -> None:
        # Build an engine with no LLM manager; fallback path runs.
        engine = EntityExtractionEngine()
        # Force the manager to None to exercise the fallback.
        engine.manager = None

        result = await engine.extract_entities(
            user_input="I prefer dark mode", ai_output="noted"
        )
        assert result.llm_provider == "pattern"
        # The pattern extractor picks "preferences" based on keyword matching.
        assert result.processed_memory.category == "preferences"

    async def test_engine_initializes_with_none_manager(self) -> None:
        # The constructor catches ImportError/TypeError and stores manager=None.
        engine = EntityExtractionEngine()
        # manager may be a real LLMManager (if SDK installed) or None.
        # The fallback extractor must always exist.
        assert engine.fallback_extractor is not None
        assert isinstance(engine.fallback_extractor, PatternBasedExtractor)


class TestEntityExtractionEngineCascade:
    """Tests for EntityExtractionEngine.extract_entities cascade path."""

    async def test_cascade_uses_first_successful_provider(self) -> None:
        engine = EntityExtractionEngine()
        # Replace manager with a fake whose `generate` returns valid JSON.
        fake_pm = ProcessedMemory(
            category="facts",
            importance_score=0.7,
            summary="LLM summary",
            searchable_content="content",
            reasoning="because",
        )

        class FakeResponse:
            def __init__(self, content: str) -> None:
                self.content = content

        fake_response = FakeResponse(fake_pm.model_dump_json())

        async def fake_generate(messages, provider, temperature):  # noqa: ARG001
            return fake_response

        engine.manager = MagicMock()
        engine.manager.generate = fake_generate

        result = await engine.extract_entities(
            user_input="x", ai_output="y"
        )
        # Cascade prefers "openai" first.
        assert result.llm_provider == "openai"
        assert result.processed_memory.summary == "LLM summary"

    async def test_cascade_falls_back_after_all_providers_fail(self) -> None:
        engine = EntityExtractionEngine()
        engine.timeout_s = 0.1
        engine.retries = 0

        async def fake_generate(messages, provider, temperature):  # noqa: ARG001
            raise RuntimeError("provider unavailable")

        engine.manager = MagicMock()
        engine.manager.generate = fake_generate

        result = await engine.extract_entities(
            user_input="I learned something",
            ai_output="noted",
        )
        # All providers failed → falls back to pattern-based.
        assert result.llm_provider == "pattern"
        # "learned" triggers the "skills" branch in the pattern extractor.
        assert result.processed_memory.category == "skills"

    async def test_cascade_retries_then_raises(self) -> None:
        engine = EntityExtractionEngine()
        engine.timeout_s = 0.1
        engine.retries = 2
        call_count = 0

        async def fake_generate(messages, provider, temperature):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            raise RuntimeError("always fail")

        engine.manager = MagicMock()
        engine.manager.generate = fake_generate

        result = await engine.extract_entities(
            user_input="x", ai_output="y"
        )
        # 3 attempts per provider × 3 providers = 9 attempts before fallback.
        assert call_count == (engine.retries + 1) * 3
        assert result.llm_provider == "pattern"


# ------------------------------------------------------------------
# ProcessedMemory JSON round-trip
# ------------------------------------------------------------------


class TestProcessedMemoryJSON:
    """Tests for ProcessedMemory.model_validate_json."""

    def test_validate_json_minimal_payload(self) -> None:
        payload = json.dumps(
            {
                "category": "facts",
                "importance_score": 0.5,
                "summary": "s",
                "searchable_content": "c",
                "reasoning": "r",
            }
        )
        m = ProcessedMemory.model_validate_json(payload)
        assert m.summary == "s"

    def test_validate_json_invalid_payload_raises(self) -> None:
        # Missing required field "summary".
        bad = json.dumps(
            {
                "category": "facts",
                "importance_score": 0.5,
                "searchable_content": "c",
                "reasoning": "r",
            }
        )
        with pytest.raises(ValidationError):
            ProcessedMemory.model_validate_json(bad)