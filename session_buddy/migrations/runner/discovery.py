"""Lexicographic discovery of migration scripts inside a bundle directory."""

from __future__ import annotations

from pathlib import Path


class ScriptDiscovery:
    """Resolve forward / rollback scripts inside a single migration bundle.

    Scripts are identified by a 3-digit prefix (``000``..``999``) and a
    descriptive slug. Forward scripts end in ``.sql``; rollback scripts add a
    ``_down`` segment before the extension (e.g. ``001_init_down.sql``).
    """

    def __init__(self, bundle_dir: Path) -> None:
        self._bundle_dir = bundle_dir

    def discover_scripts(self) -> list[Path]:
        """Return every forward script under ``bundle_dir`` in lex order.

        Rollback files (``*_down.sql``) are explicitly excluded.
        """
        return sorted(
            p
            for p in self._bundle_dir.glob("0*.sql")
            if not p.name.endswith("_down.sql")
        )

    def discover_down_scripts(self) -> list[Path]:
        """Return every rollback script under ``bundle_dir`` in lex order.

        Only step IDs ``001``..``007`` are considered: ``000_`` is the bootstrap
        step (irreversible) and ``008+`` are terminal cleanup steps (also
        irreversible in this bundle layout).
        """
        return sorted(
            p
            for p in self._bundle_dir.glob("0*_down.sql")
            if "001" <= p.name[:3] <= "007"
        )

    def read_script(self, name: str) -> str:
        """Return the UTF-8 contents of ``name`` inside the bundle directory."""
        return (self._bundle_dir / name).read_text(encoding="utf-8")
