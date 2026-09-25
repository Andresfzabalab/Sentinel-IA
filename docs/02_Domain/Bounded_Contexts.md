# Bounded Contexts

## Why this document exists
Provides the per-context detail that `Domain_Model.md` summarizes: internal model, exposed ports, dependencies, boundary rules, and — critically — the Process Model classification (in-process vs. independent process) for each context's runtime components.

## Identity
- **Internal model (as originally envisioned)**: User, Organization, Role, Permission.
- **Internal model (as actually built, Phase 8)**: deliberately simplified. `Interaction_Model.md`'s permission table has exactly two rows -- Developer (no direct access at all) and DevSecOps (full access to everything) -- so there is no role differentiation for `IdentityPort` to arbitrate between, and no use case (UC-1..UC-9) ever checks a permission finer-grained than "is this an authenticated DevSecOps session." Building a full User/Organization/Role/Permission model to serve a single implicit role would have been exactly the kind of speculative generality `Architecture_Patterns.md` and `Objectives.md` argue against. What was actually implemented: a `session` table (`Data_Model.md`) mapping an opaque session token to a DevSecOps' GitHub login and an expiry -- that login string *is* the DevSecOps identity, used directly as the `actor` field on Audit Records. If a second role or per-repository permission scoping ever becomes a real requirement, that is a new product decision belonging in `09_Decisions`, not a retroactive reinterpretation of this note.
- **Ports (as built)**: no `IdentityPort` — authentication is `interfaces/http/middleware/auth.py`'s `require_devsecops_session` FastAPI dependency, checked directly against the `session` table. This is an interfaces-layer concern, not a Sentinel Core domain port, precisely because there is no domain decision being made (no role/permission logic) — only "does a valid, unexpired session exist."
- **Depends on**: nothing else.
- **Boundary rule**: no other context implements its own auth logic; every DevSecOps-facing route goes through the one shared dependency.
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
