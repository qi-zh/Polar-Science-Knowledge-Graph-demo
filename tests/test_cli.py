"""Offline acceptance tests for the small construction demonstration."""

import builtins
import contextlib
import csv
import io
import json
from pathlib import Path
import runpy
import socket
import sys
import tempfile
import unittest
from unittest import mock


DEMO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILES = {
    "records.csv",
    "knowledge.csv",
    "anchors.csv",
    "scientific_relations.csv",
    "graph.json",
    "validation.json",
}


class OfflineBuildTests(unittest.TestCase):
    def run_build(self, output_dir):
        original_import = builtins.__import__

        def import_without_neo4j(name, *args, **kwargs):
            if name == "neo4j" or name.startswith("neo4j."):
                raise AssertionError("An offline build must not load the Neo4j driver")
            return original_import(name, *args, **kwargs)

        with (
            mock.patch.object(
                sys,
                "argv",
                [str(DEMO_ROOT / "main.py"), "build", "--output-dir", str(output_dir)],
            ),
            mock.patch.object(builtins, "__import__", side_effect=import_without_neo4j),
            mock.patch.object(socket, "socket", side_effect=AssertionError("Network disabled")),
            mock.patch.object(
                socket, "create_connection", side_effect=AssertionError("Network disabled")
            ),
            mock.patch.object(
                socket, "getaddrinfo", side_effect=AssertionError("Network disabled")
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            try:
                runpy.run_path(str(DEMO_ROOT / "main.py"), run_name="__main__")
            except SystemExit as exc:
                self.assertIn(exc.code, (None, 0), "The offline CLI failed")

    def test_offline_cli_builds_the_complete_discovery_path(self):
        with tempfile.TemporaryDirectory(prefix="pskg-demo-cli-") as temporary:
            output_dir = Path(temporary) / "output"
            self.run_build(output_dir)
            self.assertTrue(OUTPUT_FILES.issubset({p.name for p in output_dir.iterdir()}))
            graph = json.loads((output_dir / "graph.json").read_text(encoding="utf-8"))

            self.assertEqual(len(graph["nodes"]), 4)
            self.assertEqual(len(graph["relationships"]), 3)
            nodes = {node["id"]: node for node in graph["nodes"]}
            self.assertEqual(len(nodes), 4)
            records = [node for node in nodes.values() if node["node_type"] == "record"]
            knowledge = [node for node in nodes.values() if node["node_type"] == "knowledge"]
            self.assertEqual(len(records), 2)
            self.assertEqual(len(knowledge), 2)

            for record in records:
                self.assertTrue(record["name"])
                self.assertTrue(record["platform_name"])
                self.assertTrue(record["source_record_key"])
                self.assertTrue(record["record_unit"])
                self.assertTrue(record["source_url"].startswith("https://"))

            specimen = next(node for node in records if "BiologicalSpecimen" in node["labels"])
            survey = next(node for node in records if "PopulationObservation" in node["labels"])
            self.assertEqual(
                {node["id"] for node in knowledge},
                {"demo_organism_6819", "demo_organism_9238"},
            )
            actual_edges = {
                (edge["source_id"], edge["type"], edge["target_id"], edge["kind"])
                for edge in graph["relationships"]
            }
            self.assertEqual(
                actual_edges,
                {
                    (
                        specimen["id"],
                        "SPECIMEN_OF_ORGANISM",
                        "demo_organism_6819",
                        "anchoring",
                    ),
                    (
                        survey["id"],
                        "OBSERVES_ORGANISM",
                        "demo_organism_9238",
                        "anchoring",
                    ),
                    (
                        "demo_organism_9238",
                        "PREYS_ON",
                        "demo_organism_6819",
                        "scientific",
                    ),
                },
            )
            for edge in graph["relationships"]:
                self.assertIn(edge["source_id"], nodes)
                self.assertIn(edge["target_id"], nodes)
                if edge["kind"] == "scientific":
                    self.assertTrue(edge["source_name"].strip())
                    self.assertTrue(edge["source_url"].strip())

            for filename, expected_rows in (
                ("records.csv", 2),
                ("knowledge.csv", 2),
                ("anchors.csv", 2),
                ("scientific_relations.csv", 1),
            ):
                with self.subTest(filename=filename):
                    with (output_dir / filename).open(encoding="utf-8", newline="") as stream:
                        self.assertEqual(len(list(csv.DictReader(stream))), expected_rows)

    def test_repeated_builds_are_byte_for_byte_deterministic(self):
        with tempfile.TemporaryDirectory(prefix="pskg-demo-repeat-") as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            self.run_build(first)
            first_bytes = {name: (first / name).read_bytes() for name in OUTPUT_FILES}
            self.run_build(first)
            self.run_build(second)
            for filename, expected in first_bytes.items():
                with self.subTest(filename=filename):
                    self.assertEqual((first / filename).read_bytes(), expected)
                    self.assertEqual((second / filename).read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
