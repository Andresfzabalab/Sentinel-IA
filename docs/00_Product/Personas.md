# Personas

## Why this document exists
SentinelAI has exactly two actor types with very different permissions (see `Interaction_Model.md`). This document grounds them as personas so product and UX decisions (what a status check says, what a report contains) stay consistent with real needs instead of generic assumptions.

## Persona 1 — Developer ("Dana")
- **Role**: application engineer contributing code via Pull Requests.
- **Interaction with SentinelAI**: indirect only, through GitHub.
- **Sees**: PR status check (PASS/BLOCK), inline comments on specific lines, a summary comment.
- **Cannot do**: configure SentinelAI, define or change policies, suppress findings, access full reports or the audit trail.
- **Needs**: fast feedback, in-context explanations, actionable remediation — not a security report she has to interpret herself.
- **Frustration SentinelAI must avoid**: noisy, duplicated, unexplained findings that erode trust and get ignored.

## Persona 2 — DevSecOps engineer ("Devon")
- **Role**: owns application security posture across repositories.
- **Interaction with SentinelAI**: direct — the only actor with configuration access.
- **Can do**: configure scanners, AI provider, Git integration; define policy thresholds, mandatory scanners, suppressions and exceptions; view full analysis reports, history, and the audit trail.
- **Needs**: a system whose PASS/BLOCK decisions are deterministic, reproducible, and defensible to auditors and to engineering leadership — with AI explanations as a productivity aid, never as the source of the decision.
- **Frustration SentinelAI must avoid**: a "black box" verdict that can't be traced to a specific rule, or that changes because a model version changed.

## Why the split matters architecturally
This two-persona model is why the Policy context is deterministic and DevSecOps-owned, why the AI context is explicitly advisory-only, and why the Audit context exists as an independent bounded context rather than a logging afterthought.
