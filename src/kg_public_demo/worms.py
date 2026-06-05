from __future__ import annotations

import time
from typing import Iterable
from urllib.parse import quote

from kg_public_demo.cache import JsonCache
from kg_public_demo.http_utils import fetch_json
from kg_public_demo.models import HabitatRecord, OrganismRecord, RelationRecord

WORMS_API_BASE_URL = "https://www.marinespecies.org/rest/AphiaRecordsByName"
WORMS_HABITAT_FIELDS = {
    "isMarine": "marine",
    "isBrackish": "brackish",
    "isFreshwater": "freshwater",
    "isTerrestrial": "terrestrial",
}
HABITAT_TYPES = [
    HabitatRecord(id="habitattype_marine", name="marine"),
    HabitatRecord(id="habitattype_brackish", name="brackish"),
    HabitatRecord(id="habitattype_freshwater", name="freshwater"),
    HabitatRecord(id="habitattype_terrestrial", name="terrestrial"),
]


def worms_flag_is_positive(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true"}


def build_worms_record_url(record: dict[str, object]) -> str:
    record_url = record.get("url")
    if isinstance(record_url, str) and record_url.strip():
        return record_url.strip()

    aphia_id = record.get("AphiaID")
    if aphia_id in (None, ""):
        return ""
    return f"https://www.marinespecies.org/aphia.php?p=taxdetails&id={aphia_id}"


class WoRMSClient:
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
        self._refreshed_keys: set[str] = set()

    def get_record(self, scientific_name: str) -> dict[str, object] | None:
        normalized_name = scientific_name.strip()

        if self.cache.has(normalized_name) and (
            not self.refresh_cache or normalized_name in self._refreshed_keys
        ):
            print(f"  - WoRMS cache hit: {normalized_name}")
            return self.cache.get(normalized_name)

        if self.mode == "frozen":
            raise RuntimeError(
                f"Missing cached WoRMS record for '{normalized_name}'. "
                "Run in live mode once to refresh the cache."
            )

        print(f"  - Querying WoRMS: {normalized_name}")
        records = fetch_json(
            f"{WORMS_API_BASE_URL}/{quote(normalized_name)}",
            {
                "like": "false",
                "marine_only": "false",
            },
        )
        record = records[0] if isinstance(records, list) and records else None
        self.cache.set(normalized_name, record)
        self._refreshed_keys.add(normalized_name)
        self.cache.save()
        time.sleep(self.delay_seconds)
        return record


def build_inhabits_relations(
    organisms: Iterable[OrganismRecord],
    client: WoRMSClient,
) -> tuple[list[HabitatRecord], list[RelationRecord]]:
    habitat_name_to_id = {habitat.name: habitat.id for habitat in HABITAT_TYPES}
    existing_keys: set[tuple[str, str, str]] = set()
    relations: list[RelationRecord] = []

    for organism in organisms:
        print(f"[WoRMS] Enriching organism: {organism.scientific_name}")
        record = client.get_record(organism.scientific_name)
        if not isinstance(record, dict):
            print("  - No WoRMS record found")
            continue

        record_url = build_worms_record_url(record)
        added_for_source = 0
        for api_field, habitat_name in WORMS_HABITAT_FIELDS.items():
            if not worms_flag_is_positive(record.get(api_field)):
                continue

            habitat_id = habitat_name_to_id[habitat_name]
            key = (organism.id, habitat_id, "INHABITS")
            if key in existing_keys:
                continue

            existing_keys.add(key)
            added_for_source += 1
            relations.append(
                RelationRecord(
                    from_id=organism.id,
                    to_id=habitat_id,
                    relation_type="INHABITS",
                    url=record_url,
                )
            )

        print(f"  - Added {added_for_source} organism-to-habitat relation(s)")

    print(f"[WoRMS] Total habitat relations: {len(relations)}")
    return HABITAT_TYPES, relations
