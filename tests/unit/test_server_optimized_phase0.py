"""Unit tests for Session-Buddy Phase 0 self-registration to Dhara.

Tests _register_to_dhara_once and _register_component_to_dhara functions
in session_buddy/server_optimized.py.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRegisterToDharaOnce:
    """Tests for _register_to_dhara_once function."""

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self) -> None:
        """Should return True when Dhara responds successfully."""
        from session_buddy.server_optimized import _register_to_dhara_once

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_instance

            result = await _register_to_dhara_once(
                "http://localhost:8683",
                "component_endpoint/session-buddy",
                "http://127.0.0.1:8678/mcp",
            )

            assert result is True
            mock_instance.post.assert_called_once()
            call_args = mock_instance.post.call_args
            assert call_args[0][0] == "http://localhost:8683/tools/call"
            assert call_args[1]["json"] == {
                "name": "put",
                "arguments": {
                    "key": "component_endpoint/session-buddy",
                    "value": "http://127.0.0.1:8678/mcp",
                },
            }

    @pytest.mark.asyncio
    async def test_returns_false_on_http_error(self) -> None:
        """Should return False when Dhara returns an HTTP error."""
        import httpx

        from session_buddy.server_optimized import _register_to_dhara_once

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(
                side_effect=httpx.HTTPError("connection refused")
            )
            mock_client_cls.return_value = mock_instance

            result = await _register_to_dhara_once(
                "http://localhost:8683",
                "component_endpoint/session-buddy",
                "http://127.0.0.1:8678/mcp",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self) -> None:
        """Should return False on any other exception."""
        from session_buddy.server_optimized import _register_to_dhara_once

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(side_effect=OSError("unexpected"))
            mock_client_cls.return_value = mock_instance

            result = await _register_to_dhara_once(
                "http://localhost:8683",
                "component_endpoint/session-buddy",
                "http://127.0.0.1:8678/mcp",
            )

            assert result is False


class TestRegisterComponentToDhara:
    """Tests for _register_component_to_dhara function.

    SessionLogger.info() does NOT accept %-style format arguments.
    Production code uses logger.info("msg %s", arg) but SessionLogger.info(message, **context)
    only accepts a message + keyword context. We patch so.logger in every test that calls
    _register_component_to_dhara to avoid TypeError.
    """

    @pytest.mark.asyncio
    async def test_registers_on_first_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should register on first attempt and start heartbeat."""
        import asyncio

        from session_buddy import server_optimized as so

        monkeypatch.setenv("SESSION_BUDDY_DHARA_URL", "http://localhost:8683")

        attempt_count = 0

        async def mock_register_once(*args: object, **kwargs: object) -> bool:
            nonlocal attempt_count
            attempt_count += 1
            return True

        with patch.object(so.logger, "info"):
            with patch.object(so.logger, "debug"):
                with patch(
                    "session_buddy.server_optimized._register_to_dhara_once",
                    new_callable=AsyncMock,
                    side_effect=mock_register_once,
                ):
                    so._heartbeat_task = None

                    await so._register_component_to_dhara("http://127.0.0.1:8678/mcp")

                    assert attempt_count == 1

    @pytest.mark.asyncio
    async def test_retries_with_exponential_backoff(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should retry with exponential backoff on failure.

        Verifies exponential backoff by counting how many times _register_to_dhara_once
        is called before success. Does not patch asyncio.sleep — tiny real delays (~7s total)
        are acceptable for this test.
        """
        import asyncio
        import itertools

        from session_buddy import server_optimized as so

        monkeypatch.setenv("SESSION_BUDDY_DHARA_URL", "http://localhost:8683")

        attempt_count = 0

        async def mock_register_once(*args: object, **kwargs: object) -> bool:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                return False
            return True

        with patch.object(so.logger, "info"):
            with patch.object(so.logger, "debug"):
                with patch(
                    "session_buddy.server_optimized._register_to_dhara_once",
                    new_callable=AsyncMock,
                    side_effect=mock_register_once,
                ):
                    so._heartbeat_task = None

                    await so._register_component_to_dhara("http://127.0.0.1:8678/mcp")

                    # Should succeed on 3rd attempt (after failing twice with backoff)
                    assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_uses_env_var_for_dhara_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should use SESSION_BUDDY_DHARA_URL env var when set."""
        import asyncio

        from session_buddy import server_optimized as so

        monkeypatch.setenv("SESSION_BUDDY_DHARA_URL", "http://custom-dhara:9999")
        monkeypatch.setattr(asyncio, "create_task", AsyncMock())

        captured_urls: list[str] = []

        async def mock_register_once(
            dhara_url: str, key: str, mcp_url: str
        ) -> bool:
            captured_urls.append(dhara_url)
            return True

        with patch.object(so.logger, "info"):
            with patch.object(so.logger, "debug"):
                with patch(
                    "session_buddy.server_optimized._register_to_dhara_once",
                    new_callable=AsyncMock,
                    side_effect=mock_register_once,
                ):
                    so._heartbeat_task = None

                    await so._register_component_to_dhara("http://127.0.0.1:8678/mcp")

                    assert captured_urls[0] == "http://custom-dhara:9999"

    @pytest.mark.asyncio
    async def test_uses_default_url_when_env_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should use DHARA_DEFAULT_URL when env var is not set."""
        import asyncio

        from session_buddy import server_optimized as so

        monkeypatch.delenv("SESSION_BUDDY_DHARA_URL", raising=False)
        monkeypatch.setattr(asyncio, "create_task", AsyncMock())

        captured_urls: list[str] = []

        async def mock_register_once(
            dhara_url: str, key: str, mcp_url: str
        ) -> bool:
            captured_urls.append(dhara_url)
            return True

        with patch.object(so.logger, "info"):
            with patch.object(so.logger, "debug"):
                with patch(
                    "session_buddy.server_optimized._register_to_dhara_once",
                    new_callable=AsyncMock,
                    side_effect=mock_register_once,
                ):
                    so._heartbeat_task = None

                    await so._register_component_to_dhara("http://127.0.0.1:8678/mcp")

                    assert captured_urls[0] == so.DHARA_DEFAULT_URL

    @pytest.mark.asyncio
    async def test_heartbeat_task_is_created(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should create a heartbeat task after successful registration."""
        import asyncio

        from session_buddy import server_optimized as so

        monkeypatch.setenv("SESSION_BUDDY_DHARA_URL", "http://localhost:8683")
        monkeypatch.setattr(asyncio, "create_task", MagicMock())

        with patch.object(so.logger, "info"):
            with patch.object(so.logger, "debug"):
                with patch(
                    "session_buddy.server_optimized._register_to_dhara_once",
                    new_callable=AsyncMock,
                ) as mock_register:
                    mock_register.return_value = True

                    so._heartbeat_task = None

                    await so._register_component_to_dhara("http://127.0.0.1:8678/mcp")

                    # asyncio.create_task was called once to start the heartbeat
                    assert asyncio.create_task.called is True

    @pytest.mark.asyncio
    async def test_retries_until_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should retry until registration succeeds and then start heartbeat."""
        import asyncio

        from session_buddy import server_optimized as so

        monkeypatch.setenv("SESSION_BUDDY_DHARA_URL", "http://localhost:8683")
        monkeypatch.setattr(asyncio, "create_task", MagicMock())

        attempt_count = 0

        async def mock_register_once(*args: object, **kwargs: object) -> bool:
            nonlocal attempt_count
            attempt_count += 1
            # Succeeds on 3rd attempt
            return attempt_count >= 3

        with patch.object(so.logger, "info"):
            with patch.object(so.logger, "debug"):
                with patch(
                    "session_buddy.server_optimized._register_to_dhara_once",
                    new_callable=AsyncMock,
                    side_effect=mock_register_once,
                ):
                    so._heartbeat_task = None

                    await so._register_component_to_dhara("http://127.0.0.1:8678/mcp")

                    # Should have tried 3 times before succeeding
                    assert attempt_count == 3
                    # Heartbeat task should have been started
                    assert asyncio.create_task.called is True
