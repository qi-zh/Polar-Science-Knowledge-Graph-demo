"""Fixed illustrative knowledge responses. This module makes no network calls."""

from copy import deepcopy


def mock_ncbi_lookup(tax_id: str, responses: dict) -> dict:
    """Return a fixed identity response for an already reviewed TaxID."""
    if not isinstance(responses, dict):
        raise ValueError("Simulated NCBI responses must be an object keyed by TaxID")
    if tax_id not in responses:
        raise ValueError(f"No simulated NCBI response for TaxID {tax_id}")
    response = deepcopy(responses[tax_id])
    if not isinstance(response, dict) or response.get("tax_id") != tax_id:
        raise ValueError(f"Simulated NCBI identity disagrees with TaxID {tax_id}")
    return response


def mock_globi_interactions(tax_ids: set[str], relation_types: set[str],
                            responses: list[dict]) -> list[dict]:
    """Select fixed interactions among the confirmed entities under the rule."""
    if not isinstance(responses, list):
        raise ValueError("Simulated GloBI responses must be a list")
    required = ("source_tax_id", "target_tax_id", "relationship_type",
                "source_name", "source_url")
    for item in responses:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in required
        ):
            raise ValueError("A simulated GloBI response has missing fields")
    return [deepcopy(item) for item in responses
            if item["source_tax_id"] in tax_ids
            and item["target_tax_id"] in tax_ids
            and item["relationship_type"] in relation_types]
