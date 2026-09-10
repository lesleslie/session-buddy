"""Phase 3 server-published agents tools (Phase 3 of bodai-skill-agent-distribution).

Exposes the ``mcp__session_buddy__session_buddy_list_agents`` and
``mcp__session_buddy__session_buddy_get_agent`` tools that advertise the
server-defined agents to Phase 2's installer and the Claude Code picker.
Agents live as markdown bodies under
``session_buddy/mcp/agents/<name>.md``; this module reads them at request
time and signs the metadata via the lifespan-owned
:class:`SkillsSigner`.

Security gates (per plan §11):

- **B-1** — every ``get_agent`` response carries an ed25519 signature over
  the canonicalized metadata (the Phase 2 installer verifies this before
  any write to ``~/.claude/agents/session-buddy-<name>.md``).
- **B-4** — path-traversal allowlist ``^[a-z0-9][a-z0-9._-]{0,62}$`` is
  enforced on the ``name`` parameter at the API boundary, BEFORE the
  metadata model re-validates it. Defense-in-depth: an unknown /
  forbidden ``name`` returns an error envelope rather than raising past
  the MCP boundary.
- **B-7** — each successful tool call bumps ``SignerFeedState.cycles_total``
  via :meth:`record_cycle` so the four mandatory feed signals stay
  accurate.

Non-goals:

- Body content is loaded at request time (L-6). No session-start pre-load.
- The 3 starter agents ship as static markdown files in
  ``agents/``; Phase 4's federation layer
  (``mcp__akosha__list_ecosystem_skills``) is what exposes them alongside
  the other 4 servers' catalogs.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from session_buddy.mcp.agent_schema import AgentMetadata
from session_buddy.skills_signer import canonical_payload_for_signing

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


# Allowlist mirror — see B-4 / plan §5 task #1. Duplicated here so the
# API boundary rejects forbidden ``name`` values BEFORE constructing the
# Pydantic model (avoids letting a path-traversal payload reach the
# validator, which would surface as a different error class).
_NAME_ALLOWLIST_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


# Catalog lives next to this module so deployment paths stay self-contained.
# The catalog is static — new agents are added by dropping a new ``.md``
# file under ``agents/`` and adding an entry to ``_STATIC_AGENTS``.
_CATALOG_DIR = Path(__file__).parent.parent / "agents"


# Phase 3: 3 starter agents with real session-buddy content. Each tuple
# is the body's filename (relative to ``agents/``), the semantic
# version, the description that goes in the AgentMetadata, the model,
# the list of MCP tool names the agent may invoke, dependencies, and
# metadata fields (title, category, owner, status, last_reviewed, scope).
#
# Adding a new server-published agent: drop ``<name>.md`` under
# ``agents/`` AND add an entry below. The validator runs at module
# load — a missing file or mismatched hash fails fast.
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


_SERVER_NAME = "session_buddy"


# Name-indexed view of the static catalog — built once at module load so
# the tool handlers can do O(1) lookups instead of scanning the list.
# This MUST stay below ``_STATIC_AGENTS`` so the dict comprehension sees
# the full list (Python's module body executes top-to-bottom; this lookup
# is never called before the module finishes loading).
_STATIC_AGENTS_BY_NAME: dict[str, dict[str, Any]] = {
    entry["name"]: entry for entry in _STATIC_AGENTS
}


def _read_body(filename: str) -> str:
    """Load an agent body from the catalog, asserting the file exists.

    The validator at module load time catches missing files before any
    MCP request reaches the runtime path. Returns the body as UTF-8 text.
    For agents, this is the full markdown file (YAML frontmatter +
    markdown body) which Claude Code reads verbatim as the system
    prompt (per Phase 3 task #2: ``body == system_prompt``).
    """
    path = _CATALOG_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"Agent body {filename!r} missing from catalog at {path}"
        )
    return path.read_text(encoding="utf-8")


def _build_unsigned_metadata(name: str) -> AgentMetadata:
    """Build an :class:`AgentMetadata` for the named static agent.

    The metadata has ``signature=None`` and ``server_pubkey_id=None``;
    those fields are populated by :func:`_sign_metadata` after signing.
    The ``system_prompt`` field carries the FULL markdown body
    (YAML frontmatter + markdown body) — equal to what ``get_agent``
    returns in its ``body`` field per Phase 3 task #2.
    ``content_hash`` is the lowercase hex SHA-256 of those body bytes.
    Raises :class:`KeyError` if ``name`` is not a known static agent.
    """
    for entry in _STATIC_AGENTS:
        if entry["name"] != name:
            continue
        body = _read_body(entry["body_filename"])
        body_bytes = body.encode("utf-8")
        content_hash = hashlib.sha256(body_bytes).hexdigest()
        version = entry["version"]
        return AgentMetadata(
            id=f"{_SERVER_NAME}:{name}:{version}",
            server_key=_SERVER_NAME,
            name=name,
            title=entry.get("title"),
            description=entry["description"],
            version=version,
            model=entry["model"],
            tools=list(entry["tools"]),
            system_prompt=body,
            dependencies=list(entry["dependencies"]),
            tool_refs=list(entry["tool_refs"]),
            category=entry.get("category"),
            owner=entry.get("owner"),
            status=entry.get("status"),
            last_reviewed=entry.get("last_reviewed"),
            scope=entry.get("scope", "user-global"),
            content_hash=content_hash,
            timestamp=datetime.now(UTC).timestamp(),
        )
    msg = f"unknown agent {name!r}"
    raise KeyError(msg)


def _sign_metadata(metadata: AgentMetadata, signer: Any) -> AgentMetadata:
    """Apply an ed25519 signature to a copy of ``metadata``.

    The canonical payload strips ``signature`` and ``server_pubkey_id``
    BEFORE canonicalization so the signature doesn't cover itself (per
    ``canonical_payload_for_signing`` docstring + plan §10.1.3). The
    returned copy has both signing fields populated.
    """
    unsigned_dict = metadata.model_dump(mode="json")
    canonical = canonical_payload_for_signing(unsigned_dict)
    signed = signer.sign(canonical)
    return metadata.model_copy(
        update={
            "signature": signed.signature_b64,
            "server_pubkey_id": signed.key_id,
        }
    )


def _is_allowlisted(name: str) -> bool:
    """B-4 API-boundary check on the ``name`` parameter.

    Forbids ``/``, ``..``, leading ``.``, uppercase, length > 63, and any
    character outside ``[a-z0-9._-]``. Mirrors the AgentMetadata
    validator so failures at the API boundary return a uniform
    ``{"success": False, "error": ...}`` envelope.
    """
    return bool(_NAME_ALLOWLIST_RE.fullmatch(name)) and ".." not in name


def register_agents_tools(app: FastMCP) -> None:
    """Register ``session_buddy_list_agents`` and ``session_buddy_get_agent`` MCP tools.

    Idempotent at module level (the static catalog is loaded once at
    import). Calling this twice is safe — FastMCP's ``@app.tool``
    decorator is idempotent within a single ``app`` instance.

    The tools access the lifespan-owned :class:`SkillsSigner` via
    ``get_signer_feed_state()``; if the server is running without the
    Phase 1.5 wiring (lite mode / pre-startup), both tools return an
    error envelope rather than raising.
    """

    @app.tool(name="session_buddy_list_agents")
    async def session_buddy_list_agents() -> list[dict[str, Any]]:
        """Return metadata for agents this server publishes.

        Returns at least 3 entries (one per static agent in
        ``_STATIC_AGENTS``). The ``signature`` and ``server_pubkey_id``
        fields are ``None`` here — those are populated by
        ``session_buddy_get_agent`` since the signature is over the
        canonical payload WITHOUT the signing fields themselves.

        Per Phase 3 task #1, each entry includes ``system_prompt`` (the
        full markdown body) and ``content_hash`` (sha256 of those bytes)
        so the installer can write the agent file verbatim after signature
        verification.
        """
        from session_buddy.mcp.signer_feed import (
            get_signer_feed_state,
        )

        state = get_signer_feed_state()
        if state is not None:
            state.record_cycle()

        out: list[dict[str, Any]] = []
        for entry in _STATIC_AGENTS:
            try:
                metadata = _build_unsigned_metadata(entry["name"])
            except (FileNotFoundError, ValidationError, KeyError):
                logger.exception(
                    "list_agents: failed to build metadata for %s",
                    entry["name"],
                )
                continue
            out.append(metadata.model_dump(mode="json"))
        return out

    @app.tool(name="session_buddy_get_agent")
    async def session_buddy_get_agent(name: str) -> dict[str, Any]:
        """Return the signed metadata + body for one agent.

        Validates ``name`` against the B-4 allowlist BEFORE constructing
        the metadata. Signs the metadata via the lifespan-owned
        :class:`SkillsSigner`. The body is the raw markdown text from
        ``agents/<name>.md`` — the client (Phase 2 installer) writes
        this verbatim to ``~/.claude/agents/session-buddy-<name>.md``
        so Claude Code can read the YAML frontmatter (name, description,
        model, allowed-tools) at agent-invocation time.

        Per Phase 3 task #2: ``body == metadata.system_prompt`` (both
        are the full markdown file content, frontmatter + body).
        """
        from session_buddy.mcp.signer_feed import (
            get_signer_feed_state,
        )

        if not _is_allowlisted(name):
            return {
                "success": False,
                "error": (
                    f"name {name!r} violates path-traversal allowlist "
                    "(B-4): must match ^[a-z0-9][a-z0-9._-]{0,62}$ "
                    "with no '..' substring"
                ),
            }

        state = get_signer_feed_state()
        if state is None:
            return {
                "success": False,
                "error": "signer not initialized (server may still be starting up)",
            }
        state.record_cycle()

        try:
            unsigned = _build_unsigned_metadata(name)
        except KeyError:
            return {"success": False, "error": f"agent {name!r} not found on this server"}
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc)}
        except ValidationError as exc:
            return {"success": False, "error": f"metadata validation failed: {exc}"}

        signed = _sign_metadata(unsigned, state.signer)
        body = _read_body(_STATIC_AGENTS_BY_NAME[name]["body_filename"])
        return {
            "success": True,
            "metadata": signed.model_dump(mode="json"),
            "body": body,
        }


# Build a {name: entry} index for O(1) lookup in the tool handlers. Done
# at module load; ``_STATIC_AGENTS`` is a static list so this is safe.
# (declared above; this comment is a navigation aid for readers — the
# dict comprehension lives just below the ``_STATIC_AGENTS`` list above.)


__all__ = ["register_agents_tools"]
