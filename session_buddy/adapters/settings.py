from __future__ import annotations

import typing as t
from dataclasses import dataclass, field
from pathlib import Path

from session_buddy.settings import get_settings


def _resolve_data_dir() -> Path:
    settings = get_settings()
    data_dir = settings.data_dir.expanduser()
    return data_dir if data_dir.is_absolute() else Path.home() / data_dir


def default_session_buckets(data_dir: Path) -> dict[str, str]:
    return {
        "sessions": str(data_dir / "sessions"),
        "checkpoints": str(data_dir / "checkpoints"),
        "handoffs": str(data_dir / "handoffs"),
        "test": str(data_dir / "test"),
    }


@dataclass(frozen=True, slots=True)
class ReflectionAdapterSettings:
    database_path: Path
    collection_name: str = "default"
    embedding_dim: int = 384
    distance_metric: str = "cosine"
    enable_vss: bool = True
    threads: int = 4
    memory_limit: str = "2GB"
    enable_embeddings: bool = True

    @classmethod
    def from_settings(cls) -> ReflectionAdapterSettings:
        data_dir = _resolve_data_dir()
        return cls(database_path=data_dir / "reflection.duckdb")


@dataclass(frozen=True, slots=True)
class KnowledgeGraphAdapterSettings:
    database_path: Path
    graph_name: str = "session_mgmt_graph"
    nodes_table: str = "kg_entities"
    edges_table: str = "kg_relationships"
    install_extensions: tuple[str, ...] = ("duckpgq",)

    @classmethod
    def from_settings(cls) -> KnowledgeGraphAdapterSettings:
        data_dir = _resolve_data_dir()
        return cls(database_path=data_dir / "knowledge_graph.duckdb")


@dataclass(frozen=True, slots=True)
class StorageAdapterSettings:
    default_backend: str = "file"
    buckets: dict[str, str] = field(default_factory=dict)
    local_path: Path = field(default_factory=_resolve_data_dir)

    @classmethod
    def from_settings(cls) -> StorageAdapterSettings:
        data_dir = _resolve_data_dir()
        return cls(
            buckets=default_session_buckets(data_dir),
            local_path=data_dir,
        )


@dataclass(frozen=True, slots=True)
class CacheAdapterSettings:
    chunk_cache_ttl_seconds: int = 3600
    history_cache_ttl_seconds: int = 300
