# Deployment Strategy

## Why this document exists
Describes how SentinelAI actually runs — locally today, and how that evolves — grounded in the Process Model distinction between in-process and independent-process components (see `Bounded_Contexts.md`).

## Local development (current target)
Single machine (reference hardware: 8th-gen i7, 16GB RAM, no GPU, mechanical HDD), running:
- The SentinelAI Python process (Orchestrator, all 10 bounded contexts' domain logic, in-process event bus, SQLite persistence).
- Scanner tools invoked as subprocesses or local Docker containers, on demand, per analysis.
- Ollama as a background local service on `localhost:11434`, if the local AI provider is configured.
- No Kubernetes, no orchestration layer — this is deliberate: it matches actual usage (one operator, one or few repositories) and avoids operational complexity with no corresponding benefit.

## Docker Compose (near-term)
As scanner tooling and Ollama both benefit from containerized, reproducible environments, a `docker-compose.yml` will define: the SentinelAI service, an optional Ollama service, and scanner containers invoked ad hoc. This keeps local setup reproducible across Windows/Linux/macOS (QA-09) without requiring Kubernetes.

## Production (future, Phase 3+)
- SentinelAI process deployed as a container, still a modular monolith (no premature microservice split).
- PostgreSQL as an independent, externally managed database service, replacing SQLite.
- Observability stack (structured logging, metrics, tracing) attached at the process boundary.
- Scanners remain independent processes/containers, invoked per analysis — this property doesn't change with scale, only where those processes run.

## What does NOT change across environments
The Process Model boundary is environment-independent by design:
- **In-process** (fails together with SentinelAI): Orchestrator, artifact classification, correlation, Risk Engine, Policy Engine, report generation, audit recording, event bus, persistence adapters.
- **Independent processes** (fail independently): scanners, Ollama, the database server (from Phase 3).

This means a scanner crash or a slow AI provider behaves identically whether SentinelAI runs on a laptop or in production — a property directly required by QA-03 and QA-04.

## Deployment non-goals for now
No multi-region deployment, no autoscaling, no Kubernetes operator for SentinelAI itself. These would be solving problems the project doesn't have yet; revisit only when a real scaling requirement is documented.
