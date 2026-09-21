# Domain Services

## Purpose

This document defines SentinelAI's Domain Services: which cross-cutting logic needs a service at all, which of that logic is genuine domain logic versus application/orchestration logic, and which logic should simply stay as a method on an Aggregate. It builds directly on `Aggregates_and_Boundaries.md` (the Aggregates these services operate on or around) and `Module_Boundaries.md` (which module each service lives in and what it may cross).

## Classification Principle

Three categories, not two — conflating them is exactly the kind of ambiguity that causes rework once code exists:

- **Aggregate method**: logic that only needs the state already inside one Aggregate's consistency boundary. No service needed — it belongs on the Entity/Aggregate Root itself.
- **Domain Service**: logic that expresses a business rule or invariant, needs no external I/O to compute, but doesn't belong to any single Aggregate (it reads across aggregates, or the rule itself is the reason it exists as an addressable thing).
- **Application/Orchestration Service**: logic that coordinates — calls ports in sequence, handles external I/O, manages scheduling/retries — without itself encoding a business rule. It moves data and triggers domain logic; it does not decide anything.

Getting this right now matters because a Domain Service must stay testable with zero infrastructure (QA-05); an Application/Orchestration Service is exactly where infrastructure concerns are allowed to live.

## Domain Services — Sentinel Core

| Service | Reads across | Inputs | Outputs | Invariant enforced |
|---|---|---|---|---|
| **Artifact Classification Service** | Configured classification rules (path/extension patterns → Artifact type mapping — system-level, not per-Aggregate state) | Changed file paths (from the PR snapshot or manual trigger) | `Artifact` values (path, type, changeKind) — this output *becomes* Analysis's `ArtifactList` once written at T1; the service builds that list, it does not read it as a pre-existing input | Every changed file gets exactly one type before scanner selection runs |
| **Scanner Selection Service** (Strategy) | Repository Aggregate (`enabledScanners`) + Analysis Aggregate (`ArtifactList`) | Artifact types, Repository config | Set of scanners to invoke per Artifact | A scanner is only selected if both enabled for the Repository and applicable to the Artifact type (QA-07) |
| **Risk Assessment Service** | Analysis's Findings + configured heuristics | Findings with Severity | Risk value per Finding | Deterministic: identical inputs always produce identical output (P-03); never calls `AIProviderPort` |
| **Security Score Calculation Service** | Analysis's risk-assessed Findings | Risk-assessed Findings | One `SecurityScore` value | Pure aggregation — no side effects, no external calls |
| **Policy Evaluation Service** | Analysis Aggregate (Findings/Risk/Score) + Policy Aggregate (`PolicyVersion`, including any suppression rules it contains — UC-9) | Risk-assessed Findings, Security Score, a specific Policy Version | A **computed** PASS/BLOCK verdict *value* | The only service that decides what the verdict should be (P-04); never calls `AIProviderPort`; must produce the same verdict for the same (Findings, Risk, PolicyVersion) triple (QA-02). It does not persist the verdict — see "What Stays Inside an Aggregate" below for `Analysis.recordVerdict()`, the Aggregate method that does |

## Domain Services — AI & Agent Module

| Service | Reads across | Inputs | Outputs | Invariant enforced |
|---|---|---|---|---|
| **AI Enrichment Service** | The completed Security Result (read-only, via `SecurityResultQueryPort`) | Correlated Findings / Security Result context | AI Enrichment values | Structurally cannot produce a verdict or score field (P-02); read-only against Sentinel Core — no write path exists |

The **Security Investigation Agent's** reasoning loop (deciding which read-only tool to call next, when to cite the Knowledge Base, when to declare "insufficient knowledge") is domain logic specific to that agent's role, but it runs *inside* the Agent Execution Framework's execution loop — it is not listed as a separate Domain Service here because its behavior is bounded by the Framework's guardrails (`AI_Agent_Architecture.md` §4) rather than by an independent contract of its own.

## Explicitly Application/Orchestration Services, Not Domain Services

| Service | Module | Why it is orchestration, not domain |
|---|---|---|
| **Analysis Orchestrator** | Sentinel Core | Calls `RepositoryPort`, `ScannerPort`, `RiskPort`, `PolicyPort` in sequence (P-01). It coordinates; it does not itself compute Risk, Policy, or any business rule. This is the textbook Application Service — thin by design. |
| **Knowledge Refresh Service** | Security Intelligence & Data Module | Schedules and executes calls to `SecurityIntelligenceSourcePort` adapters, versions the results, and writes them to `KnowledgeBaseStore`. It computes no business rule — it acquires, versions, and stores external data. Treating it as a Domain Service would blur business logic with external data acquisition, which is exactly the ambiguity this module exists to avoid. |
| **Agent Execution Runner** | AI & Agent Module | Drives one Security Investigation Agent run end to end: pulls the Security Result via `SecurityResultQueryPort`, enforces execution limits, logs tool calls, and hands the result to Report generation. It orchestrates the Agent Execution Framework; the actual advisory content comes from the AI Enrichment Service and the LLM call, not from this runner. |
| **Report Generation Service** | AI & Agent Module | Merges the (already-final) Security Result with the (possibly still-pending) Agent Execution output into a Report projection. It applies formatting/redaction rules, not business rules about severity or risk. |
| **Notification Dispatch Service** | Sentinel Core (mandatory channel) / AI & Agent Module (enriched channels) | Delivers a verdict or Report to a channel and records the delivery outcome. Pure I/O coordination. |

## What Stays Inside an Aggregate (No Service at All)

- **Correlation of Findings**: happens entirely within the Analysis Aggregate's own boundary (Findings are child entities of the same Analysis), per `Architecture_Overview.md`. It's internal Analysis behavior invoked during T3 — not a cross-aggregate concern, so it does not need a Domain Service wrapper.
- **`ScannerExecution` state transitions** (`running` → `succeeded`/`failed`/`timedOut`): a method on the `ScannerExecution` Entity itself.
- **`Analysis.recordVerdict(verdict)`**: a method on the Aggregate Root that enforces "write-once" — distinct from the *Policy Evaluation Service*, which computes what the verdict should be. The service decides; the Aggregate method enforces the invariant about how that decision gets recorded.
- **`Policy.publishVersion(...)`**: a method on the Policy Aggregate that enforces immutability of prior versions.

## Service → Port Mapping

| Service | Calls |
|---|---|
| Scanner Selection Service | reads Repository config (via `RepositoryConfigStore`) |
| Risk Assessment Service | no external port — pure function over in-memory Analysis state |
| Policy Evaluation Service | reads `PolicyStore` for the referenced `PolicyVersion` |
| Analysis Orchestrator | `RepositoryPort`, `ScannerPort`, `EventBusPort` |
| AI Enrichment Service | `AIProviderPort`, `SecurityResultQueryPort` (read-only) |
| Agent Execution Runner | `SecurityResultQueryPort`, `SecurityKnowledgeBasePort` (both read-only), `AgentExecutionStore`, `AuditRecorderPort` (write, restricted to Audit only) |
| Knowledge Refresh Service | `SecurityIntelligenceSourcePort`, `KnowledgeBaseStore` |
| Report Generation Service | reads `AnalysisStore` and `AgentExecutionStore`; writes a Report projection |
| Notification Dispatch Service | `RepositoryPort` — **used exclusively to deliver the GitHub status check/comment (the mandatory channel)**; never to read or modify the Repository Aggregate's configuration (that is `RepositoryConfigStore`'s exclusive concern, per `Ports_and_Interfaces.md`) — plus other channel adapters as they're added |

See `Ports_and_Interfaces.md` for the full port catalog and read/write direction of each.
