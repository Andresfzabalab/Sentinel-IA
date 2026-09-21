# Quality Attributes

## Why this document exists
Makes non-functional requirements concrete and testable using SEI-style scenarios (stimulus, environment, response, response measure), instead of vague adjectives like "scalable" or "secure."

## QA-01 — Auditability
**Scenario**: A DevSecOps engineer reviews why a specific PR was blocked six months ago.
**Response**: The audit trail returns the exact findings, risk scores, policy version, and rule(s) that produced the verdict.
**Measure**: 100% of historical PASS/BLOCK verdicts are reconstructable from the Audit context alone, without needing AI provider logs.

## QA-02 — Determinism of the merge decision
**Scenario**: The same PR is re-analyzed twice with the same policy configuration but a different AI provider.
**Response**: The PASS/BLOCK verdict is identical both times.
**Measure**: 0% variance in verdict across AI providers for identical findings/policy inputs (see P-02, P-04).

## QA-03 — Resilience to independent-process failure
**Scenario**: A scanner subprocess crashes mid-analysis.
**Response**: The analysis completes using the remaining scanners' results, with a recorded partial-failure note.
**Measure**: Analysis completion rate unaffected by single-scanner failure, verified by fault injection (P-09).

## QA-04 — Graceful AI degradation
**Scenario**: The configured AI provider (local or API) is unreachable or times out.
**Response**: The analysis proceeds to Risk and Policy without AI enrichment; findings are still reported, minus explanations/remediation text.
**Measure**: Analysis still reaches a verdict within the normal time budget plus a bounded AI-timeout margin.

## QA-05 — Testability
**Scenario**: A developer wants to test Policy Engine behavior without running any scanner or AI provider.
**Response**: The Policy Engine can be exercised with fixture `NormalizedFinding` and risk-assessment data via its port, with no infrastructure dependency.
**Measure**: Domain logic (Analysis, Risk, Policy) reaches meaningfully higher unit-test coverage than adapters, and can run fully offline.

## QA-06 — Provider portability
**Scenario**: An operator switches from Ollama to an API-based AI provider.
**Response**: Only configuration changes; no code changes anywhere in the domain or Orchestrator.
**Measure**: The full Orchestrator test suite passes unmodified against a fake `AIProviderPort`.

## QA-07 — Scanner extensibility
**Scenario**: A new scanner (e.g., a new SAST tool) is added.
**Response**: A new adapter implementing `ScannerPort` is added; no existing code outside the Scanner context changes.
**Measure**: Adding a scanner requires zero changes to Orchestrator, Risk, or Policy code.

## QA-08 — Resource frugality
**Scenario**: SentinelAI runs a full analysis on the reference hardware (8th-gen i7, 16GB RAM, no GPU, mechanical HDD).
**Response**: The analysis completes without requiring GPU acceleration or exceeding available RAM, using either a small local model or an API provider.
**Measure**: Peak memory and CPU usage stay within limits validated on the reference hardware; no hard dependency on GPU libraries.

## QA-09 — Cross-platform local development
**Scenario**: A developer sets up SentinelAI locally on Windows, Linux, or macOS.
**Response**: Setup succeeds using the documented steps without OS-specific code branches in the domain.
**Measure**: The same test suite passes on all three OSes in CI.
