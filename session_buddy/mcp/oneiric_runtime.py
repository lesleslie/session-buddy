"""Phase 3 runtime-fact push helper for Session-Buddy.

SB has NO engine-adapter enum (no ``list_adapters`` analog). It exposes
domain adapters (knowledge_graph, reflection, serverless_storage,
session_storage) and a single LLM provider slot. So we push one fact
keyed ``__main__`` to Oneiric with the configuration snapshot that
operators care about:

- LLM provider: default + fallback chain + Ollama endpoint + default model
- Storage backend: DuckDB (SB's only built-in store; "postgres" tag only
  appears if a non-default storage provider is configured — SB does not
  expose one today, but the capability tag is reserved for future use)
- bodai_events: stream + consumer_group + enabled
- Network: http_port (8678) + websocket_port (8677)

Pure httpx. NO direct oneiric imports — that would re-introduce the
resolver chain that Phase 1/2 spent effort decoupling.

Fail-soft on push failure. Oneiric unavailability MUST NOT block SB
boot — mirrors the Dhara registration pattern at
``server_optimized.py:320-323`` where the existing
``_register_component_to_dhara`` call is wrapped in
``asyncio.create_task`` and protected by a narrow except.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx

from session_buddy.utils.logging import get_session_logger

logger = get_session_logger()

ONEIRIC_BASE_URL = "http://127.0.0.1:8681"
ONEIRIC_PUSH_TIMEOUT_SECONDS = 5.0

DOMAIN = "session_buddy"
FACT_KEY = "__main__"
CALLER_COMPONENT = "session-buddy"


def _build_capabilities(settings: Any) -> list[str]:
    """Derive capability tags from the loaded SB configuration.

    Returns a list of ``"subsystem:detail"`` tags that Oneiric's
    health/registry feeds surface. Tags are deterministic so the
    contract is testable — no random ordering, no set-vs-list drift.
    """
    capabilities: list[str] = [
        f"llm:{settings.llm.default_provider}",
        f"llm:ollama_url:{settings.llm.ollama_base_url}",
        f"llm:ollama_model:{settings.llm.ollama_default_model}",
    ]
    for provider in settings.llm.fallback_providers or ():
        capabilities.append(f"llm:fallback:{provider}")
    capabilities.append("storage:duckdb")
    if settings.bodai_events.enabled:
        capabilities.append("events:bodai_events")
        capabilities.append(
            f"events:bodai_stream:{settings.bodai_events.stream}",
        )
        capabilities.append(
            f"events:bodai_group:{settings.bodai_events.consumer_group}",
        )
    capabilities.append(f"http:{settings.http_port}")
    capabilities.append(f"ws:{settings.websocket_port}")
    return capabilities


def _build_runtime_facts(settings: Any) -> dict[str, Any]:
    """Assemble the runtime_facts payload mirrored on the Oneiric side.

    Matches the shape ``oneiric_report_runtime`` expects under
    ``arguments.runtime_facts``. ``generated_at_unix`` lets the Oneiric
    aggregator distinguish duplicate pushes (the reconfigure watcher in
    Mahavishnu uses this; SB pushes once at boot so the value is
    informational, not load-bearing).
    """
    import time

    return {
        "enabled": True,
        "features": _build_capabilities(settings),
        "type": "service",
        "source": "session_buddy.mcp.oneiric_runtime",
        "generated_at_unix": time.time(),
        "config": {
            "llm": {
                "default_provider": settings.llm.default_provider,
                "fallback_providers": list(
                    settings.llm.fallback_providers or (),
                ),
                "ollama_base_url": settings.llm.ollama_base_url,
                "ollama_default_model": settings.llm.ollama_default_model,
            },
            "storage": {"backend": "duckdb"},
            "bodai_events": {
                "enabled": settings.bodai_events.enabled,
                "stream": settings.bodai_events.stream,
                "consumer_group": settings.bodai_events.consumer_group,
            },
            "network": {
                "http_port": settings.http_port,
                "websocket_port": settings.websocket_port,
            },
        },
    }


async def report_runtime_to_oneiric() -> None:
    """Snapshot SB config and push a single fact to Oneiric.

    No-op (logged) if Oneiric is unreachable. Mirrors the
    ``_register_component_to_dhara`` fail-soft pattern at
    ``server_optimized.py:320-323`` so a Oneiric outage cannot block
    SB's MCP handshake.
    """
    status = "fail"
    try:
        from session_buddy.settings import get_settings

        settings = get_settings()
        runtime_facts = _build_runtime_facts(settings)
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": "oneiric_report_runtime",
                "arguments": {
                    "domain": DOMAIN,
                    "key": FACT_KEY,
                    "provider": FACT_KEY,
                    "runtime_facts": runtime_facts,
                    "caller_component": CALLER_COMPONENT,
                },
            },
        }
        async with httpx.AsyncClient(
            timeout=ONEIRIC_PUSH_TIMEOUT_SECONDS,
        ) as client:
            response = await client.post(
                f"{ONEIRIC_BASE_URL}/mcp",
                json=payload,
            )
            response.raise_for_status()
        status = "ok"
    except Exception as exc:  # noqa: BLE001 - push failure must never block boot
        logger.warning(
            f"runtime-push component={CALLER_COMPONENT} "
            f"adapter={FACT_KEY} status={status} error={exc!s}",
        )
        return
    logger.info(
        f"runtime-push component={CALLER_COMPONENT} "
        f"adapter={FACT_KEY} status={status}",
    )
