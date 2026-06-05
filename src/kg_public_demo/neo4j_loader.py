from __future__ import annotations

import re
import time
from collections import defaultdict

from neo4j import GraphDatabase

from kg_public_demo.config import Neo4jSettings
from kg_public_demo.models import HabitatRecord, OrganismRecord, RelationRecord, SpecimenRecord
from kg_public_demo.reporting import GraphSummary

VALID_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(identifier: str) -> str:
    if not VALID_IDENTIFIER_PATTERN.match(identifier):
        raise ValueError(f"Unsafe Cypher identifier: {identifier}")
    return identifier


class Neo4jLoader:
    def __init__(self, settings: Neo4jSettings):
        self.settings = settings
        self.driver = GraphDatabase.driver(
            settings.uri,
            auth=(settings.username, settings.password),
        )

    def close(self) -> None:
        self.driver.close()

    def wait_until_available(self, wait_seconds: int) -> None:
        deadline = time.time() + wait_seconds
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                self.driver.verify_connectivity()
                print(f"Connected to Neo4j at {self.settings.uri}")
                return
            except Exception as exc:  # pragma: no cover - exercised in integration use
                last_error = exc
                print("Waiting for Neo4j to become available...")
                time.sleep(3)

        raise RuntimeError("Neo4j did not become available in time.") from last_error

    def reset_database(self) -> None:
        print("Resetting Neo4j database...")
        with self.driver.session(database=self.settings.database) as session:
            session.run("MATCH (n) DETACH DELETE n").consume()

    def ensure_constraints(self, labels: list[str]) -> None:
        unique_labels = sorted(set(labels))
        with self.driver.session(database=self.settings.database) as session:
            for label in unique_labels:
                safe_label = _validate_identifier(label)
                constraint_name = _validate_identifier(f"{safe_label.lower()}_id_unique")
                session.run(
                    f"""
                    CREATE CONSTRAINT {constraint_name}
                    IF NOT EXISTS
                    FOR (n:{safe_label})
                    REQUIRE n.id IS UNIQUE
                    """
                ).consume()

    def load_nodes(
        self,
        specimens: list[SpecimenRecord],
        organisms: list[OrganismRecord],
        habitats: list[HabitatRecord],
    ) -> None:
        specimen_rows_by_label: dict[str, list[dict[str, str]]] = defaultdict(list)
        for specimen in specimens:
            specimen_rows_by_label[specimen.label].append(
                {
                    "id": specimen.id,
                    "name": specimen.name,
                    "url": specimen.url,
                    "scientific_name": specimen.scientific_name,
                    "node_type": "data",
                }
            )

        with self.driver.session(database=self.settings.database) as session:
            for label, rows in specimen_rows_by_label.items():
                safe_label = _validate_identifier(label)
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MERGE (n:{safe_label} {{id: row.id}})
                    SET n += row
                    """,
                    rows=rows,
                ).consume()

            organism_rows = [
                {
                    "id": organism.id,
                    "name": organism.scientific_name,
                    "scientific_name": organism.scientific_name,
                    "common_name": organism.common_name,
                    "url": organism.url,
                    "tax_id": organism.tax_id,
                    "rank": organism.rank,
                    "node_type": "knowledge",
                }
                for organism in organisms
            ]
            session.run(
                """
                UNWIND $rows AS row
                MERGE (n:Organism {id: row.id})
                SET n += row
                """,
                rows=organism_rows,
            ).consume()

            habitat_rows = [
                {
                    "id": habitat.id,
                    "name": habitat.name,
                    "node_type": "knowledge",
                }
                for habitat in habitats
            ]
            session.run(
                """
                UNWIND $rows AS row
                MERGE (n:HabitatType {id: row.id})
                SET n += row
                """,
                rows=habitat_rows,
            ).consume()

    def load_relationships(self, relations: list[RelationRecord]) -> None:
        rows_by_type: dict[str, list[dict[str, object]]] = defaultdict(list)
        for relation in relations:
            rows_by_type[relation.relation_type].append(
                {
                    "from_id": relation.from_id,
                    "to_id": relation.to_id,
                    "properties": {"url": relation.url} if relation.url else {},
                }
            )

        with self.driver.session(database=self.settings.database) as session:
            for relation_type, rows in rows_by_type.items():
                safe_relation_type = _validate_identifier(relation_type)
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MATCH (a {{id: row.from_id}})
                    MATCH (b {{id: row.to_id}})
                    MERGE (a)-[r:{safe_relation_type}]->(b)
                    SET r += row.properties
                    """,
                    rows=rows,
                ).consume()

    def summarize_graph(self) -> GraphSummary:
        with self.driver.session(database=self.settings.database) as session:
            label_rows = session.run(
                """
                MATCH (n)
                UNWIND labels(n) AS label
                RETURN label, count(*) AS count
                ORDER BY label
                """
            ).data()
            relation_rows = session.run(
                """
                MATCH ()-[r]->()
                RETURN type(r) AS relation_type, count(*) AS count
                ORDER BY relation_type
                """
            ).data()
            total_nodes = session.run(
                "MATCH (n) RETURN count(n) AS total_nodes"
            ).single()["total_nodes"]
            total_relationships = session.run(
                "MATCH ()-[r]->() RETURN count(r) AS total_relationships"
            ).single()["total_relationships"]

        return GraphSummary(
            total_nodes=total_nodes,
            total_relationships=total_relationships,
            label_counts=[(row["label"], row["count"]) for row in label_rows],
            relation_counts=[
                (row["relation_type"], row["count"]) for row in relation_rows
            ],
        )
