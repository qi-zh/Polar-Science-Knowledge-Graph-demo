"""Source adaptation, reviewed identities, rule-guided assembly and checks."""

import csv
import json
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from .mocks import mock_globi_interactions, mock_ncbi_lookup


class DemoError(ValueError):
    """An input or graph violates the small example's explicit contract."""


def read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise DemoError(f"Missing or duplicate CSV headers: {path.name}")
        rows = list(reader)
    if not rows or any(None in row or None in row.values() for row in rows):
        raise DemoError(f"Empty or malformed CSV: {path.name}")
    return rows


def require_text(obj: dict, *keys: str) -> None:
    if not isinstance(obj, dict):
        raise DemoError("Expected a field-value object")
    for key in keys:
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            raise DemoError(f"Missing non-empty field: {key}")


def require_url(value: str) -> None:
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        valid = False
    if not valid or any(char.isspace() for char in value):
        raise DemoError(f"Invalid source URL: {value!r}")


def validate_rules(rules: dict) -> None:
    if not isinstance(rules, dict) or not rules:
        raise DemoError("Label rules must be a non-empty object")
    for label, rule in rules.items():
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", label) or not isinstance(rule, dict):
            raise DemoError(f"Invalid label rule: {label}")
        if rule.get("node_type") == "record":
            require_text(rule, "anchor_field", "target_label", "relationship_type")
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", rule["relationship_type"]):
                raise DemoError("Invalid anchoring relationship name")
            if rules.get(rule["target_label"], {}).get("node_type") != "knowledge":
                raise DemoError("An anchoring rule must target a Knowledge label")
        elif rule.get("node_type") == "knowledge":
            require_text(rule, "identity_source", "interaction_source", "expansion_scope")
            if rule["expansion_scope"] != "confirmed_entities_only":
                raise DemoError("This example supports confirmed-entity expansion only")
            names = rule.get("scientific_relations")
            if (not isinstance(names, list) or not names
                    or any(not isinstance(name, str) for name in names)
                    or len(set(names)) != len(names)):
                raise DemoError("Scientific relation names must be a non-empty unique list")
            if any(not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
                   for name in names):
                raise DemoError("Invalid scientific relationship name")
        else:
            raise DemoError(f"Invalid node_type in the rule for {label}")
    if "Organism" not in rules:
        raise DemoError("The example requires an Organism rule")


def applicable_rules(node: dict, rules: dict) -> list[dict]:
    labels = node.get("labels")
    if not isinstance(labels, list) or not labels or any(
        not isinstance(label, str) for label in labels
    ) or len(labels) != len(set(labels)):
        raise DemoError("Node labels must be a non-empty unique list")
    result = []
    for label in labels:
        if label not in rules:
            raise DemoError(f"Unknown label: {label}")
        rule = rules[label]
        if rule["node_type"] != node["node_type"]:
            raise DemoError(f"Label {label} disagrees with node_type")
        result.append(rule)
    return result


def build_anchors(records: list[dict], knowledge: list[dict], rules: dict) -> list[dict]:
    """Execute every record-label rule using saved, confirmed entity IDs."""
    entities = {node["id"]: node for node in knowledge}
    anchors = []
    seen = set()
    for record in records:
        for rule in applicable_rules(record, rules):
            target_id = record.get(rule["anchor_field"])
            target = entities.get(target_id)
            if target is None or rule["target_label"] not in target["labels"]:
                raise DemoError(f"Record {record['id']} has no confirmed permitted anchor")
            key = (record["id"], target_id, rule["relationship_type"])
            if key not in seen:
                anchors.append(dict(source_id=key[0], target_id=key[1], type=key[2],
                                    kind="anchoring"))
                seen.add(key)
    return anchors


def find_figure3_paths(graph: dict) -> list[tuple[str, str, str, str]]:
    nodes = {node["id"]: node for node in graph["nodes"]}
    edges = graph["relationships"]
    specimens = [edge for edge in edges if edge["type"] == "SPECIMEN_OF_ORGANISM"]
    observations = [edge for edge in edges if edge["type"] == "OBSERVES_ORGANISM"]
    feeding = [edge for edge in edges if edge["type"] == "PREYS_ON"]
    paths = []
    for specimen in specimens:
        for prey in feeding:
            for observation in observations:
                if (specimen["target_id"] == prey["target_id"]
                        and observation["target_id"] == prey["source_id"]
                        and nodes[specimen["source_id"]].get("platform_name") == "AMIDER"
                        and nodes[observation["source_id"]].get("platform_name") == "ADS"
                        and nodes[prey["target_id"]].get("tax_id") == "6819"
                        and nodes[prey["source_id"]].get("tax_id") == "9238"):
                    paths.append((specimen["source_id"], prey["target_id"],
                                  prey["source_id"], observation["source_id"]))
    return sorted(paths)


def validate_graph(graph: dict, rules: dict, require_path: bool = True) -> dict:
    """Check actual graph structure, source fields and rule-required anchors."""
    validate_rules(rules)
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(
        graph.get("relationships"), list
    ):
        raise DemoError("Graph must contain nodes and relationships lists")
    nodes = {}
    for node in graph["nodes"]:
        require_text(node, "id", "name", "node_type", "source_url")
        if node["id"] in nodes:
            raise DemoError(f"Duplicate node ID: {node['id']}")
        if node["node_type"] not in {"record", "knowledge"}:
            raise DemoError("Invalid node_type")
        applicable_rules(node, rules)
        require_url(node["source_url"])
        if node["node_type"] == "record":
            require_text(node, "platform_name", "source_record_key", "record_unit")
        else:
            require_text(node, "source_name", "tax_id")
            if not re.fullmatch(r"[0-9]+", node["tax_id"]):
                raise DemoError("Organism identity must use a numeric TaxID")
            if node["id"] != f"demo_organism_{node['tax_id']}":
                raise DemoError("Organism ID and TaxID disagree")
            if any(node["source_name"] != rule["identity_source"]
                   for rule in applicable_rules(node, rules)):
                raise DemoError("Knowledge identity source disagrees with its label rule")
        nodes[node["id"]] = node
    keys = set()
    actual_anchors = set()
    for edge in graph["relationships"]:
        require_text(edge, "source_id", "target_id", "type", "kind")
        key = (edge["source_id"], edge["target_id"], edge["type"])
        if key in keys:
            raise DemoError("Duplicate relationship")
        keys.add(key)
        if edge["source_id"] not in nodes or edge["target_id"] not in nodes:
            raise DemoError("Relationship endpoint is missing")
        source, target = nodes[edge["source_id"]], nodes[edge["target_id"]]
        if edge["kind"] == "anchoring":
            if source["node_type"] != "record" or target["node_type"] != "knowledge":
                raise DemoError("Anchors must point from Record to Knowledge")
            actual_anchors.add(key)
        elif edge["kind"] == "scientific":
            if source["node_type"] != "knowledge" or target["node_type"] != "knowledge":
                raise DemoError("Scientific relations must connect Knowledge nodes")
            if source["id"] == target["id"]:
                raise DemoError("This example permits no scientific self-links")
            require_text(edge, "source_name", "source_url")
            require_url(edge["source_url"])
            if not any(edge["type"] in rule["scientific_relations"]
                       and edge["source_name"] == rule["interaction_source"]
                       for rule in applicable_rules(source, rules)):
                raise DemoError("Scientific relation or its source violates the Organism rule")
        else:
            raise DemoError("Unknown relationship kind")
    records = [node for node in nodes.values() if node["node_type"] == "record"]
    knowledge = [node for node in nodes.values() if node["node_type"] == "knowledge"]
    expected_anchors = {(e["source_id"], e["target_id"], e["type"])
                        for e in build_anchors(records, knowledge, rules)}
    if expected_anchors != actual_anchors:
        raise DemoError("Graph anchors do not match every applicable record-label rule")
    paths = find_figure3_paths(graph)
    if require_path and not paths:
        raise DemoError("The expected Figure 3 cross-platform path is missing")
    return {
        "status": "passed", "scope": "Figure 3 construction example",
        "external_knowledge_access": "fixed simulated responses",
        "node_count": len(nodes), "record_count": len(records),
        "knowledge_count": len(knowledge), "relationship_count": len(keys),
        "anchoring_count": len(actual_anchors),
        "scientific_relation_count": len(keys) - len(actual_anchors),
        "figure3_path_count": len(paths),
        "checks": ["unique identities", "all applicable label rules",
                   "confirmed anchoring targets", "relationship endpoints and direction",
                   "node source URLs", "scientific source names and URLs",
                   "Figure 3 cross-platform path"],
    }


def build_demo(project_dir: Path, emit=print) -> tuple[dict, dict]:
    """Build the small graph from local samples; no network or database access."""
    project_dir = Path(project_dir)
    rules = read_json(project_dir / "rules/label_rules.json")
    mappings = read_json(project_dir / "rules/source_mappings.json")
    validate_rules(rules)
    reviewed_rows = read_csv(project_dir / "data/reviewed_identity_mappings.csv")
    reviewed = {}
    for row in reviewed_rows:
        require_text(row, "source_platform", "source_key", "scientific_name", "tax_id", "review_status")
        key = (row["source_platform"], row["source_key"])
        if key in reviewed:
            raise DemoError("Duplicate reviewed identity mapping")
        if row["review_status"] != "confirmed" or not re.fullmatch(r"[0-9]+", row["tax_id"]):
            raise DemoError("Every sample requires a confirmed identity mapping")
        reviewed[key] = row
    emit("[1/7] Load source samples and human-defined field mappings")
    prepared = []
    used_reviews = set()
    for platform, filename in (("AMIDER", "amider_specimen.csv"), ("ADS", "ads_survey.csv")):
        mapping = mappings[platform]
        label = mapping["record_label"]
        labels = [label] if isinstance(label, str) else label
        for row in read_csv(project_dir / "data" / filename):
            fields = set(mapping["source_key_fields"] + mapping["name_fields"]
                         + [mapping["scientific_name_field"], mapping["source_url_field"]])
            require_text(row, *sorted(fields))
            key = "|".join(row[field] for field in mapping["source_key_fields"])
            decision = reviewed.get((platform, key))
            if decision is None:
                raise DemoError(f"No reviewed identity for {platform}: {key}")
            if row[mapping["scientific_name_field"]] != decision["scientific_name"]:
                raise DemoError(f"Source name disagrees with reviewed identity: {platform}: {key}")
            used_reviews.add((platform, key))
            year_field = mapping.get("year_field")
            if year_field and not re.fullmatch(r"[0-9]{4}", row[year_field]):
                raise DemoError("The observation year must have four digits")
            record = dict(
                id=f"demo_record_{platform.lower()}_{quote(key, safe='')}",
                name=f"{platform}: " + " | ".join(row[field] for field in mapping["name_fields"]),
                node_type="record", labels=list(labels), platform_name=platform,
                source_record_key=key, record_unit=mapping["record_unit"],
                source_url=row[mapping["source_url_field"]],
            )
            applicable_rules(record, rules)
            prepared.append((record, decision))
            emit(f"  {platform}: {key} -> {', '.join(labels)}; unit: {record['record_unit']}")
    if used_reviews != set(reviewed):
        raise DemoError("Reviewed mappings and selected source samples do not correspond exactly")
    organism_rule = rules["Organism"]
    identity_lookup = {"NCBI Taxonomy": mock_ncbi_lookup}.get(organism_rule["identity_source"])
    interaction_lookup = {"GloBI": mock_globi_interactions}.get(organism_rule["interaction_source"])
    if identity_lookup is None or interaction_lookup is None:
        raise DemoError("The Organism rule selects a mock provider not configured in this example")
    emit("[2/7] Apply the Organism identity rule using confirmed mappings")
    emit("  Human-reviewed mappings are supplied inputs; no automatic identity approval occurs.")
    emit(f"  Selected provider: {organism_rule['identity_source']} (SIMULATED).")
    ncbi_responses = read_json(project_dir / "data/mock_ncbi.json")
    knowledge_by_id = {}
    records = []
    for record, decision in prepared:
        try:
            identity = identity_lookup(decision["tax_id"], ncbi_responses)
        except ValueError as exc:
            raise DemoError(str(exc)) from exc
        require_text(identity, "tax_id", "scientific_name", "source_name", "source_url")
        if identity["scientific_name"] != decision["scientific_name"]:
            raise DemoError("Simulated identity disagrees with the confirmed name")
        entity_id = f"demo_organism_{identity['tax_id']}"
        if entity_id not in knowledge_by_id:
            knowledge_by_id[entity_id] = dict(
                id=entity_id, name=identity["scientific_name"], node_type="knowledge",
                labels=["Organism"], tax_id=identity["tax_id"],
                source_name=identity["source_name"], source_url=identity["source_url"],
            )
            emit(f"  SIMULATED lookup -> {identity['scientific_name']} (TaxID {identity['tax_id']})")
        else:
            emit(f"  Reuse confirmed Organism: {identity['scientific_name']}")
        for rule in applicable_rules(record, rules):
            record[rule["anchor_field"]] = entity_id
        records.append(record)
    emit("[3/7] Convert source fields into labelled records with saved Organism identifiers")
    for record in records:
        emit(f"  {record['source_record_key']} -> {record['organism_node_id']}")
        emit(f"  Retained source URL: {record['source_url']}")
    emit("[4/7] Apply the Organism rule to prepare scientific relations")
    emit("  SIMULATED GloBI lookup among confirmed entities; retain source and direction.")
    try:
        responses = interaction_lookup(
            {node["tax_id"] for node in knowledge_by_id.values()},
            set(organism_rule["scientific_relations"]), read_json(project_dir / "data/mock_globi.json"),
        )
    except ValueError as exc:
        raise DemoError(str(exc)) from exc
    scientific = [dict(
        source_id=f"demo_organism_{row['source_tax_id']}",
        target_id=f"demo_organism_{row['target_tax_id']}", type=row["relationship_type"],
        kind="scientific", source_name=row["source_name"], source_url=row["source_url"],
    ) for row in responses]
    for edge in scientific:
        emit(f"  {knowledge_by_id[edge['source_id']]['name']} --{edge['type']}--> "
             f"{knowledge_by_id[edge['target_id']]['name']} [source: {edge['source_name']}]")
    emit("[5/7] Apply record-label rules and assemble the graph")
    knowledge = list(knowledge_by_id.values())
    anchors = build_anchors(records, knowledge, rules)
    by_id = {node["id"]: node for node in records + knowledge}
    for edge in anchors:
        emit(f"  {by_id[edge['source_id']]['labels'][0]} -> {edge['type']} -> Organism")
    graph = dict(nodes=sorted(records + knowledge, key=lambda n: n["id"]),
                 relationships=sorted(anchors + scientific,
                                      key=lambda e: (e["source_id"], e["type"], e["target_id"])))
    emit("[6/7] Validate the constructed graph")
    report = validate_graph(graph, rules)
    for check in report["checks"]:
        emit(f"  PASS: {check}")
    return graph, report


def write_outputs(graph: dict, report: dict, output_dir: Path) -> None:
    """Write deterministic, inspectable construction artifacts after validation."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, value in (("graph.json", graph), ("validation.json", report)):
        (output_dir / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                                    sort_keys=True) + "\n", encoding="utf-8")
    tables = (
        ("records.csv", [n for n in graph["nodes"] if n["node_type"] == "record"]),
        ("knowledge.csv", [n for n in graph["nodes"] if n["node_type"] == "knowledge"]),
        ("anchors.csv", [e for e in graph["relationships"] if e["kind"] == "anchoring"]),
        ("scientific_relations.csv", [e for e in graph["relationships"] if e["kind"] == "scientific"]),
    )
    for filename, rows in tables:
        fields = sorted({key for row in rows for key in row})
        with (output_dir / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows({key: json.dumps(value) if isinstance(value, list) else value
                              for key, value in row.items()} for row in rows)


def print_summary(graph: dict, report: dict, emit=print) -> None:
    emit(f"  Result: {report['record_count']} Record nodes + {report['knowledge_count']} Knowledge nodes; "
         f"{report['anchoring_count']} anchors + {report['scientific_relation_count']} scientific relation.")
    nodes = {node["id"]: node for node in graph["nodes"]}
    emit("  Figure 3 path (arrows preserve stored relation direction):")
    for specimen, krill, penguin, observation in find_figure3_paths(graph):
        emit(f"    {nodes[specimen]['name']} --SPECIMEN_OF_ORGANISM--> {nodes[krill]['name']}")
        emit(f"    {nodes[penguin]['name']} --PREYS_ON--> {nodes[krill]['name']}")
        emit(f"    {nodes[observation]['name']} --OBSERVES_ORGANISM--> {nodes[penguin]['name']}")
    emit("  Discovery: specimen -> krill -> penguin -> ADS survey -> original source URL.")
    emit("  The relation between the two organisms supports navigation in either direction.")
