"""Data_Contracts.md's versioning convention: every cross-module contract
(Security Result, Finding, AI Enrichment, Agent Execution, Report) carries a
`contractVersion` field identifying the *shape* version, independent of
Policy Version or Security Knowledge Base entry versions. A single shared
constant, bumped only when a documented breaking change (Data_Contracts.md's
Schema Evolution Rules) actually happens -- never "just in case".
"""

from __future__ import annotations

CONTRACT_VERSION = "1.0"
