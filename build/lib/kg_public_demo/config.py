from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ProjectPaths:
    root_dir: Path
    input_file: Path
    output_dir: Path
    cache_dir: Path

    @property
    def organism_file(self) -> Path:
        return self.output_dir / "organism.csv"

    @property
    def anchor_file(self) -> Path:
        return self.output_dir / "anchor.csv"

    @property
    def habitat_file(self) -> Path:
        return self.output_dir / "habitat.csv"

    @property
    def globi_file(self) -> Path:
        return self.output_dir / "globi.csv"

    @property
    def inhabit_file(self) -> Path:
        return self.output_dir / "inhabit.csv"

    @property
    def source_copy_file(self) -> Path:
        return self.output_dir / "source_records.csv"

    @property
    def ncbi_cache_file(self) -> Path:
        return self.cache_dir / "ncbi_taxonomy.json"

    @property
    def globi_cache_file(self) -> Path:
        return self.cache_dir / "globi_interactions.json"

    @property
    def worms_cache_file(self) -> Path:
        return self.cache_dir / "worms_records.json"


@dataclass(frozen=True)
class RuntimeSettings:
    mode: str
    refresh_cache: bool
    import_to_neo4j: bool
    reset_db: bool
    http_delay_seconds: float
    neo4j_wait_seconds: int


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    username: str
    password: str
    database: str
