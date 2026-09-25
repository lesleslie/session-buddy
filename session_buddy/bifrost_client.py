"""OpenAI-compatible client for the Bifrost LLM gateway.

Bifrost (port 8471 by default) is the Bodai LLM gateway. This client is
a thin httpx2 wrapper around the ``/chat/completions`` endpoint and
returns an OpenAI-style completion dict.

Per the CLAUDE.md model-routing config, model names use the canonical
provider prefix (e.g. ``minimax/MiniMax-M3``) so Bifrost can route to the
right backend (cloud, ollama, llama_server).

Credential resolution (Track A-ext1 of the serverless-tiering plan):
``BIFROST_API_KEY`` is read via the Oneiric secrets adapter wrapper
(``session_buddy.secrets_oneiric``). The wrapper falls back to the legacy
``BIFROST_API_KEY`` env var when ``ONEIRIC_SECRET_BIFROST_API_KEY`` is
absent. Because ``__init__`` is synchronous but the resolver is async,
``api_key`` is resolved lazily on the first ``chat()`` call.
"""

from __future__ import annotations

import os
from typing import Any

import httpx2 as httpx

from .secrets_oneiric import get_secret

DEFAULT_BASE_URL = "http://localhost:8471/v1"
DEFAULT_TIMEOUT = 30.0


class BifrostClient:
    """Minimal OpenAI-compat chat client for the Bifrost gateway."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("BIFROST_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        # API key resolved lazily (sync __init__ cannot await). Resolved on
        # first chat() call via _resolve_api_key(). Explicit api_key
        # argument or legacy BIFROST_API_KEY env var short-circuits the
        # secrets lookup.
        self._api_key_explicit = api_key
        self.api_key: str | None = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _resolve_api_key(self) -> str | None:
        """Resolve api_key from explicit arg → Oneiric secrets → None."""
        if self._api_key_explicit is not None:
            return self._api_key_explicit
        if self.api_key is not None:
            return self.api_key
        self.api_key = await get_secret("BIFROST_API_KEY")
        return self.api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(
        self,
        prompt: str,
        *,
        model: str = "minimax/MiniMax-M3",
        system: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """One-shot chat completion. Returns {content, usage, model, raw}."""
        # Ensure api_key is resolved before posting.
        if not self.api_key:
            await self._resolve_api_key()
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {"model": model, "messages": messages}
        payload.update(kwargs)
        resp = await self._client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        choice = body["choices"][0]
        return {
            "content": choice["message"]["content"],
            "usage": body.get("usage", {}),
            "model": body.get("model", model),
            "raw": body,
        }

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
