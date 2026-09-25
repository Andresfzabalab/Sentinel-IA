"""MitreCweSource -- a real SecurityIntelligenceSourcePort adapter backed
by MITRE's public CWE REST API (cwe-api.mitre.org), the official machine-
readable Common Weakness Enumeration catalog. Egress is scoped to exactly
one pre-configured host (Module_Boundaries.md's single-endpoint pattern,
the same discipline OllamaProvider/OpenAIProvider already follow) -- this
adapter never contacts any other domain.

Each SentinelAI finding category is mapped to the specific CWE ID(s) most
relevant to it; the fetched name/description/mitigation text for those IDs
becomes the topic's content. A single CWE lookup failing (network error,
unexpected shape) is skipped, not fatal -- the topic still returns whatever
other CWE IDs succeeded, or None if all of them failed.
"""

from __future__ import annotations

import httpx

_CWE_API_BASE_URL = "https://cwe-api.mitre.org/api/v1"

# The CWE ID(s) most relevant to each finding category SentinelAI's MVP
# scanners produce (Bounded_Contexts.md) -- curated once, by hand, same
# spirit as StaticSeedSource's original topic list.
_CATEGORY_TO_CWE_IDS: dict[str, tuple[int, ...]] = {
    "sast": (89, 78, 79),  # SQL Injection, OS Command Injection, XSS
    "sca": (1104,),  # Use of Unmaintained Third Party Components
    "secret": (798,),  # Use of Hard-coded Credentials
    "container": (250,),  # Execution with Unnecessary Privileges
    "iac": (732,),  # Incorrect Permission Assignment for Critical Resource
}


class MitreCweSource:
    def __init__(self, *, timeout_seconds: float = 30.0, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=_CWE_API_BASE_URL, transport=transport, timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def fetch(self, topic: str) -> str | None:
        cwe_ids = _CATEGORY_TO_CWE_IDS.get(topic)
        if cwe_ids is None:
            return None  # this source has no mapping for this topic -- not an error

        sections = [section for cwe_id in cwe_ids if (section := self._fetch_one(cwe_id)) is not None]
        if not sections:
            return None
        return "\n\n".join(sections)

    def _fetch_one(self, cwe_id: int) -> str | None:
        try:
            response = self._client.get(f"/cwe/weakness/{cwe_id}")
        except httpx.TransportError:
            return None

        if response.status_code >= 400:
            return None

        try:
            body = response.json()
            weakness = body["Weaknesses"][0]
            name = weakness["Name"]
            description = weakness["Description"]
        except (ValueError, KeyError, IndexError):
            return None

        mitigations = _extract_mitigations(weakness)
        section = f"CWE-{cwe_id} ({name}): {description}"
        if mitigations:
            section += "\nMitigation: " + " ".join(mitigations)
        return section


def _extract_mitigations(weakness: dict) -> list[str]:
    """MITRE's PotentialMitigations shape varies (a list of objects with a
    free-text 'Description'); missing or malformed entries are skipped
    rather than failing the whole CWE lookup.
    """
    raw = weakness.get("PotentialMitigations")
    if not isinstance(raw, list):
        return []
    return [m["Description"] for m in raw if isinstance(m, dict) and isinstance(m.get("Description"), str)]
