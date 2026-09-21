# Entities & Value Objects

## Purpose

This document gives the tactical DDD definition — identity (or lack of it), attributes, invariants, and mutability — for every concept classified in `Domain_Concept_Model.md`. It is the level of detail an implementer needs before writing a class or a table; `Aggregates_and_Boundaries.md` then groups these into consistency boundaries and transactions.

## Entities

An Entity's identity is stated first, since that is what distinguishes it from a Value Object with the same attributes.

### Analysis
- **Identity**: a generated `AnalysisId`, one per triggering event (a GitHub PR event — opened or synchronize — or a DevSecOps-initiated manual trigger, per `Application_Use_Cases.md` UC-1/UC-2 and `Domain_Events.md`'s Mode A/Mode B `correlationId` generation). Two Analyses for the same PR (e.g., after a new commit) are different Entities, never the same one mutated; the same is true for two manual triggers.
- **Attributes**: `RepositoryId`, `correlationId`, `PullRequestSnapshot` (VO, nullable — absent for a Mode B ad hoc manual trigger with no PR reference), `ArtifactList` (VO), `status` (started/running/completed), `findings` (collection of Finding entities), `scannerExecutions` (collection), `risk` (VO, once computed), `securityScore` (VO, once computed), `policyVersionId`, `verdict` (VO, once decided), `completedAt`.
- **Invariants**: a `verdict` can only be set once, and only by the Policy Evaluation step (P-02, P-04); `findings` can only grow during the scanning/correlation phase and become immutable once `verdict` is set; `securityScore` and `risk` must be present before `verdict` can be set.
- **Lifecycle**: `started` → `running` (scanning/correlation/risk/policy in progress) → `completed` (verdict + Security Result fixed). No further transitions — a new commit, or a new manual trigger, creates a new Analysis, it never reopens a completed one.

### Finding
- **Identity**: scoped to one Analysis — identified by `(AnalysisId, scannerId, ruleOrCategoryId, locationHash)`. Not global; the same underlying issue reported in a different Analysis is a different Finding instance.
- **Attributes**: `artifactReference` (path/location), `scannerId`, `category`, `severity` (VO), `risk` (VO, once assessed), `correlationGroupId` (nullable, set during correlation). **No AI Enrichment attribute** — see the note below.
- **Invariants**: a Finding never exists without normalization having already occurred (P-05) — no raw scanner output is ever stored as a Finding; `risk` can only be set after `severity` exists; once the owning Analysis reaches `completed`, no attribute of Finding listed above may change.
- **Lifecycle**: created at normalization → optionally grouped by correlation → risk-assessed → frozen once the owning Analysis completes.
- **On AI Enrichment**: an earlier draft of this document listed `aiEnrichment` as a Finding attribute. That was corrected — Finding is part of the frozen Security Result (`Data_Contracts.md`'s immutability rule), and AI Enrichment is produced later, asynchronously, by the AI & Agent Module. Attaching it as a Finding attribute would require writing into an already-frozen Entity. The association is one-directional and lives on the AI Enrichment side instead: an `AI Enrichment` record references the Finding it explains via `subjectId`, never the reverse (`Data_Contracts.md`, Cross-Contract Consistency Rules).

### Scanner Execution
- **Identity**: `(AnalysisId, scannerId)` — one execution per scanner per Analysis.
- **Attributes**: `status` (running/succeeded/failed/timedOut), `startedAt`, `completedAt`, `findingsProduced` (count or reference), `failureNote` (nullable).
- **Invariants**: a `failed` or `timedOut` status must never be interpreted as "zero findings" — it must be distinguishable at the data level from a `succeeded` execution that legitimately found nothing (P-09, QA-03).
- **Lifecycle**: `running` → exactly one terminal state (`succeeded`, `failed`, `timedOut`), each independent of every other Scanner Execution in the same Analysis.

### Repository
- **Identity**: the Git provider's repository identifier (e.g., GitHub `owner/repo` or numeric ID).
- **Attributes**: `enabledScanners` (list), `assignedPolicyId`, `aiProviderConfig` (reference, may be absent/degraded), `active` (boolean).
- **Invariants**: a Repository must have at least a default Policy assignment before any Analysis can produce a verdict — an Analysis must never fall back to "no policy" silently.
- **Lifecycle**: `registered` → `configured` (scanners/policy/AI set by DevSecOps) → `active`/`inactive`, toggled by DevSecOps at any time; configuration changes are themselves audited (`Input_Output_Model.md`).

### Policy
- **Identity**: a `PolicyId` stable across its version history.
- **Attributes**: `versions` (ordered collection of Policy Version VOs), `currentVersionId`.
- **Invariants**: publishing a new version never edits a prior version's content — every historical version stays byte-identical and retrievable, because a past verdict must be reconstructable against the exact version that produced it (QA-01).
- **Lifecycle**: `draft` → `published` (immutable from this point on) for each version; the Policy Entity itself simply accumulates published versions over time.

### Audit Record
- **Identity**: its own generated ID per event.
- **Attributes**: `subjectAnalysisId` (nullable — some records are configuration changes, not tied to an Analysis), `actor` (DevSecOps identity or "system"), `timestamp`, `eventType`, `payload` (the recorded facts — Findings/Risk/Score/verdict for an Analysis event, or the before/after for a config change), `origin` (`scanner` | `sentinel-core` | `llm-agent`, per `AI_Agent_Architecture.md` §9).
- **Invariants**: once written, never updated or deleted (append-only); every Analysis completion produces at least one Audit Record before the flow is considered finished from a governance standpoint — though, per `Aggregates_and_Boundaries.md`, this write is not in the same transaction as the verdict itself.
- **Lifecycle**: created once, read many times, never mutated.

### Notification
- **Identity**: its own generated ID per delivery attempt.
- **Attributes**: `subjectAnalysisId`, `channel` (GitHub status/comment, Slack, email, etc.), `status` (pending/delivered/failed), `attemptedAt`, `contentRef` (what was sent — a reference to Report or a minimal verdict summary).
- **Invariants**: a failed Notification must never be interpreted as a failed Analysis — delivery and decision are different facts (`Ubiquitous_Language.md`, Notification entry).
- **Lifecycle**: `pending` → `delivered` or `failed` (retryable, producing a new attempt, not a mutation of the failed one).

### Agent Execution *(Advisory)*
- **Identity**: its own generated ID, one per Security Investigation Agent run, referencing `subjectAnalysisId`.
- **Attributes**: `startedAt`, `completedAt`, `status` (running/completed/pending-unavailable), `toolCallsLog` (list), `knowledgeBaseEntriesUsed` (list of versioned references), `output` (advisory text, nullable if `pending-unavailable`).
- **Invariants**: `output` must never contain a verdict-shaped field or a Security Score value; a `pending-unavailable` status must never block or delay the Analysis it references, which has already completed independently (`AI_Agent_Architecture.md` §8).
- **Lifecycle**: `running` → `completed` normally, or `pending-unavailable` if the LLM was unreachable, resumable later into `completed` without touching the referenced Analysis.

### Security Knowledge Base Entry *(Data/Knowledge concept — Security Intelligence & Data Module, not part of the verdict-critical domain)*
- **Identity**: `(topicOrCategory, version)`.
- **Attributes**: `content` (remediation/security guidance text), `sourceReference`, `version`, `publishedAt`.
- **Invariants**: entries are immutable once published — a refresh creates a new version, never edits an old one, so an Agent Execution can cite exactly which knowledge-base version it used.
- **Lifecycle**: created by the Security Intelligence & Data Module's refresh cycle → published → superseded by a later version (old versions retained for traceability, not deleted).
- **Classification note**: unlike Agent Execution — which is an *advisory* concept still tied to a specific Analysis via `subjectAnalysisId` — a Security Knowledge Base Entry has no relationship to any Analysis at all. It is general-purpose reference data owned entirely by the Security Intelligence & Data Module. It is listed here as an Entity for completeness, not because it belongs to the same domain layer as Analysis, Repository, or Policy; `Aggregates_and_Boundaries.md` treats it as a data-management boundary rather than a domain aggregate.

## Value Objects

Value Objects have no identity; equality is by value, and every instance is immutable once constructed.

### Pull Request (external reference / snapshot)
Fields: `provider` (GitHub for MVP), `prNumber`, `baseBranch`, `headBranch`, `author`, `changedFilePaths`. Listed here for completeness, but per `Domain_Concept_Model.md` and `Ubiquitous_Language.md` it is **not** a domain-owned Value Object in the strict sense — it is an External Reference: a read-only, immutable snapshot of state SentinelAI does not own (the Pull Request itself is GitHub's). Captured once when an Analysis starts; a later commit produces a new snapshot inside a new Analysis, never an edit to this one.

### Artifact
Fields: `path`, `type` (source/Dockerfile/K8s-Helm/Terraform/GitHub-Actions/dependency-manifest/other), `changeKind` (added/modified/deleted). Two Artifacts with the same values are interchangeable — there is no reason to distinguish them by identity.

### Severity
Fields: `scannerAssignedLevel` (critical/high/medium/low, or a CVSS-derived number), `scannerId` (which tool assigned it). Set once at normalization; never edited — a re-scan produces a new Finding with a new Severity, not a mutated one.

### Risk
Fields: `adjustedLevel`, `inputs` (the Severity plus the heuristic factors applied: path pattern match, artifact type, correlation density). Deterministic function of its inputs (P-03) — the same inputs always produce the same Risk value, and it is never computed from anything outside the current Analysis.

### Security Score
Fields: `value`, `computedFrom` (reference to the set of Risk-assessed Findings that produced it). A pure aggregation; recomputing it with the same Findings always yields the same value.

### Policy Version
Fields: `versionNumber`, `rules` (thresholds and conditions), `publishedAt`, `publishedBy`. Immutable once published — this is the object an Analysis actually references, never "the current Policy" as a mutable thing.

### Security Result
Fields: `analysisId`, `findings` (reference), `risk`, `securityScore`, `policyVersionId`, `verdict` (PASS/BLOCK), `completedAt`. This is the frozen, final-state view of an Analysis — not a separately created object, but the Value Object *representation* of Analysis once `status = completed`. Regenerating it from the same Analysis always yields the same values.

### AI Enrichment *(Advisory)*
Fields: `scope` (`finding` or `analysis`), `subjectId` (the `findingId` or `analysisId` it explains — the one and only link between this Value Object and the Security Result side, per `Data_Contracts.md`), `explanation`, `remediationSuggestion` (nullable if the Security Knowledge Base had insufficient information — see `AI_Agent_Architecture.md` §6), `sourceAgentExecutionId`. Structurally excludes any field that could represent a verdict or a Security Score (P-02).

### Report
Fields: `analysisId`, `audience` (Developer/DevSecOps), `content` (structured or rendered representation), `aiSectionStatus` (`complete` | `pending`), `generatedAt`. A disposable projection — regenerable at any time from the Security Result plus, if available, the Agent Execution output. Never a source of truth on its own (`Ubiquitous_Language.md`).

## Invariant Summary

| Invariant | Owning concept | Enforced by |
|---|---|---|
| A verdict is set exactly once, only by Policy Evaluation | Analysis | Sentinel Core (P-02, P-04) |
| No Finding exists without normalization | Finding | Scanner adapters (P-05) |
| A failed/timed-out Scanner Execution ≠ zero findings | Scanner Execution | Scanner context (P-09, QA-03) |
| AI Enrichment / Agent Execution output never carries a verdict or score field | AI Enrichment, Agent Execution | AI & Agent Module's output schema (P-02) |
| Policy Versions are immutable once published | Policy Version | Policy context |
| Audit Records are append-only | Audit Record | Audit context |
| Security Knowledge Base entries are immutable once published | Security Knowledge Base Entry | Security Intelligence & Data Module |
| A Report is always regenerable from Analysis + Agent Execution, never a separate source of truth | Report | Reporting responsibility (AI & Agent Module) |

## Consistency Notes

These definitions intentionally do not yet say which of these objects share a database transaction — that is a consistency-boundary decision, made explicitly in `Aggregates_and_Boundaries.md`, including which SQLite transactions group which writes.
