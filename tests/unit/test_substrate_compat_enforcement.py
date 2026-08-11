"""Verify every cross-portfolio producer module carries the substrate-compat pattern.

Each producer module MUST stamp ``dhara.put`` to ``None`` at import time
when the local dhara distribution does not expose it. The stamp is
idempotent and runs unconditionally — the assertion below catches a
regression where a producer drops the import-time guard.
"""
from __future__ import annotations

import importlib

import pytest

PRODUCER_MODULES = [
    "session_buddy.channel.state_writer",
]


@pytest.mark.parametrize("module_name", PRODUCER_MODULES)
def test_producer_stamps_dhara_put(module_name: str) -> None:
    """Each producer must stamp ``dhara.put`` to None when absent at import time."""
    importlib.import_module(module_name)
    import dhara

    # The hasattr guard ran at import time — `dhara.put` MUST exist (possibly None).
    assert hasattr(dhara, "put"), (
        f"{module_name} did not stamp dhara.put at import time"
    )
