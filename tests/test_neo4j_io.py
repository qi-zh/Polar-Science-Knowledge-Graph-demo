"""Importer safety tests using an in-memory transaction double, never Neo4j."""

from copy import deepcopy
import os
from pathlib import Path
import re
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


DEMO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO_ROOT / "src"))

from pskg_demo.construction import DemoError, build_demo
from pskg_demo.neo4j_io import (
    canonical_state, connection_settings, expected_state, import_graph, import_transaction,
    read_state,
)


TEST_ENVIRONMENT = {
    "PSKG_DEMO_CONTAINER": "1",
    "NEO4J_URI": "bolt://neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_DATABASE": "neo4j",
    "NEO4J_PASSWORD": "unit-test-value-no-service",
}


class FakeResult(list):
    def single(self):
        return self[0] if self else None


class FakeTransaction:
    def __init__(self, database):
        self.database = database
        self.state = deepcopy(database.state)
        self.writes = 0
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, query, **parameters):
        if query.startswith("MATCH (n) RETURN"):
            nodes = deepcopy(self.state["nodes"])
            if self.writes and self.database.corrupt_precommit and nodes:
                nodes[0]["props"]["name"] = "Unexpected staged value"
            return FakeResult(nodes)
        if query.startswith("MATCH (a)-[r]->(b) RETURN"):
            return FakeResult(deepcopy(self.state["relationships"]))
        node_create = re.search(r"CREATE \(n:([A-Za-z0-9:]+)\)", query)
        if node_create:
            self.writes += 1
            self.state["nodes"].append({
                "labels": sorted(node_create.group(1).split(":")),
                "props": deepcopy(parameters["props"]),
            })
            return FakeResult([{"created": 1}])
        relationship_create = re.search(r"CREATE \(a\)-\[r:([A-Z0-9_]+)\]->\(b\)", query)
        if relationship_create:
            self.writes += 1
            sources = [node for node in self.state["nodes"]
                       if node["props"]["id"] == parameters["source_id"]]
            targets = [node for node in self.state["nodes"]
                       if node["props"]["id"] == parameters["target_id"]]
            created = len(sources) * len(targets)
            if self.database.fail_edge_count:
                created = 0
            if created == 1:
                self.state["relationships"].append({
                    "source_id": parameters["source_id"],
                    "target_id": parameters["target_id"],
                    "type": relationship_create.group(1),
                    "props": deepcopy(parameters["props"]),
                })
            return FakeResult([{"created": created}])
        raise AssertionError(f"Unexpected query in transaction double: {query}")

    def commit(self):
        self.database.state = deepcopy(self.state)
        self.database.commits += 1
        self.committed = True
        if self.database.corrupt_postcommit:
            self.database.state["nodes"][0]["props"]["name"] = "Unexpected committed value"


class FakeDatabase:
    def __init__(self, state=None):
        self.state = deepcopy(state or {"nodes": [], "relationships": []})
        self.transactions = []
        self.commits = 0
        self.fail_edge_count = False
        self.corrupt_precommit = False
        self.corrupt_postcommit = False
        self.driver_calls = []
        self.connectivity_checked = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def driver(self, *args, **kwargs):
        self.driver_calls.append((args, kwargs))
        return self

    def verify_connectivity(self):
        self.connectivity_checked = True

    def session(self, **kwargs):
        if kwargs != {"database": "neo4j"}:
            raise AssertionError("Importer selected an unexpected database")
        return self

    def begin_transaction(self, **kwargs):
        transaction = FakeTransaction(self)
        self.transactions.append(transaction)
        return transaction


class Neo4jImportSafetyTests(unittest.TestCase):
    def setUp(self):
        self.graph, _ = build_demo(DEMO_ROOT, emit=lambda _: None)

    def import_with_fake_driver(self, database):
        module = SimpleNamespace(GraphDatabase=database)
        with (
            mock.patch.dict(os.environ, TEST_ENVIRONMENT, clear=True),
            mock.patch.dict(sys.modules, {"neo4j": module}),
            mock.patch.object(socket, "socket", side_effect=AssertionError("Network disabled")),
            mock.patch.object(
                socket, "create_connection", side_effect=AssertionError("Network disabled")
            ),
        ):
            return import_graph(self.graph)

    def test_connection_settings_reject_unapproved_environment(self):
        mutations = (
            ("PSKG_DEMO_CONTAINER", "0"),
            ("NEO4J_URI", "bolt://localhost:7687"),
            ("NEO4J_URI", "neo4j://example.org:7687"),
            ("NEO4J_USER", "another-user"),
            ("NEO4J_DATABASE", "another-database"),
            ("NEO4J_PASSWORD", ""),
        )
        for key, value in mutations:
            with self.subTest(field=key, value=value):
                environment = dict(TEST_ENVIRONMENT, **{key: value})
                with self.assertRaises(DemoError):
                    connection_settings(environment)

    def test_empty_state_returns_after_the_node_query(self):
        transaction = mock.Mock()
        transaction.run.return_value = FakeResult([])
        self.assertEqual(read_state(transaction), {"nodes": [], "relationships": []})
        transaction.run.assert_called_once_with(
            "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props"
        )

    def test_nonempty_state_still_reads_all_relationships(self):
        expected = expected_state(self.graph)
        transaction = FakeTransaction(FakeDatabase(expected))
        transaction.run = mock.Mock(wraps=transaction.run)
        self.assertEqual(canonical_state(read_state(transaction)), canonical_state(expected))
        self.assertEqual(transaction.run.call_count, 2)
        self.assertTrue(
            transaction.run.call_args_list[1].args[0].startswith("MATCH (a)-[r]->(b) RETURN")
        )

    def test_empty_database_is_created_then_read_back_before_and_after_commit(self):
        database = FakeDatabase()
        status = self.import_with_fake_driver(database)
        self.assertIn("committed contents verified", status)
        self.assertEqual(database.commits, 1)
        self.assertEqual(len(database.transactions), 2)
        self.assertEqual(database.transactions[0].writes, 7)
        self.assertEqual(database.transactions[1].writes, 0)
        self.assertEqual(canonical_state(database.state), canonical_state(expected_state(self.graph)))
        self.assertTrue(database.connectivity_checked)
        self.assertEqual(database.driver_calls[0][1]["max_transaction_retry_time"], 0)

    def test_exact_prior_graph_is_verified_without_writes(self):
        state = expected_state(self.graph)
        state["nodes"].reverse()
        state["relationships"].reverse()
        transaction = FakeTransaction(FakeDatabase(state))
        status = import_transaction(transaction, self.graph)
        self.assertIn("no graph changes needed", status)
        self.assertEqual(transaction.writes, 0)

    def test_changed_or_foreign_graph_is_refused_before_any_writes(self):
        for changed in (False, True):
            with self.subTest(changed_existing_demo=changed):
                state = expected_state(self.graph)
                if changed:
                    state["nodes"][0]["props"]["name"] = "A user's changed node"
                else:
                    state["nodes"].append({"labels": ["Unrelated"], "props": {"id": "external"}})
                database = FakeDatabase(state)
                before = deepcopy(database.state)
                with self.assertRaisesRegex(DemoError, "differs from this demo"):
                    self.import_with_fake_driver(database)
                self.assertEqual(database.state, before)
                self.assertEqual(database.commits, 0)
                self.assertEqual(database.transactions[0].writes, 0)

    def test_missing_endpoint_count_aborts_without_publishing_partial_nodes(self):
        database = FakeDatabase()
        database.fail_edge_count = True
        with self.assertRaisesRegex(DemoError, "exactly one pair"):
            self.import_with_fake_driver(database)
        self.assertEqual(database.commits, 0)
        self.assertEqual(database.state, {"nodes": [], "relationships": []})

    def test_precommit_mismatch_does_not_publish_the_graph(self):
        database = FakeDatabase()
        database.corrupt_precommit = True
        with self.assertRaisesRegex(DemoError, "precommit"):
            self.import_with_fake_driver(database)
        self.assertEqual(database.commits, 0)
        self.assertEqual(database.state, {"nodes": [], "relationships": []})

    def test_postcommit_mismatch_is_reported_as_failure(self):
        database = FakeDatabase()
        database.corrupt_postcommit = True
        with self.assertRaisesRegex(DemoError, "postcommit"):
            self.import_with_fake_driver(database)
        self.assertEqual(database.commits, 1)
        self.assertNotEqual(canonical_state(database.state), canonical_state(expected_state(self.graph)))

    def test_unsafe_dynamic_labels_and_relationship_names_are_rejected(self):
        for collection, field, value in (
            ("nodes", "labels", ["Organism) RETURN 1 //"]),
            ("relationships", "type", "PREYS_ON] DELETE r //"),
        ):
            with self.subTest(field=field):
                graph = deepcopy(self.graph)
                graph[collection][0][field] = value
                transaction = FakeTransaction(FakeDatabase())
                with self.assertRaisesRegex(DemoError, "Unsafe"):
                    import_transaction(transaction, graph)
                self.assertEqual(transaction.writes, 0)


if __name__ == "__main__":
    unittest.main()
