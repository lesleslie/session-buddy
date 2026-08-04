#!/usr/bin/env python3
"""Wave-1 module selection.

Reads coverage.json + the anti-target list and selects exactly 10 modules
across 4 layers (5 MCP / 2 CLI / 2 core / 1 util), honoring the spec's
hard floors and tie-breakers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SLOTS = {
    "mcp": 5,
    "cli": 2,
    "core": 2,
    "util": 1,
}


def layer_of(path: str) -> str:
    """Return the Wave-1 layer for a coverage path."""
    normalized = path.replace("\\", "/")
    if "/mcp/tools/" in normalized:
        return "mcp"
    if normalized.startswith("session_buddy/cli") or "/cli/" in normalized:
        return "cli"
    if (
        "/core/" in normalized
        or "/coordinator" in normalized
        or "/manager" in normalized
        or "/app_monitor" in normalized
        or "/natural_scheduler" in normalized
    ):
        return "core"
    if "/utils/" in normalized:
        return "util"
    return "other"


def select(
    cov_files: dict[str, dict],
    anti_targets: set[str],
    min_statements: int = 20,
    max_statements: int = 600,
    pct_min: float = 30.0,
    pct_max: float = 94.0,
) -> list[dict]:
    """Apply floors and tie-breakers, then return picks for each slot."""
    candidates = []
    for path, file_data in cov_files.items():
        if path in anti_targets or path.endswith("/__init__.py"):
            continue
        summary = file_data.get("summary", {}) if isinstance(file_data, dict) else {}
        percent_covered = float(summary.get("percent_covered", 0.0))
        statements = int(summary.get("num_statements", 0))
        if not (pct_min <= percent_covered <= pct_max):
            continue
        if not (min_statements <= statements <= max_statements):
            continue
        layer = layer_of(path)
        if layer == "other":
            continue
        candidates.append(
            {
                "path": path,
                "pct": percent_covered,
                "n": statements,
                "layer": layer,
            }
        )

    # Tie-breakers: smaller LOC, then closer to 30% from below.
    candidates.sort(key=lambda candidate: (candidate["n"], abs(candidate["pct"] - 30)))

    picks = []
    picked_paths = set()
    for layer, count in SLOTS.items():
        layer_candidates = [
            candidate
            for candidate in candidates
            if candidate["layer"] == layer and candidate["path"] not in picked_paths
        ]
        for candidate in layer_candidates[:count]:
            picks.append(
                {
                    "path": candidate["path"],
                    "layer": candidate["layer"],
                    "pct": round(candidate["pct"], 2),
                    "statements": candidate["n"],
                }
            )
            picked_paths.add(candidate["path"])
    return picks


def main(argv: list[str]) -> int:
    """Select Wave-1 modules and write the machine-readable result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", required=True)
    parser.add_argument("--anti-targets-json", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv[1:])

    coverage = json.loads(Path(args.coverage_json).read_text())
    anti_target_data = json.loads(Path(args.anti_targets_json).read_text())
    anti_targets = set(anti_target_data.get("anti_targets", []))

    files = coverage.get("files", {})
    if not files:
        print(
            "coverage.json has no files; did the pytest run complete?",
            file=sys.stderr,
        )
        return 1

    picks = select(files, anti_targets)
    counts = {
        layer: sum(1 for pick in picks if pick["layer"] == layer)
        for layer in SLOTS
    }
    missing_slots = [
        layer for layer, count in counts.items() if count < SLOTS[layer]
    ]

    output = {
        "selected": picks,
        "slot_counts": counts,
        "selection_rules": {
            "anti_target_count": len(anti_targets),
            "pct_window": "[30, 94]",
            "statements_window": "[20, 600]",
            "tie_breakers": ["smaller_n", "closer_to_30pct"],
        },
        "generated_at": "wave-1",
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2))

    # Write partial picks before reporting an under-fill so callers can inspect them.
    if missing_slots:
        print(
            f"Slot under-fill: {missing_slots} need more candidates. "
            f"Picked: {[pick['path'] for pick in picks]}",
            file=sys.stderr,
        )
        return 1

    print(f"WROTE {len(picks)} picks across {len(SLOTS)} layers to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
