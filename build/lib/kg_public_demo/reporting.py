from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kg_public_demo.pipeline import PipelineArtifacts


@dataclass(frozen=True)
class GraphSummary:
    total_nodes: int
    total_relationships: int
    label_counts: list[tuple[str, int]]
    relation_counts: list[tuple[str, int]]


def print_output_summary(artifacts: PipelineArtifacts) -> None:
    print("\nGenerated CSV artifacts")
    print(f"  - source records: {artifacts.paths.source_copy_file}")
    print(f"  - organisms:      {artifacts.paths.organism_file}")
    print(f"  - anchors:        {artifacts.paths.anchor_file}")
    print(f"  - habitats:       {artifacts.paths.habitat_file}")
    print(f"  - GloBI edges:    {artifacts.paths.globi_file}")
    print(f"  - habitat edges:  {artifacts.paths.inhabit_file}")

    print("\nArtifact counts")
    print(f"  - specimen records: {len(artifacts.specimens)}")
    print(f"  - organism nodes:   {len(artifacts.organisms)}")
    print(f"  - habitat nodes:    {len(artifacts.habitats)}")
    print(f"  - anchor edges:     {len(artifacts.anchor_relations)}")
    print(f"  - GloBI edges:      {len(artifacts.globi_relations)}")
    print(f"  - habitat edges:    {len(artifacts.inhabit_relations)}")


def print_neo4j_summary(summary: GraphSummary) -> None:
    print("\nNeo4j graph summary")
    print(f"  - total nodes: {summary.total_nodes}")
    print(f"  - total edges: {summary.total_relationships}")

    print("\nNode labels")
    for label, count in summary.label_counts:
        print(f"  - {label}: {count}")

    print("\nRelationship types")
    for relation_type, count in summary.relation_counts:
        print(f"  - {relation_type}: {count}")
