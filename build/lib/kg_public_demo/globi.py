from __future__ import annotations

import re
import time
from typing import Iterable
from urllib.parse import quote

from kg_public_demo.cache import JsonCache
from kg_public_demo.http_utils import fetch_json
from kg_public_demo.models import OrganismRecord, RelationRecord

GLOBI_API_URL = "https://api.globalbioticinteractions.org/interaction"
GLOBI_INTERACTION_TYPES = {
    "coOccursWith",
    "eatenBy",
    "eats",
    "hasHost",
    "hasParasite",
    "hasPathogen",
    "hasVector",
    "hostOf",
    "interactsWith",
    "killedBy",
    "kills",
    "parasiteOf",
    "pathogenOf",
    "preyedUponBy",
    "preysOn",
    "symbiontOf",
    "vectorOf",
}


def camel_to_upper_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def normalize_tax_id(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "unknown":
        return None
    try:
        return str(int(float(text)))
    except ValueError:
        return None


def extract_ncbi_taxid(external_id: str | None) -> str | None:
    if not external_id or not external_id.startswith("NCBI:"):
        return None
    return normalize_tax_id(external_id.split(":", 1)[1])


def build_globi_interaction_url(
    source_name: str,
    interaction_type: str,
    target_name: str,
) -> str:
    return (
        "https://www.globalbioticinteractions.org/?"
        f"sourceTaxon={quote(source_name)}&"
        f"interactionType={quote(interaction_type)}&"
        f"targetTaxon={quote(target_name)}"
    )


class GloBIClient:
    def __init__(
        self,
        cache: JsonCache,
        mode: str,
        refresh_cache: bool,
        delay_seconds: float,
    ):
        self.cache = cache
        self.mode = mode
        self.refresh_cache = refresh_cache
        self.delay_seconds = delay_seconds

    def get_interactions(self, scientific_name: str) -> list[dict[str, str]]:
        normalized_name = scientific_name.strip()

        if self.cache.has(normalized_name) and not self.refresh_cache:
            print(f"  - GloBI cache hit: {normalized_name}")
            return list(self.cache.get(normalized_name, []))

        if self.mode == "frozen":
            raise RuntimeError(
                f"Missing cached GloBI interactions for '{normalized_name}'. "
                "Run in live mode once to refresh the cache."
            )

        print(f"  - Querying GloBI interactions: {normalized_name}")
        payload = fetch_json(
            GLOBI_API_URL,
            {
                "sourceTaxon": normalized_name,
                "fields": "target_taxon_external_id,interaction_type",
            },
        )

        columns = payload.get("columns", [])
        data = payload.get("data", [])
        records: list[dict[str, str]] = []
        for raw_record in data:
            if len(raw_record) != len(columns):
                continue
            record = dict(zip(columns, raw_record))
            records.append(
                {
                    "target_taxon_external_id": str(
                        record.get("target_taxon_external_id", "")
                    ),
                    "interaction_type": str(record.get("interaction_type", "")),
                }
            )

        self.cache.set(normalized_name, records)
        self.cache.save()
        time.sleep(self.delay_seconds)
        return records


def build_globi_relations(
    organisms: Iterable[OrganismRecord],
    client: GloBIClient,
) -> list[RelationRecord]:
    organism_list = list(organisms)
    taxid_to_organism = {
        normalize_tax_id(organism.tax_id): organism
        for organism in organism_list
    }

    existing_keys: set[tuple[str, str, str]] = set()
    relations: list[RelationRecord] = []

    for organism in organism_list:
        print(f"[GloBI] Enriching organism: {organism.scientific_name}")
        records = client.get_interactions(organism.scientific_name)
        added_for_source = 0

        for record in records:
            interaction_type = record.get("interaction_type", "")
            if interaction_type not in GLOBI_INTERACTION_TYPES:
                continue

            target_taxid = extract_ncbi_taxid(record.get("target_taxon_external_id"))
            if target_taxid is None:
                continue

            target_organism = taxid_to_organism.get(target_taxid)
            if target_organism is None:
                continue

            relation_type = camel_to_upper_snake(interaction_type)
            key = (organism.id, target_organism.id, relation_type)
            if key in existing_keys:
                continue

            existing_keys.add(key)
            added_for_source += 1
            relations.append(
                RelationRecord(
                    from_id=organism.id,
                    to_id=target_organism.id,
                    relation_type=relation_type,
                    url=build_globi_interaction_url(
                        source_name=organism.scientific_name,
                        interaction_type=interaction_type,
                        target_name=target_organism.scientific_name,
                    ),
                )
            )

        print(f"  - Added {added_for_source} organism-to-organism relation(s)")

    print(f"[GloBI] Total organism relations: {len(relations)}")
    return relations
