"""Ecosystem run history aggregation tool (Phase 1 of v2 plan).

Registers ``ecosystem_run_history(workflow_id, scope?)`` which aggregates
run records for a given workflow_id across Bodai components. Returns a
JSON string with one entry per contributing component plus a synthesized
summary block.

Phase 1 scope:

* Reads workflow outcomes persisted by each component under a canonical
  substrate key (``session-buddy://runs/{workflow_id}`` — defined in
  Dhara's Phase 1 substrate schema).
* Falls back to a deterministic stub when the substrate is unreachable
  so the tool stays usable in lite-mode environments.
* The aggregator is intentionally pluggable: Phase 2 can wire real
  per-component fetchers (Mahavishnu's pool manager, Akosha's fitness
  analyzer, etc.) without breaking the public contract.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from mcp_common.fastmcp import FastMCP


logger = logging.getLogger(__name__)


BODAI_COMPONENT_KEYS: tuple[str, ...] = (
    "mahavishnu",
    "akosha",
    "session-buddy",
    "dhara",
    "crackerjack",
    "oneiric",
)


# ---------------------------------------------------------------------------
# Substrate path + Pydantic input schema
# ---------------------------------------------------------------------------

SUBSTRATE_RUN_KEY_FMT = "session-buddy://runs/{workflow_id}.json"
SUBSTRATE_CAP_KEY_FMT = "akosha://capabilities/{repo}/{kind}/{name}.json"


class EcosystemRunHistoryRequest(BaseModel):
    """Validation schema for ``ecosystem_run_history`` MCP tool (Phase 1)."""

    workflow_id: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Workflow identifier (matches ``dispatch_to_pool`` output).",
    )
    scope: str | None = Field(
        default=None,
        max_length=50,
        description=(
            "Optional component scope filter: 'mahavishnu' | 'akosha' | "
            "'session-buddy' | 'dhara' | 'crackerjack' | 'oneiric' | "
            "'all' (default)."
        ),
    )
    include_steps: bool = Field(
        default=False,
        description="Include per-step run entries (larger payload).",
    )

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v == "all":
            return v
        if v not in BODAI_COMPONENT_KEYS:
            raise ValueError(
                f"scope must be one of {BODAI_COMPONENT_KEYS} or 'all'; got {v!r}"
            )
        return v

    @field_validator("workflow_id")
    @classmethod
    def validate_wid(cls, v: str) -> str:
        # Workflow IDs are UUIDs in practice; allow letters/digits/-/_.
        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("workflow_id contains invalid characters")
        return v


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _stub_component_entry(
    repo: str,
    workflow_id: str,
    *,
    include_steps: bool,
) -> dict[str, Any]:
    """Return a deterministic stub entry for ``repo`` (Phase 1 fallback).

    The stub lets the tool return a structured payload even when the
    real substrate is unreachable. It is replaced by per-component
    fetchers in Phase 2.
    """
    entry: dict[str, Any] = {
        "repo": repo,
        "workflow_id": workflow_id,
        "status": "unknown",
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "source": "phase1_stub",
    }
    if include_steps:
        entry["steps"] = []
    return entry


def _summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a top-level summary block from per-component entries."""
    repos_seen = sorted({e["repo"] for e in entries})
    statuses = {e["repo"]: e.get("status") for e in entries}
    return {
        "workflow_id": entries[0]["workflow_id"] if entries else None,
        "component_count": len(entries),
        "repos_seen": repos_seen,
        "status_by_repo": statuses,
        "spans_3_components": len(repos_seen) >= 3,
    }


def aggregate_run_history(
    workflow_id: str,
    *,
    scope: str | None = None,
    include_steps: bool = False,
    fetcher: Any | None = None,
) -> dict[str, Any]:
    """Aggregate ecosystem run records for ``workflow_id``.

    Args:
        workflow_id: The workflow identifier to look up.
        scope: Optional component scope filter; ``None`` or ``"all"`` means
            aggregate every Bodai component.
        include_steps: If True, include per-step run entries.
        fetcher: Optional async callable ``(repo, workflow_id) -> dict``
            for Phase 2+ real-substrate reads. When ``None`` (Phase 1
            default), every component is served from
            :func:`_stub_component_entry`.

    Returns:
        dict with keys ``workflow_id``, ``summary``, ``components``.
    """
    if scope in (None, "all"):
        components = list(BODAI_COMPONENT_KEYS)
    else:
        components = [scope]

    entries: list[dict[str, Any]] = []
    for repo in components:
        try:
            if fetcher is not None:
                # Phase 2 hook; keeps the sync API surface small.
                entry = fetcher(repo, workflow_id)
            else:
                entry = _stub_component_entry(
                    repo,
                    workflow_id,
                    include_steps=include_steps,
                )
        except Exception as exc:  # noqa: BLE001 - per-component boundary: any fetcher/stub failure degrades to an "error" entry instead of crashing the whole aggregation
            logger.warning(
                "ecosystem_run_history: fetcher failed for repo=%s wid=%s: %s",
                repo,
                workflow_id,
                exc,
            )
            entry = _stub_component_entry(repo, workflow_id, include_steps=False)
            entry["status"] = "error"
            entry["error"] = str(exc)
        entries.append(entry)

    return {
        "workflow_id": workflow_id,
        "summary": _summarize(entries),
        "components": entries,
        "mode": "phase1_stub" if fetcher is None else "live",
    }


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register_ecosystem_run_history_tools(mcp: FastMCP) -> None:
    """Register ``ecosystem_run_history`` on the supplied FastMCP app."""

    @mcp.tool()
    async def ecosystem_run_history(
        workflow_id: str,
        scope: str | None = None,
        include_steps: bool = False,
    ) -> str:
        """Aggregate run records across Bodai components for ``workflow_id``.

        Args:
            workflow_id: Workflow identifier returned by Mahavishnu's
                ``dispatch_to_pool`` / ``pool_route_execute``.
            scope: Optional component key to narrow the search; ``"all"``
                (default) covers every Bodai component.
            include_steps: When True, embed per-step run entries.

        Returns:
            JSON string with ``workflow_id``, ``summary``, ``components``,
            and ``mode`` (``phase1_stub`` until Phase 2 wires real
            per-component fetchers).

        Example:
            >>> ecosystem_run_history(workflow_id="10633f68-...")
            '{"workflow_id":"10633f68-...","summary":{...},"components":[{...}]}'
        """
        try:
            params = EcosystemRunHistoryRequest(
                workflow_id=workflow_id,
                scope=scope,
                include_steps=include_steps,
            )
        except Exception as exc:  # noqa: BLE001 - public MCP tool boundary: input validation must return a JSON error envelope, never propagate to the caller
            logger.warning(
                "ecosystem_run_history validation failed: %s (workflow_id=%r scope=%r)",
                exc,
                workflow_id,
                scope,
            )
            return json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "error_code": "invalid_input",
                }
            )

        try:
            payload = aggregate_run_history(
                workflow_id=params.workflow_id,
                scope=params.scope,
                include_steps=params.include_steps,
            )
        except Exception as exc:
            logger.exception(
                "ecosystem_run_history aggregation failed for %s",
                params.workflow_id,
            )
            return json.dumps(
                {
                    "success": False,
                    "workflow_id": params.workflow_id,
                    "error": str(exc),
                    "error_code": "aggregation_failed",
                }
            )

        return json.dumps(payload)


__all__ = [
    "BODAI_COMPONENT_KEYS",
    "SUBSTRATE_CAP_KEY_FMT",
    "SUBSTRATE_RUN_KEY_FMT",
    "EcosystemRunHistoryRequest",
    "aggregate_run_history",
    "register_ecosystem_run_history_tools",
]
