"""Tests for session_buddy.utils.crackerjack.fallback."""

from __future__ import annotations

import asyncio

import pytest

from session_buddy.config import feature_flags
from session_buddy.config.feature_flags import FeatureFlags
from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli


def _enable_flag(monkeypatch, enable: bool = True):
    """Patch get_feature_flags to return a FeatureFlags with the requested value."""
    monkeypatch.setattr(
        feature_flags,
        "get_feature_flags",
        lambda: FeatureFlags(enable_crackerjack_fallback=enable),
    )


@pytest.mark.asyncio
async def test_disabled_flag_returns_none(monkeypatch, tmp_path):
    """When enable_crackerjack_fallback is False, helper returns None without invoking subprocess."""
    _enable_flag(monkeypatch, enable=False)

    spawn_called = False

    async def fake_spawn(*args, **kwargs):
        nonlocal spawn_called
        spawn_called = True
        raise AssertionError("subprocess should not have been spawned")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    result = await try_crackerjack_cli(
        project_dir=tmp_path,
        missing_metrics=frozenset({"lint_score"}),
    )
    assert result is None
    assert spawn_called is False
