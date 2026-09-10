"""Phase 3 end-to-end integration test for ``session_buddy_get_agent``.

Per plan §5 Phase 3 task #2 and the exit criteria:

- The ``session_buddy_get_agent(name)`` MCP tool returns
  ``{success: True, metadata, body}`` where ``body == metadata.system_prompt``.
- The signature verifies against the server's pubkey manifest.
- ``content_hash`` matches the SHA-256 of the body bytes (round-trip
  integrity — guards the installer against drift).
- The B-4 path-traversal allowlist is enforced at the API boundary.
- Unknown names return the documented error envelope rather than raising.

This integration test complements ``test_list_agents_e2e.py``: that
one exercises the catalog-level listing; this one exercises the
per-agent round-trip via the wire signature verification step that
Phase 2's installer will perform before writing
``~/.claude/agents/session-buddy-<name>.md``.
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
    canonical_payload_for_signing,
    generate_keypair,
    verify_signature,
)

# ---------------------------------------------------------------------------
# Helpers (mirrors production wiring)
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
    """Return the registered tool callable by its public name."""
    tools = await app.list_tools()
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool.fn
    msg = (
        f"tool {name!r} not found; "
        f"registered: {[getattr(t, 'name', '?') for t in tools]}"
    )
    raise KeyError(msg)


# ---------------------------------------------------------------------------
# get_agent end-to-end: each of the 3 static agents
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetAgentE2E:
    """``session_buddy_get_agent`` returns signed metadata + body for each agent."""

    def setup_method(self) -> None:
        reset_signer_feed_state()

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        _install_state(None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_name",
        [entry["name"] for entry in _STATIC_AGENTS],
    )
    async def test_get_agent_returns_signed_metadata_and_body(
        self,
        agent_name: str,
    ) -> None:
        """Round-trip: get_agent returns signed metadata + the body file text."""
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_agent")
        result = await tool(agent_name)
        assert result["success"] is True
        meta = result["metadata"]
        body = result["body"]
        assert meta["server_key"] == "session_buddy"
        assert meta["name"] == agent_name
        assert meta["schema_version"] == 1
        # Signing fields are populated by ``_sign_metadata`` post-construction.
        assert meta["signature"] is not None
        assert meta["server_pubkey_id"] == state.signer.key_id
        # Body must be the full markdown (frontmatter + body) — Claude Code
        # reads the frontmatter at agent-invocation time.
        assert body.startswith("---\n"), (
            f"agent body for {agent_name!r} must start with YAML frontmatter"
        )
        # Per Phase 3 task #2: body == system_prompt
        assert body == meta["system_prompt"]
        # Body must have real content (≥200 chars per the brief).
        assert len(body) >= 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_name",
        [entry["name"] for entry in _STATIC_AGENTS],
    )
    async def test_get_agent_signature_verifies_against_manifest(
        self,
        agent_name: str,
    ) -> None:
        """The signature on the response verifies against the test manifest."""
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_agent")
        result = await tool(agent_name)
        assert result["success"] is True
        meta = result["metadata"]
        # Strip the signing fields before canonicalization so the signature
        # actually covers the payload it claims to (Phase 2 installer will
        # perform the same re-derivation).
        canonical = canonical_payload_for_signing(meta)
        manifest_entry = verify_signature(
            canonical,
            meta["signature"],
            meta["server_pubkey_id"],
            state.manifest,
        )
        assert manifest_entry.key_id == meta["server_pubkey_id"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_name",
        [entry["name"] for entry in _STATIC_AGENTS],
    )
    async def test_get_agent_content_hash_matches_body(
        self,
        agent_name: str,
    ) -> None:
        """``content_hash`` is the sha256 of ``system_prompt`` / body bytes.

        Per Phase 3 task #2 the body field IS the system_prompt; the
        content_hash field is the sha256 of those bytes. The Phase 2
        installer re-derives the hash from the body it receives over the
        wire and asserts it matches metadata.content_hash before writing
        to ``~/.claude/agents/session-buddy-<name>.md``. This test guards
        the round-trip.
        """
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_agent")
        result = await tool(agent_name)
        assert result["success"] is True
        meta = result["metadata"]
        body = result["body"]
        expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert meta["content_hash"] == expected
        # And the system_prompt field gives the same hash (consistency
        # between the two representations of "the body").
        sys_prompt_hash = hashlib.sha256(
            meta["system_prompt"].encode("utf-8"),
        ).hexdigest()
        assert sys_prompt_hash == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_name",
        [entry["name"] for entry in _STATIC_AGENTS],
    )
    async def test_get_agent_metadata_validates_against_schema(
        self,
        agent_name: str,
    ) -> None:
        """The returned metadata must round-trip through AgentMetadata.model_validate."""
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_agent")
        result = await tool(agent_name)
        assert result["success"] is True
        meta = result["metadata"]
        # model_validate catches any schema drift (e.g. a field removed
        # from the model). AgentMetadata.model_validate re-runs all
        # field validators, including the B-4 allowlist on server_key
        # and name — so a forged metadata would fail here.
        AgentMetadata.model_validate(meta)

    @pytest.mark.asyncio
    async def test_get_agent_rejects_path_traversal(self) -> None:
        """B-4: forbidden ``name`` returns an error envelope, NOT a raise.

        Defense-in-depth: the API boundary checks ``name`` BEFORE
        constructing the metadata model, so a path-traversal payload
        (e.g. ``../../etc/passwd``) returns a uniform error envelope
        rather than surfacing a ValidationError past the MCP boundary.
        """
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_agent")
        for bad_name in [
            "../../etc/passwd",
            "FOO",
            "foo/bar",
            ".hidden",
            "a..b",
            "a" * 64,
            "",
        ]:
            result = await tool(bad_name)
            assert result["success"] is False, (
                f"expected rejection for {bad_name!r}, got {result}"
            )
            assert "allowlist" in result["error"], (
                f"unexpected error for {bad_name!r}: {result['error']}"
            )

    @pytest.mark.asyncio
    async def test_get_agent_unknown_returns_error_envelope(self) -> None:
        """An unknown (allowlisted) name returns an error envelope, NOT a raise."""
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_agent")
        result = await tool("nonexistent-agent")
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_agent_without_signer_returns_error(self) -> None:
        """Pre-lifespan: get_agent surfaces the 'not initialized' envelope.

        The W0 helper at MINIMAL/STANDARD tiers always wires the
        signer lifespan, but in a no-lifespan regression test the tool
        must NOT raise past the MCP boundary — it returns the
        documented error envelope so the picker can surface the
        degraded mode to the user.
        """
        _install_state(None)  # simulate pre-lifespan
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_agent")
        result = await tool(_STATIC_AGENTS[0]["name"])
        assert result["success"] is False
        assert "not initialized" in result["error"]

    @pytest.mark.asyncio
    async def test_get_agent_bumps_cycle_counter(self) -> None:
        """B-7: each successful call bumps ``SignerFeedState.cycles_total``."""
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_agent")
        before = state.cycles_total
        result = await tool(_STATIC_AGENTS[0]["name"])
        assert result["success"] is True
        assert state.cycles_total == before + 1
