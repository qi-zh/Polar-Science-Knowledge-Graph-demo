"""Import only into the isolated Compose demo; never clear an existing graph."""

import json
import os
import re

from . import DEMO_ID
from .construction import DemoError


def connection_settings(environ=None) -> dict:
    env = os.environ if environ is None else environ
    if env.get("PSKG_DEMO_CONTAINER") != "1":
        raise DemoError("Neo4j import is available only through the dedicated Docker demo")
    if (env.get("NEO4J_URI") != "bolt://neo4j:7687"
            or env.get("NEO4J_USER") != "neo4j"
            or env.get("NEO4J_DATABASE") != "neo4j"):
        raise DemoError("Refusing a database endpoint outside the fixed demo configuration")
    if not env.get("NEO4J_PASSWORD"):
        raise DemoError("The demo database password is missing")
    return dict(uri=env["NEO4J_URI"], user=env["NEO4J_USER"],
                password=env["NEO4J_PASSWORD"], database=env["NEO4J_DATABASE"])


def expected_state(graph: dict) -> dict:
    nodes, edges = [], []
    for node in graph["nodes"]:
        if any(not re.fullmatch(r"[A-Z][A-Za-z0-9]*", label) for label in node["labels"]):
            raise DemoError("Unsafe graph label")
        props = {key: value for key, value in node.items() if key != "labels"}
        props["demo_id"] = DEMO_ID
        nodes.append(dict(labels=sorted(node["labels"]), props=props))
    for edge in graph["relationships"]:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", edge["type"]):
            raise DemoError("Unsafe relationship name")
        props = {key: value for key, value in edge.items()
                 if key not in {"source_id", "target_id", "type"}}
        props["demo_id"] = DEMO_ID
        edges.append(dict(source_id=edge["source_id"], target_id=edge["target_id"],
                          type=edge["type"], props=props))
    return dict(nodes=nodes, relationships=edges)


def canonical_state(state: dict) -> tuple:
    return tuple(tuple(sorted(json.dumps(row, sort_keys=True, ensure_ascii=False)
                              for row in state[key]))
                 for key in ("nodes", "relationships"))


def read_state(transaction) -> dict:
    nodes = [dict(labels=sorted(row["labels"]), props=dict(row["props"]))
             for row in transaction.run("MATCH (n) RETURN labels(n) AS labels, properties(n) AS props")]
    # An empty node set also means no relationships. Avoid referring to the
    # not-yet-created id property while inspecting a fresh database.
    if not nodes:
        return dict(nodes=[], relationships=[])
    edges = [dict(source_id=row["source_id"], target_id=row["target_id"],
                  type=row["type"], props=dict(row["props"]))
             for row in transaction.run(
                 "MATCH (a)-[r]->(b) RETURN a.id AS source_id, b.id AS target_id, "
                 "type(r) AS type, properties(r) AS props")]
    return dict(nodes=nodes, relationships=edges)


def import_transaction(transaction, graph: dict) -> str:
    """Create an empty demo graph or verify an exact prior run, without deletion."""
    expected = expected_state(graph)
    actual = read_state(transaction)
    if actual["nodes"] or actual["relationships"]:
        if canonical_state(actual) != canonical_state(expected):
            raise DemoError("The database differs from this demo. No graph changes were made. "
                            "Inspect it first; ./reset_demo.sh --confirm resets only the demo volume.")
        return "existing sample graph verified; no graph changes needed"
    for node in sorted(expected["nodes"],
                       key=lambda n: (n["props"]["node_type"] != "knowledge", n["props"]["id"])):
        labels = ":".join(node["labels"])
        row = transaction.run(f"CREATE (n:{labels}) SET n = $props RETURN count(n) AS created",
                              props=node["props"]).single()
        if row is None or row["created"] != 1:
            raise DemoError("Node creation failed its count check")
    for edge in sorted(expected["relationships"],
                       key=lambda e: (e["props"]["kind"], e["source_id"], e["type"], e["target_id"])):
        row = transaction.run(
            f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
            f"CREATE (a)-[r:{edge['type']}]->(b) SET r = $props RETURN count(r) AS created",
            source_id=edge["source_id"], target_id=edge["target_id"], props=edge["props"],
        ).single()
        if row is None or row["created"] != 1:
            raise DemoError("Relationship creation did not find exactly one pair of endpoints")
    if canonical_state(read_state(transaction)) != canonical_state(expected):
        raise DemoError("Neo4j graph contents failed the precommit check")
    return "sample graph created and checked"


def import_graph(graph: dict) -> str:
    settings = connection_settings()
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise DemoError("The Neo4j driver is supplied by the Docker image") from exc
    try:
        with GraphDatabase.driver(settings["uri"], auth=(settings["user"], settings["password"]),
                                  connection_timeout=10, max_transaction_retry_time=0) as driver:
            driver.verify_connectivity()
            with driver.session(database=settings["database"]) as session:
                with session.begin_transaction(timeout=60) as tx:
                    status = import_transaction(tx, graph)
                    tx.commit()
                # A fresh transaction independently verifies the committed contents.
                with session.begin_transaction(timeout=30) as tx:
                    if canonical_state(read_state(tx)) != canonical_state(expected_state(graph)):
                        raise DemoError("Neo4j postcommit readback differs from the expected graph")
                return status + "; committed contents verified"
    except DemoError:
        raise
    except Exception as exc:
        raise DemoError("Neo4j import or verification failed. Inspect the demo database before "
                        f"retrying; commit status may be uncertain ({type(exc).__name__}).") from exc
