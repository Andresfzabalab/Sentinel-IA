# Data Contracts

## Purpose

This document formalizes the exact structure of the five data contracts that cross module boundaries: `Security Result`, `Finding`, `AI Enrichment`, `Agent Execution`, and `Report`. These are the shapes Sentinel Core, the AI & Agent Module, the Security Intelligence & Data Module, and any Entry Point (webhook handler, CLI, API) exchange — not internal implementation detail of any one Aggregate.

## Versioning Convention

Every contract in this document carries a `contractVersion` field: a simple integer or `major.minor` string identifying which version of the *shape* a given record conforms to. This is deliberately lightweight:

- **Additive changes** (a new optional field) do not require a `contractVersion` bump — a consumer that doesn't know the field yet simply ignores it.
- **Breaking changes** (removing a field, changing a field's type or meaning, changing what "verdict" can contain) require a `contractVersion` bump, and the old version's readers/writers must be migrated deliberately — never silently reinterpreted.
- `contractVersion` describes the **schema shape**, not the content of one specific record. It is unrelated to `Policy Version` (which versions policy *rules*) or to Security Knowledge Base entry versions (which version *knowledge content*) — three different, independent versioning axes that must not be conflated.

## Security Result

**Immutability rule**: once written by T3 (`Aggregates_and_Boundaries.md`), a Security Result is frozen. No field in this contract is ever updated after `verdict` is set. Any process that appears to "update" a Security Result (e.g., attaching AI Enrichment later) does so by writing to a *different* contract (`AI Enrichment`, `Agent Execution`, `Report`) that merely *references* this frozen one — never by mutating it.

| Field | Type | Notes |
|---|---|---|
| `contractVersion` | string | Schema version of this contract |
| `analysisId` | id | — |
| `correlationId` | string | Per `Domain_Events.md`: derived from `(repositoryId, prNumber, headCommitSha)` under Mode A (PR-linked trigger), or from `(repositoryId, manualTriggerKey)` under Mode B (ad hoc manual trigger with no PR) |
| `repositoryId` | id | — |
| `pullRequestReference` | object `{ provider, prNumber, headBranch, baseBranch, author }`, **nullable** | Read-only echo of the external snapshot — absent under Mode B, since an ad hoc manual trigger has no Pull Request to reference |
| `findings` | `Finding[]` | See below; frozen alongside this record |
| `scannerExecutionSummary` | `{ scannerId, status, findingsCount }[]` | Makes partial scanner failure visible without inspecting raw execution logs (QA-03) |
| `securityScore` | `{ value, computedFrom }` | — |
| `policyVersionId` | id | Always a specific version, never "current policy" |
| `verdict` | `"PASS"` \| `"BLOCK"` | Written exactly once (P-04) |
| `completedAt` | timestamp | — |
| `degradationFlags` | `{ anyScannerFailed: bool, aiAvailableAtCompletion: bool }` | Explicit, so consumers don't have to re-derive degradation state |

## Finding

| Field | Type | Notes |
|---|---|---|
| `contractVersion` | string | — |
| `findingId` | id | Scoped to one Analysis, per `Entities_Value_Objects.md` |
| `analysisId` | id | — |
| `scannerId` | string | — |
| `category` | string | — |
| `artifactReference` | `{ path, type }` | — |
| `location` | `{ file, lineStart, lineEnd }` nullable | Not every scanner reports line-level location |
| `ruleOrCheckId` | string | Opaque outside the Scanner context (P-05) |
| `severity` | `{ scannerAssignedLevel, scannerRawValue }` | Set once at normalization, never edited |
| `risk` | `{ adjustedLevel, appliedHeuristics[] }` nullable | Null until Risk Assessment runs; deterministic once set (P-03) |
| `correlationGroupId` | id, nullable | Set during correlation |
| `secretValueRedactionFlag` | boolean | Required by the redaction rule in `Input_Output_Model.md` |

**No AI Enrichment reference on this contract.** `Finding` is part of the frozen `Security Result` (immutable after T3). AI Enrichment is produced later, asynchronously, by the AI & Agent Module — attaching a reference to it here would mean writing into an already-frozen contract, which is exactly what the immutability rule forbids. The association is modeled the other way around: see "Cross-Contract Consistency Rules" below.

## AI Enrichment

**Structural exclusion, not a convention**: this contract has no field, at any nesting level, capable of representing a verdict or a Security Score. This is enforced at the schema level so that a consumer cannot accidentally read a verdict-shaped value out of AI Enrichment even by mistake (P-02).

| Field | Type | Notes |
|---|---|---|
| `contractVersion` | string | — |
| `aiEnrichmentId` | id | — |
| `scope` | `"finding"` \| `"analysis"` | Applies to a single Finding or to the whole Analysis |
| `subjectId` | id | `findingId` or `analysisId`, depending on `scope` |
| `explanation` | string | — |
| `consequenceFraming` | string, nullable | — |
| `prioritizationHint` | string/enum, nullable | — |
| `remediationSuggestion` | string, nullable | — |
| `remediationStatus` | `"provided"` \| `"insufficient_knowledge"` | Mandatory — never silently omitted; enforces decision 5 (no invented remediation) |
| `knowledgeBaseEntriesCited` | `{ topic, version }[]` | — |
| `sourceAgentExecutionId` | id | — |
| ~~`verdict`~~ | — | **Not a field. Never added.** |
| ~~`securityScore`~~ | — | **Not a field. Never added.** |

## Agent Execution

| Field | Type | Notes |
|---|---|---|
| `contractVersion` | string | — |
| `agentExecutionId` | id | — |
| `subjectAnalysisId` | id | References a Security Result that is already frozen |
| `correlationId` | string | Inherited from the originating Analysis, per `Domain_Events.md` |
| `agentType` | string | Extensible via the Agent Registry (`AI_Agent_Architecture.md` §4) |
| `status` | `"running"` \| `"completed"` \| `"pending-unavailable"` | — |
| `toolCallsLog` | `{ toolName, calledAt, resultSummary }[]` | Every tool in this log is read-only by construction |
| `knowledgeBaseEntriesUsed` | `{ topic, version }[]` | — |
| `outputRefs` | `AI Enrichment id[]` | Reference only |
| `executionLimits` | `{ maxDurationSeconds, maxToolCalls, maxOutputSize }` | Declared by the Agent Registry, enforced by the Agent Execution Framework |
| `startedAt` / `completedAt` | timestamp, nullable | `completedAt` is null while `status = running` or `pending-unavailable` |

## Report

| Field | Type | Notes |
|---|---|---|
| `contractVersion` | string | — |
| `reportId` | id | — |
| `analysisId` | id | References the frozen Security Result |
| `audience` | `"Developer"` \| `"DevSecOps"` | Determines redaction level (`Input_Output_Model.md`) |
| `content` | audience-specific structure | Developer: redacted, no raw secret values; DevSecOps: full detail |
| `aiSection` | `{ status: "complete" \| "pending", contentRef: id, nullable }` | This is where `AI Analysis: PENDING` (decision 6) lives |
| `format` | `"markdown"` \| `"sarif"` \| `"json"` \| `"html"` \| `"github-status"` \| `"github-comment"` | Per the PRD's output requirements |
| `generatedAt` | timestamp | Regenerable — this timestamp reflects the most recent generation, not a creation event |
| `regeneratedFromAgentExecutionId` | id, nullable | Traces which Agent Execution, if any, is reflected in the current `aiSection` |

## Cross-Contract Consistency Rules

1. **IDs are stable and never reused.** `analysisId`, `findingId`, `aiEnrichmentId`, `agentExecutionId`, and `reportId` are each generated once and referenced everywhere else by that same value — no contract ever embeds a full copy of another contract's content.
2. **The link between the verdict-critical Security Result and the advisory AI Enrichment contract is one-directional, and it lives entirely on the advisory side.** `AI Enrichment.subjectId` (matching a `findingId` or `analysisId`) is the only pointer between the two — `Finding` and `Security Result` hold no reference back to `AI Enrichment`. This is what keeps the Security Result genuinely frozen: creating, updating, or even deleting an AI Enrichment record never requires touching `Security Result` or any `Finding` inside it. When the Report Generation Service assembles a Report, it performs this join at presentation time — querying AI Enrichment records by `subjectId` against the Findings already present in the frozen Security Result — rather than by mutating either contract.
3. **A Report is always regenerable from a Security Result plus zero or more Agent Execution outputs.** It is never itself a source of truth (`Ubiquitous_Language.md`, Report entry) — deleting and regenerating a Report must reproduce equivalent content given the same inputs.
4. **`correlationId` threads through every contract that relates to an Analysis** (Security Result, Finding indirectly via `analysisId`, Agent Execution), but not through `Security Knowledge Base Entry`, which has no relationship to any Analysis (`Aggregates_and_Boundaries.md` §Data Management Boundary) and is therefore intentionally outside this document's scope.

## Schema Evolution Rules

- Add fields as optional/nullable first; only promote a field to required in a new `contractVersion`.
- Never repurpose an existing field name for a different meaning — retire it and introduce a new name instead.
- A `contractVersion` bump must state, in the change itself, which of the four rules above (if any) motivated it — "just in case" version bumps are discouraged; this convention stays useful only if it reflects real shape changes.
