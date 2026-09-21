# C4 Level 2 — Container Architecture

## 1. Purpose

This document defines the container-level (C4 Level 2) architecture of SentinelAI: the major runtime/deployment units, their responsibilities, how they communicate, and why the current boundaries are appropriate for the MVP. It sits between the system-context view (SentinelAI as a black box among GitHub, AI providers, and scanners) and the component-level view (the 10 bounded contexts inside the Python process). It does not redesign the component architecture — it explains how that architecture is packaged and deployed.

## 2. Architecture Summary

For the MVP, SentinelAI is a **modular monolith**: one Python process holds the Orchestrator and all domain logic (Analysis, Risk, Policy, Reporting, Audit, Repository, Scanner-coordination, AI-coordination, Notification, Identity), communicating internally through an in-process event bus and talking to SQLite through persistence adapters. Everything untrusted or independently failure-prone runs **outside** that process: security scanners run as controlled subprocesses, AI inference runs as an external HTTP service (Ollama locally, or an API provider), and GitHub is an external system reached over HTTPS. This split exists for one reason: PR code is untrusted input, and a scanner or AI failure must never be able to crash or block the deterministic security decision. Four containers, one process, no microservices — the boundaries are drawn around *failure isolation*, not around perceived future scale.

## 3. Container Diagram

```mermaid
C4Container
    title Container Diagram — SentinelAI (MVP)

    Person(devsecops, "DevSecOps", "Configures scanners, policy, AI provider. Views full reports and audit trail.")
    Person(developer, "Developer", "Opens PRs. Sees PASS/BLOCK and comments in GitHub only.")

    System_Ext(github, "GitHub", "Source of PR events. Destination for status checks and comments.")
    System_Ext(notify, "Notification Provider", "Slack / Teams / email (near-term extension).")

    Container_Boundary(sentinel, "SentinelAI Application") {
        Container(app, "SentinelAI Process", "Python (FastAPI candidate)", "Orchestrator + 10 bounded contexts' domain logic, in-process event bus, persistence adapters. THE modular monolith.")
    }

    ContainerDb(sqlite, "SQLite", "Embedded file DB", "MVP persistence: findings, reports, audit trail, config. In-process, file-based.")
    ContainerDb(postgres, "PostgreSQL (FUTURE — Phase 3+)", "External DB server", "Not deployed in MVP. Replaces SQLite when multi-instance/concurrent-write needs are real.")

    Container(scanners, "Security Scanner Execution", "Subprocess (future: Docker worker)", "Semgrep, Bandit, Trivy, Gitleaks, Checkov run as isolated, time/resource-limited subprocesses per analysis.")

    System_Ext(ai, "AI Provider", "Ollama (local, localhost:11434) or OpenAI / Claude / Gemini (API)", "Advisory-only enrichment: explanation, correlation context, remediation text. No verdict.")

    Rel(developer, github, "Opens/updates PR", "HTTPS")
    Rel(github, app, "PR opened/synchronize event", "Webhook (HTTPS, signature-verified)")
    Rel(app, github, "PR context fetch; status check + comments", "REST API (HTTPS)")
    Rel(github, developer, "Shows PASS/BLOCK + comments", "GitHub PR UI")

    Rel(devsecops, app, "Configure scanners/policy/AI, view full report + audit", "CLI / future web UI (HTTPS)")

    Rel(app, scanners, "Invoke per artifact type; return findings or failure", "Subprocess exec / stdout-stderr / exit code")
    Rel(app, ai, "Send correlated findings for enrichment", "HTTP (AIProviderPort)")
    Rel(ai, app, "Advisory text (explanation, remediation) — no verdict field", "HTTP response")

    Rel(app, sqlite, "Persist findings, reports, audit records, config", "File I/O (embedded)")
    Rel(app, postgres, "FUTURE: same persistence role as SQLite", "SQL over network — not present in MVP")

    Rel(app, notify, "Deliver PASS/BLOCK notification (near-term)", "Webhook / API")

    UpdateRelStyle(app, postgres, $lineStyle="dashed")
    UpdateLayout(TB)
```

**Notes on the diagram**

- `PostgreSQL` is drawn to show the evolution target only — it is **not** part of the MVP deployment and the relationship is dashed to mark it as future.
- AI providers are modeled as an **external system**, not an internal container, consistent with C4 semantics: SentinelAI does not own or deploy Ollama or any API provider's infrastructure — it only calls it through `AIProviderPort`.
- Notification provider (Slack/Teams/email) is included because it's named in the PRD as a near-term extension; the MVP's only guaranteed notification channel is the GitHub status check + comments, already covered by the GitHub relationship.

## 4. Container Responsibilities

| Container | Responsibility | Runtime | Communication |
|---|---|---|---|
| **SentinelAI Application** | API/webhook entry points, artifact classification, scanner selection, finding correlation, risk assessment, policy evaluation, report generation, audit recording, notification coordination, in-process event bus, persistence adapters | Single Python process (modular monolith) | Inbound: GitHub webhook (HTTPS), DevSecOps CLI/UI (HTTPS). Outbound: GitHub API, scanner subprocess exec, AI provider HTTP, SQLite file I/O |
| **Security Scanner Execution** | Runs Semgrep, Bandit, Trivy, Gitleaks, Checkov against PR-changed files; returns native output or a failure signal | Controlled subprocess per invocation (future: isolated Docker worker) | Invoked by the Orchestrator via subprocess exec; returns via stdout/stderr + exit code, consumed by the Scanner context's adapters |
| **AI Provider** | Advisory enrichment only: explanation, remediation suggestions, deduplication for readability | External HTTP service — Ollama locally (`localhost:11434`) or an API provider (OpenAI/Claude/Gemini) | Called via `AIProviderPort` over HTTP; response has no verdict field (P-02) |
| **SQLite** | MVP persistence for findings, reports, audit trail, configuration | Embedded, file-based, in the same process as the application | Local file I/O, no network hop |
| **PostgreSQL (future)** | Same persistence role as SQLite, for Phase 3+ when multi-instance/concurrent-write needs are documented | External, independently managed DB server | SQL over network — not present in the MVP |
| **GitHub (external)** | Source of PR events; destination for status checks, inline comments, summary comments | External SaaS | Inbound webhook to SentinelAI; outbound REST API calls from SentinelAI |
| **Notification Provider (external, near-term)** | Delivers PASS/BLOCK results to channels beyond GitHub | External SaaS/service | Outbound webhook/API call from SentinelAI's Notification context |

## 5. Runtime Boundaries

- **In-process** (fails together with SentinelAI, always available if the process is up): Orchestrator, artifact classification, correlation, Risk Engine, Policy Engine, Reporting, Audit recording, in-process event bus, persistence adapters.
- **Subprocess** (fails independently, isolated by the OS process boundary): each scanner invocation. A crash here cannot corrupt or halt the main process.
- **External service** (fails independently, reached over the network): AI provider (Ollama or API), GitHub, notification provider.
- **Embedded persistence**: SQLite lives inside the application's runtime footprint (a file on disk) — it is not a separate deployable, but it is architecturally treated as a replaceable adapter target (Repository pattern) so the future PostgreSQL migration touches only the persistence adapter layer, never domain logic.

This boundary is deliberately environment-independent: the same split applies whether SentinelAI runs on a laptop or, later, in a container in production (see `Deployment_Strategy.md`).

## 6. Main Analysis Flow

```
GitHub Webhook (PR opened/synchronize, signature-verified)
    → SentinelAI Application receives event
    → Retrieve PR Context (Repository Port → GitHub API)
    → Classify Changes (artifact type per file)
    → Select Scanners (Strategy: which scanners apply to which artifact types)
    → Execute Scanners (Security Scanner Execution container, isolated subprocesses)
    → Normalize Findings (per-scanner adapter → NormalizedFinding)
    → Correlate Findings (Orchestrator's correlation responsibility — not AI)
    → [Optional] AI Enrichment (AI Provider — explanation, remediation; advisory only)
    → Risk Assessment (deterministic, in-process)
    → Policy Evaluation (deterministic, in-process) → PASS / BLOCK
    → Report Generation (developer summary + DevSecOps full report)
    → GitHub status check + comments (Developer-visible)
    → Notification (near-term, additional channels)
    → Audit Recording (immutable, every run)
```

AI enrichment is explicitly a side branch: if skipped or unavailable, the flow proceeds directly from Correlation to Risk Assessment with no change to how a verdict is produced.

## 7. Failure Isolation

| Failure | Behavior | Effect on verdict |
|---|---|---|
| **Scanner crash/timeout** | Caught at the Scanner context's adapter boundary; that scanner's result is marked failed; remaining eligible scanners continue; the gap is recorded (never interpreted as "no findings") | Analysis still reaches a verdict, based on available scanner results |
| **AI provider unavailable/slow** | AI enrichment stage is skipped or marked degraded; flow proceeds directly to Risk Assessment | No effect — Risk and Policy never depended on AI (P-02, P-03, P-04) |
| **Persistence failure (SQLite)** | Must not change the deterministic decision already computed in-memory; the system distinguishes *security decision completed* from *persistence/audit failure* as separate outcomes | The verdict itself is unaffected, but its durability/auditability is — this must be surfaced distinctly, not silently swallowed |

Candidate status names for these outcomes (e.g., `ANALYSIS_COMPLETED_PERSISTENCE_FAILED` vs. `ANALYSIS_FAILED`) are not finalized here — see Open Questions.

## 8. Security Considerations

- **Untrusted PR code**: scanners run against attacker-influenced input by definition; they are isolated in their own subprocess so a malicious payload targeting a scanner cannot reach the main application memory space or persistence layer.
- **Scanner isolation**: today, OS-level subprocess isolation (timeout, working-directory scoping); the documented evolution path is Docker-based workers for stronger filesystem/network isolation.
- **Least privilege**: scanner subprocesses should run non-privileged, with restricted filesystem access (scoped to the PR diff/checkout) and restricted network access (most scanners need none).
- **Timeouts and resource limits**: every scanner invocation must have a bounded timeout and resource ceiling so one PR cannot exhaust host resources or stall the pipeline indefinitely.
- **Secret handling**: Gitleaks findings may contain actual secret values — these must never appear in Developer-visible outputs (GitHub status/comments), only in the DevSecOps-only full report, per the redaction rule in `Input_Output_Model.md`.
- **Webhook validation**: every inbound GitHub webhook must be signature-verified before triggering any analysis — it is untrusted input by definition (`System_Boundaries.md`).
- **AI output as untrusted text**: AI provider responses are never parsed as instructions and structurally cannot carry a verdict field (P-02); they are treated as opaque advisory text through the entire pipeline.

## 9. Evolution Path

```
MVP
Modular Monolith (single process) + SQLite (embedded) + Scanner Subprocesses + Optional Ollama
    ↓
Near-term
Docker Compose: SentinelAI container + optional Ollama container + scanner containers (reproducible local setup)
    ↓
Future (Phase 3+)
Containerized SentinelAI deployment + PostgreSQL (external, independent process)
    ↓
Future
Worker-based scanner execution (isolated Docker workers instead of local subprocesses)
    ↓
Future
Scalable SaaS architecture (only if a documented scaling need appears — no premature microservice split)
```

This path is described at the depth needed to show the current boundaries don't paint the project into a corner — not as a committed future design.

## 10. Open Architectural Questions

1. **Web/API framework**: FastAPI is the leading candidate (per `Technology_Strategy.md`) but not yet confirmed via `08_Engineering_Research` or locked into an ADR.
2. **Scanner isolation mechanism for MVP**: whether the first implementation uses bare subprocesses or local Docker containers from day one, or subprocess first with Docker as a fast-follow, is not yet decided.
3. **DevSecOps interface**: CLI, web UI, or both for the MVP — `Interaction_Model.md` explicitly defers this to a later implementation phase.
4. **Final domain status vocabulary for degraded outcomes**: e.g., how to name "verdict completed but audit write failed" distinctly from "verdict completed normally" and from "analysis failed entirely" — proposed candidates exist above but are not ratified.
5. **Notification container boundary**: whether the Notification context talks to external providers directly from the main process (as modeled here) or through a dedicated outbound adapter process, once more than GitHub is in scope.

---

*This document assumes the existence of a C4 Level 1 (System Context) diagram and the C4 Level 3 component architecture described in the project brief. Both were referenced during this work but were not available as separate files at the time of writing — see the consistency review for details.*
