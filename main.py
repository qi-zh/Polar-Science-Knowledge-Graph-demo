#!/usr/bin/env python3
"""Run the Figure 3 example with optional import into its dedicated Neo4j."""

import argparse
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from pskg_demo.construction import (DemoError, build_demo, print_summary, write_outputs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="Build from local samples and simulated knowledge responses")
    build.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "outputs/current")
    build.add_argument("--import-neo4j", action="store_true",
                       help="Import into the isolated Docker demo database")
    args = parser.parse_args()
    try:
        print("PSKG Figure 3 construction demo", flush=True)
        print("Knowledge access: SIMULATED NCBI Taxonomy and GloBI responses.", flush=True)
        graph, report = build_demo(PROJECT_DIR, emit=lambda s: print(s, flush=True))
        print("[7/7] Publish the checked graph and stage tables", flush=True)
        # Finish local file writes before making any database changes.
        write_outputs(graph, report, args.output_dir)
        print(f"  Local graph artifacts written to: {args.output_dir.resolve()}", flush=True)
        if args.import_neo4j:
            from pskg_demo.neo4j_io import import_graph
            print("  Import into the dedicated Neo4j demo and verify its contents.", flush=True)
            status = import_graph(graph)
            print(f"  Neo4j: {status}", flush=True)
        print_summary(graph, report)
        if args.import_neo4j:
            print("Neo4j remains available. Run ./query_demo.sh to explore the graph.")
        else:
            print("Local construction completed. Run ./run_demo.sh for Neo4j import and interaction.")
        return 0
    except (DemoError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
