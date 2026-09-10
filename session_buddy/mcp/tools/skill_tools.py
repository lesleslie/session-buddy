"""Phase 1 server-published skills tools (Phase 1 of bodai-skill-agent-distribution).

Exposes the ``mcp__session_buddy__session_buddy_list_skills`` and
``mcp__session_buddy__session_buddy_get_skill`` tools that advertise the
server-defined skills to Phase 2's installer and the Claude Code picker.
Skills live as markdown bodies under
``session_buddy/mcp/skills_catalog/<name>.md``; this module reads them at
request time and signs the metadata via the lifespan-owned
:class:`SkillsSigner`.

H-6 collision (plan §11 H-6): the previous ``mcp__session_buddy__list_skills``
(returning LEARNED workflow patterns from the IntelligenceEngine) was
renamed to ``mcp__session_buddy__session_buddy_list_workflow_patterns`` in
the prior commit. This module reclaims the bare ``list_skills`` name for
the new packaging-metadata shape (per ``SkillMetadata``).

Security gates (per plan §11):

- **B-1** — every ``get_skill`` response carries an ed25519 signature over
  the canonicalized metadata (the Phase 2 installer verifies this before
  any write to ``~/.claude/skills/``).
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
- The 3 starter skills ship as static markdown files in
  ``skills_catalog/``; Phase 4's federation layer
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

from session_buddy.mcp.skill_schema import SkillMetadata
from session_buddy.skills_signer import canonical_payload_for_signing

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


# Allowlist mirror — see B-4 / plan §5 task #4. Duplicated here so the
# API boundary rejects forbidden ``name`` values BEFORE constructing the
# Pydantic model (avoids letting a path-traversal payload reach the
# validator, which would surface as a different error class).
_NAME_ALLOWLIST_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


# Catalog lives next to this module so deployment paths stay self-contained.
# The catalog is static — new skills are added by dropping a new ``.md``
# file under ``skills_catalog/`` and adding an entry to ``_STATIC_SKILLS``.
_CATALOG_DIR = Path(__file__).parent.parent / "skills_catalog"


# Phase 1: 3 starter skills with real session-buddy content. Each tuple
# is the body's filename (relative to ``skills_catalog/``), the semantic
# version, the description that goes in both the SkillMetadata AND the
# frontmatter, the list of MCP tool names the skill may invoke, and the
# dependency list (other skill names).
#
# Adding a new server-published skill: drop ``<name>.md`` under
# ``skills_catalog/`` AND add an entry below. The validator runs at module
# load — a missing file or mismatched hash fails fast.
_STATIC_SKILLS: list[dict[str, Any]] = [
    {
        "name": "search-sessions",
        "body_filename": "search-sessions.md",
        "version": "1.0.0",
        "description": (
            "Use ONLY when the user explicitly types "
            "`/session-buddy:search-sessions` or selects this Skill from "
            "the picker to run hybrid semantic + lexical search across "
            "the Session-Buddy memory corpus. Do not auto-trigger. Routes "
            "through `mcp__session_buddy__search_by_concept` to find "
            "semantically similar reflections across the indexed "
            "conversation history, captured checkpoints, and learned "
            "patterns."
        ),
        "tool_refs": ["mcp__session_buddy__search_by_concept"],
        "allowed_tools": [
            "mcp__session_buddy__search_by_concept",
            "mcp__session_buddy__search_by_source",
            "mcp__session_buddy__quick_search",
            "Read",
        ],
        "dependencies": [],
    },
    {
        "name": "code-archaeologist",
        "body_filename": "code-archaeologist.md",
        "version": "1.0.0",
        "description": (
            "Use ONLY when the user explicitly types "
            "`/session-buddy:code-archaeologist` or selects this Skill "
            "from the picker to trace transitive caller/callee "
            "relationships of a symbol in the indexed Session-Buddy code "
            "graph. Do not auto-trigger. Routes through "
            "`mcp__session_buddy__code_call_chain` with configurable "
            "direction (callers | callees | both) and max_depth "
            "(1-10)."
        ),
        "tool_refs": ["mcp__session_buddy__code_call_chain"],
        "allowed_tools": [
            "mcp__session_buddy__code_call_chain",
            "mcp__session_buddy__code_impact_analysis",
            "mcp__session_buddy__code_search_symbols",
            "Read",
        ],
        "dependencies": [],
    },
    {
        "name": "pattern-capture",
        "body_filename": "pattern-capture.md",
        "version": "1.0.0",
        "description": (
            "Use ONLY when the user explicitly types "
            "`/session-buddy:pattern-capture` or selects this Skill from "
            "the picker to persist a high-quality workflow pattern into "
            "the Session-Buddy reflection database for cross-project "
            "reuse. Do not auto-trigger. Routes through "
            "`mcp__session_buddy__capture_successful_pattern` with strict "
            "outcome_score thresholding (>= 0.75 for cross-project "
            "promotion; 0.50-0.74 for project-local capture)."
        ),
        "tool_refs": ["mcp__session_buddy__capture_successful_pattern"],
        "allowed_tools": [
            "mcp__session_buddy__capture_successful_pattern",
            "mcp__session_buddy__search_similar_patterns",
            "mcp__session_buddy__apply_pattern",
            "Read",
        ],
        "dependencies": [],
    },
]


_SERVER_NAME = "session_buddy"


# Name-indexed view of the static catalog — built once at module load so
# the tool handlers can do O(1) lookups instead of scanning the list.
# This MUST stay below ``_STATIC_SKILLS`` so the dict comprehension sees
# the full list (Python's module body executes top-to-bottom; this lookup
# is never called before the module finishes loading).
_STATIC_SKILLS_BY_NAME: dict[str, dict[str, Any]] = {
    entry["name"]: entry for entry in _STATIC_SKILLS
}


def _read_body(filename: str) -> str:
    """Load a skill body from the catalog, asserting the file exists.

    The validator at module load time catches missing files before any
    MCP request reaches the runtime path. Returns the body as UTF-8 text.
    """
    path = _CATALOG_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"Skill body {filename!r} missing from catalog at {path}"
        )
    return path.read_text(encoding="utf-8")


def _build_unsigned_metadata(name: str) -> SkillMetadata:
    """Build a :class:`SkillMetadata` for the named static skill.

    The metadata has ``signature=None`` and ``server_pubkey_id=None``;
    those fields are populated by :func:`_sign_metadata` after signing.
    Raises :class:`KeyError` if ``name`` is not a known static skill.
    """
    for entry in _STATIC_SKILLS:
        if entry["name"] != name:
            continue
        body = _read_body(entry["body_filename"])
        body_bytes = body.encode("utf-8")
        content_hash = hashlib.sha256(body_bytes).hexdigest()
        version = entry["version"]
        return SkillMetadata(
            id=f"{_SERVER_NAME}:{name}:{version}",
            server=_SERVER_NAME,
            name=name,
            description=entry["description"],
            version=version,
            tool_refs=list(entry["tool_refs"]),
            dependencies=list(entry["dependencies"]),
            content_type="skill",
            content_hash=content_hash,
            body_size=len(body_bytes),
            body_format="yaml-frontmatter+markdown",
            allowed_tools=list(entry["allowed_tools"]),
            timestamp=datetime.now(UTC).timestamp(),
        )
    msg = f"unknown skill {name!r}"
    raise KeyError(msg)


def _sign_metadata(metadata: SkillMetadata, signer: Any) -> SkillMetadata:
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
    character outside ``[a-z0-9._-]``. Mirrors the SkillMetadata
    validator so failures at the API boundary return a uniform
    ``{"success": False, "error": ...}`` envelope.
    """
    return bool(_NAME_ALLOWLIST_RE.fullmatch(name)) and ".." not in name


def register_skill_tools(app: FastMCP) -> None:
    """Register ``session_buddy_list_skills`` and ``session_buddy_get_skill`` MCP tools.

    Idempotent at module level (the static catalog is loaded once at
    import). Calling this twice is safe — FastMCP's ``@app.tool``
    decorator is idempotent within a single ``app`` instance.

    The tools access the lifespan-owned :class:`SkillsSigner` via
    ``get_signer_feed_state()``; if the server is running without the
    Phase 1.5 wiring (lite mode / pre-startup), both tools return an
    error envelope rather than raising.
    """

    @app.tool(name="session_buddy_list_skills")
    async def session_buddy_list_skills() -> list[dict[str, Any]]:
        """Return metadata for skills this server publishes.

        Returns at least 3 entries (one per static skill in
        ``_STATIC_SKILLS``). The ``signature`` and ``server_pubkey_id``
        fields are ``None`` here — those are populated by
        ``session_buddy_get_skill`` since the signature is over the
        canonical payload WITHOUT the signing fields themselves.

        H-6 (plan §11): the previously-existing
        ``mcp__session_buddy__list_skills`` (returning LEARNED workflow
        patterns) was renamed to
        ``mcp__session_buddy__session_buddy_list_workflow_patterns``;
        this reclaims the bare ``list_skills`` name for the new
        packaging-metadata shape.
        """
        from session_buddy.mcp.signer_feed import (
            get_signer_feed_state,
        )

        state = get_signer_feed_state()
        if state is not None:
            state.record_cycle()

        out: list[dict[str, Any]] = []
        for entry in _STATIC_SKILLS:
            try:
                metadata = _build_unsigned_metadata(entry["name"])
            except (FileNotFoundError, ValidationError, KeyError):
                logger.exception(
                    "list_skills: failed to build metadata for %s",
                    entry["name"],
                )
                continue
            out.append(metadata.model_dump(mode="json"))
        return out

    @app.tool(name="session_buddy_get_skill")
    async def session_buddy_get_skill(name: str) -> dict[str, Any]:
        """Return the signed metadata + body for one skill.

        Validates ``name`` against the B-4 allowlist BEFORE constructing
        the metadata. Signs the metadata via the lifespan-owned
        :class:`SkillsSigner`. The body is the raw markdown text from
        ``skills_catalog/<name>.md`` — the client (Phase 2 installer)
        writes this verbatim to
        ``~/.claude/skills/session-buddy-<name>/SKILL.md``.
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
            return {"success": False, "error": f"skill {name!r} not found on this server"}
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc)}
        except ValidationError as exc:
            return {"success": False, "error": f"metadata validation failed: {exc}"}

        signed = _sign_metadata(unsigned, state.signer)
        body = _read_body(_STATIC_SKILLS_BY_NAME[name]["body_filename"])
        return {
            "success": True,
            "metadata": signed.model_dump(mode="json"),
            "body": body,
        }


# Build a {name: entry} index for O(1) lookup in the tool handlers. Done
# at module load; ``_STATIC_SKILLS`` is a static list so this is safe.
# (declared above; this comment is a navigation aid for readers — the
# dict comprehension lives just below the ``_STATIC_SKILLS`` list above.)


__all__ = ["register_skill_tools"]
