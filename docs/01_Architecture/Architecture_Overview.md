# Architecture Overview

## Why this document exists
Gives a single-page mental model of the whole system before diving into principles, patterns, or per-context detail. Every other document in `01_Architecture` and `02_Domain` elaborates on something introduced here.

## Architectural style
**Modular Monolith + Hexagonal Architecture + Domain-Driven Design.**

- **Modular monolith**: one deployable Python process containing 10 bounded contexts, each with clear boundaries and dependency rules — not a distributed system. This matches a single-operator project on modest hardware; splitting into microservices would add operational cost with no corresponding benefit at this scale.
- **Hexagonal architecture**: each bounded context exposes ports (interfaces) that adapters implement. The domain never depends on infrastructure; infrastructure depends on the domain's ports.
- **DDD**: 10 bounded contexts with their own ubiquitous language, entities, aggregates and domain events (see `02_Domain`).

## The core pipeline, one level down
```
Developer → GitHub PR → Webhook → SentinelAI Event Handler
  → Repository Port (fetch PR context)
  → Analysis Orchestrator (THIN — classification + coordination + correlation)
      → Scanner Port      → run scanners, normalize → NormalizedFinding
      → AI Port            → advisory enrichment (explain, suggest, deduplicate)
      → Risk Port          → deterministic contextual severity
      → Policy Port        → deterministic PASS / BLOCK
  → Reporting (developer view via GitHub, DevSecOps view: full report)
  → Audit (immutable record of the whole run)
```
See `Security_Decision_Flow.md` for the authoritative, detailed flow and `Analysis_Lifecycle.md` for the 12-stage breakdown.

## The rule that shapes everything else
**The Analysis Orchestrator is thin.** It classifies artifacts, correlates findings, and calls ports in sequence — it does not contain scanning logic, AI logic, risk logic, or policy logic. Each of those lives in its own bounded context behind its own port. This is what makes the system testable in isolation and what prevents "orchestrator sprawl," where all business logic silently accumulates in the one place everything passes through. See `Architecture_Principles.md` (P-01) for the enforced rule and its violation test.

## Process model in one sentence
Only the Orchestrator, Risk Engine, Policy Engine, correlation logic, persistence adapters and the in-process event bus run inside SentinelAI's Python process; scanners, the Ollama runtime, and (from Phase 3) the database server run as independent processes that can fail without taking the rest of the system down. Full detail in `Deployment_Strategy.md` and the Process Model section of `Bounded_Contexts.md`.

## The two actors
Developer (indirect, via GitHub only) and DevSecOps (direct, full configuration and reporting access). See `Interaction_Model.md`.

## Reading order for the rest of `01_Architecture`
`Architecture_Principles.md` → `Architecture_Patterns.md` → `Quality_Attributes.md` → `System_Boundaries.md` → `Interaction_Model.md` → `Input_Output_Model.md` → `Security_Decision_Flow.md` → `Technology_Strategy.md` → `Deployment_Strategy.md`.
