# Testing Strategy

## Purpose

This document defines how SentinelAI proves it works, at every level from a single Domain Service to a full end-to-end Analysis. It is written to convert directly into `pytest` suites: each section below names a real test category, what it exercises, what it depends on, and where it lives under `tests/` (`Project_Structure.md`).

## Test Pyramid and Fakes

Every port in `Ports_and_Interfaces.md` has exactly one **Fake** implementation (in-memory, deterministic, scriptable) used across unit and application-layer tests — not a mocking-framework mock reconstructed per test file. This is what makes QA-05 ("domain logic reaches meaningfully higher unit-test coverage than adapters, and can run fully offline") and QA-06 ("the full Orchestrator test suite passes unmodified against a fake `AIProviderPort`") checkable rather than aspirational. The pyramid, from most to fewest tests:

1. **Unit tests** (`domain/`, pure Domain Services) — no I/O, no fakes even needed, just function calls.
2. **Application-layer tests** — Application Services wired to Fakes.
3. **Persistence tests** — real SQLite, no domain logic.
4. **Contract tests** — schema/shape verification, independent of behavior.
5. **Integration tests** — two or more real components together (e.g., real `AnalysisStore` + real Domain Services).
6. **Adapter-specific tests** (scanner, GitHub, AI provider) — one real external dependency at a time.
7. **End-to-end tests** — the fewest, slowest, most realistic.

## Unit Tests

**Location**: `tests/core/domain/`, `tests/intelligence/domain/`, `tests/ai_agent/domain/`.

**Covers**: every invariant in `Entities_Value_Objects.md`'s "Invariant Summary" table (verdict set exactly once, no Finding without normalization, Policy Versions immutable once published, Audit Records append-only, AI Enrichment/Agent Execution output structurally excludes a verdict/score field); every Domain Service in `Domain_Services.md` as a pure function (Artifact Classification, Scanner Selection, Risk Assessment, Security Score Calculation, Policy Evaluation, including suppression-rule application per UC-9).

**Explicit test**: **PASS/BLOCK determinism** (QA-02) — call Policy Evaluation twice with byte-identical (Findings, Risk, PolicyVersion) inputs and assert a byte-identical verdict; repeat with a different (or absent) AI-provider configuration in the surrounding context and assert the verdict is unaffected, since Policy Evaluation never reads AI state at all (P-02, P-04).

## Application-Layer Tests (Against Fakes)

**Location**: `tests/core/application/`, `tests/ai_agent/application/`, `tests/intelligence/application/`.

**Covers**: the Analysis Orchestrator running a full T1→T3 sequence against `FakeRepositoryPort` and `FakeScannerPort`; the Agent Execution Runner against a `FakeAIProviderPort` and `FakeSecurityResultQueryPort`; the Knowledge Refresh Service against a `FakeSecurityIntelligenceSourcePort`.

**Explicit test**: **QA-06 (provider portability)** — the entire Orchestrator/Agent test suite runs unmodified against a `FakeAIProviderPort` that simulates Ollama, then again simulating an API provider's response shape; both pass with no code change.

## Persistence Tests

**Location**: `tests/infrastructure/core/sqlite/`, `tests/infrastructure/ai_agent/sqlite/`, `tests/infrastructure/intelligence/sqlite/`. Real SQLite file (a fresh temp file per test), no domain logic involved.

**Covers**: every constraint in `Data_Model.md` directly — `UNIQUE(correlation_id)` rejects a duplicate T1 insert; the `WHERE verdict IS NULL` clause rejects a second T3 write attempt; `UNIQUE(policy_id, version_number)` and `UNIQUE(topic, version)` reject duplicate publishes; a query against `agent_execution`/`ai_enrichment` never requires or exercises a foreign key into `analysis`/`finding` (there isn't one, by design — `Data_Model.md`'s physical-layout rule).

## Contract Tests

**Location**: `tests/contract/`.

**Covers**: every payload named in `Data_Contracts.md` (Security Result, Finding, AI Enrichment, Agent Execution, Report) validates against its documented shape, including the `contractVersion` field being present and the structural exclusion of `verdict`/`securityScore` from `AI Enrichment` being enforced by schema, not just by convention; every endpoint in `API_Contract.md` is asserted against its documented request/response shape and error envelope, independent of what the endpoint actually does behind the scenes.

## Scanner Adapter Tests

**Location**: `tests/infrastructure/core/scanners/`.

**Covers**, per adapter (Semgrep, Bandit, Trivy, Gitleaks, Checkov): a **golden-fixture** approach — a canned native output fixture in, an expected `NormalizedFinding` set out, verifying P-05's translation boundary is respected (no native format ever leaks past the adapter). Separately: `scanner_version`, `exit_code`, and `execution_metadata` (`Data_Model.md`) are correctly populated from a real or simulated subprocess run; a forced timeout produces `status = 'timed_out'`, not a hang or an unhandled exception in the calling Orchestrator.

## GitHub Integration Tests

**Location**: `tests/infrastructure/core/github/`.

**Covers**: signature validation against both a valid and a deliberately invalid `X-Hub-Signature-256` (the invalid case must never reach `correlationId` derivation); webhook payload parsing for `opened`/`synchronize` and correct ignoring of other actions; retry/backoff behavior against simulated `5xx` and `429` responses (mocked HTTP, not real GitHub, for the automated suite); pagination handling for the changed-files endpoint. A small, separate, manually-run suite against a real sandbox GitHub repository is out of the automated CI tier — it exists as a pre-release smoke check, not a per-commit gate.

## Pipeline Tests

**Location**: `tests/integration/pipeline/`.

**Covers**: the full UC-1/UC-2 flow at increasing levels of realism — all-fakes (Phase 3, `Implementation_Strategy.md`), real GitHub adapter with faked scanners (Phase 4), real scanners with faked GitHub (Phase 5), and fully real (Phase 6). Each level is its own test tier, not a single test re-run with different flags, so a regression is traceable to exactly which boundary broke.

## Security Tests

**Location**: `tests/security/`.

**Covers**: webhook signature bypass attempts (tampered body with a stale/reused signature); redaction verification — a Finding with `secret_value_redaction_flag = true` never appears with its raw value in a Developer-facing Report, an API response, or a log line (`Observability_and_Logging.md`); auth bypass attempts on every DevSecOps-facing endpoint (missing token, expired session, malformed token — all must be `401` before any business logic runs); input validation on every write endpoint (`API_Contract.md`'s error model) against malformed/oversized payloads; a scanner subprocess's filesystem/network restriction is actually enforced, not just documented (`C4_Container.md` §8).

## Failure / Recovery Tests

**Location**: `tests/integration/resilience/`.

**Covers**: a scanner killed mid-execution (simulated crash, not just a non-zero exit) still allows the owning Analysis to reach T3 using the remaining scanners' results (P-09, QA-03); a SentinelAI process killed between T1 and T2, between two T2s, and between the last T2 and T3, followed by a restart, verified against `Persistence_Strategy.md`'s Crash & Restart Recovery sweep — no row is left permanently `running` in any of the three timing scenarios; an exhausted PR-context-retrieval retry sequence produces a `failed` Analysis with `failure_reason = 'pr_context_retrieval_failed'`, never a hang, never a fabricated verdict (`Persistence_Strategy.md`, `GitHub_Integration.md`).

## AI Unavailable Tests

**Location**: `tests/integration/ai_agent/`.

**Covers**: a `FakeAIProviderPort` configured to time out or error produces `Agent Execution.status = 'pending_unavailable'` and `Report.aiSection.status = 'pending'`, while the Analysis's `verdict` and `securityScore` — computed entirely before this point — are asserted to be **byte-identical** to a control run where the AI provider succeeds. This is the direct, automated proof of P-02 and QA-04, not just a documented claim.

## Idempotency Tests

**Location**: `tests/integration/idempotency/`.

**Covers**: a duplicate Mode A trigger (same `repositoryId` + `prNumber` + `headCommitSha`, simulating a redelivered webhook) returns the same `analysisId` and creates no second `analysis` row; a duplicate Mode B trigger with the same `manualTriggerKey` behaves the same way; a duplicate Mode B trigger with **no** key (or a different key) is asserted to correctly create a **second**, legitimate Analysis — proving the idempotency boundary is exactly where `Domain_Events.md` draws it, not broader.

## Crash Recovery Tests

**Location**: `tests/integration/resilience/` (alongside Failure/Recovery, sharing fixtures — listed separately here because it is explicitly called out as its own test category).

**Covers**: the specific recovery-sweep steps from `Persistence_Strategy.md` in isolation — step 1 (every `running` `scanner_execution` becomes `failed` on startup) and step 2 (every `running` `analysis` is re-evaluated against the now-resolved scanner set) are each tested independently before being tested together, so a failure in the sweep is traceable to the specific step.

## What Is Deliberately Not in Automated CI

- Real calls to GitHub, real AI providers, or real security intelligence feeds — all covered by Fakes or mocks in the automated tiers, with a small, separately-run manual/staging suite for pre-release confidence.
- Load/performance testing — no requirement in `Quality_Attributes.md` currently calls for it beyond QA-08's resource-frugality scenario, which is validated by observation on the reference hardware, not a dedicated load-testing harness, consistent with not building more than the MVP's stated scale requires.

## Coverage Expectation

Per QA-05: `core/domain/`, `intelligence/domain/`, and `ai_agent/domain/` (the pure logic) carry meaningfully higher test coverage than `infrastructure/` — an adapter's job is to correctly implement a port's contract, which is proven by its specific adapter test, not by chasing a uniform coverage percentage across the whole codebase.
