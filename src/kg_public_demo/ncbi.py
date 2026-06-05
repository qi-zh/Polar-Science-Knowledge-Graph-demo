from __future__ import annotations

import time
import xml.etree.ElementTree as ET

from kg_public_demo.cache import JsonCache
from kg_public_demo.http_utils import fetch_json, fetch_text

NCBI_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class NCBITaxonomyClient:
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

    def get_taxonomy(self, scientific_name: str) -> dict[str, str] | None:
        normalized_name = scientific_name.strip()

        if self.cache.has(normalized_name) and (
            not self.refresh_cache or normalized_name in self._refreshed_keys
        ):
            print(f"  - NCBI cache hit: {normalized_name}")
            return self.cache.get(normalized_name)

        if self.mode == "frozen":
            raise RuntimeError(
                f"Missing cached NCBI taxonomy for '{normalized_name}'. "
                "Run in live mode once to refresh the cache."
            )

        print(f"  - Querying NCBI taxonomy: {normalized_name}")
        payload = fetch_json(
            NCBI_ESEARCH_URL,
            {
                "db": "taxonomy",
                "term": normalized_name,
                "retmode": "json",
            },
        )
        id_list = payload.get("esearchresult", {}).get("idlist", [])

        if not id_list:
            self.cache.set(normalized_name, None)
            self._refreshed_keys.add(normalized_name)
            self.cache.save()
            time.sleep(self.delay_seconds)
            return None

        tax_id = id_list[0]
        xml_text = fetch_text(
            NCBI_EFETCH_URL,
            {
                "db": "taxonomy",
                "id": tax_id,
                "retmode": "xml",
            },
        )
        root = ET.fromstring(xml_text)
        taxon = root.find(".//Taxon")
        if taxon is None:
            raise RuntimeError(f"NCBI returned no <Taxon> element for '{normalized_name}'.")

        def get_text(tag: str) -> str:
            element = taxon.find(tag)
            if element is None or element.text is None:
                return ""
            return element.text.strip()

        common_name = get_text("CommonName")
        other_names = taxon.find("OtherNames")
        if other_names is not None:
            for tag in ("GenbankCommonName", "CommonName"):
                element = other_names.find(tag)
                if element is not None and element.text:
                    common_name = element.text.strip()
                    break

        result = {
            "id": f"organism_{tax_id}",
            "tax_id": get_text("TaxId"),
            "scientific_name": get_text("ScientificName"),
            "common_name": common_name,
            "rank": get_text("Rank"),
            "url": f"https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={tax_id}",
        }
        self.cache.set(normalized_name, result)
        self._refreshed_keys.add(normalized_name)
        self.cache.save()
        time.sleep(self.delay_seconds)
        return result
