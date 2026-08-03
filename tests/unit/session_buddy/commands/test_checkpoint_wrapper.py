"""Test that the commands.checkpoint wrapper applies HookSingleFlight.

The wrapper forwards to the underlying ``_checkpoint_impl`` and
suppresses a second call within 5 seconds via :class:`HookSingleFlight`.

We patch the underlying implementation so the test does not touch the
real crackerjack/git subprocess chain.
"""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import patch

import pytest


@pytest.fixture
def wrapper_module():
    """Lazy import so test fails with a useful ImportError if renamed."""
    return importlib.import_module("session_buddy.commands.checkpoint")


@pytest.fixture
def fresh_flight(wrapper_module):
    """Reset the module-level HookSingleFlight between tests.

    The gate stores ``_last_seen`` keyed by ``(project_path, agent_idx)``.
    Without resetting, a prior test using the same key would suppress
    the first call here, hiding regressions.
    """
    wrapper_module._FLIGHT._last_seen.clear()
    return wrapper_module._FLIGHT


async def test_first_checkpoint_call_runs_body(
    wrapper_module, fresh_flight,
) -> None:
    calls = {"n": 0}

    async def fake_impl(working_directory):  # noqa: ARG001 - signature match
        calls["n"] += 1
        return "checkpoint-output"

    with patch(
        "session_buddy.commands.checkpoint._checkpoint_impl",
        new=fake_impl,
    ):
        result = await wrapper_module.checkpoint(
            project_path="/proj", agent_idx=1,
        )

    assert calls["n"] == 1
    assert result == "checkpoint-output"


async def test_second_within_ttl_is_coalesced(
    wrapper_module, fresh_flight,
) -> None:
    calls = {"n": 0}

    async def fake_impl(working_directory):  # noqa: ARG001 - signature match
        calls["n"] += 1
        return f"result-{calls['n']}"

    with patch(
        "session_buddy.commands.checkpoint._checkpoint_impl",
        new=fake_impl,
    ):
        first = await wrapper_module.checkpoint(
            project_path="/proj", agent_idx=1,
        )
        second = await wrapper_module.checkpoint(
            project_path="/proj", agent_idx=1,
        )

    assert first == "result-1"
    assert second == "coalesced"
    assert calls["n"] == 1


async def test_distinct_agent_keys_dont_coalesce(
    wrapper_module, fresh_flight,
) -> None:
    calls = {"n": 0}

    async def fake_impl(working_directory):  # noqa: ARG001 - signature match
        calls["n"] += 1
        return "x"

    with patch(
        "session_buddy.commands.checkpoint._checkpoint_impl",
        new=fake_impl,
    ):
        first = await wrapper_module.checkpoint(
            project_path="/proj", agent_idx=1,
        )
        second = await wrapper_module.checkpoint(
            project_path="/proj", agent_idx=2,
        )

    assert calls["n"] == 2
    assert first == "x"
    assert second == "x"


async def test_distinct_project_paths_dont_coalesce(
    wrapper_module, fresh_flight,
) -> None:
    calls = {"n": 0}

    async def fake_impl(working_directory):  # noqa: ARG001 - signature match
        calls["n"] += 1
        return f"for-{working_directory}"

    with patch(
        "session_buddy.commands.checkpoint._checkpoint_impl",
        new=fake_impl,
    ):
        await wrapper_module.checkpoint(
            project_path="/proj-a", agent_idx=1,
        )
        await wrapper_module.checkpoint(
            project_path="/proj-b", agent_idx=1,
        )

    assert calls["n"] == 2


async def test_gate_disabled_via_env(
    wrapper_module, fresh_flight, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_BUDDY_HOOK_SINGLE_FLIGHT", "false")
    # Reload module so _GATE_ENABLED picks up the env var.
    reloaded = importlib.reload(wrapper_module)
    reloaded._FLIGHT._last_seen.clear()

    calls = {"n": 0}

    async def fake_impl(working_directory):  # noqa: ARG001
        calls["n"] += 1
        return "x"

    with patch(
        "session_buddy.commands.checkpoint._checkpoint_impl",
        new=fake_impl,
    ):
        first = await reloaded.checkpoint(
            project_path="/proj", agent_idx=1,
        )
        second = await reloaded.checkpoint(
            project_path="/proj", agent_idx=1,
        )

    assert calls["n"] == 2
    assert first == "x"
    assert second == "x"


async def test_second_after_ttl_runs_again(
    wrapper_module, fresh_flight,
) -> None:
    fresh_flight._ttl = 0.1
    calls = {"n": 0}

    async def fake_impl(working_directory):  # noqa: ARG001
        calls["n"] += 1
        return f"call-{calls['n']}"

    with patch(
        "session_buddy.commands.checkpoint._checkpoint_impl",
        new=fake_impl,
    ):
        first = await wrapper_module.checkpoint(
            project_path="/proj", agent_idx=1,
        )
        await asyncio.sleep(0.15)
        second = await wrapper_module.checkpoint(
            project_path="/proj", agent_idx=1,
        )

    assert calls["n"] == 2
    assert first == "call-1"
    assert second == "call-2"
