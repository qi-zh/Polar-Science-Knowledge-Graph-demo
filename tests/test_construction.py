"""Contract tests for confirmed identity and label-guided graph construction."""

from copy import deepcopy
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


DEMO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO_ROOT / "src"))

from pskg_demo.construction import DemoError, build_anchors, build_demo, validate_graph
from pskg_demo.mocks import mock_globi_interactions, mock_ncbi_lookup


class ConstructionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pskg-demo-inputs-")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        for directory in ("data", "rules"):
            shutil.copytree(DEMO_ROOT / directory, self.project / directory)
        self.rules = self.read_json("rules/label_rules.json")
        self.graph, self.report = build_demo(self.project, emit=lambda _: None)

    def read_json(self, relative):
        return json.loads((self.project / relative).read_text(encoding="utf-8"))

    def write_json(self, relative, value):
        (self.project / relative).write_text(json.dumps(value), encoding="utf-8")

    def change_csv(self, relative, transform):
        path = self.project / relative
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        transform(rows)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def records_and_knowledge(self):
        return (
            [node for node in self.graph["nodes"] if node["node_type"] == "record"],
            [node for node in self.graph["nodes"] if node["node_type"] == "knowledge"],
        )

    def test_validated_report_has_expected_graph_and_path_counts(self):
        self.assertEqual(self.report["status"], "passed")
        self.assertEqual(
            {key: self.report[key] for key in (
                "node_count", "record_count", "knowledge_count", "relationship_count",
                "anchoring_count", "scientific_relation_count", "figure3_path_count",
            )},
            {
                "node_count": 4,
                "record_count": 2,
                "knowledge_count": 2,
                "relationship_count": 3,
                "anchoring_count": 2,
                "scientific_relation_count": 1,
                "figure3_path_count": 1,
            },
        )

    def test_actual_label_selects_rule_despite_record_name_and_platform(self):
        records, knowledge = self.records_and_knowledge()
        specimen = next(node for node in records if "BiologicalSpecimen" in node["labels"])
        specimen["name"] = "PopulationObservation survey"
        specimen["platform_name"] = "ADS"
        anchors = build_anchors([specimen], knowledge, self.rules)
        self.assertEqual([edge["type"] for edge in anchors], ["SPECIMEN_OF_ORGANISM"])
        specimen["labels"] = ["PopulationObservation"]
        anchors = build_anchors([specimen], knowledge, self.rules)
        self.assertEqual([edge["type"] for edge in anchors], ["OBSERVES_ORGANISM"])

    def test_configured_rule_relationship_is_executed(self):
        records, knowledge = self.records_and_knowledge()
        self.rules["BiologicalSpecimen"]["relationship_type"] = "EXAMPLE_SPECIMEN_ANCHOR"
        anchors = build_anchors(records, knowledge, self.rules)
        self.assertIn("EXAMPLE_SPECIMEN_ANCHOR", {edge["type"] for edge in anchors})
        self.assertNotIn("SPECIMEN_OF_ORGANISM", {edge["type"] for edge in anchors})
        self.graph["relationships"] = anchors + [
            edge for edge in self.graph["relationships"] if edge["kind"] == "scientific"
        ]
        validate_graph(self.graph, self.rules, require_path=False)

    def test_every_applicable_record_label_generates_its_anchor(self):
        mappings = self.read_json("rules/source_mappings.json")
        mappings["AMIDER"]["record_label"] = ["BiologicalSpecimen", "SecondaryObservation"]
        self.rules["SecondaryObservation"] = {
            "node_type": "record",
            "anchor_field": "subject_organism_node_id",
            "target_label": "Organism",
            "relationship_type": "SECONDARY_OBSERVATION_OF",
        }
        self.write_json("rules/source_mappings.json", mappings)
        self.write_json("rules/label_rules.json", self.rules)
        graph, report = build_demo(self.project, emit=lambda _: None)
        specimen_edges = [
            edge for edge in graph["relationships"]
            if edge["source_id"] == "demo_record_amider_A00850-0001"
        ]
        self.assertEqual(
            {edge["type"] for edge in specimen_edges},
            {"SPECIMEN_OF_ORGANISM", "SECONDARY_OBSERVATION_OF"},
        )
        self.assertEqual({edge["target_id"] for edge in specimen_edges}, {"demo_organism_6819"})
        self.assertEqual(report["anchoring_count"], 3)
        graph["relationships"] = [
            edge for edge in graph["relationships"] if edge["type"] != "SECONDARY_OBSERVATION_OF"
        ]
        with self.assertRaises(DemoError):
            validate_graph(graph, self.rules)

    def test_unknown_label_is_rejected(self):
        mappings = self.read_json("rules/source_mappings.json")
        mappings["AMIDER"]["record_label"] = "UnregisteredSpecimen"
        self.write_json("rules/source_mappings.json", mappings)
        with self.assertRaisesRegex(DemoError, "Unknown label"):
            build_demo(self.project, emit=lambda _: None)

    def test_organism_rule_rejects_unconfigured_knowledge_providers(self):
        for field in ("identity_source", "interaction_source"):
            with self.subTest(field=field):
                rules = deepcopy(self.rules)
                rules["Organism"][field] = "Unconfigured provider"
                self.write_json("rules/label_rules.json", rules)
                with self.assertRaises(DemoError):
                    build_demo(self.project, emit=lambda _: None)

    def test_rule_excluding_preys_on_cannot_build_the_figure3_path(self):
        self.rules["Organism"]["scientific_relations"] = ["EATS"]
        responses = self.read_json("data/mock_globi.json")
        selected = mock_globi_interactions(
            {"6819", "9238"}, set(self.rules["Organism"]["scientific_relations"]), responses
        )
        self.assertEqual(selected, [])
        self.write_json("rules/label_rules.json", self.rules)
        with self.assertRaisesRegex(DemoError, "Figure 3.*missing"):
            build_demo(self.project, emit=lambda _: None)

    def test_identity_requires_explicit_confirmed_review(self):
        self.change_csv(
            "data/reviewed_identity_mappings.csv",
            lambda rows: rows[0].update(review_status="candidate"),
        )
        with self.assertRaisesRegex(DemoError, "confirmed"):
            build_demo(self.project, emit=lambda _: None)

    def test_missing_review_does_not_create_an_unanchored_record(self):
        self.change_csv("data/reviewed_identity_mappings.csv", lambda rows: rows.pop(0))
        with self.assertRaisesRegex(DemoError, "No reviewed identity"):
            build_demo(self.project, emit=lambda _: None)

    def test_missing_required_source_field_fails(self):
        self.change_csv("data/amider_specimen.csv", lambda rows: rows[0].update(source_url=""))
        with self.assertRaisesRegex(DemoError, "source_url"):
            build_demo(self.project, emit=lambda _: None)

    def test_changed_source_name_cannot_reuse_an_unrelated_review(self):
        self.change_csv(
            "data/amider_specimen.csv",
            lambda rows: rows[0].update(scientific_name="Pygoscelis adeliae"),
        )
        with self.assertRaisesRegex(DemoError, "disagrees"):
            build_demo(self.project, emit=lambda _: None)

    def test_identity_mock_must_match_the_reviewed_tax_id(self):
        identities = self.read_json("data/mock_ncbi.json")
        identities["6819"]["tax_id"] = "9238"
        self.write_json("data/mock_ncbi.json", identities)
        with self.assertRaisesRegex(DemoError, "TaxID"):
            build_demo(self.project, emit=lambda _: None)

    def test_missing_knowledge_response_fails_before_graph_publication(self):
        identities = self.read_json("data/mock_ncbi.json")
        del identities["6819"]
        self.write_json("data/mock_ncbi.json", identities)
        with self.assertRaisesRegex(DemoError, "No simulated NCBI"):
            build_demo(self.project, emit=lambda _: None)

    def test_missing_relationship_endpoint_is_rejected(self):
        self.graph["relationships"][0]["target_id"] = "demo_organism_missing"
        with self.assertRaisesRegex(DemoError, "endpoint"):
            validate_graph(self.graph, self.rules)

    def test_record_without_its_required_anchor_is_rejected(self):
        self.graph["relationships"] = [
            edge for edge in self.graph["relationships"] if edge["type"] != "SPECIMEN_OF_ORGANISM"
        ]
        with self.assertRaisesRegex(DemoError, "anchors"):
            validate_graph(self.graph, self.rules)

    def test_record_with_a_saved_unknown_identity_is_rejected(self):
        records, _ = self.records_and_knowledge()
        records[0]["organism_node_id"] = "demo_organism_missing"
        with self.assertRaisesRegex(DemoError, "confirmed permitted anchor"):
            validate_graph(self.graph, self.rules)

    def test_reversing_an_anchor_is_rejected(self):
        edge = next(edge for edge in self.graph["relationships"] if edge["kind"] == "anchoring")
        edge["source_id"], edge["target_id"] = edge["target_id"], edge["source_id"]
        with self.assertRaisesRegex(DemoError, "Record to Knowledge"):
            validate_graph(self.graph, self.rules)

    def test_reversing_prey_direction_does_not_pass_the_expected_path(self):
        edge = next(edge for edge in self.graph["relationships"] if edge["kind"] == "scientific")
        edge["source_id"], edge["target_id"] = edge["target_id"], edge["source_id"]
        with self.assertRaisesRegex(DemoError, "Figure 3"):
            validate_graph(self.graph, self.rules)

    def test_scientific_relation_requires_its_source_fields(self):
        edge = next(edge for edge in self.graph["relationships"] if edge["kind"] == "scientific")
        del edge["source_name"]
        with self.assertRaisesRegex(DemoError, "source_name"):
            validate_graph(self.graph, self.rules)

    def test_duplicate_node_or_relation_is_rejected(self):
        for collection in ("nodes", "relationships"):
            with self.subTest(collection=collection):
                graph = deepcopy(self.graph)
                graph[collection].append(deepcopy(graph[collection][0]))
                with self.assertRaisesRegex(DemoError, "Duplicate"):
                    validate_graph(graph, self.rules)


class MockKnowledgeTests(unittest.TestCase):
    def test_identity_responses_are_returned_without_mutating_the_source(self):
        responses = {"6819": {"tax_id": "6819", "scientific_name": "Euphausia superba"}}
        result = mock_ncbi_lookup("6819", responses)
        result["scientific_name"] = "Changed by caller"
        self.assertEqual(responses["6819"]["scientific_name"], "Euphausia superba")
        with self.assertRaises(ValueError):
            mock_ncbi_lookup("unknown", responses)

    def test_interactions_keep_direction_and_stay_within_confirmed_entities(self):
        interaction = {
            "source_tax_id": "9238",
            "target_tax_id": "6819",
            "relationship_type": "PREYS_ON",
            "source_name": "GloBI",
            "source_url": "https://www.globalbioticinteractions.org/",
        }
        outside = dict(interaction, target_tax_id="999999")
        other_relation = dict(interaction, relationship_type="EATS")
        responses = [interaction, outside, other_relation]
        result = mock_globi_interactions({"6819", "9238"}, {"PREYS_ON"}, responses)
        self.assertEqual(result, [interaction])
        self.assertEqual((result[0]["source_tax_id"], result[0]["target_tax_id"]), ("9238", "6819"))
        result[0]["source_tax_id"] = "6819"
        self.assertEqual(interaction["source_tax_id"], "9238")

    def test_missing_interaction_fields_are_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            mock_globi_interactions({"6819", "9238"}, {"PREYS_ON"}, [{"source_tax_id": "9238"}])


if __name__ == "__main__":
    unittest.main()
