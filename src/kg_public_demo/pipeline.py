from __future__ import annotations

from dataclasses import dataclass

from kg_public_demo.cache import JsonCache
from kg_public_demo.config import ProjectPaths, RuntimeSettings
from kg_public_demo.csv_utils import read_csv_rows, write_csv_rows
from kg_public_demo.globi import GloBIClient, build_globi_relations
from kg_public_demo.models import HabitatRecord, OrganismRecord, RelationRecord, SpecimenRecord
from kg_public_demo.ncbi import NCBITaxonomyClient
from kg_public_demo.worms import WoRMSClient, build_inhabits_relations


@dataclass(frozen=True)
class PipelineArtifacts:
    specimens: list[SpecimenRecord]
    organisms: list[OrganismRecord]
    habitats: list[HabitatRecord]
    anchor_relations: list[RelationRecord]
    globi_relations: list[RelationRecord]
    inhabit_relations: list[RelationRecord]
    paths: ProjectPaths


def _load_specimens(paths: ProjectPaths) -> list[SpecimenRecord]:
    required_columns = {"id", "name", "label", "url", "scientific_name"}
    rows = read_csv_rows(paths.input_file)
    if not rows:
        raise RuntimeError(f"Input file is empty: {paths.input_file}")

    missing = required_columns - set(rows[0].keys())
    if missing:
        raise RuntimeError(
            f"Input file is missing required columns: {sorted(missing)}"
        )

    return [
        SpecimenRecord(
            id=row["id"].strip(),
            name=row["name"].strip(),
            label=row["label"].strip(),
            url=row["url"].strip(),
            scientific_name=row["scientific_name"].strip(),
        )
        for row in rows
    ]


def _sort_relations(relations: list[RelationRecord]) -> list[RelationRecord]:
    return sorted(
        relations,
        key=lambda relation: (
            relation.from_id,
            relation.to_id,
            relation.relation_type,
            relation.url,
        ),
    )


def _write_outputs(artifacts: PipelineArtifacts) -> None:
    paths = artifacts.paths
    paths.output_dir.mkdir(parents=True, exist_ok=True)

    write_csv_rows(
        paths.source_copy_file,
        ["id", "name", "label", "url", "scientific_name"],
        [specimen.to_row() for specimen in artifacts.specimens],
    )
    write_csv_rows(
        paths.organism_file,
        ["id", "tax_id", "scientific_name", "common_name", "rank", "url"],
        [organism.to_row() for organism in artifacts.organisms],
    )
    write_csv_rows(
        paths.anchor_file,
        ["from_id", "to_id", "relation_type"],
        [
            {
                "from_id": relation.from_id,
                "to_id": relation.to_id,
                "relation_type": relation.relation_type,
            }
            for relation in artifacts.anchor_relations
        ],
    )
    write_csv_rows(
        paths.habitat_file,
        ["id", "name"],
        [habitat.to_row() for habitat in artifacts.habitats],
    )
    write_csv_rows(
        paths.globi_file,
        ["from_id", "to_id", "relation_type", "url"],
        [relation.to_row() for relation in artifacts.globi_relations],
    )
    write_csv_rows(
        paths.inhabit_file,
        ["from_id", "to_id", "relation_type", "url"],
        [relation.to_row() for relation in artifacts.inhabit_relations],
    )


def run_pipeline(paths: ProjectPaths, runtime: RuntimeSettings) -> PipelineArtifacts:
    print(f"Input file: {paths.input_file}")
    print(f"Cache mode: {runtime.mode}")
    print(f"Output directory: {paths.output_dir}")

    specimens = _load_specimens(paths)
    print(f"Loaded {len(specimens)} specimen record(s)")

    ncbi_client = NCBITaxonomyClient(
        cache=JsonCache(paths.ncbi_cache_file),
        mode=runtime.mode,
        refresh_cache=runtime.refresh_cache,
        delay_seconds=runtime.http_delay_seconds,
    )
    globi_client = GloBIClient(
        cache=JsonCache(paths.globi_cache_file),
        mode=runtime.mode,
        refresh_cache=runtime.refresh_cache,
        delay_seconds=runtime.http_delay_seconds,
    )
    worms_client = WoRMSClient(
        cache=JsonCache(paths.worms_cache_file),
        mode=runtime.mode,
        refresh_cache=runtime.refresh_cache,
        delay_seconds=runtime.http_delay_seconds,
    )

    organisms_by_id: dict[str, OrganismRecord] = {}
    anchor_relations: list[RelationRecord] = []
    seen_anchor_keys: set[tuple[str, str, str]] = set()

    for index, specimen in enumerate(specimens, start=1):
        print(
            f"[NCBI] ({index}/{len(specimens)}) Anchoring specimen "
            f"{specimen.id} -> {specimen.scientific_name}"
        )
        ncbi_result = ncbi_client.get_taxonomy(specimen.scientific_name)
        if ncbi_result is None:
            print("  - No NCBI match found; skipping anchor")
            continue

        organism = OrganismRecord(
            id=ncbi_result["id"],
            tax_id=ncbi_result["tax_id"],
            scientific_name=ncbi_result["scientific_name"],
            common_name=ncbi_result["common_name"],
            rank=ncbi_result["rank"],
            url=ncbi_result["url"],
        )
        organisms_by_id.setdefault(organism.id, organism)

        anchor_key = (specimen.id, organism.id, "SPECIMEN_OF_ORGANISM")
        if anchor_key not in seen_anchor_keys:
            seen_anchor_keys.add(anchor_key)
            anchor_relations.append(
                RelationRecord(
                    from_id=specimen.id,
                    to_id=organism.id,
                    relation_type="SPECIMEN_OF_ORGANISM",
                )
            )

    organisms = sorted(
        organisms_by_id.values(),
        key=lambda organism: (organism.scientific_name.lower(), organism.id),
    )
    print(f"Resolved {len(organisms)} unique organism node(s)")

    globi_relations = _sort_relations(build_globi_relations(organisms, globi_client))
    habitats, inhabit_relations = build_inhabits_relations(organisms, worms_client)

    artifacts = PipelineArtifacts(
        specimens=specimens,
        organisms=organisms,
        habitats=habitats,
        anchor_relations=_sort_relations(anchor_relations),
        globi_relations=globi_relations,
        inhabit_relations=_sort_relations(inhabit_relations),
        paths=paths,
    )
    _write_outputs(artifacts)
    return artifacts
