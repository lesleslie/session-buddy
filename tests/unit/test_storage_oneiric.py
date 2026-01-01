from __future__ import annotations

from typing import TYPE_CHECKING

from session_buddy.adapters import storage_oneiric

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


async def test_register_storage_adapter_reuses_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = storage_oneiric.StorageRegistryOneiric()
    monkeypatch.setattr(storage_oneiric, "_storage_registry", registry)

    adapter = storage_oneiric.register_storage_adapter("memory")
    adapter_again = storage_oneiric.register_storage_adapter("memory")

    assert adapter_again is adapter

    adapter_forced = storage_oneiric.register_storage_adapter("memory", force=True)
    assert adapter_forced is not adapter


async def test_register_storage_adapter_applies_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = storage_oneiric.StorageRegistryOneiric()
    monkeypatch.setattr(storage_oneiric, "_storage_registry", registry)

    overrides = {
        "local_path": str(tmp_path),
        "buckets": {"primary": str(tmp_path / "primary")},
    }

    adapter = storage_oneiric.register_storage_adapter(
        "file",
        config_overrides=overrides,
        force=True,
    )

    assert adapter.settings.local_path == tmp_path
    assert adapter.buckets["primary"] == str(tmp_path / "primary")
