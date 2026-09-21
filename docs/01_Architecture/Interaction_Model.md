# Interaction Model

## Why this document exists
Specifies precisely how each actor — human or system — interacts with SentinelAI, so UI/reporting decisions and permission boundaries stay consistent with `Personas.md`.

## Developer — indirect interaction only
```
Developer → creates/updates Pull Request → GitHub
GitHub → SentinelAI (via webhook, system-to-system)
SentinelAI → GitHub (status check + inline comments + summary comment)
GitHub → Developer (sees results in the PR UI)
```
The Developer never calls SentinelAI directly and has no configuration surface. This is deliberate: it keeps SentinelAI's trusted configuration surface limited to one persona (P-06-adjacent: reduces attack surface, simplifies the Identity context).

## DevSecOps — direct interaction
```
DevSecOps
    │
    ├── Configure   → scanners, AI provider, Git integration        (Identity + Policy + Scanner + AI contexts)
    ├── Policies    → thresholds, mandatory scanners, suppressions  (Policy context)
    └── Reports     → full analysis reports, audit trail, history   (Reporting + Audit contexts)
```
DevSecOps interacts through a dedicated interface (CLI and/or web UI, to be decided in later implementation phases) authenticated via the Identity context.

## System-to-system interactions
| From | To | Trigger | Nature |
|---|---|---|---|
| GitHub | SentinelAI | PR opened/synchronized | Webhook (untrusted input, signature-verified) |
| SentinelAI | GitHub | Analysis complete | API call (status check, comments) |
| SentinelAI (Orchestrator) | Scanner processes | Analysis start | Subprocess/container invocation |
| SentinelAI (Orchestrator) | Ollama or API provider | AI enrichment stage | HTTP call via `AIProviderPort` |
| SentinelAI internal contexts | Each other | Domain events | In-process publish/subscribe (event bus) |

## Permission summary
| Capability | Developer | DevSecOps |
|---|---|---|
| Trigger analysis (via PR) | Yes (indirect) | Yes (indirect) |
| See PASS/BLOCK + inline comments | Yes | Yes |
| Configure scanners/AI/Git integration | No | Yes |
| Define/change policy | No | Yes |
| View full report | No | Yes |
| View audit trail | No | Yes |
| Suppress a finding | No | Yes |

## What this document conditions
The Identity bounded context's authorization model must enforce exactly this table — not a generic role system with more permissions than the product needs.
