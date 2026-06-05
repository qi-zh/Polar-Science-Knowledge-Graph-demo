from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecimenRecord:
    id: str
    name: str
    label: str
    url: str
    scientific_name: str

    def to_row(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "url": self.url,
            "scientific_name": self.scientific_name,
        }


@dataclass(frozen=True)
class OrganismRecord:
    id: str
    tax_id: str
    scientific_name: str
    common_name: str
    rank: str
    url: str

    def to_row(self) -> dict[str, str]:
        return {
            "id": self.id,
            "tax_id": self.tax_id,
            "scientific_name": self.scientific_name,
            "common_name": self.common_name,
            "rank": self.rank,
            "url": self.url,
        }


@dataclass(frozen=True)
class HabitatRecord:
    id: str
    name: str

    def to_row(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
        }


@dataclass(frozen=True)
class RelationRecord:
    from_id: str
    to_id: str
    relation_type: str
    url: str = ""

    def to_row(self) -> dict[str, str]:
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "relation_type": self.relation_type,
            "url": self.url,
        }
