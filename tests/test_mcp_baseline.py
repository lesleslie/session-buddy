"""Per-repo baseline-surface gate for Session-Buddy.

Phase 3 of ``docs/plans/2026-08-20-bodai-mcp-surface-standardization.md``
adds a Session-Buddy-specific test that runs in Session-Buddy's own
CI. It asserts that Session-Buddy's MCP server exposes the 4 Bodai
baseline tools (``discover_tools``, ``get_liveness``, ``get_readiness``,
``health_check_all``) plus the deprecated ``ping`` alias preserved for
the 3 confirmed callers (Akosha, Mahavishnu, Crackerjack) until the
next release.

The helper is provided by ``mcp_common.testing.baseline_surface``,
which is pinned to the Phase 1 commit on the
``feat/bodai-mcp-baseline-tools`` branch of mcp-common (see the
``pyproject.toml`` dependency). The test is marked
``@pytest.mark.integration`` so it only runs when Session-Buddy's
local server is reachable.
"""

from __future__ import annotations

import pytest
from mcp_common.testing.baseline_surface import assert_baseline_surface

SESSION_BUDDY_MCP_URL = "http://localhost:8678/mcp"


@pytest.mark.integration
async def test_session_buddy_baseline_surface() -> None:
    """Session-Buddy exposes the 4 Bodai baseline tools + ping alias."""
    tool_names = await assert_baseline_surface(SESSION_BUDDY_MCP_URL)

    expected = {"discover_tools", "get_liveness", "get_readiness", "health_check_all"}
    missing = expected - set(tool_names)
    assert not missing, (
        f"Session-Buddy missing baseline tools {sorted(missing)}; "
        f"got {sorted(tool_names)}"
    )

    # The ``ping`` tool is intentionally preserved as a deprecated alias
    # for the 3 confirmed consumers (Akosha, Mahavishnu, Crackerjack)
    # until the next release. Removing it without a migration window
    # would break those callers.
    assert "ping" in set(tool_names), (
        "ping should remain as deprecated alias until next release "
        "(see Phase 2 exit criteria in the standardization plan)"
    )
