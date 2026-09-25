"""StaticSeedSource -- the MVP's one real SecurityIntelligenceSourcePort
adapter: a small, curated, built-in set of remediation guidance for the
finding categories SentinelAI's MVP scanners actually produce (sast, sca,
secret, container, iac). This is a deliberate, documented placeholder --
AI_Agent_Architecture.md §11 explicitly leaves "the exact external
source(s) feeding the Security Intelligence & Data Module (which
advisory/CVE/remediation feed)" as an open, unselected implementation
concern, not an architectural one. Wiring a real external feed (a CVE
database, an advisory API) is a drop-in replacement of this one adapter --
nothing else in the module changes (mirrors ScannerPort's own
extensibility story, QA-07).
"""

from __future__ import annotations

_SEED_CONTENT: dict[str, str] = {
    "sast": (
        "Validate and sanitize all external input before use. For SQL "
        "injection specifically, use parameterized queries/prepared "
        "statements -- never string-concatenate user input into a query. "
        "For command injection, avoid shell=True equivalents and prefer "
        "argument-list subprocess APIs."
    ),
    "sca": (
        "Upgrade the affected dependency to a patched version referenced by "
        "its advisory. If no patched version exists yet, evaluate whether "
        "the vulnerable code path is actually reachable before deciding on "
        "a temporary mitigation."
    ),
    "secret": (
        "Revoke and rotate the exposed credential immediately -- treat it "
        "as compromised the moment it is committed, regardless of "
        "repository visibility. Remove it from version control history and "
        "store secrets in a dedicated secret manager or environment "
        "variable injected at runtime, never in source."
    ),
    "container": (
        "Pin base images to a specific digest, run as a non-root user, and "
        "remove unnecessary packages/build tools from the final image "
        "layer. Re-scan after upgrading the base image, since the "
        "vulnerability may originate there rather than in application code."
    ),
    "iac": (
        "Apply the principle of least privilege to the affected resource "
        "(narrow IAM policies, security groups, or network ACLs to exactly "
        "what is needed) and enable encryption at rest/in transit where the "
        "provider supports it by configuration."
    ),
}


class StaticSeedSource:
    def fetch(self, topic: str) -> str | None:
        return _SEED_CONTENT.get(topic)
