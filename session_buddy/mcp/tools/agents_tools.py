"""Phase 3 server-published agents tools for Session-Buddy.

Exposes the ``mcp__session_buddy__session_buddy_list_agents`` and
``mcp__session_buddy__session_buddy_get_agent`` MCP tools that
advertise the server-defined agents to the Phase 3 installer and
the Claude Code picker. Agents live as markdown bodies (with
YAML frontmatter) under
``session_buddy/mcp/agents/<name>.md``.

This module is a thin server-specific wrapper around
:func:`mcp_common.agents_tools.build_register_agents_tools`. The
factory owns the mechanism — the B-4 allowlist, B-6 body
normalization + content-hash, the wire shape, the success/error
envelope, and the tool registration plumbing. Session-Buddy owns
the policy: the catalog, where bodies live, the tool name prefix
(``"session_buddy_"``), how the signer is acquired (lifespan via
``signer_feed.get_signer_feed_state()``), and the signing function
(canonicalization via session-buddy's local
``canonical_payload_for_signing``).

Security gates (per plan §11):

- **B-1** — every ``get_agent`` response carries an ed25519 signature
  over the canonicalized metadata. The Phase 3 installer verifies
  this before any write to ``~/.claude/agents/session-buddy-<name>.md``.
- **B-4** — the path-traversal allowlist
  ``^[a-z0-9][a-z0-9._-]{0,62}$`` lives in
  ``mcp_common.canonical_schemas._validators.NAME_OR_SERVER_RE``;
  the factory enforces it at the API boundary. The per-server
  regex copy that used to live here is gone.
- **B-6** — ``get_agent`` returns ``body == system_prompt``. The
  factory computes ``content_hash`` from the stripped body and
  the schema's body-integrity model_validator asserts the hash
  matches the system_prompt bytes.
- **B-7** — each successful tool call invokes ``on_call``, which
  bumps ``SignerFeedState.cycles_total`` via
  :meth:`record_cycle` so the four mandatory feed signals stay
  accurate.

Body shape note: the body is the FULL markdown file (YAML
frontmatter + markdown body), which Claude Code reads verbatim
as the system prompt. Per Phase 3 task #2: ``body ==
metadata.system_prompt`` — both fields carry the same bytes.

Non-goals:

- Body content is loaded at request time (L-6). No session-start
  pre-load.
- The 3 starter agents ship as static markdown files in
  ``session_buddy/mcp/agents/``; Phase 4's federation layer
  (``mcp__akosha__list_ecosystem_agents``) is what exposes them
  alongside the other 4 servers' catalogs.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_common.agents_tools import build_register_agents_tools
from mcp_common.canonical_schemas.agent import AgentCanonicalSchema

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


# Catalog lives next to this module so deployment paths stay self-
# contained. The catalog is static — new agents are added by
# dropping a new ``.md`` file under ``agents/`` AND adding an entry
# to ``_STATIC_AGENTS``.
_CATALOG_DIR = Path(__file__).parent.parent / "agents"


# Phase 3: 3 starter agents with real session-buddy content. Each
# dict is the body's filename (relative to ``agents/``), the
# semantic version, the description that goes in the
# AgentMetadata, the model, the list of MCP tool names the agent
# may invoke, dependencies, and the optional governance metadata
# (title, category, owner, status, last_reviewed, scope).
#
# Adding a new server-published agent: drop ``<name>.md`` under
# ``agents/`` AND add an entry below. The factory's catalog
# validation runs at module load — a missing file or duplicate
# name fails fast.
_STATIC_AGENTS: list[dict[str, Any]] = [
    {
        "name": "session-buddy-specialist",
        "body_filename": "session-buddy-specialist.md",
        "version": "1.0.0",
        "title": "Session-Buddy Specialist",
        "description": (
            "Use proactively for anything touching the Session-Buddy MCP "
            "server — its 49 tools, the Phase 1/1.5 signer feed, the Phase "
            "3 agent catalog, the reflection database, and the lifespan-"
            "owned SkillsSigner. Routes through "
            "mcp__session_buddy__session_buddy_list_skills and "
            "mcp__session_buddy__session_buddy_get_skill for skill "
            "discovery and through "
            "mcp__session_buddy__session_buddy_list_agents plus "
            "mcp__session_buddy__session_buddy_get_agent for agent "
            "installs. Self-published from the session-buddy server "
            "(genuinely new — no adjacent specialist in the ecosystem)."
        ),
        "model": "sonnet",
        "tools": [
            "mcp__session_buddy__session_buddy_list_skills",
            "mcp__session_buddy__session_buddy_get_skill",
            "mcp__session_buddy__session_buddy_list_agents",
            "mcp__session_buddy__session_buddy_get_agent",
            "mcp__session_buddy__search_by_concept",
            "mcp__session_buddy__quick_search",
            "mcp__session_buddy__capture_successful_pattern",
            "Read",
        ],
        "tool_refs": [
            "mcp__session_buddy__session_buddy_list_skills",
            "mcp__session_buddy__session_buddy_get_skill",
            "mcp__session_buddy__session_buddy_list_agents",
            "mcp__session_buddy__session_buddy_get_agent",
        ],
        "dependencies": [],
        "category": "inventory",
        "owner": "session-buddy",
        "status": "active",
        "last_reviewed": "2026-09-10",
        "scope": "user-global",
    },
    {
        "name": "session_archaeologist_agent",
        "body_filename": "session_archaeologist_agent.md",
        "version": "1.0.0",
        "title": "Session Archaeologist",
        "description": (
            "Use proactively for 'what did we do last time X' queries "
            "across indexed Session-Buddy conversation history — searches "
            "past Claude Code sessions, captured reflections, learned "
            "patterns, and stored checkpoints for any topic the user "
            "names. Routes through mcp__session_buddy__search_by_concept "
            "(hybrid semantic + lexical) and mcp__session_buddy__"
            "search_by_source (entity-keyed) with optional project "
            "scoping."
        ),
        "model": "sonnet",
        "tools": [
            "mcp__session_buddy__search_by_concept",
            "mcp__session_buddy__search_by_source",
            "mcp__session_buddy__quick_search",
            "mcp__session_buddy__code_call_chain",
            "mcp__session_buddy__code_search_symbols",
            "Read",
        ],
        "tool_refs": [
            "mcp__session_buddy__search_by_concept",
            "mcp__session_buddy__search_by_source",
            "mcp__session_buddy__quick_search",
            "mcp__session_buddy__code_call_chain",
            "mcp__session_buddy__code_search_symbols",
        ],
        "dependencies": [],
        "category": "retrieval",
        "owner": "session-buddy",
        "status": "active",
        "last_reviewed": "2026-09-10",
        "scope": "user-global",
    },
    {
        "name": "reflection_miner_agent",
        "body_filename": "reflection_miner_agent.md",
        "version": "1.0.0",
        "title": "Reflection Miner",
        "description": (
            "Use proactively when the user wants to persist a high-quality "
            "workflow pattern into the Session-Buddy reflection database "
            "for cross-project reuse. Routes through "
            "mcp__session_buddy__capture_successful_pattern with strict "
            "outcome_score thresholding (>= 0.75 for cross-project "
            "promotion; 0.50-0.74 for project-local capture) and "
            "mcp__session_buddy__apply_pattern for retrieval. Adjacent to "
            "session_archaeologist_agent (read-only retrieval) and "
            "session-buddy-specialist (inventory oracle)."
        ),
        "model": "sonnet",
        "tools": [
            "mcp__session_buddy__capture_successful_pattern",
            "mcp__session_buddy__apply_pattern",
            "mcp__session_buddy__search_similar_patterns",
            "mcp__session_buddy__search_by_concept",
            "Read",
        ],
        "tool_refs": [
            "mcp__session_buddy__capture_successful_pattern",
            "mcp__session_buddy__apply_pattern",
            "mcp__session_buddy__search_similar_patterns",
            "mcp__session_buddy__search_by_concept",
        ],
        "dependencies": ["session_archaeologist_agent"],
        "category": "capture",
        "owner": "session-buddy",
        "status": "active",
        "last_reviewed": "2026-09-10",
        "scope": "user-global",
    },
]


# Note: server_key uses underscore ("session_buddy"), not hyphen.
# The MCP tool name prefix is "session_buddy_" to match the
# existing wire names (mcp__session_buddy__session_buddy_*).
_SERVER_KEY = "session_buddy"


# Name-indexed view of the static catalog — built once at module
# load so the body loader can do O(1) lookups instead of scanning
# the list.
_STATIC_AGENTS_BY_NAME: dict[str, dict[str, Any]] = {
    entry["name"]: entry for entry in _STATIC_AGENTS
}


# --- Body source (server-specific) ------------------------------------


def _read_body(filename: str) -> str:
    """Load an agent body from the catalog, asserting the file exists.

    The body is the FULL markdown file (YAML frontmatter + markdown
    body) which Claude Code reads verbatim as the system prompt
    (per Phase 3 task #2: ``body == system_prompt``).
    """
    path = _CATALOG_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"Agent body {filename!r} missing from catalog at {path}"
        )
    return path.read_text(encoding="utf-8")


def _body_loader(name: str) -> str:
    """Factory's body source: read the file from disk.

    The factory's ``_build_unsigned_metadata`` calls this on demand
    for any catalog entry that doesn't carry ``system_prompt``
    inline. The factory strips the returned string and computes
    the B-6 content_hash from the stripped bytes.
    """
    return _read_body(_STATIC_AGENTS_BY_NAME[name]["body_filename"])


# --- Signing policy (server-specific) ---------------------------------


def _sign(metadata: AgentCanonicalSchema) -> AgentCanonicalSchema:
    """Apply an ed25519 signature using the lifespan-owned signer.

    The factory hands the unsigned metadata to this callable and
    receives the signed copy. Acquires the signer via
    :func:`session_buddy.mcp.signer_feed.get_signer_feed_state`
    (lifespan-owned), canonicalizes via session-buddy's local
    :func:`canonical_payload_for_signing` (which strips the
    ``signature`` + ``server_pubkey_id`` fields before signing so
    the signature doesn't cover itself), and attaches the result.

    Raises if the signer feed state isn't initialized (server
    still starting up, or pre-Phase-1.5 lite mode). The factory
    converts the exception into the standard error envelope.
    """
    from session_buddy.mcp.signer_feed import get_signer_feed_state
    from session_buddy.skills_signer import canonical_payload_for_signing

    state = get_signer_feed_state()
    if state is None:
        raise RuntimeError(
            "signer not initialized (server may still be starting up)"
        )

    canonical = canonical_payload_for_signing(metadata.to_dict())
    signed = state.signer.sign(canonical)
    return metadata.model_copy(
        update={
            "signature": signed.signature_b64,
            "server_pubkey_id": signed.key_id,
        }
    )


# --- B-7 cycle bump (server-specific) ---------------------------------


def _on_call() -> None:
    """B-7: bump ``SignerFeedState.cycles_total`` on every tool call.

    The factory invokes this at the start of every list_agents and
    get_agent call so the four mandatory feed signals stay
    accurate. No-op if the signer feed state isn't initialized
    yet (matches the pre-refactor behavior).
    """
    from session_buddy.mcp.signer_feed import get_signer_feed_state

    state = get_signer_feed_state()
    if state is not None:
        state.record_cycle()


# --- Tool registration ------------------------------------------------


def register_agents_tools(app: FastMCP) -> None:
    """Register ``session_buddy_list_agents`` and ``session_buddy_get_agent``.

    Idempotent at module level (the static catalog is loaded once
    at import). Calling this twice is safe — FastMCP's
    ``@app.tool`` decorator is idempotent within a single
    ``app`` instance.

    Delegates to :func:`mcp_common.agents_tools.build_register_agents_tools`
    with session-buddy's catalog, body source, signing policy,
    cycle-bump hook, and tool name prefix. The wire shape,
    allowlist enforcement, and envelope contract all live in
    the factory; session-buddy only owns the data, the signer,
    and the prefix.

    The call site is profile-gated (see
    ``session_buddy/mcp/tools/profiles.py``) so the tool
    registration respects the active ``SESSION_BUDDY_TOOL_PROFILE``
    environment variable.
    """
    build_register_agents_tools(
        server_key=_SERVER_KEY,
        catalog=_STATIC_AGENTS,
        body_loader=_body_loader,
        sign=_sign,
        on_call=_on_call,
        tool_name_prefix=f"{_SERVER_KEY}_",
        # The hook and any in-flight clients expect the
        # "session_buddy_" prefix on both tool names.
    )(app)


__all__ = ["register_agents_tools", "AgentCanonicalSchema"]
