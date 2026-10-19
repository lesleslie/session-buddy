"""Integration test: Session-Buddy pushes runtime facts to Oneiric (Phase 3).

Three scenarios, each guarded by ``_oneiric_reachable()`` so the test
suite skips cleanly when the Oneiric MCP HTTP endpoint is offline:

* ``test_session_buddy_boot_pushes_runtime_to_oneiric`` — call the
  helper directly, then poll Oneiric for the single ``session_buddy /
  __main__`` fact and assert the runtime block carries the expected
  capability tags + config snapshot.

* ``test_session_buddy_no_oneiric_imports`` — grep the new files for
  ``from oneiric|import oneiric`` and assert zero hits. Pins the
  httpx-only contract so a future refactor cannot silently re-introduce
  the resolver chain Phase 1/2 spent effort decoupling.

* ``test_session_buddy_fail_soft_on_push_failure`` — mock httpx to
  raise a network error, call the helper, assert it returns cleanly
  without raising. Pins the contract that Oneiric unavailability MUST
  NOT block SB boot.

All three skip cleanly when Oneiric's MCP HTTP endpoint is not
reachable on ``127.0.0.1:8681`` (guards unit CI). Marked with
``@pytest.mark.integration`` AND ``@pytest.mark.slow`` per project
conventions. asyncio_mode is ``auto`` per project pyproject, so no
``@pytest.mark.asyncio`` decorator.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

ONEIRIC_BASE_URL = "http://127.0.0.1:8681"
ONEIRIC_HEALTH_TIMEOUT_SECONDS = 5.0
PUSH_PROPAGATION_TIMEOUT_SECONDS = 30.0
PUSH_POLL_INTERVAL_SECONDS = 1.0

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = REPO_ROOT / "session_buddy" / "mcp" / "oneiric_runtime.py"
SERVER_OPTIMIZED_PATH = REPO_ROOT / "session_buddy" / "server_optimized.py"

EXPECTED_KEY = "__main__"
EXPECTED_DOMAIN = "session_buddy"
EXPECTED_CALLER = "session-buddy"


def _oneiric_reachable(
    timeout_seconds: float = ONEIRIC_HEALTH_TIMEOUT_SECONDS,
) -> bool:
    """Probe the Oneiric MCP HTTP endpoint via a JSON-RPC tools/list call."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = httpx.post(
                f"{ONEIRIC_BASE_URL}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "method": "tools/list",
                    "params": {},
                },
                timeout=2.0,
            )
            if response.status_code == 200:
                return True
        except (httpx.RequestError, httpx.TimeoutException):
            time.sleep(0.5)
    return False


def _fetch_runtime_block(*, domain: str, key: str, provider: str) -> dict[str, Any] | None:
    """Call ``oneiric_get_adapter_health`` via JSON-RPC; return runtime block."""
    try:
        response = httpx.post(
            f"{ONEIRIC_BASE_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": "oneiric_get_adapter_health",
                    "arguments": {
                        "domain": domain,
                        "key": key,
                        "provider": provider,
                    },
                },
            },
            timeout=5.0,
        )
        response.raise_for_status()
    except (httpx.RequestError, httpx.TimeoutException):
        return None
    envelope: dict[str, Any] = response.json()
    result: dict[str, Any] = envelope.get("result") or {}
    runtime: dict[str, Any] | None = result.get("runtime")
    return runtime if isinstance(runtime, dict) else None


async def test_session_buddy_boot_pushes_runtime_to_oneiric() -> None:
    """After ``report_runtime_to_oneiric``, Oneiric sees the SB fact.

    SB has no per-adapter enum, so the single fact is keyed
    ``session_buddy / __main__``. We assert the runtime block carries
    the canonical capability tags and the expected source tag.
    """
    if not _oneiric_reachable():
        pytest.skip("Oneiric MCP HTTP endpoint unreachable on 127.0.0.1:8681")

    from session_buddy.mcp.oneiric_runtime import report_runtime_to_oneiric
    from session_buddy.settings import get_settings

    settings = get_settings()
    await report_runtime_to_oneiric()

    deadline = time.monotonic() + PUSH_PROPAGATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        runtime = _fetch_runtime_block(
            domain=EXPECTED_DOMAIN, key=EXPECTED_KEY, provider=EXPECTED_KEY,
        )
        if runtime is not None:
            features = runtime.get("features") or []
            assert "enabled" in runtime, "runtime block missing 'enabled'"
            assert isinstance(features, list) and features, (
                f"features empty in runtime block: {runtime}"
            )
            assert runtime.get("source") == "session_buddy.mcp.oneiric_runtime", (
                f"runtime source tag mismatch: {runtime.get('source')!r}"
            )
            expected_llm_tag = f"llm:{settings.llm.default_provider}"
            assert expected_llm_tag in features, (
                f"missing capability tag {expected_llm_tag!r} in {features!r}"
            )
            assert "storage:duckdb" in features, (
                f"missing storage:duckdb tag in {features!r}"
            )
            assert f"http:{settings.http_port}" in features, (
                f"missing http:{settings.http_port} tag in {features!r}"
            )
            assert f"ws:{settings.websocket_port}" in features, (
                f"missing ws:{settings.websocket_port} tag in {features!r}"
            )
            config = runtime.get("config") or {}
            llm_config = config.get("llm") or {}
            assert llm_config.get("default_provider") == settings.llm.default_provider
            return
        await asyncio.sleep(PUSH_POLL_INTERVAL_SECONDS)

    pytest.fail(
        f"Oneiric did not reflect {EXPECTED_DOMAIN}/{EXPECTED_KEY} fact within "
        f"{PUSH_PROPAGATION_TIMEOUT_SECONDS}s",
    )


def test_session_buddy_no_oneiric_imports() -> None:
    """New helper MUST NOT import oneiric directly.

    Phase 1/2 spent effort decoupling the runtime-fact push from the
    oneiric resolver chain. This test pins the httpx-only contract for
    the new helper. We intentionally do NOT scan
    ``server_optimized.py`` here — that file pre-exists with a
    legitimate ``from oneiric.core.logging`` import for the
    logging-infrastructure surface, which is unrelated to the
    runtime-fact push and is pure-additive protected.
    """
    assert HELPER_PATH.exists(), f"expected {HELPER_PATH} to exist"
    text = HELPER_PATH.read_text(encoding="utf-8")
    forbidden = ("from oneiric", "import oneiric")
    hits = [line for line in text.splitlines() if any(f in line for f in forbidden)]
    assert not hits, (
        f"file={HELPER_PATH} must not import oneiric directly; "
        f"found hits={hits!r}"
    )


async def test_session_buddy_fail_soft_on_push_failure() -> None:
    """Helper MUST swallow httpx failures and return None (no raise).

    Oneiric unavailability MUST NOT block SB boot. We patch
    ``httpx.AsyncClient.post`` to raise and assert the helper exits
    cleanly.
    """
    from session_buddy.mcp.oneiric_runtime import report_runtime_to_oneiric

    with patch(
        "session_buddy.mcp.oneiric_runtime.httpx.AsyncClient",
        autospec=True,
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("simulated oneiric outage"),
        )
        result = await report_runtime_to_oneiric()
    assert result is None, (
        f"helper must return None on push failure; got {result!r}"
    )
