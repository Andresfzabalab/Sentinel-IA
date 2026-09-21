# Architecture Principles

## Why this document exists
Each principle here is enforceable, not aspirational: it comes with a rule and, where meaningful, a description of a test that would fail if the principle were violated. This is what keeps the "critical architecture rules" from section 18 of the project handoff from eroding as the codebase grows.

## P-01 — The Analysis Orchestrator is thin
**Rule**: the Orchestrator may only classify artifacts, correlate findings, and call `RepositoryPort`, `ScannerPort`, `AIPort`, `RiskPort`, `PolicyPort` in sequence. It may not implement scanning, AI, risk, or policy logic itself.
**Violation test**: a test asserts that the Orchestrator module has no direct dependency on any scanner library, AI SDK, or policy rule structure — only on the port interfaces.

## P-02 — AI is advisory only
**Rule**: no code path may allow an AI response to set or influence the PASS/BLOCK verdict. The AI Port's return type must not include a verdict field; only `PolicyPort` may return one.
**Violation test**: a contract test on `AIPort`'s output schema asserts the absence of any pass/fail/verdict field; a separate test asserts `PolicyEngine` is the only caller of the function that produces the final verdict.

## P-03 — Risk assessment is deterministic
**Rule**: given identical inputs and identical configuration, the Risk Engine must always produce the same output. It must not call any AI provider.
**Violation test**: run the Risk Engine twice with identical inputs and assert byte-identical output; static check that the Risk context has no dependency on the AI context.

## P-04 — Policy evaluation is deterministic and DevSecOps-owned
**Rule**: policy rules are explicit, versioned, human-authored configuration. The Policy Engine must not call any AI provider and must produce the same verdict for the same (findings, risk, policy-version) triple.
**Violation test**: same determinism test pattern as P-03; a test confirms `PolicyEngine` has no dependency on the AI context.

## P-05 — Scanner output diversity is isolated at the adapter boundary
**Rule**: every scanner adapter is solely responsible for translating its tool's native format into `NormalizedFinding`. No component outside the Scanner context may parse native scanner output.
**Violation test**: static check that only Scanner-context adapter modules import scanner-specific parsing libraries or reference scanner-specific JSON keys.

## P-06 — Domain independence
**Rule**: each of the 10 bounded contexts depends on other contexts only through ports and domain events — never on another context's internal types.
**Violation test**: dependency-direction check (e.g., import-linter) run in CI across context boundaries.

## P-07 — AI provider independence
**Rule**: the domain and Orchestrator depend only on `AIProviderPort`; Ollama and API-provider adapters are interchangeable via configuration.
**Violation test**: the same Orchestrator integration test suite runs against a fake `AIProviderPort` implementation and must pass unmodified.

## P-08 — Git provider independence
**Rule**: the domain depends only on `RepositoryPort`; GitHub-specific types (webhook payloads, API models) stay inside the Repository context's adapter layer.
**Violation test**: static check that no domain or Orchestrator module imports a GitHub SDK type.

## P-09 — Independent-process failure isolation
**Rule**: a crash or timeout in an independent process (scanner subprocess, Ollama) must be caught at its adapter boundary and converted into a partial-result / degraded-mode outcome, never an unhandled exception that aborts the whole analysis.
**Violation test**: fault-injection test that kills a scanner subprocess mid-run and asserts the overall analysis still completes with the remaining scanners' results and a recorded partial-failure note.

## How these principles relate to Quality Attributes
Each principle above exists to satisfy one or more quality attribute scenarios in `Quality_Attributes.md` (auditability, testability, resilience). Where a future decision seems to require violating one of these, it must go through `09_Decisions` as an explicit, justified exception — not a silent drift.
