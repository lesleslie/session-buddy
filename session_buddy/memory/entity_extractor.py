"""
LLM-Powered Entity Extraction - Memori pattern with multi-provider cascade.

Primary: OpenAI → Anthropic → Gemini → Pattern-based fallback.

Uses Pydantic models for typed outputs. Providers are optional; cascade
skips any unavailable provider gracefully and falls back to patterns.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# Pydantic models for structured extraction (Memori pattern)
class ExtractedEntity(BaseModel):
    """Single extracted entity with type and confidence."""

    entity_type: str = Field(
        description="Type of entity: person, technology, file, concept, organization"
    )
    entity_value: str = Field(description="The actual entity value")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence score 0.0-1.0"
    )


class EntityRelationship(BaseModel):
    """Relationship between two entities."""

    from_entity: str = Field(description="Source entity value")
    to_entity: str = Field(description="Target entity value")
    relationship_type: str = Field(
        description="Type: uses, extends, references, related_to, depends_on"
    )
    strength: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Relationship strength"
    )


class ProcessedMemory(BaseModel):
    """
    Complete processed memory structure - Memori pattern.

    This is the output from LLM-powered analysis of conversations.
    """

    # Categorization (Memori's 5 categories)
    category: str = Field(
        description="Memory category: facts, preferences, skills, rules, context"
    )
    subcategory: str | None = Field(
        default=None, description="Optional subcategory for finer granularity"
    )

    # Importance scoring
    importance_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Importance score 0.0-1.0 based on relevance and utility",
    )

    # Content processing
    summary: str = Field(
        description="Concise summary of the conversation (1-2 sentences)"
    )
    searchable_content: str = Field(
        description="Optimized content for search/retrieval"
    )
    reasoning: str = Field(description="Why this memory is important and how to use it")

    # Entity extraction
    entities: list[ExtractedEntity] = Field(
        default_factory=list, description="Extracted entities from conversation"
    )
    relationships: list[EntityRelationship] = Field(
        default_factory=list, description="Relationships between entities"
    )

    # Metadata
    suggested_tier: str = Field(
        default="long_term",
        description="Suggested memory tier: working, short_term, long_term",
    )
    tags: list[str] = Field(
        default_factory=list, description="Relevant tags for categorization"
    )


@dataclass
class EntityExtractionResult:
    """Result of entity extraction operation."""

    processed_memory: ProcessedMemory
    entities_count: int
    relationships_count: int
    extraction_time_ms: float
    llm_provider: str


class LLMEntityExtractor:
    """
    LLM-powered entity extraction using OpenAI Structured Outputs.

    Inspired by Memori's MemoryAgent pattern but adapted for session-mgmt-mcp's
    development workflow context.
    """

    def __init__(
        self,
        llm_provider: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
    ):
        """
        Initialize entity extractor with LLM configuration.

        Args:
            llm_provider: LLM provider (openai, anthropic, etc.)
            model: Model name (gpt-4o-mini recommended for cost/performance)
            api_key: Optional API key (uses environment variable if not provided)

        """
        self.llm_provider = llm_provider
        self.model = model
        self.api_key = api_key
        self._client: Any = None

    async def initialize(self) -> None:
        """Initialize LLM client (lazy initialization)."""
        if self._client is not None:
            return

        try:
            if self.llm_provider == "openai":
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=self.api_key)
                logger.info(f"Initialized OpenAI client with model: {self.model}")
            else:
                msg = f"Unsupported LLM provider: {self.llm_provider}"
                raise ValueError(msg)
        except ImportError:
            logger.exception(
                f"LLM provider '{self.llm_provider}' not available. "
                "Install openai package: pip install openai"
            )
            raise

    async def extract_entities(
        self,
        user_input: str,
        ai_output: str,
        context: dict[str, Any] | None = None,
    ) -> EntityExtractionResult:
        """
        Extract entities and categorize memory using LLM structured outputs.

        Args:
            user_input: User's input message
            ai_output: AI assistant's response
            context: Optional context (project, session_id, etc.)

        Returns:
            EntityExtractionResult with processed memory

        """
        await self.initialize()

        start_time = datetime.now()

        # Build prompt requesting JSON compatible with ProcessedMemory
        system = (
            "You are an information extraction assistant. Return ONLY valid JSON "
            "matching this schema keys: {category, subcategory, importance_score, "
            "summary, searchable_content, reasoning, entities, relationships, "
            "suggested_tier, tags}. Entities contain {entity_type, entity_value, confidence}. "
            "Relationships contain {from_entity, to_entity, relationship_type, strength}."
        )
        prompt = (
            f"User: {user_input}\nAssistant: {ai_output}\n"
            "Extract structured memory now."
        )

        try:
            # Prefer OpenAI structured output when available
            if self.llm_provider == "openai":
                client = self._client
                assert client is not None
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or "{}"
                pm = ProcessedMemory.model_validate_json(content)
                processed_memory = pm
            else:
                # Unsupported provider in this class; delegate to cascade engine
                msg = "Unsupported provider in LLMEntityExtractor"
                raise RuntimeError(msg)

            extraction_time = (datetime.now() - start_time).total_seconds() * 1000
            return EntityExtractionResult(
                processed_memory=processed_memory,
                entities_count=len(processed_memory.entities),
                relationships_count=len(processed_memory.relationships),
                extraction_time_ms=extraction_time,
                llm_provider=self.llm_provider,
            )
        except Exception:
            # Fall back to a minimal default to avoid hard failure
            logger.info("LLM extraction failed; falling back to default output")
            processed_memory = ProcessedMemory(
                category="context",
                importance_score=0.5,
                summary="Conversation recorded",
                searchable_content=f"{user_input} {ai_output}",
                reasoning="LLM extraction fallback",
            )
            extraction_time = (datetime.now() - start_time).total_seconds() * 1000
            return EntityExtractionResult(
                processed_memory=processed_memory,
                entities_count=0,
                relationships_count=0,
                extraction_time_ms=extraction_time,
                llm_provider=self.llm_provider,
            )


class PatternBasedExtractor:
    """Regex/keyword-based extraction as a no-deps fallback."""

    def _categorize(self, text: str) -> str:
        lower = text.lower()
        if any(k in lower for k in ("prefer", "like", "avoid")):
            return "preferences"
        if any(k in lower for k in ("skill", "learned", "expert")):
            return "skills"
        if any(k in lower for k in ("rule", "policy", "guideline")):
            return "rules"
        if any(k in lower for k in ("context", "today", "currently", "now")):
            return "context"
        return "facts"

    async def extract_entities(
        self, user_input: str, ai_output: str
    ) -> ProcessedMemory:
        text = f"{user_input}\n{ai_output}"
        category = self._categorize(text)
        return ProcessedMemory(
            category=category,
            importance_score=0.5,
            summary="Conversation recorded",
            searchable_content=text,
            reasoning="Pattern-based extraction",
            tags=[category],
            suggested_tier="long_term",
        )


class EntityExtractionEngine:
    """Multi-provider extraction with cascade fallback."""

    def __init__(self) -> None:
        from session_buddy.llm_providers import LLMManager, LLMMessage
        from session_buddy.settings import get_settings

        self._LLMMessage = LLMMessage
        self.manager = LLMManager()
        self.fallback_extractor = PatternBasedExtractor()
        settings = get_settings()
        self.timeout_s = settings.llm_extraction_timeout
        self.retries = settings.llm_extraction_retries

    async def extract_entities(
        self, user_input: str, ai_output: str
    ) -> EntityExtractionResult:
        system = (
            "You are an information extraction assistant. Return ONLY valid JSON "
            "for keys: category, subcategory, importance_score, summary, "
            "searchable_content, reasoning, entities, relationships, suggested_tier, tags."
        )
        from session_buddy.llm_providers import LLMMessage

        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(
                role="user",
                content=(
                    "Extract structured memory from the following.\n"
                    f"User: {user_input}\nAssistant: {ai_output}"
                ),
            ),
        ]

        providers = ["openai", "anthropic", "gemini"]
        start_time = datetime.now()

        for provider in providers:
            try:
                resp: Any | None = (
                    None  # Initialize to prevent "possibly unbound" error
                )
                for attempt in range(max(1, self.retries + 1)):
                    try:
                        resp = await asyncio.wait_for(
                            self.manager.generate(
                                messages, provider=provider, temperature=0.2
                            ),
                            timeout=self.timeout_s,
                        )
                        break
                    except Exception:
                        if attempt >= self.retries:
                            raise
                        continue
                assert resp is not None  # Type narrowing for pyright
                pm = ProcessedMemory.model_validate_json(resp.content)
                extraction_time = (datetime.now() - start_time).total_seconds() * 1000
                return EntityExtractionResult(
                    processed_memory=pm,
                    entities_count=len(pm.entities),
                    relationships_count=len(pm.relationships),
                    extraction_time_ms=extraction_time,
                    llm_provider=provider,
                )
            except Exception as e:
                logger.warning(f"{provider} extraction failed: {e}")
                continue

        # Final fallback: pattern-based
        pm = await self.fallback_extractor.extract_entities(user_input, ai_output)
        extraction_time = (datetime.now() - start_time).total_seconds() * 1000
        return EntityExtractionResult(
            processed_memory=pm,
            entities_count=len(pm.entities),
            relationships_count=len(pm.relationships),
            extraction_time_ms=extraction_time,
            llm_provider="pattern",
        )
