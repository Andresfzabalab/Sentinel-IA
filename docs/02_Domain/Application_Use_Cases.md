# Application Use Cases

## Purpose

This document defines SentinelAI's MVP use cases: actor, trigger, preconditions, main flow, postconditions, and the permission each requires per `Interaction_Model.md`. Each use case is traced to the Aggregates, Domain/Application Services, and Domain Events it touches, so this document is the bridge between the domain model and whatever entry point (webhook handler, CLI, API) eventually implements it.

## Actors (per `Interaction_Model.md`)

| Actor | Nature | Direct access to SentinelAI? |
|---|---|---|
| Developer | Human | No — indirect only, via GitHub |
| DevSecOps | Human | Yes — authenticated, full configuration and reporting access |
| GitHub | System | Yes — webhook in, API out |
| Security Investigation Agent | System (internal) | N/A — not a use-case actor; it is triggered by the `AnalysisCompleted` event (UC-7), independent of whether the Analysis originated from UC-1 or UC-2 |
| Security Intelligence & Data Module | System (internal, scheduled) | N/A — its own internal cycle (UC-8) |

## UC-1: Process Pull Request Event

- **Actor**: GitHub (system-to-system)
- **Trigger**: webhook, `opened` or `synchronize`, signature verified
- **Preconditions**: Repository is `registered` and `active`; a Policy Version is assigned
- **Main flow**:
  1. Verify webhook signature; reject if invalid (never triggers an Analysis)
  2. Compute `correlationId` from `(repositoryId, prNumber, headCommitSha)`
  3. Check idempotency (`Domain_Events.md`) — if an Analysis already exists for this `correlationId`, stop here
  4. T1: create Analysis, publish `PullRequestReceived`
  5. Artifact Classification Service classifies changed files
  6. Scanner Selection Service selects applicable scanners against Repository config
  7. Each scanner runs (T2 per completion); `ScannerExecutionCompleted` published per scanner
  8. Once all eligible scanners reach a terminal state: Correlation → Risk Assessment Service → Security Score Calculation Service → Policy Evaluation Service (all inside T3)
  9. T3 commits: verdict fixed, `PolicyEvaluated` and `AnalysisCompleted` published
  10. Notification Dispatch Service posts the minimal GitHub status check + summary comment (does not wait on AI)
- **Postconditions**: exactly one Analysis exists for this `correlationId`, in `completed` status, with an immutable Security Result; GitHub shows PASS/BLOCK
- **Permission**: none required — GitHub is a trusted, signature-verified system source, not a human actor requiring authorization
- **Touches**: Analysis (Aggregate), Repository (read), Policy (read), all Sentinel Core Domain Services, `RepositoryPort`, `ScannerPort`

## UC-2: Trigger Manual Analysis

- **Actor**: DevSecOps
- **Trigger**: explicit command (CLI/API), naming a Repository and either (a) a reference to an existing PR, or (b) an ad hoc artifact set/branch with no PR involved
- **Preconditions**: DevSecOps is authenticated; Repository is `registered`
- **`correlationId` generation** (per `Domain_Events.md`):
  - **(a) PR reference given** — Mode A applies, identical to UC-1: `correlationId` derives deterministically from `(repositoryId, prNumber, headCommitSha)`. A manual re-run against a commit already analyzed is recognized as a duplicate, same as a redelivered webhook.
  - **(b) No PR reference (ad hoc)** — Mode B applies: `correlationId` derives from `(repositoryId, manualTriggerKey)`, where `manualTriggerKey` is either an idempotency key DevSecOps explicitly supplies, or a freshly generated identifier if none is given (in which case two calls are two separate, legitimate Analyses).
- **Main flow**: identical to UC-1 from step 4 onward (Analysis Orchestrator consumes `PullRequestReceived`, T1 proceeds) — the only difference from UC-1 is how `correlationId` was produced and that `prNumber`/`headCommitSha` may be absent under Mode B
- **Postconditions**: same as UC-1
- **Permission**: DevSecOps — "execute manual analyses" (project brief §2)
- **Touches**: same as UC-1

## UC-3: Configure Repository

- **Actor**: DevSecOps
- **Trigger**: configuration change (enable/disable scanners, assign Policy version, assign AI provider config, activate/deactivate)
- **Preconditions**: DevSecOps authenticated
- **Main flow**: `T-Repo` transaction (`Aggregates_and_Boundaries.md`) writes the new configuration; the change is itself audited (`Input_Output_Model.md`)
- **Postconditions**: any Analysis started *after* this point uses the new configuration; any Analysis already `running` continues with the configuration it read at its own T1 — a mid-flight change never retroactively alters it
- **Permission**: DevSecOps — "configure repositories / GitHub integration / scanners / AI providers"
- **Touches**: Repository (Aggregate), Audit

## UC-4: Publish Policy Version

- **Actor**: DevSecOps
- **Trigger**: new policy rules/thresholds submitted
- **Preconditions**: DevSecOps authenticated
- **Main flow**: `T-Policy` transaction inserts a new immutable `PolicyVersion`, updates `Policy.currentVersionId`; prior versions are never edited
- **Postconditions**: new Analyses reference the new version by default (unless a Repository is pinned to an older one — an explicit future extension, not required for MVP); every historical Analysis remains reconstructable against the exact version it used (QA-01)
- **Permission**: DevSecOps — "configure security policies"
- **Touches**: Policy (Aggregate), Audit

## UC-5: Inspect Full Report

- **Actor**: DevSecOps
- **Trigger**: read request for a specific Analysis's report
- **Preconditions**: Analysis exists (any status)
- **Main flow**: Report Generation Service assembles/returns the DevSecOps-facing Report from the (frozen) Security Result plus, if available, the Agent Execution output; if the Agent Execution is still `pending-unavailable`, the report's `aiSection.status` reads `pending`
- **Postconditions**: none — read-only; regenerating the report never changes the underlying Analysis
- **Permission**: DevSecOps — "inspect complete security reports"
- **Touches**: Analysis (read), Agent Execution (read), Report (projection)

## UC-6: Inspect Audit Trail / Reconstruct Historical Verdict

- **Actor**: DevSecOps
- **Trigger**: read request against Audit Records, optionally scoped to one Analysis or one time range
- **Preconditions**: none beyond authentication
- **Main flow**: query Audit Records by `analysisId` or `correlationId`; every verdict-critical fact (Findings, Risk, Security Score, Policy Version, verdict) must be reconstructable from Audit alone, without needing scanner or AI provider logs (QA-01)
- **Postconditions**: none — read-only
- **Permission**: DevSecOps — "inspect logs and audit information"
- **Touches**: Audit Record (read)

## UC-7: Execute Security Investigation Agent

- **Actor**: System (triggered by `AnalysisCompleted`, not a human actor)
- **Trigger**: `AnalysisCompleted` event
- **Preconditions**: the referenced Analysis is `completed` (verdict already fixed)
- **Main flow**:
  1. Agent Execution Runner reads the Security Result via `SecurityResultQueryPort` (read-only)
  2. Reads relevant Security Knowledge Base entries via `SecurityKnowledgeBasePort` (read-only)
  3. Calls `AIProviderPort` for explanation/prioritization/remediation text
  4. If the provider is unreachable: publish `AgentExecutionPending`, stop, resumable later
  5. If successful: attach AI Enrichment output, publish `AgentExecutionCompleted`
- **Postconditions**: the Analysis itself is never modified by this use case, regardless of outcome
- **Permission**: none — internal system use case, no human actor, and no write authority over Sentinel Core state (`AI_Agent_Architecture.md` §7)
- **Touches**: Agent Execution (Aggregate, AI & Agent Module), Security Result (read-only), Security Knowledge Base (read-only)

## UC-8: Refresh Security Knowledge Base

- **Actor**: System (scheduled, internal to the Security Intelligence & Data Module)
- **Trigger**: refresh cycle (time- or event-based, internal scheduling — not tied to any Analysis)
- **Preconditions**: none
- **Main flow**: Knowledge Refresh Service (an Application/Orchestration Service, per `Domain_Services.md`) calls `SecurityIntelligenceSourcePort` adapters, versions the results, writes new `SecurityKnowledgeBaseEntry` records via `T-Knowledge`
- **Postconditions**: new entries are available to future Agent Executions; no Analysis or Repository is affected in any way by this use case running, failing, or being delayed
- **Permission**: none — no human actor; the module's own controlled internet access is the only authorization surface (`Module_Boundaries.md`)
- **Touches**: Security Knowledge Base Entry (data boundary, not a domain aggregate)

## UC-9: Suppress a Finding

- **Actor**: DevSecOps
- **Trigger**: DevSecOps submits a suppression rule (e.g., "treat findings matching rule X on path Y as suppressed") for a Repository
- **Preconditions**: DevSecOps authenticated; the target Repository has an assigned Policy
- **Resolution**: modeled as **Policy Suppression**, not as a mutation of Finding. This is the design already identified as option (a) in the prior draft of this document, and it is the one consistent with invariants already fixed elsewhere:
  - `Entities_Value_Objects.md`: once an Analysis reaches `completed`, its Findings are frozen — no attribute may change.
  - `Data_Contracts.md`: Security Result is immutable after T3 — nothing may write to it after the fact.
  - `Architecture_Principles.md` (P-04) and `Aggregates_and_Boundaries.md`: Policy rules are explicit, versioned, human-authored configuration, and publishing a new Policy Version never edits a prior one.
  A suppression rule is therefore added as part of a new **Policy Version**, via the same `T-Policy` transaction already defined for UC-4 — suppression is not a new mechanism, it is a new kind of rule inside the existing one.
- **Main flow**:
  1. DevSecOps submits the suppression rule alongside (or as part of) a Policy update
  2. `T-Policy` publishes a new, immutable Policy Version containing the rule
  3. Repository's Policy assignment is updated to reference this version (or the version is published as the Repository's current default, per UC-4)
  4. From this point forward, any **new** Analysis that references this Policy Version has its Policy Evaluation Service treat matching Findings as suppressed for the purpose of the PASS/BLOCK threshold check — the Findings themselves, their Severity, and their Risk values are still computed and recorded exactly as for any other Finding; suppression affects only how Policy Evaluation weighs them toward the verdict
- **Postconditions**:
  - Analyses already `completed` before this Policy Version was published are **not** retroactively changed — their Security Result, Findings, and verdict remain exactly as originally decided (QA-01, immutability rule)
  - To see the effect of a new suppression rule against an existing Pull Request, DevSecOps triggers a new Analysis (UC-2) — which, because it references the new Policy Version, produces a new, distinct Security Result
  - Suppressed Findings remain visible in the full DevSecOps-facing Report, marked as suppressed and attributed to the Policy Version that suppressed them — suppression is a transparent, audited exception, never a silent deletion
- **Permission**: DevSecOps — "configure security policies" / "suppress a finding" (`Interaction_Model.md`)
- **Touches**: Policy (Aggregate, new version), Audit — no write to Analysis, Finding, or any already-completed Security Result

## Permission Summary (cross-reference)

| Use Case | Actor | Permission source |
|---|---|---|
| UC-1 | GitHub | Trusted system source, signature-verified |
| UC-2 | DevSecOps | `Interaction_Model.md` — "execute manual analyses" |
| UC-3 | DevSecOps | `Interaction_Model.md` — "configure scanners/AI/Git integration" |
| UC-4 | DevSecOps | `Interaction_Model.md` — "define/change policy" |
| UC-5 | DevSecOps | `Interaction_Model.md` — "view full report" |
| UC-6 | DevSecOps | `Interaction_Model.md` — "view audit trail" |
| UC-7 | System | No human permission model applies |
| UC-8 | System | No human permission model applies |
| UC-9 | DevSecOps | `Interaction_Model.md` — "suppress a finding" |
