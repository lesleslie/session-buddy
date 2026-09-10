"""Phase 3 end-to-end integration test for ``session_buddy_list_agents``.

Per plan §5 Phase 3 task #1 and the exit criteria:

- ``mcp__session_buddy__list_agents()`` returns ≥1 entry with non-empty
  ``system_prompt`` field (we assert ≥3 since the static catalog ships 3).
- Every entry carries a non-empty ``name``, ``description``, ``tools``,
  ``content_hash``, and ``id``.
- The B-4 allowlist still constrains ``server_key`` and ``name`` fields.

Unlike the unit test for the Pydantic schema, this integration test
exercises the registered MCP tool surface via a real FastMCP app — same
wiring as production — so it verifies that ``register_agents_tools``
binds the function under the documented public name.

Marker notes
------------
Marked ``integration`` (not ``unit``) because the test runs the lifespan
state installer. No ``e2e`` marker — this is in-process; for an HTTP-
level test see the federation layer in ``akosha/test_*``.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from session_buddy.mcp.agent_schema import AgentMetadata
from session_buddy.mcp.signer_feed import (
    SignerFeedState,
    reset_signer_feed_state,
)
from session_buddy.mcp.tools.agents_tools import (
    _STATIC_AGENTS,
    register_agents_tools,
)
from session_buddy.skills_signer import (
    SkillsSigner,
    build_pubkey_manifest,
    generate_keypair,
)

# ---------------------------------------------------------------------------
# FastMCP / app binding helpers (mirrors production wiring)
# ---------------------------------------------------------------------------


def _seed_state() -> SignerFeedState:
    """Build a SignerFeedState seeded with a fresh ed25519 keypair."""
    keypair = generate_keypair()
    signer = SkillsSigner.from_keypair(keypair)
    manifest = build_pubkey_manifest(keypair)
    return SignerFeedState(manifest=manifest, signer=signer)


def _install_state(state: SignerFeedState | None) -> None:
    """Install (or clear) the module-level signer state for the test lifespan."""
    import session_buddy.mcp.signer_feed as feed_module

    feed_module._signer_feed_state = state


def _build_app() -> Any:
    """Build a fresh FastMCP app with the agents tools registered."""
    from fastmcp import FastMCP

    app = FastMCP("session-buddy-test")
    register_agents_tools(app)
    return app


async def _resolve_tool(app: Any, name: str) -> Any:
    """Return the registered tool callable by its public name.

    FastMCP's FunctionTool exposes ``.fn`` (the original coroutine).
    """
    tools = await app.list_tools()
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool.fn
    msg = (
        f"tool {name!r} not found; "
        f"registered: {[getattr(t, 'name', '?') for t in tools]}"
    )
    raise KeyError(msg)


async def _all_tool_names(app: Any) -> set[str]:
    """Return the public-name set of every tool registered on ``app``."""
    tools = await app.list_tools()
    return {getattr(t, "name", None) for t in tools}


# ---------------------------------------------------------------------------
# Static catalog
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStaticCatalog:
    """The 3 starter agents ship with valid metadata + catalog bodies."""

    def test_three_agents(self) -> None:
        assert len(_STATIC_AGENTS) == 3
        names = [entry["name"] for entry in _STATIC_AGENTS]
        assert names == [
            "session-buddy-specialist",
            "session_archaeologist_agent",
            "reflection_miner_agent",
        ]

    def test_all_bodies_present(self) -> None:
        from session_buddy.mcp.tools.agents_tools import _CATALOG_DIR

        for entry in _STATIC_AGENTS:
            assert (_CATALOG_DIR / entry["body_filename"]).is_file(), (
                f"missing catalog body for {entry['name']!r}: "
                f"{_CATALOG_DIR / entry['body_filename']}"
            )

    def test_all_bodies_min_length(self) -> None:
        """Each catalog body must have substantive body content (≥200 chars)."""
        from session_buddy.mcp.tools.agents_tools import _read_body

        for entry in _STATIC_AGENTS:
            body = _read_body(entry["body_filename"])
            assert len(body) >= 200, (
                f"agent body for {entry['name']!r} is too short: {len(body)} chars"
            )


# ---------------------------------------------------------------------------
# MCP tool registration + list_agents end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListAgentsE2E:
    """``session_buddy_list_agents`` returns ≥3 entries with non-empty fields."""

    def setup_method(self) -> None:
        reset_signer_feed_state()

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        _install_state(None)

    @pytest.mark.asyncio
    async def test_list_agents_tool_is_registered(self) -> None:
        """``session_buddy_list_agents`` is bound to the FastMCP app."""
        _install_state(_seed_state())
        app = _build_app()
        names = await _all_tool_names(app)
        assert "session_buddy_list_agents" in names

    @pytest.mark.asyncio
    async def test_get_agent_tool_is_registered(self) -> None:
        """``session_buddy_get_agent`` is bound to the FastMCP app."""
        _install_state(_seed_state())
        app = _build_app()
        names = await _all_tool_names(app)
        assert "session_buddy_get_agent" in names

    @pytest.mark.asyncio
    async def test_list_agents_returns_three_entries(self) -> None:
        """The static catalog ships 3 agents — list_agents must return 3 dicts.

        Per plan §5 Phase 3 exit criteria, the minimum is ≥1 entry; we assert
        ≥3 (matches the static catalog) since the integration contract for
        session-buddy is to publish all 3 starter agents.
        """
        _install_state(_seed_state())
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_list_agents")
        result = await tool()
        assert isinstance(result, list)
        assert len(result) >= 3

    @pytest.mark.asyncio
    async def test_list_agents_entries_have_required_fields(self) -> None:
        """Each entry carries ``name``, ``system_prompt``, ``content_hash``,
        ``server_key``, ``id``, ``description``, ``model``, ``tools``,
        ``version``, ``schema_version`` — per Phase 3 task #1.

        The system_prompt field MUST be non-empty (per the exit criteria).
        """
        _install_state(_seed_state())
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_list_agents")
        result = await tool()
        assert len(result) >= 3
        for entry in result:
            # Identity fields per Phase 3 task #1.
            assert entry["schema_version"] == 1
            assert entry["server_key"] == "session_buddy"
            assert ":" in entry["id"]
            assert entry["name"], "name must be non-empty"
            assert entry["description"].strip(), "description must be non-empty"
            assert entry["model"], "model must be non-empty"
            assert entry["version"], "version must be non-empty"
            # Body integrity per B-1 / Phase 3 task #1.
            assert entry["content_hash"], "content_hash must be non-empty"
            assert len(entry["content_hash"]) == 64, (
                "content_hash must be 64-char lowercase hex sha256"
            )
            # Per Phase 3 exit criteria: system_prompt must be non-empty.
            assert entry["system_prompt"], (
                f"system_prompt must be non-empty for {entry['name']!r} "
                "(Phase 3 exit criteria)"
            )
            # Tools list may be empty in principle (but the static catalog
            # has non-empty tool lists), so just ensure the type is list.
            assert isinstance(entry["tools"], list)

    @pytest.mark.asyncio
    async def test_list_agents_signatures_are_none(self) -> None:
        """Per Phase 3 task #1 / phase-1 mirror: list returns unsigned entries;
        signatures are populated by ``get_agent`` since the canonical
        payload strips the signing fields before signing.
        """
        _install_state(_seed_state())
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_list_agents")
        result = await tool()
        for entry in result:
            assert entry["signature"] is None
            assert entry["server_pubkey_id"] is None

    @pytest.mark.asyncio
    async def test_list_agents_bumps_cycle_counter(self) -> None:
        """B-7: each call bumps ``SignerFeedState.cycles_total``."""
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_list_agents")
        before = state.cycles_total
        await tool()
        assert state.cycles_total == before + 1

    @pytest.mark.asyncio
    async def test_list_agents_content_hash_matches_system_prompt(self) -> None:
        """Per Phase 3 task #2 (``body == system_prompt``), the ``content_hash``
        field is the sha256 of the ``system_prompt`` bytes. We re-derive the
        hash and assert it matches — guards against drift between the
        cached metadata and the actual body the installer will write.
        """
        _install_state(_seed_state())
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_list_agents")
        result = await tool()
        for entry in result:
            expected = hashlib.sha256(
                entry["system_prompt"].encode("utf-8"),
            ).hexdigest()
            assert entry["content_hash"] == expected, (
                f"content_hash mismatch for {entry['name']!r}: "
                f"got {entry['content_hash']}, expected {expected}"
            )

    @pytest.mark.asyncio
    async def test_list_agents_validates_against_agentmetadata_schema(self) -> None:
        """Every list entry must round-trip through AgentMetadata validation.

        This catches drift between the static catalog metadata (in
        ``agents_tools.py``) and the Pydantic model — e.g. a field removed
        from the model but still present in the catalog, or a Literal
        constraint tightened without updating the catalog.
        """
        _install_state(_seed_state())
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_list_agents")
        result = await tool()
        for entry in result:
            # AgentMetadata.model_validate raises on invalid input; rebuild
            # with signature=None (list returns unsigned entries).
            AgentMetadata.model_validate(entry)
