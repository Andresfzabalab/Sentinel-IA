# Bounded Contexts

## Why this document exists
Provides the per-context detail that `Domain_Model.md` summarizes: internal model, exposed ports, dependencies, boundary rules, and — critically — the Process Model classification (in-process vs. independent process) for each context's runtime components.

## Identity
- **Internal model**: User, Organization, Role, Permission.
- **Ports**: `IdentityPort` (authenticate, authorize).
- **Depends on**: nothing else.
- **Boundary rule**: no other context implements its own auth logic; all authorization checks go through `IdentityPort`.
- **Process model**: in-process.

## Repository
- **Internal model**: Repository, Branch, Commit, PullRequest.
- **Ports**: `RepositoryPort` (fetch PR context, changed files, metadata).
- **Depends on**: Identity (for authenticated Git integration config).
- **Boundary rule**: GitHub-specific types never leak past the adapter implementing `RepositoryPort` (P-08).
- **Process model**: in-process orchestration; GitHub API calls are network I/O, not a separate process.

## Analysis
- **Internal model**: AnalysisRun, ArtifactClassification, CorrelatedFinding.
- **Ports called (not owned)**: `RepositoryPort`, `ScannerPort`, `AIPort`, `RiskPort`, `PolicyPort`.
- **Owned logic**: artifact classification, finding correlation — and nothing else (P-01).
- **Boundary rule**: THIN. Must not implement scanning, AI, risk, or policy logic. Produces `FindingsCorrelated` (owned by Analysis, not AI — corrected from prior draft).
- **Process model**: in-process (the Orchestrator itself).

## Scanner
- **Internal model**: ScanRequest, NormalizedFinding.
- **Ports**: `ScannerPort` (execute scan for a given artifact type, return NormalizedFinding[]).
- **Boundary rule**: each scanner adapter (Semgrep, Bandit, Trivy, Gitleaks, Checkov) is solely responsible for translating its unique native format into NormalizedFinding (P-05). No native format crosses this boundary.
- **Process model**: the Scanner context's coordination code is in-process; each actual scanner tool runs as an **independent process** (subprocess or Docker container) and can fail without affecting the others (P-09).

## AI
- **Internal model**: EnrichmentRequest, EnrichmentResult (explanation, remediation, deduplication — no verdict field, structurally).
- **Ports**: `AIPort` / `AIProviderPort` (provider-agnostic: Ollama, OpenAI, Claude, Gemini).
- **Boundary rule**: ADVISORY ONLY (P-02). `EnrichmentResult` cannot represent PASS/BLOCK even by accident — it is not part of the type.
- **Process model**: the AI context's coordination code is in-process; the actual inference runs as an **independent process** — Ollama as a local background service (`localhost:11434`), or a remote API call to OpenAI/Claude/Gemini. A slow/unreachable provider degrades the analysis (QA-04), it does not fail it.

## Risk
- **Internal model**: RiskAssessment (per correlated finding: contextual severity, contributing heuristics).
- **Ports**: `RiskAssessmentPort` (introduced as its own context and port — corrected from a prior draft where Risk was not separated out).
- **Boundary rule**: DETERMINISTIC (P-03). Heuristics only (path patterns, artifact type, correlation density). No dependency on AI.
- **Process model**: in-process.

## Policy
- **Internal model**: PolicyRule, PolicyVersion, Verdict (PASS/BLOCK).
- **Ports**: `PolicyPort` (evaluate risk-assessed findings against active policy → Verdict).
- **Boundary rule**: DETERMINISTIC and the ONLY producer of Verdict (P-04). No dependency on AI. Configured exclusively by DevSecOps.
- **Process model**: in-process.

## Reporting
- **Internal model**: Report (Markdown, SARIF, JSON, HTML representations).
- **Ports**: `ReportingPort`.
- **Boundary rule**: consumes events/results from Analysis/Risk/Policy; applies redaction rules from `Input_Output_Model.md`; does not alter findings or verdicts.
- **Process model**: in-process.

## Audit
- **Internal model**: AuditRecord (immutable: who, when, what, findings, risk, policy version, verdict).
- **Ports**: `AuditPort`.
- **Boundary rule**: append-only; no context may modify or delete an existing AuditRecord.
- **Process model**: in-process (SQLite in MVP); persistence adapter isolates the storage technology (Repository pattern).

## Notification
- **Internal model**: NotificationRequest, Channel (GitHub, Slack, Teams, email, webhook).
- **Ports**: `NotificationPort`.
- **Boundary rule**: channel-specific formatting stays inside each channel's adapter; respects the same redaction rules as Reporting.
- **Process model**: in-process coordination; actual delivery is network I/O to independent external services.

## Process Model summary (why the distinction matters)
In-process components fail together with SentinelAI; independent processes (scanners, Ollama, and — from Phase 3 — the database server) fail independently. This is why a scanner crash or a slow AI provider degrades gracefully instead of aborting the whole analysis (see QA-03, QA-04, and P-09).
