"""CisaKevSource -- a real SecurityIntelligenceSourcePort adapter backed by
CISA's Known Exploited Vulnerabilities (KEV) catalog, a single downloadable
JSON file published by the U.S. government listing CVEs with confirmed
active exploitation. Egress scoped to exactly one pre-configured host
(www.cisa.gov), same discipline as every other AI & Agent Module provider.

Only relevant to the finding categories where "is this actively being
exploited right now" changes prioritization: sca (vulnerable dependencies)
and container (vulnerable base images) -- the KEV catalog has no
per-category structure of its own, so this adapter answers only those two
topics and returns None for everything else.
"""

from __future__ import annotations

import httpx

_KEV_CATALOG_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_RELEVANT_TOPICS = ("sca", "container")
_MAX_ENTRIES_IN_DIGEST = 10


class CisaKevSource:
    def __init__(self, *, timeout_seconds: float = 30.0, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(transport=transport, timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def fetch(self, topic: str) -> str | None:
        if topic not in _RELEVANT_TOPICS:
            return None

        try:
            response = self._client.get(_KEV_CATALOG_URL)
        except httpx.TransportError:
            return None

        if response.status_code >= 400:
            return None

        try:
            body = response.json()
            vulnerabilities = body["vulnerabilities"]
        except (ValueError, KeyError):
            return None

        # Most-recently-added first -- what a DevSecOps reader most needs
        # to know is what changed, not the full multi-thousand-entry list.
        recent = sorted(vulnerabilities, key=lambda v: v.get("dateAdded", ""), reverse=True)[:_MAX_ENTRIES_IN_DIGEST]
        if not recent:
            return None

        lines = ["Recently confirmed actively-exploited vulnerabilities (CISA KEV catalog):"]
        for entry in recent:
            cve_id = entry.get("cveID", "unknown")
            product = entry.get("product", "unknown product")
            vendor = entry.get("vendorProject", "unknown vendor")
            date_added = entry.get("dateAdded", "unknown date")
            lines.append(f"- {cve_id} ({vendor} {product}), added {date_added}")

        return "\n".join(lines)
