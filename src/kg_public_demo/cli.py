from __future__ import annotations

import argparse
import os
from pathlib import Path

from kg_public_demo.config import (
    Neo4jSettings,
    ProjectPaths,
    RuntimeSettings,
    default_project_root,
)
from kg_public_demo.pipeline import run_pipeline
from kg_public_demo.reporting import print_neo4j_summary, print_output_summary


def build_parser() -> argparse.ArgumentParser:
    root_dir = default_project_root()
    parser = argparse.ArgumentParser(
        description="Public reproducibility demo for the PENGUIN KG onboarding workflow."
    )
    parser.add_argument(
        "--mode",
        choices=["frozen", "live"],
        default="frozen",
        help="Use bundled cache files or query external APIs live.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Refresh cached API responses while running in live mode.",
    )
    parser.add_argument(
        "--input-file",
        default=str(root_dir / "data" / "input" / "test_data.csv"),
        help="Path to the specimen input CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(root_dir / "outputs" / "current"),
        help="Directory where intermediate CSV artifacts will be written.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(root_dir / "data" / "cache"),
        help="Directory holding frozen API-response caches.",
    )
    parser.add_argument(
        "--skip-neo4j",
        action="store_true",
        help="Run the onboarding pipeline without loading Neo4j.",
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Delete all nodes and relationships from the target Neo4j database first.",
    )
    parser.add_argument(
        "--http-delay-seconds",
        type=float,
        default=0.4,
        help="Delay between live API requests.",
    )
    parser.add_argument(
        "--neo4j-wait-seconds",
        type=int,
        default=90,
        help="How long to wait for Neo4j before failing.",
    )
    parser.add_argument(
        "--neo4j-uri",
        default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j Bolt URI.",
    )
    parser.add_argument(
        "--neo4j-username",
        default=os.environ.get("NEO4J_USERNAME", "neo4j"),
        help="Neo4j username.",
    )
    parser.add_argument(
        "--neo4j-password",
        default=os.environ.get("NEO4J_PASSWORD", "demo-password"),
        help="Neo4j password.",
    )
    parser.add_argument(
        "--neo4j-database",
        default=os.environ.get("NEO4J_DATABASE", "neo4j"),
        help="Neo4j database name.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mode == "frozen" and args.refresh_cache:
        parser.error("--refresh-cache can only be used with --mode live")

    paths = ProjectPaths(
        root_dir=default_project_root(),
        input_file=Path(args.input_file).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        cache_dir=Path(args.cache_dir).resolve(),
    )
    runtime = RuntimeSettings(
        mode=args.mode,
        refresh_cache=args.refresh_cache,
        import_to_neo4j=not args.skip_neo4j,
        reset_db=args.reset_db,
        http_delay_seconds=args.http_delay_seconds,
        neo4j_wait_seconds=args.neo4j_wait_seconds,
    )

    artifacts = run_pipeline(paths=paths, runtime=runtime)
    print_output_summary(artifacts)

    if args.skip_neo4j:
        print("\nNeo4j import skipped.")
        return 0

    from kg_public_demo.neo4j_loader import Neo4jLoader

    neo4j_settings = Neo4jSettings(
        uri=args.neo4j_uri,
        username=args.neo4j_username,
        password=args.neo4j_password,
        database=args.neo4j_database,
    )
    loader = Neo4jLoader(neo4j_settings)

    try:
        loader.wait_until_available(runtime.neo4j_wait_seconds)
        if runtime.reset_db:
            loader.reset_database()
        loader.ensure_constraints(
            [specimen.label for specimen in artifacts.specimens]
            + ["Organism", "HabitatType"]
        )
        loader.load_nodes(
            specimens=artifacts.specimens,
            organisms=artifacts.organisms,
            habitats=artifacts.habitats,
        )
        loader.load_relationships(
            artifacts.anchor_relations
            + artifacts.globi_relations
            + artifacts.inhabit_relations
        )
        print_neo4j_summary(loader.summarize_graph())
    finally:
        loader.close()

    return 0
