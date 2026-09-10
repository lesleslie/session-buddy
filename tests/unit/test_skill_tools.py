"""Unit tests for the Phase 1 server-published skills tools.

Covers:
- static catalog integrity (3 starter skills with valid metadata)
- B-4 path-traversal allowlist at the API boundary
- signature verification round-trip on ``get_skill`` response
- H-6 collision: the previous ``list_skills`` MCP tool name is now
  ``session_buddy_list_workflow_patterns`` (renamed in commit H-6)
  while the bare ``list_skills`` name is reclaimed by
  ``session_buddy_list_skills`` for the new packaging-metadata shape

These tests do NOT spin up the MCP server — they exercise
``register_skill_tools`` against a real FastMCP app so the
``@app.tool(name=...)`` decorators bind the public surface exactly
as the production wiring does, then call the registered functions
directly.
"""

from __future__ import annotations

from typing import Any

import pytest

from session_buddy.mcp.signer_feed import (
    SignerFeedState,
    reset_signer_feed_state,
)
from session_buddy.mcp.skill_schema import SkillMetadata
from session_buddy.mcp.tools.skill_tools import (
    _CATALOG_DIR,
    _STATIC_SKILLS,
    _STATIC_SKILLS_BY_NAME,
    _build_unsigned_metadata,
    _is_allowlisted,
    _read_body,
    _sign_metadata,
    register_skill_tools,
)
from session_buddy.skills_signer import (
    SkillsSigner,
    build_pubkey_manifest,
    canonical_payload_for_signing,
    generate_keypair,
    verify_signature,
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
    """Build a fresh FastMCP app with the skill tools registered."""
    from fastmcp import FastMCP

    app = FastMCP("session-buddy-test")
    register_skill_tools(app)
    return app


async def _resolve_tool(app: Any, name: str) -> Any:
    """Return the registered tool callable by its public name.

    FastMCP's FunctionTool exposes ``.fn`` (the original coroutine).
    """
    tools = await app.list_tools()
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool.fn
    msg = f"tool {name!r} not found; registered: {[getattr(t, 'name', '?') for t in tools]}"
    raise KeyError(msg)


async def _all_tool_names(app: Any) -> set[str]:
    """Return the public-name set of every tool registered on ``app``."""
    tools = await app.list_tools()
    return {getattr(t, "name", None) for t in tools}


# ---------------------------------------------------------------------------
# Static catalog
# ---------------------------------------------------------------------------


class TestStaticCatalog:
    """The 3 starter skills ship with valid metadata + catalog bodies."""

    def test_three_skills(self) -> None:
        assert len(_STATIC_SKILLS) == 3
        names = [entry["name"] for entry in _STATIC_SKILLS]
        assert names == ["search-sessions", "code-archaeologist", "pattern-capture"]

    def test_all_bodies_present(self) -> None:
        for entry in _STATIC_SKILLS:
            assert (_CATALOG_DIR / entry["body_filename"]).is_file(), (
                f"missing catalog body for {entry['name']!r}: "
                f"{_CATALOG_DIR / entry['body_filename']}"
            )

    def test_server_name_is_session_buddy(self) -> None:
        """The H-6 reclaim uses the server-prefixed MCP tool name."""
        from session_buddy.mcp.tools.skill_tools import _SERVER_NAME

        assert _SERVER_NAME == "session_buddy"

    def test_build_unsigned_metadata_search_sessions(self) -> None:
        m = _build_unsigned_metadata("search-sessions")
        assert isinstance(m, SkillMetadata)
        assert m.server == "session_buddy"
        assert m.name == "search-sessions"
        assert m.version == "1.0.0"
        assert m.id == "session_buddy:search-sessions:1.0.0"
        assert m.content_type == "skill"
        assert m.signature is None
        assert m.server_pubkey_id is None
        # SHA-256 of the body matches the recorded content_hash
        body = _read_body("search-sessions.md")
        assert m.content_hash == _sha256_hex(body.encode("utf-8"))
        assert m.body_size == len(body.encode("utf-8"))

    def test_build_unsigned_metadata_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="unknown skill"):
            _build_unsigned_metadata("does-not-exist")

    def test_all_static_skills_build_metadata(self) -> None:
        """Every catalog entry round-trips through _build_unsigned_metadata."""
        for entry in _STATIC_SKILLS:
            m = _build_unsigned_metadata(entry["name"])
            assert m.tool_refs == entry["tool_refs"]
            assert m.allowed_tools == entry["allowed_tools"]
            assert m.dependencies == entry["dependencies"]

    def test_static_skills_by_name_index_complete(self) -> None:
        """The O(1) name index covers every entry in the static list."""
        assert set(_STATIC_SKILLS_BY_NAME) == {entry["name"] for entry in _STATIC_SKILLS}


# ---------------------------------------------------------------------------
# B-4 path-traversal allowlist at API boundary
# ---------------------------------------------------------------------------


class TestAllowlistBoundary:
    """Mirror ``SkillMetadata`` validation at the API boundary."""

    @pytest.mark.parametrize(
        "name",
        [
            "search-sessions",
            "code-archaeologist",
            "pattern-capture",
            "v1.2.3",
            "a",
            "a" + "b" * 62,
        ],
    )
    def test_accepted_names(self, name: str) -> None:
        assert _is_allowlisted(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "../../foo",
            "foo/bar",
            ".hidden",
            "FOO",
            "Foo",
            "foo bar",
            "foo!",
            "foo$bar",
            "foo|bar",
            "foo;bar",
            "foo&bar",
            "foo`bar`",
            "foo\nbar",
            "foo\rbar",
            "foo\tbar",
            "a..b",
            "",
            "a" * 64,
        ],
    )
    def test_rejected_names(self, name: str) -> None:
        assert _is_allowlisted(name) is False


# ---------------------------------------------------------------------------
# Signature round-trip
# ---------------------------------------------------------------------------


class TestSignatureRoundTrip:
    """``_sign_metadata`` produces a signature that verifies against the manifest."""

    def test_sign_then_verify(self) -> None:
        keypair = generate_keypair()
        signer = SkillsSigner.from_keypair(keypair)
        manifest = build_pubkey_manifest(keypair)
        assert not manifest.is_empty()

        m = _build_unsigned_metadata("search-sessions")
        signed = _sign_metadata(m, signer)
        assert signed.signature is not None
        assert signed.server_pubkey_id == keypair.key_id

        # Re-derive the canonical payload and verify against the manifest.
        payload_dict = signed.model_dump(mode="json")
        canonical = canonical_payload_for_signing(payload_dict)
        manifest_entry = verify_signature(
            canonical,
            signed.signature,
            signed.server_pubkey_id,
            manifest,
        )
        assert manifest_entry.key_id == keypair.key_id


# ---------------------------------------------------------------------------
# MCP tool registration + tool-name H-6 collision
# ---------------------------------------------------------------------------


class TestMCPToolRegistration:
    """``register_skill_tools`` binds the public surface correctly."""

    def setup_method(self) -> None:
        reset_signer_feed_state()

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        _install_state(None)

    @pytest.mark.asyncio
    async def test_both_tools_registered(self) -> None:
        _install_state(_seed_state())
        app = _build_app()
        names = await _all_tool_names(app)
        assert "session_buddy_list_skills" in names
        assert "session_buddy_get_skill" in names

    @pytest.mark.asyncio
    async def test_list_skills_returns_three_entries(self) -> None:
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_list_skills")
        result = await tool()
        assert isinstance(result, list)
        assert len(result) == 3
        for entry in result:
            assert entry["server"] == "session_buddy"
            assert entry["schema_version"] == 1
            # signatures are unsigned at list-time; get_skill adds them
            assert entry["signature"] is None
            assert entry["server_pubkey_id"] is None

    @pytest.mark.asyncio
    async def test_list_skills_bumps_cycle_counter(self) -> None:
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_list_skills")
        before = state.cycles_total
        await tool()
        assert state.cycles_total == before + 1

    @pytest.mark.asyncio
    async def test_get_skill_returns_signed_metadata_and_body(self) -> None:
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_skill")
        result = await tool("search-sessions")
        assert result["success"] is True
        meta = result["metadata"]
        assert meta["server"] == "session_buddy"
        assert meta["name"] == "search-sessions"
        assert meta["signature"] is not None
        assert meta["server_pubkey_id"] is not None
        # body has the YAML frontmatter
        assert result["body"].startswith("---\nname: search-sessions")

    @pytest.mark.asyncio
    async def test_get_skill_signature_verifies(self) -> None:
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_skill")
        result = await tool("code-archaeologist")
        assert result["success"] is True
        meta = result["metadata"]
        # The signer inside the test state must verify the response.
        canonical = canonical_payload_for_signing(meta)
        manifest_entry = verify_signature(
            canonical,
            meta["signature"],
            meta["server_pubkey_id"],
            state.manifest,
        )
        assert manifest_entry.key_id == meta["server_pubkey_id"]

    @pytest.mark.asyncio
    async def test_get_skill_rejects_path_traversal(self) -> None:
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_skill")
        for bad in ["../../foo", "FOO", "foo/bar", ".hidden"]:
            result = await tool(bad)
            assert result["success"] is False
            assert "allowlist" in result["error"]

    @pytest.mark.asyncio
    async def test_get_skill_unknown_returns_error_envelope(self) -> None:
        state = _seed_state()
        _install_state(state)
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_skill")
        result = await tool("nonexistent-skill")
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_skill_without_signer_returns_error(self) -> None:
        """Pre-lifespan: get_skill must surface the 'not initialized' error."""
        _install_state(None)  # simulates pre-lifespan
        app = _build_app()
        tool = await _resolve_tool(app, "session_buddy_get_skill")
        result = await tool("search-sessions")
        assert result["success"] is False
        assert "not initialized" in result["error"]


# ---------------------------------------------------------------------------
# H-6 collision: the renamed tool and the reclaimed tool co-exist
# ---------------------------------------------------------------------------


class TestH6Collision:
    """The renamed ``list_workflow_patterns`` and the reclaimed ``list_skills``
    must co-exist in the session-buddy tool surface without collision."""

    def setup_method(self) -> None:
        reset_signer_feed_state()

    def teardown_method(self) -> None:
        reset_signer_feed_state()
        _install_state(None)

    def test_renamed_workflow_patterns_tool_exists(self) -> None:
        """``list_workflow_patterns`` is the renamed H-6 function."""
        from session_buddy.mcp.tools.intelligence.intelligence_tools import (
            list_workflow_patterns,
        )

        assert list_workflow_patterns.__name__ == "list_workflow_patterns"

    def test_intelligence_module_does_not_export_list_skills(self) -> None:
        """The H-6 rename removed the bare ``list_skills`` MCP tool from the
        intelligence_tools module."""
        import session_buddy.mcp.tools.intelligence.intelligence_tools as mod

        # ``list_workflow_patterns`` is the new name; the bare ``list_skills``
        # MCP tool wrapper no longer exists in this module.
        assert hasattr(mod, "list_workflow_patterns")
        assert not hasattr(mod, "list_skills")

    def test_new_skill_tools_module_exports_register_fn(self) -> None:
        from session_buddy.mcp.tools.skill_tools import register_skill_tools

        assert callable(register_skill_tools)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
