# Usage guide

Run commands from the repository root.

## 1. Check the environment

The Docker workflow requires Linux, Bash, `flock` from util-linux, Docker, and Docker Compose v2. Use a regular user with access to a local Unix-socket Docker engine. Allow at least 2 GB of Docker memory. The first build downloads pinned container images and Python packages.

```bash
docker info
docker compose version
command -v flock
```

If Docker access is unavailable, ask the host administrator to configure it. If access was just granted, open a new login session so group membership takes effect. Do not run the demo scripts with `sudo`; the scripts require a non-root user so output files remain user-owned.

## 2. Build and import

```bash
./run_demo.sh
```

The script builds the application image, starts Neo4j, and runs the seven-stage builder using bundled samples, mappings, rules, and simulated knowledge-source responses.

Expect this result:

```text
Result: 2 Record nodes + 2 Knowledge nodes; 2 anchors + 1 scientific relation.
```

The message **committed Neo4j contents were verified** confirms successful import or verification of an identical existing graph.

The initial import requires an empty demo database. Repeating the command with unchanged inputs verifies the identical graph without replacing it. If database contents differ from the prepared graph, the builder stops for review.

## 3. Explore the graph

Open an interactive Cypher shell:

```bash
./query_demo.sh
```

Cypher queries must end with a semicolon. List the three relationships:

```cypher
MATCH (a)-[r]->(b)
RETURN a.name AS source, type(r) AS relation, b.name AS target;
```

Find the complete Figure 3 path and both original source links:

```cypher
MATCH (specimen:BiologicalSpecimen)-[:SPECIMEN_OF_ORGANISM]->
      (krill:Organism)<-[:PREYS_ON]-
      (penguin:Organism)<-[:OBSERVES_ORGANISM]-
      (survey:PopulationObservation)
RETURN specimen.name AS specimen,
       specimen.source_url AS specimen_source,
       krill.name AS krill,
       penguin.name AS penguin,
       survey.name AS survey,
       survey.source_url AS survey_source;
```

The result connects AMIDER specimen `A00850-0001` to the ADS `Mame_Island` survey in 2020 (`JARE61`). The scientific relation is directed from the penguin to the krill; the query follows it in the incoming direction when exploring from the specimen. The source URLs lead to the original platform pages.

Inspect the scientific relation's reference:

```cypher
MATCH (a)-[r:PREYS_ON]->(b)
RETURN a.name, b.name, r.source_name, r.source_url;
```

Leave the shell with:

```text
:exit
```

Exiting the shell leaves Neo4j running. You can also submit a query directly:

```bash
./query_demo.sh 'MATCH (n) RETURN n.node_type, count(*) AS nodes;'
```

Three reusable read-only query files provide counts, the full path, and source fields:

```bash
./query_demo.sh "$(cat queries/01_graph_counts.cypher)"
./query_demo.sh "$(cat queries/02_discovery_path.cypher)"
./query_demo.sh "$(cat queries/03_source_fields.cypher)"
```

See [expected results](EXPECTED_RESULTS.txt). Queries run inside the demo container; no host database ports are exposed. Keep the public demo credential confined to this isolated example.

## 4. Inspect generated files

The builder writes these files to `outputs/current/`:

| File | Content |
|---|---|
| `records.csv` | Two converted source records with their fields and labels. |
| `knowledge.csv` | Two organism identities and their references. |
| `anchors.csv` | Record-to-organism anchoring relations. |
| `scientific_relations.csv` | The directed feeding relation and its reference. |
| `graph.json` | The complete prepared demonstration graph. |
| `validation.json` | Local graph checks and their results. |

Files are written **before database import**. `validation.json` reports local graph checks. Confirm database success from the committed-content verification message; an import failure returns an error even when output files exist.

Outputs are excluded from version control and owned by the calling user.

## 5. Stop, resume, or reset

Close interactive query sessions before running build, stop, or reset commands.

```bash
./stop_demo.sh
```

Stopping removes this demo's containers and network while retaining its graph volume and generated files. Resume with:

```bash
./run_demo.sh
```

To deliberately discard the demo database and start again:

```bash
./reset_demo.sh --confirm
./run_demo.sh
```

**Reset permanently deletes the owned `pskg-paper-demo-data` volume.** It checks ownership before deletion and retains generated output files. Changes made interactively to the database are lost; the next build recreates the supplied example. Reset is optional and unnecessary for ordinary repeated runs.

## 6. Run without Docker

Python 3.12 can build and validate the local artifacts using only its standard library:

```bash
python3 -B main.py build
```

Choose another output directory when needed:

```bash
python3 -B main.py build --output-dir outputs/local-check
```

This mode writes the same graph artifacts without starting or querying Neo4j. The `--import-neo4j` option is reserved for the supplied application container, whose endpoint is fixed to its dedicated demo service.

## Troubleshooting and isolation

- **Docker is unavailable:** check `docker info` as your regular user. Resolve engine availability or account access with the administrator; the scripts do not change permissions or start the Docker daemon.
- **Another demo command is active:** close `cypher-shell` with `:exit`, or wait for the active command to finish. Query sessions hold a shared lock; build, stop, and reset require an exclusive lock. Keep `.demo.lock` in place, even between runs.
- **Ownership labels do not match this directory:** use the checkout that created the resources. Only one checkout per Docker engine is supported. Moving or cloning the directory does not transfer ownership, and stopping retains the owned volume. Use the original checkout or a separate Docker engine; do not reset or relabel another directory's resources.
- **Compose or Docker environment override rejected:** the scripts select their own configuration and require a local Unix-socket context. Use a clean shell without conflicting override variables, as identified in the error message.
- **Graph differs from the prepared example:** inspect any interactive edits and input changes. Preserve work you need before choosing the explicit reset procedure. The builder does not overwrite a different graph automatically.
- **Image download or startup fails:** check internet access for the first build and available Docker memory. After resolving the cause, rerun `./run_demo.sh`.

The runtime uses an internal Docker network. Only `outputs/` is mounted from the host.
