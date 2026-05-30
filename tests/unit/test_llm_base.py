from __future__ import annotations

from collections.abc import AsyncGenerator


def test_llm_provider_base_initialization() -> None:
    from session_buddy.llm.base import LLMProvider
    from session_buddy.llm.models import LLMMessage, LLMResponse

    class DummyProvider(LLMProvider):
        async def generate(
            self,
            messages: list[LLMMessage],
            model: str | None = None,
            temperature: float = 0.7,
            max_tokens: int | None = None,
            **kwargs,
        ) -> LLMResponse:
            return LLMResponse(
                content="ok",
                model=model or "dummy",
                provider=self.name,
                usage={},
                finish_reason="stop",
                timestamp="2026-01-01T00:00:00",
            )

        async def stream_generate(
            self,
            messages: list[LLMMessage],
            model: str | None = None,
            temperature: float = 0.7,
            max_tokens: int | None = None,
            **kwargs,
        ) -> AsyncGenerator[str]:
            if False:
                yield ""

        async def is_available(self) -> bool:
            return True

        def get_models(self) -> list[str]:
            return ["dummy"]

    provider = DummyProvider({"api_key": "x"})

    assert provider.config == {"api_key": "x"}
    assert provider.name == "dummy"
    assert provider.logger.name == "llm_providers.dummy"
