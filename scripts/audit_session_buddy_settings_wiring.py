#!/usr/bin/env python3
"""Audit Oneiric config-schema wiring across the Bodai ecosystem.

Oneiric is a config-loader library: ``OneiricSettings`` (oneiric/core/config.py)
is consumed by 4 downstream Bodai projects (Mahavishnu, Crackerjack, Session-Buddy,
Akosha). A field is "wired" if any of those 5 source trees (Oneiric + 4
consumers) actually consults it at runtime.

Strategy: build a single ripgrep pattern per repo that captures every
``settings.<group>.<leaf>`` or ``settings.<leaf>`` access in one pass, then
post-process the JSON output to count consumers per leaf. ripgrep is far
faster than Python regex on 5 repos × thousands of files.

Run from anywhere:
    python scripts/audit_session_buddy_settings_wiring.py

Or override the consumer-root resolution:
    BODAI_ROOT=/path/to/ecosystem python scripts/audit_session_buddy_settings_wiring.py
    python scripts/audit_session_buddy_settings_wiring.py --ecosystem-root /path/to/ecosystem
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# --- Configuration -----------------------------------------------------------

# Repo-root resolution: this script lives in ``scripts/`` of the host repo.
# Auto-detect from the script's own path so we don't hardcode filesystem
# layout (which would leak the operator's local paths if committed).
_THIS_SCRIPT = Path(__file__).resolve()
SCRIPT_REPO_ROOT = _THIS_SCRIPT.parent.parent
SESSION_BUDDY_ROOT = SCRIPT_REPO_ROOT

# Consumer roots: try ``BODAI_ROOT`` env var first; fall back to scanning
# the host repo's parent directory for sibling repos. Operators can override
# via the ``--ecosystem-root`` CLI flag or by passing ``--consumer-root``
# multiple times.
_BODAI_SIBLINGS = ("mahavishnu", "crackerjack", "session-buddy", "oneiric", "akosha")


def _default_consumer_roots() -> list[Path]:
    """Resolve consumer roots from ``BODAI_ROOT`` env, then sibling scan."""
    env_root = os.environ.get("BODAI_ROOT")
    if env_root:
        root = Path(env_root).expanduser().resolve()
        if root.is_dir():
            return [root / name for name in _BODAI_SIBLINGS if (root / name).is_dir()]
    candidates: list[Path] = []
    parent = SCRIPT_REPO_ROOT.parent
    for sibling_name in _BODAI_SIBLINGS:
        sibling = parent / sibling_name
        if sibling.is_dir() and sibling != SCRIPT_REPO_ROOT:
            candidates.append(sibling)
    return [SCRIPT_REPO_ROOT] + candidates


CONSUMER_ROOTS = _default_consumer_roots()

# Source dirs per repo (skip tests, dist, worktrees, venvs at the rg level).
# Format: rg --type-add 'py:*.py' --type py --type-add exclusion
EXCLUDE_GLOBS = [
    "!.venv",
    "!venv",
    "!.git",
    "!node_modules",
    "!.worktrees",
    "!dist",
    "!build",
    "!htmlcov",
    "!.pytest_cache",
    "!.ruff_cache",
    "!.mypy_cache",
]

# Status codes.
WIRED = "WIRED"
WIRED_DYNAMIC = "WIRED-DYNAMIC"
INDIRECT = "INDIRECT"
DEAD = "DEAD"

# --- Schema extraction -------------------------------------------------------


@dataclass(frozen=True)
class Field:
    group: str  # top-level group, e.g. "remote"
    leaf: str  # leaf field name, e.g. "circuit_breaker_threshold"
    parent: str  # parent class name, e.g. "RemoteSourceConfig"
    python_path: str  # "remote.circuit_breaker_threshold"
    is_list_parent: bool = False  # True if this is a list[X] / dict[X] field whose inner fields are accessed transitively


def extract_schema() -> list[Field]:
    """Import Session-Buddy's ``SessionBuddySettings`` and walk every nested field.

    Path scheme:
      - Top-level leaf field ``foo`` -> group="", leaf="foo", path="foo"
      - Top-level nested BaseModel ``bar`` containing ``baz`` ->
            group="bar", leaf="baz", path="bar.baz"
      - ``list[X]``/``dict[X]`` where X is a BaseModel -> record the LIST as
        a leaf (group="parent", leaf="list_name", path="parent.list_name")
        AND walk X's fields, each getting path
        "parent.list_name[].inner_leaf" so the consumer scan can match
        either the list itself or the inner attribute access.
    """
    if str(SESSION_BUDDY_ROOT) not in sys.path:
        sys.path.insert(0, str(SESSION_BUDDY_ROOT))
    from pydantic import BaseModel

    from session_buddy.settings import (
        SessionBuddySettings,  # type: ignore[import-not-found]
    )

    fields: list[Field] = []

    def walk(model: type[BaseModel], group: str) -> None:
        for name, fld in model.model_fields.items():
            annotation = fld.annotation
            origin = getattr(annotation, "__origin__", None)
            args = getattr(annotation, "__args__", ())
            nested_cls: type[BaseModel] | None = None
            is_list_of_model = False
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                nested_cls = annotation
            elif origin in (list, dict) and args:
                inner = args[-1]
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    nested_cls = inner
                    is_list_of_model = True
            if nested_cls is not None:
                # The field IS the path component (regardless of nesting kind).
                new_group = f"{group}.{name}" if group else name
                if is_list_of_model:
                    # Record the list/dict field as its own leaf, marked as
                    # a list parent so transitive-wiring can flow through.
                    fields.append(
                        Field(
                            group=group or "(root)",
                            leaf=name,
                            parent=model.__name__,
                            python_path=f"{group}.{name}" if group else name,
                            is_list_parent=True,
                        )
                    )
                    # Walk the inner model — inner fields get paths like
                    # "logging.sinks.target" (dots, no [] suffix). They are
                    # NOT directly accessible as ``settings.logging.sinks.target``
                    # (you'd need an index), so the static scan alone won't
                    # hit them; classify() applies transitive-wiring.
                    walk(nested_cls, new_group)
                else:
                    # Plain BaseModel field — recurse, inner fields are
                    # children of this group.
                    walk(nested_cls, new_group)
            else:
                # Leaf field. The leaf NAME is `name`, the GROUP is the
                # group's path so far. python_path joins them with ".".
                fields.append(
                    Field(
                        group=group or "(root)",
                        leaf=name,
                        parent=model.__name__,
                        python_path=f"{group}.{name}" if group else name,
                    )
                )

    walk(SessionBuddySettings, "")
    return fields


# --- Consumer scanning via ripgrep ------------------------------------------


def rg() -> str:
    """Return path to ripgrep, falling back to None."""
    return shutil.which("rg") or shutil.which("ripgrep") or ""


def grep() -> str:
    """Return path to grep."""
    return shutil.which("grep") or "/usr/bin/grep"


def scan_with_ripgrep(
    fields: list[Field], consumer_roots: list[Path]
) -> dict[str, list[tuple[Path, int]]]:
    """Use ripgrep --json to capture every field access in one pass per repo.

    Resolution rules:
      1. Exact (group, leaf) match wins.
      2. If only one identifier is captured (e.g. ``cfg.environment`` — the
         rg pattern strips the cfg. prefix leaving just ``environment``),
         the match is ambiguous: multiple nested fields may share the leaf
         name. In that case, we mark EVERY field whose leaf matches as
         WIRED. This is the audit's safety bias — false-positive "wired"
         is preferable to false-positive "dead" because the operator-facing
         action is the same (delete vs. keep).
    """
    consumers: dict[str, list[tuple[Path, int]]] = {f.python_path: [] for f in fields}

    # Build (group, leaf) -> python_path AND leaf -> [python_paths]
    field_index: dict[tuple[str, str], str] = {}
    leaf_index: dict[str, list[str]] = {}
    for f in fields:
        g = f.group if f.group != "(root)" else ""
        field_index[(g, f.leaf)] = f.python_path
        leaf_index.setdefault(f.leaf, []).append(f.python_path)

    # Pattern: common access prefixes for Oneiric settings.
    prefix_alt = r"settings|cfg|config|_settings|self\.config|self\._config"
    pattern = rf"(?:{prefix_alt})\.([a-z_][a-z0-9_]*)(?:\.([a-z_][a-z0-9_]*))?"

    rg_path = rg()
    if not rg_path:
        print("ripgrep not found, falling back to grep (slower).", file=sys.stderr)
        return scan_with_grep(fields, consumer_roots)

    for root in consumer_roots:
        argv = [
            rg_path,
            "--json",
            "--no-config",
            "--no-messages",
            "-g",
            "*.py",
        ]
        for g in EXCLUDE_GLOBS:
            argv.extend(["-g", g])
        argv.extend([pattern, str(root)])
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print(f"  [timeout] {root}", file=sys.stderr)
            continue

        for line in proc.stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") != "match":
                continue
            data = ev["data"]
            path_obj = data["path"]["text"]
            line_no = data["line_number"]
            found_for_this_line: set[str] = set()
            for sm in data.get("submatches", []):
                capture_text = sm.get("match", {}).get("text", "")
                if not capture_text or "." not in capture_text:
                    continue
                rest = capture_text.split(".", 1)[1]
                parts = rest.split(".")
                if len(parts) >= 2:
                    group, leaf = parts[0], parts[1]
                elif len(parts) == 1:
                    group, leaf = "", parts[0]
                else:
                    continue
                # Skip prefix-like parts (e.g. group="self" if prefix was "self.X.Y")
                if group in {"self", "cls"}:
                    continue
                resolved: list[str] = []
                # Exact match wins.
                if (group, leaf) in field_index:
                    resolved.append(field_index[(group, leaf)])
                else:
                    # Ambiguous single-identifier match — wire ALL fields with
                    # this leaf name (audit safety bias).
                    resolved.extend(leaf_index.get(leaf, []))
                if not resolved:
                    continue
                for path in resolved:
                    if path in found_for_this_line:
                        continue
                    consumers[path].append((Path(path_obj), line_no))
                    found_for_this_line.add(path)
    return consumers


def scan_with_grep(
    fields: list[Field], consumer_roots: list[Path]
) -> dict[str, list[tuple[Path, int]]]:
    """Fallback: GNU grep -rE with structured output parsing."""
    consumers: dict[str, list[tuple[Path, int]]] = {f.python_path: [] for f in fields}
    field_index: dict[tuple[str, str], str] = {}
    leaf_index: dict[str, list[str]] = {}
    for f in fields:
        g = f.group if f.group != "(root)" else ""
        field_index[(g, f.leaf)] = f.python_path
        leaf_index.setdefault(f.leaf, []).append(f.python_path)
    grep_bin = grep()
    prefix_alt = r"settings|cfg|config|_settings|self\.config|self\._config"
    pattern = rf"(?:{prefix_alt})\.([a-z_][a-z0-9_]*)(?:\.([a-z_][a-z0-9_]*))?"

    for root in consumer_roots:
        excludes = []
        for g in EXCLUDE_GLOBS:
            excludes.extend(["--exclude-dir", g.lstrip("!")])
        argv = [
            grep_bin,
            "-rEn",
            "--include=*.py",
            *excludes,
            pattern,
            str(root),
        ]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            print(f"  [timeout] {root}", file=sys.stderr)
            continue
        if proc.returncode not in (0, 1):
            continue
        for line in proc.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            file_path, line_no_str, mt = parts
            try:
                line_no = int(line_no_str)
            except ValueError:
                continue
            m = re.search(pattern, mt)
            if not m:
                continue
            groups = m.groups()
            if groups[1]:
                group, leaf = groups[0], groups[1]
            else:
                group, leaf = "", groups[0]
            if group in {"self", "cls"}:
                continue
            resolved: list[str] = []
            if (group, leaf) in field_index:
                resolved.append(field_index[(group, leaf)])
            else:
                resolved.extend(leaf_index.get(leaf, []))
            for path in resolved:
                consumers[path].append((Path(file_path), line_no))
    return consumers


def find_dynamic_consumers(
    fields: list[Field], consumer_roots: list[Path]
) -> dict[str, bool]:
    """Find fields consumed via ``getattr(settings.X, "...")`` with a runtime name.

    Conservative heuristic: a field is WIRED-DYNAMIC if its leaf appears as
    a STRING LITERAL or f-string interpolation inside a ``getattr`` call on
    a settings-like prefix anywhere in the ecosystem. We accept any depth:
        getattr(settings, "x")
        getattr(settings.runtime_paths, "x")
        getattr(self.settings, "x")
    """
    result: dict[str, bool] = {}
    rg_path = rg()
    if not rg_path:
        return result
    # Two patterns: string-literal arg, and f-string arg.
    # Accept any settings-like prefix (settings, self.settings, _settings, cfg, ...).
    patterns = [
        r'getattr\s*\([^,]+,\s*"([a-z_][a-z0-9_]*)"',
        r"getattr\s*\([^,]+,\s*f['\"]\{?([a-z_][a-z0-9_]*)\}?",
    ]
    leaf_index: dict[str, list[str]] = {}
    for f in fields:
        leaf_index.setdefault(f.leaf, []).append(f.python_path)

    for root in consumer_roots:
        for pattern in patterns:
            argv = [
                rg_path,
                "--no-config",
                "--no-messages",
                "-o",
                "-g",
                "*.py",
                pattern,
                str(root),
            ]
            for g in EXCLUDE_GLOBS:
                argv.extend(["-g", g])
            try:
                proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                continue
            for line in proc.stdout.splitlines():
                m = re.search(pattern, line)
                if not m:
                    continue
                captured_name = m.group(1)
                # Wire all fields with this leaf name.
                for path in leaf_index.get(captured_name, []):
                    result[path] = True
    return result


# --- Classification ----------------------------------------------------------


def classify(
    fields: list[Field],
    consumers: dict[str, list[tuple[Path, int]]],
    dynamic: dict[str, bool],
) -> list[tuple[Field, str, list[tuple[Path, int]]]]:
    """Classify each field; apply transitive wiring for list[X]/dict[X] parents.

    When a ``list[X]`` or ``dict[X]`` field is WIRED, every inner field of
    ``X`` inherits WIRED status — because iterating the list and reading
    each element's attributes is the same code path.
    """
    out: list[tuple[Field, str, list[tuple[Path, int]]]] = []
    # Build map: parent list path -> [inner field python_paths].
    list_to_inners: dict[str, list[str]] = {}
    for f in fields:
        if f.is_list_parent:
            list_to_inners.setdefault(f.python_path, [])
        elif "." in f.python_path:
            # Inner field — find its list parent by walking up the path.
            parts = f.python_path.split(".")
            for i in range(len(parts), 0, -1):
                candidate = ".".join(parts[:i])
                if candidate in list_to_inners:
                    list_to_inners[candidate].append(f.python_path)
                    break

    # Pass 1: classify without transitive inheritance.
    base_status: dict[str, str] = {}
    for f in fields:
        hits = consumers.get(f.python_path, [])
        if hits:
            base_status[f.python_path] = WIRED
        elif dynamic.get(f.python_path):
            base_status[f.python_path] = WIRED_DYNAMIC
        else:
            base_status[f.python_path] = DEAD

    # Pass 2: propagate WIRED through list/dict transitive closure.
    for list_path, inner_paths in list_to_inners.items():
        if base_status.get(list_path) == WIRED:
            for inner_path in inner_paths:
                if base_status.get(inner_path) == DEAD:
                    base_status[inner_path] = WIRED

    # Emit final classifications.
    for f in fields:
        status = base_status[f.python_path]
        hits = consumers.get(f.python_path, [])
        out.append((f, status, hits))
    return out


# --- Reporting ---------------------------------------------------------------


def print_report(
    results: list[tuple[Field, str, list[tuple[Path, int]]]],
    consumer_roots: list[Path],
    title: str = "config-schema wiring audit",
) -> None:
    by_status: dict[str, list[Field]] = {
        WIRED: [],
        WIRED_DYNAMIC: [],
        INDIRECT: [],
        DEAD: [],
    }
    for f, status, _ in results:
        by_status[status].append(f)
    total = len(results)
    print()
    print("=" * 78)
    print(f"{title} ({total} fields, {len(consumer_roots)} repos)")
    print("=" * 78)
    print()
    for status in (WIRED, WIRED_DYNAMIC, INDIRECT, DEAD):
        n = len(by_status[status])
        pct = (100.0 * n / total) if total else 0.0
        print(f"  {status:<14} {n:>4}  ({pct:5.1f}%)")
    print()
    if by_status[DEAD]:
        print("-" * 78)
        print(f"DEAD fields ({len(by_status[DEAD])}):")
        print("-" * 78)
        for f in sorted(by_status[DEAD], key=lambda x: x.python_path):
            print(f"  - {f.python_path}    [{f.parent}]")
        print()
    if by_status[WIRED_DYNAMIC]:
        print("-" * 78)
        print(f"WIRED-DYNAMIC fields ({len(by_status[WIRED_DYNAMIC])}):")
        print("-" * 78)
        for f in sorted(by_status[WIRED_DYNAMIC], key=lambda x: x.python_path):
            print(f"  - {f.python_path}    [{f.parent}]")
        print()
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-wired",
        action="store_true",
        help="Print every WIRED field with its first consumer file:line.",
    )
    args = parser.parse_args()

    print(f"Session-Buddy root: {SESSION_BUDDY_ROOT}")
    print(f"Consumer roots: {len(CONSUMER_ROOTS)} repos")
    for r in CONSUMER_ROOTS:
        print(f"  - {r}")
    rg_path = rg()
    print(f"Scanner: {'ripgrep (' + rg_path + ')' if rg_path else 'grep (fallback)'}")
    print()
    print("Extracting schema from session_buddy.settings.SessionBuddySettings ...")
    fields = extract_schema()
    print(f"Found {len(fields)} fields.")
    print()
    print(f"Scanning {len(CONSUMER_ROOTS)} repos for consumers ...")
    consumers = scan_with_ripgrep(fields, CONSUMER_ROOTS)
    print(
        f"  -> {sum(1 for hits in consumers.values() if hits)} fields have static consumers"
    )
    dynamic = find_dynamic_consumers(fields, CONSUMER_ROOTS)
    print(f"  -> {sum(1 for v in dynamic.values() if v)} fields have dynamic consumers")
    results = classify(fields, consumers, dynamic)

    print_report(results, CONSUMER_ROOTS, title="SessionBuddySettings wiring audit")

    if args.show_wired:
        print("WIRED fields with first consumer:")
        print("-" * 78)
        for f, status, hits in results:
            if status == WIRED and hits:
                py_file, line = hits[0]
                if line == 0:
                    print(f"  {f.python_path:<60s}  (typed accessor)  {py_file}")
                else:
                    print(f"  {f.python_path:<60s}  {py_file}:{line}")
        print()

    has_dead = any(s == DEAD for _, s, _ in results)
    return 1 if has_dead else 0


if __name__ == "__main__":
    raise SystemExit(main())
