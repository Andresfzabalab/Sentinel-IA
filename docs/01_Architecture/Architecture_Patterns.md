# Architecture Patterns

## Why this document exists
Names the concrete design patterns used across SentinelAI and, for each, explains *why this pattern* rather than just describing it — the rationale is what makes this useful in an interview or a future decision.

## Hexagonal Architecture (Ports & Adapters)
**Where**: every bounded context that touches the outside world (Repository, Scanner, AI, Reporting, Notification, and persistence for all contexts).
**Why**: it is the single pattern that makes P-06/P-07/P-08 (domain, AI-provider, Git-provider independence) enforceable rather than aspirational — the domain simply cannot reach infrastructure types because it never imports them.

## Adapter Pattern
**Where**: `ScannerAdapter` implementations (Semgrep, Bandit, Trivy, Gitleaks, Checkov), `AIProviderAdapter` implementations (Ollama, OpenAI, Claude, Gemini), `RepositoryAdapter` (GitHub).
**Why**: each external tool or provider has a unique native format or API. The adapter is the only place that format-specific translation logic is allowed to live (P-05).

## Strategy Pattern
**Where**: scanner selection based on artifact type, and AI provider selection based on configuration.
**Why**: lets the Orchestrator ask "which scanners apply to this artifact?" or "which AI provider is configured?" without an if/else ladder that grows every time a new tool is added.

## Pipeline Pattern
**Where**: the whole PR analysis flow — classification → scanning → normalization → correlation → AI enrichment → risk → policy → reporting.
**Why**: each stage has a single input/output contract and can be tested, replaced, or made to degrade independently (e.g., AI enrichment stage becomes a no-op when the provider is unavailable, without changing the stages around it).

## Observer / Publish-Subscribe (in-process Event Bus)
**Where**: domain events such as `PullRequestReceived`, `ScanCompleted`, `FindingsCorrelated`, `RiskAssessed`, `PolicyEvaluated`, `AnalysisCompleted` (full list in `Domain_Events.md`).
**Why**: lets Audit, Reporting, and Notification react to what happened in the pipeline without the Orchestrator needing to know they exist — keeping the Orchestrator thin (P-01) and the contexts decoupled (P-06).

## Repository Pattern
**Where**: persistence access for every bounded context's aggregates (SQLite in MVP, PostgreSQL from Phase 3).
**Why**: isolates storage technology behind a domain-owned interface, so the Phase 3 SQLite→PostgreSQL migration touches only adapters, never domain logic.

## Explicitly avoided patterns (and why)
- **Microservices**: rejected for MVP — a modular monolith gives the same internal boundaries without the operational cost of a distributed system on single-operator hardware. Revisit only if a documented scaling need appears (`09_Decisions`).
- **Generic plugin framework for scanners**: rejected in favor of explicit adapters per scanner — a plugin system is speculative generality without a second consumer to justify it yet.
