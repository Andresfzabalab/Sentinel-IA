# Implementation Strategy

## Purpose

This document fixes the order SentinelAI gets built in, and — for each phase — what gets built, what it depends on, what proves it works before moving on, and which existing document governs it. The order is chosen specifically so that hexagonal architecture's actual payoff (testing domain logic without any real infrastructure) is realized early, rather than being a claim the architecture makes that the build order never takes advantage of.

## Why This Order

The build order is bottom-up through `Project_Structure.md`'s dependency direction (`interfaces → application → domain`, with `infrastructure` implementing `ports` on the side), not top-down through the user-visible feature list. GitHub integration and scanner adapters — the two most "visible" pieces of the MVP — deliberately come *after* persistence and domain, because everything in between can be built and fully tested against fakes (per QA-05/QA-06) before any real external system is involved. Building GitHub or scanner adapters first would mean testing domain logic through real network calls and real subprocesses from day one, which is slower, flakier, and exactly what the port/adapter separation exists to avoid.

## Phase 0 — Foundation

**Builds**: project skeleton (`Project_Structure.md`), configuration loading and the local execution gate (`Configuration_and_Secrets.md`), structured logging setup (`Observability_and_Logging.md`), the `correlationId` derivation utility (Mode A/B, `Domain_Events.md`), and the API error envelope shape (`API_Contract.md`).

**Depends on**: nothing.

**Proves it works when**: the application starts, logs a structured startup event, and refuses to start (with a clear error) when a mandatory secret is missing, per `Configuration_and_Secrets.md`'s gate table.

## Phase 1 — Persistence

**Builds**: every table in `Data_Model.md`, a migration runner satisfying `Persistence_Strategy.md`'s principles (forward-only, additive-first, `schema_migrations` tracked), and every `*Store` adapter (`SqliteAnalysisStore`, `SqliteRepositoryConfigStore`, `SqlitePolicyStore`, `SqliteAuditStore`, `SqliteNotificationStore`, `SqliteAgentExecutionStore`, `SqliteKnowledgeBaseStore`), WAL mode enabled, with the per-`analysis_id` serialization queue stubbed in (its real exercise comes in Phase 6).

**Depends on**: Phase 0.

**Proves it works when**: persistence tests (`Testing_Strategy.md`) pass against a real SQLite file — every constraint in `Data_Model.md` is exercised directly (the `UNIQUE(correlation_id)` idempotency backstop, the `WHERE verdict IS NULL` write-once guard, the absence of cross-module foreign keys), with no domain logic involved yet.

## Phase 2 — Domain

**Builds**: every Aggregate, Entity, and Value Object (`Entities_Value_Objects.md`) and every pure Domain Service (`Domain_Services.md`): Artifact Classification, Scanner Selection, Risk Assessment, Security Score Calculation, Policy Evaluation, plus the Aggregate methods that enforce invariants (`Analysis.recordVerdict()`, `Policy.publishVersion()`).

**Depends on**: Phase 0 only — **not** Phase 1. This is deliberate: domain code must compile, run, and be fully unit-tested using in-memory fakes for every port, with zero SQLite involvement, per QA-05.

**Proves it works when**: unit tests cover every invariant in `Entities_Value_Objects.md`'s "Invariant Summary" table, and the determinism property (QA-02 — same inputs always produce the same Risk/Score/verdict) is directly tested by calling the same Domain Service twice with identical inputs.

## Phase 3 — Application Use Cases (Against Fakes)

**Builds**: the Analysis Orchestrator (`Domain_Services.md`), wiring T1→T3 (`Aggregates_and_Boundaries.md`, `Persistence_Strategy.md`) end-to-end — but against **fake** `RepositoryPort` and `ScannerPort` implementations (in-memory, scripted to return canned PR contexts and canned scanner outputs), not real ones yet. Real `*Store` adapters from Phase 1 are used here, since persistence is already proven.

**Depends on**: Phases 1 and 2.

**Proves it works when**: a full, real database-backed Analysis runs from a fake `PullRequestReceived` trigger through to a persisted verdict — including the idempotency path (a repeated `correlationId` returns the same `analysisId`) and the T1-Failed path (a fake `RepositoryPort` configured to fail produces a `failed` Analysis, never a hang). This is the first point at which "the whole pipeline works" is demonstrable, entirely offline.

## Phase 4 — GitHub Integration

**Builds**: the real `RepositoryPort` adapter (`GitHub_Integration.md`): webhook signature validation, PR/changed-files retrieval, Commit Status posting, PR comment posting, retry/backoff, rate-limit handling.

**Depends on**: Phase 3 (the fake `RepositoryPort` is simply swapped for the real one — nothing else in the Orchestrator changes, which is the point of the port/adapter separation).

**Proves it works when**: a real webhook delivery (from a sandbox/test GitHub repository) reaches the webhook endpoint, is signature-verified, and is retrievable end-to-end through to a Commit Status post — with `ScannerPort` still faked, since scanner adapters aren't built yet.

## Phase 5 — Scanner Adapters

**Builds**: the real `ScannerPort` implementations — Semgrep, Bandit, Trivy, Gitleaks, Checkov — each translating native output into `NormalizedFinding` (P-05), enforcing the configured `timeout_seconds`, and populating `scanner_version`, `exit_code`, and `execution_metadata` (`Data_Model.md`).

**Depends on**: Phase 2 (the `Finding` domain shape) and Phase 1 (the `scanner_execution`/`finding` tables) — not Phase 4, since scanner adapters have no dependency on GitHub at all.

**Proves it works when**: each adapter, run against a fixture repository with a known vulnerability of its category, produces the expected `NormalizedFinding`; a forced timeout produces `status = 'timed_out'`, never a hang or an unhandled exception (P-09).

## Phase 6 — Analysis Pipeline (Full Integration)

**Builds**: nothing new — this phase wires the real `RepositoryPort` (Phase 4) and real `ScannerPort` adapters (Phase 5) into the same Analysis Orchestrator proven in Phase 3, and exercises the per-`analysis_id` serialization queue for real, concurrent scanner completions.

**Depends on**: Phases 3, 4, and 5.

**Proves it works when**: a real GitHub PR against a real test repository, scanned by real tools, produces a real, persisted verdict — plus the Crash & Restart Recovery sweep (`Persistence_Strategy.md`) is exercised by deliberately killing the process mid-Analysis and verifying no row is left permanently `running` after restart.

## Phase 7 — Repository & Policy Configuration (Including Suppression)

**Builds**: `T-Repo` and `T-Policy` write paths (UC-3, UC-4, UC-9) as callable application-layer operations, including Policy Version publishing with suppression rules.

**Depends on**: Phase 1 (the tables already exist) and Phase 2 (Policy Evaluation Service already knows how to apply suppression rules from a Policy Version).

**Proves it works when**: a DevSecOps-authored suppression rule, published as a new Policy Version, changes a subsequent (not a retroactive) Analysis's verdict — and an Analysis already `completed` before that publish is provably unaffected.

## Phase 8 — API

**Builds**: every endpoint in `API_Contract.md`, the OAuth boundary (login/callback/logout, session validation), and the error envelope wired to real error conditions from every phase so far.

**Depends on**: Phases 6 and 7 (there must be something real to trigger, query, and configure).

**Proves it works when**: a DevSecOps user can authenticate, trigger a Mode A or Mode B Analysis, poll its status via `GET /analyses?correlationId=...`, and read its report and audit trail — entirely through HTTP, no direct database or code access needed.

## Phase 9 — AI / Agent

**Builds**: the real `AIProviderPort` adapters (Ollama, OpenAI, Claude, Gemini), the Agent Execution Framework (Agent Registry, Tool Registry, guardrails, execution limits), the Security Investigation Agent, and the Security Intelligence & Data Module (Knowledge Refresh Service, `SecurityKnowledgeBasePort`).

**Depends on**: Phase 6 only, for the `SecurityResultQueryPort` it reads through. **This phase can be built in parallel with Phases 4–8** — its internal mechanics (the Framework, the Agent's tool-calling loop, the Knowledge Base) need only a fake `SecurityResultQueryPort` to develop and test against, since the module boundary (`Module_Boundaries.md`) already guarantees it has no dependency in the other direction.

**Proves it works when**: a completed Analysis triggers a Security Investigation Agent run that produces advisory output citing real Security Knowledge Base entries; separately, a simulated AI provider outage produces `AI Analysis: PENDING` on the Report without at any point affecting the Analysis's already-fixed verdict (QA-04) — this is the single most important test in this phase, since it's the direct, demonstrable proof of P-02.

## Phase 10 — Reports & Notifications

**Builds**: the Report Generation Service (joining the frozen Security Result with, when available, AI Enrichment output — never mutating either), and the Notification Dispatch Service for channels beyond the mandatory GitHub status (already working since Phase 4).

**Depends on**: Phases 6, 8, and 9.

**Proves it works when**: the Developer-facing and DevSecOps-facing Report representations both render correctly from the same Analysis, redaction is verified (no raw secret values reach the Developer-facing representation), and the `aiSection.status` transition from `pending` to `complete` is observable without regenerating anything else in the Report.

## Phase 11 — Observability & Hardening

**Builds**: the full structured-logging surface (`Observability_and_Logging.md`), the error-handling behavior for every case in `Error_Handling_and_Resilience.md` not already exercised incidentally by an earlier phase's tests (notably SQLite write-failure handling and invalid-configuration rejection), and a final pass against the whole `Testing_Strategy.md` test matrix.

**Depends on**: every prior phase.

**Proves it works when**: the full test matrix in `Testing_Strategy.md` passes, and a complete Analysis's story — from webhook receipt to Commit Status post — is reconstructable purely from logs plus the Audit trail, for both a successful run and a `failed`/degraded one.

## Phase Gate Summary

| Phase | Gate to enter next phase |
|---|---|
| 0 → 1 | App starts and enforces the secrets gate |
| 1 → 2 | Persistence tests pass against real SQLite |
| 2 → 3 | Domain unit tests pass fully offline, determinism proven |
| 3 → 4 | Full T1–T3 pipeline works against fakes, including idempotency and T1-Failed |
| 4 → 5 | Real webhook reaches a real Commit Status post (scanners still faked) |
| 5 → 6 | Each real scanner adapter passes its fixture test, including timeout handling |
| 6 → 7 | A real end-to-end Analysis persists a real verdict; crash recovery verified |
| 7 → 8 | Suppression provably affects only future, not past, Analyses |
| 8 → 9 | Full DevSecOps flow works over HTTP |
| 9 → 10 | AI unavailability provably never changes a verdict |
| 10 → 11 | Both Report audiences render correctly with proven redaction |
| 11 → done | Full test matrix passes; any Analysis is fully diagnosable from logs + Audit |

No phase is considered complete on the basis of code existing — only on the basis of its stated proof passing, per `Testing_Strategy.md`.
