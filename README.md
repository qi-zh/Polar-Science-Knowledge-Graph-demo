# Polar Science Knowledge Graph: Construction Demo

Build and explore a small Polar Science Knowledge Graph (PSKG) example in one command. This repository demonstrates the construction workflow in Figure 3 of *The Polar Science Knowledge Graph: A Scientific Index for Cross-Platform Data Discovery*.

The example connects an AMIDER Antarctic krill specimen to an ADS Adélie penguin population survey through the organisms they describe and a feeding relation. Both records retain links to their original platforms.

## What the demo builds

The result is **four nodes and three relationships**: two Record nodes, two Organism Knowledge nodes, two anchoring relations, and one scientific relation.

```text
AMIDER specimen --SPECIMEN_OF_ORGANISM--> Antarctic krill
Adélie penguin  --PREYS_ON--------------> Antarctic krill
ADS survey     --OBSERVES_ORGANISM-----> Adélie penguin
```

The feeding relation lets users navigate from the krill specimen to the penguin survey. The terminal traces seven stages, from source-field mapping to the checked graph.

NCBI Taxonomy and GloBI access is **simulated using fixed local responses**. Field conversion, label-based rules, graph construction, validation, and Neo4j import execute normally. Human-confirmed identity mappings are supplied inputs.

## Quick start

Requirements: Linux, Git, Bash, `flock` from util-linux, Docker, and Docker Compose v2. Use a regular user with access to a local Unix-socket Docker engine. Allow at least 2 GB of Docker memory and internet access for the initial image build.

```bash
git clone https://github.com/qi-zh/Polar-Science-Knowledge-Graph-demo.git
cd Polar-Science-Knowledge-Graph-demo
docker info
./run_demo.sh
```

A successful run reports the graph size and verifies the database contents. Open the terminal query interface:

```bash
./query_demo.sh
```

Then enter a query, ending with a semicolon:

```cypher
MATCH (a)-[r]->(b)
RETURN a.name, type(r), b.name;
```

Enter `:exit` to leave the query interface. Stop the demo with `./stop_demo.sh`; its graph and generated files are retained. Run `./run_demo.sh` again to verify and reuse that graph.

Use **one checkout per Docker engine**: resource ownership is tied to the checkout directory. No host database ports or Neo4j Browser are exposed. See the [usage guide](docs/USAGE.md) for lifecycle controls and troubleshooting.

## Rules and inputs

[Source mappings](rules/source_mappings.json) define record units and field conversion. [Label-based rules](rules/label_rules.json) govern the graph:

| Node label | Rule responsibility |
|---|---|
| `BiologicalSpecimen` | Anchor the specimen to its confirmed Organism using `SPECIMEN_OF_ORGANISM`. |
| `PopulationObservation` | Anchor the survey to its confirmed Organism using `OBSERVES_ORGANISM`. |
| `Organism` | Select the identity source and prepare the supported scientific relation among confirmed organisms. |

Inputs and mock responses are in `data/`; implementation is in `src/`. Generated tables, `graph.json`, and `validation.json` appear in `outputs/current/`.

## Documentation and tests

- [Usage guide](docs/USAGE.md): Docker and file-only execution, queries, outputs, stopping, and reset.
- [Sources and scope](docs/SOURCES.txt): sample provenance, confirmed identities, and mock responses.
- [Expected results](docs/EXPECTED_RESULTS.txt): graph contents and query results.
- [Query files](queries/): counts, cross-platform path, and source-field inspection.

Run the automated tests with Python 3.12:

```bash
python3 -B -m unittest discover -s tests -v
```

The software uses the [MIT license](LICENSE). See [sample sources and reuse terms](docs/SOURCES.txt) for third-party fields and references.
