#!/usr/bin/env python3
"""Deterministic backlog validator.

Compares every file in coverage.json against rows in the backlog doc and
fails on missing, duplicate, stale-pct, or wrong-tier entries.

Tier boundaries (must match the L0/L1/L2/L3 spec):
  0%   → untested
  1-49% → low
  50-79% → partial
  80%+ → good

Usage:
    python scripts/verify_backlog.py coverage.json docs/coverage-backlog.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


TIER_RANGES = (
    ("untested", lambda pct: pct == 0),
    ("low", lambda pct: 0 < pct <= 49),
    ("partial", lambda pct: 49 < pct <= 79),
    ("good", lambda pct: pct >= 80),
)


def tier_for(pct: float) -> str:
    for name, pred in TIER_RANGES:
        if pred(pct):
            return name
    return "unknown"


_HEADING_RE = re.compile(r"^#{2,4}\s+`([^`]+)`")
_PCT_RE = re.compile(r"pct[:\s=]+(\d+(?:\.\d+)?)")
_TIER_RE = re.compile(r"tier[:\s=]+(\w+)")


def extract_backlog_rows(backlog_md: str) -> list[tuple[str, float | None, str | None]]:
    """Walk the backlog doc and pull out (path, pct, tier) per file row.

    A row begins at any heading line (## or ###) whose text leads with a
    backticked path. Metadata (pct, tier) is read from the heading line
    and from any subsequent non-heading lines until the next heading or EOF.
    """
    rows: list[tuple[str, float | None, str | None]] = []
    current_path: str | None = None
    current_pct: float | None = None
    current_tier: str | None = None

    def flush() -> None:
        nonlocal current_path, current_pct, current_tier
        if current_path:
            rows.append((current_path, current_pct, current_tier))
        current_path = None
        current_pct = None
        current_tier = None

    for line in backlog_md.splitlines():
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush()
            current_path = heading_match.group(1)
        elif current_path is None:
            continue

        pct_match = _PCT_RE.search(line)
        if pct_match:
            current_pct = float(pct_match.group(1))
        tier_match = _TIER_RE.search(line)
        if tier_match:
            current_tier = tier_match.group(1)

    flush()
    return rows


def _suffix_match_key(rel_path: str, by_path: dict[str, list]) -> str | None:
    """Find a backlog row whose key matches ``rel_path`` by suffix or basename.

    Allows ``foo.py`` (backlog) to match ``session_buddy/foo.py`` (coverage)
    when the writer used the short form.
    """
    name = Path(rel_path).name
    for key in by_path:
        if key == rel_path:
            return key
        if Path(key).name == name and rel_path.endswith("/" + key):
            return key
        if Path(key).name == name and rel_path == key:
            return key
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: verify_backlog.py coverage.json docs/coverage-backlog.md", file=sys.stderr)
        return 2
    cov_path = Path(argv[1])
    backlog_path = Path(argv[2])

    cov = json.loads(cov_path.read_text())
    files = cov.get("files", {})
    backlog_text = backlog_path.read_text()
    backlog_rows = extract_backlog_rows(backlog_text)

    failures: list[str] = []

    # Index backlog by path; detect duplicates
    by_path: dict[str, list[tuple[float | None, str | None]]] = {}
    for path, pct, tier in backlog_rows:
        by_path.setdefault(path, []).append((pct, tier))

    for path, entries in by_path.items():
        if len(entries) > 1:
            failures.append(f"DUPLICATE entry: {path} appears {len(entries)} times")

    # Check every file in coverage.json appears in backlog with matching pct + tier
    for rel_path, fd in sorted(files.items()):
        if not isinstance(fd, dict):
            continue
        s = fd.get("summary", {}) if isinstance(fd.get("summary"), dict) else {}
        pct = float(s.get("percent_covered", 0.0))
        expected_tier = tier_for(pct)

        matched_key = rel_path if rel_path in by_path else _suffix_match_key(rel_path, by_path)
        if matched_key is None:
            failures.append(f"MISSING: {rel_path} ({pct:.1f}%, tier={expected_tier}) not in backlog")
            continue
        entries = by_path[matched_key]
        for entry_pct, entry_tier in entries:
            if entry_pct is not None and abs(entry_pct - pct) > 0.5:
                failures.append(f"STALE pct: {rel_path} backlog={entry_pct} coverage={pct:.1f}")
            if entry_tier and entry_tier != expected_tier:
                failures.append(
                    f"WRONG tier: {rel_path} backlog={entry_tier} expected={expected_tier}"
                )

    if failures:
        print("❌ Backlog validation FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        # Also print to stdout so the script's exit is observable from CI logs
        for f in failures:
            print(f"- {f}")
        return 1

    if not files:
        print("✅ Empty coverage.json + empty backlog — nothing to validate")
        return 0

    print(f"✅ Backlog validates against coverage.json ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
