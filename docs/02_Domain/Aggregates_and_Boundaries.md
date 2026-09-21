# Aggregates and Boundaries

## Purpose

This document defines SentinelAI's Aggregates, their roots, their transactional consistency boundaries, and — per the MVP's single-process SQLite deployment — the concrete SQLite transactions that implement those boundaries. Per the agreed scope, the transactional core (Analysis and everything verdict-critical) is treated in full depth; secondary aggregates (Repository, Policy, Audit Record, Notification, Agent Execution) are treated more lightly, since none of them is allowed to gate a verdict. The Security Knowledge Base is treated separately still, as a data-management boundary rather than a domain aggregate — see that section below.

## Aggregate Design Principles

1. **One aggregate, one transaction.** A single write transaction touches exactly one aggregate's data. Cross-aggregate effects happen via subsequent, separate transactions — never by extending one transaction across aggregate boundaries.
2. **Reference by ID, never embed.** An aggregate that needs data owned by another aggregate holds that aggregate's identifier, not a copy of its mutable state (e.g., Analysis holds `policyVersionId`, not a copy of the Policy Version's rules).
3. **Verdict-critical vs. everything else.** Exactly one aggregate — Analysis — is verdict-critical: its internal consistency directly determines PASS/BLOCK. Every other aggregate's failure, delay, or unavailability must be structurally incapable of changing that verdict (P-02, P-03, P-04, QA-03, QA-04).
4. **Secondary aggregates are eventually consistent with Analysis, never the reverse.** Audit, Notification, Report, and Agent Execution all read from a completed Analysis; none of them writes back to it.

## Primary Aggregate: Analysis

**Root**: `Analysis` (Entity, per `Entities_Value_Objects.md`).

**Contains** (same consistency boundary, same aggregate):
- `Finding` (child Entity, local identity within the Analysis)
- `ScannerExecution` (child Entity, local identity within the Analysis)
- `Severity`, `Risk`, `SecurityScore`, `Verdict` (Value Objects, attributes of Findings/Analysis)
- `PullRequestSnapshot` (Value Object, nullable — absent under Mode B), `ArtifactList` (Value Object) — captured at creation

**References, but does not contain**: `RepositoryId`, `PolicyVersionId` — both are IDs pointing to other aggregates, never embedded copies.

**Invariants enforced within this boundary**:
- The `verdict` field can be written exactly once, and only after `securityScore` and `risk` are both present.
- `findings` may only be added during the `running` state; once `status = completed`, the Finding set is frozen.
- A `ScannerExecution` marked `failed` or `timedOut` never causes the aggregate to silently omit that scanner's absence — the status is recorded, not erased.

### SQLite Transactions for the Analysis Aggregate

| Transaction | Trigger | What it writes (single atomic transaction) |
|---|---|---|
| **T1 — Analysis Created** | A triggering event is accepted: a GitHub webhook received and signature-verified (Mode A), or a DevSecOps manual trigger accepted (Mode A or B) — in both cases, only after the `correlationId` idempotency check (`Domain_Events.md`) finds no existing Analysis for it | `INSERT` into `analysis` (status=`running`, `correlationId`), `pull_request_snapshot` (nullable — absent under Mode B), `artifact_list` rows — all in one transaction |
| **T2 — Scanner Execution Completed** | One scanner subprocess finishes (success, failure, or timeout) | `UPDATE`/`INSERT` on that scanner's `scanner_execution` row plus its `finding` rows (if any), scoped to this Analysis — one transaction per scanner, independent of every other scanner's T2 |
| **T3 — Correlation + Risk + Policy Finalized** | All eligible Scanner Executions have reached a terminal state | Single atomic transaction: write `correlation_group_id` on affected Findings, write `risk` per Finding, write `security_score`, write `verdict`, set `status = completed` on the Analysis row |

**T3 is the critical transaction.** It is the only write in the entire system that sets a PASS/BLOCK verdict, and it commits or does not commit as a single unit — there is no partially-decided verdict state visible to any reader. Nothing outside Sentinel Core (no AI Enrichment, no Agent Execution, no Security Intelligence & Data Module content) participates in T3, and T3 has no dependency on any of them succeeding, being available, or having run.

**Explicitly excluded from T1–T3**: AI Enrichment attachment, Agent Execution, Audit Record writes, Notification delivery, and Report generation are all **separate transactions**, described below, that happen *after* T3 commits and read the already-final Analysis row. This separation is what makes the LLM-unavailable behavior in `AI_Agent_Architecture.md` §8 possible — T3 never waits on any of them.

## Secondary Aggregates

Treated more lightly, per agreed scope — each gets its root, its boundary, and its transaction pattern, without the same depth as Analysis.

### Repository
- **Root**: `Repository`. Owns its own configuration (`enabledScanners`, `assignedPolicyId`, `aiProviderConfig`, `active`).
- **Transaction**: `T-Repo — Configuration Changed`, a single transaction per DevSecOps configuration edit, independent of any in-flight Analysis. An Analysis already in `running` state uses the Repository configuration it read at T1; a mid-flight config change never retroactively alters an Analysis already in progress.

### Policy
- **Root**: `Policy`, containing an ordered set of immutable `PolicyVersion` values.
- **Transaction**: `T-Policy — Version Published`, a single transaction that inserts a new, immutable `policy_version` row and updates `Policy.currentVersionId`. Existing `policy_version` rows are never updated by this or any other transaction — this is what guarantees QA-01's reconstructability.
- **Suppression (UC-9)**: a Finding suppression rule is simply new content within a `PolicyVersion` — no separate transaction type or Aggregate is introduced for it. Publishing a suppression rule uses the same `T-Policy` transaction as any other Policy update; it takes effect only for Analyses that reference the new version, never retroactively for Analyses already `completed`.

### Audit Record
- **Root**: `AuditRecord`, append-only.
- **Transaction**: `T-Audit — Record Written`, one transaction per event, fired *after* T3 commits (for Analysis completions) or after `T-Repo`/`T-Policy` commit (for configuration changes), and again independently when Agent Execution completes — this last case arrives via `AuditRecorderPort`, the one documented write exception among Cross-Module Ports (`Ports_and_Interfaces.md`), scoped strictly to Audit and nothing else. An Audit write failing is itself recorded as a distinguishable failure mode (per `C4_Container.md` §7: "security decision completed" vs. "persistence/audit failure") — it never rolls back T3.

### Notification
- **Root**: `Notification`, one row per delivery attempt.
- **Transaction**: `T-Notify — Delivery Attempted`, one transaction per attempt (including retries, each a new row, never an edit of a failed one), fired after T3 for the mandatory GitHub channel, and again after Report generation for any richer channel.

### Agent Execution *(Advisory)*
- **Root**: `AgentExecution`, referencing `subjectAnalysisId` by ID only.
- **Transaction**: `T-Agent — Execution Recorded`, one transaction per Security Investigation Agent run, entirely separate from T1–T3. It may commit long after T3 (even after the GitHub status check has already posted), or may never complete if the LLM stays unavailable — in which case the referenced Analysis remains `completed` with its verdict already delivered, and the Report's AI section stays `pending` (`AI_Agent_Architecture.md` §8).

## Data Management Boundary (Security Intelligence & Data Module)

`Security Knowledge Base Entry` is deliberately **not** listed as a Secondary Aggregate above. It sits at a different conceptual level: it is not domain state tied to an Analysis, a Repository, or a Policy — it has no relationship to any single Analysis at all, and it carries no invariant that touches a verdict, directly or indirectly. Treating it as an Aggregate alongside Analysis, Repository, Policy, Audit Record, Notification, and Agent Execution would imply it participates in the same kind of domain consistency they do, which it does not.

Instead, it is managed as a **data-management boundary** owned entirely by the Security Intelligence & Data Module:

- **Store**: `SecurityKnowledgeBaseEntry`, versioned, identified by `(topicOrCategory, version)`.
- **Transaction**: `T-Knowledge — Entry Published`, local to the Security Intelligence & Data Module's own refresh cycle, with no relationship to any specific Analysis, Repository, or Policy transaction.
- **Consumption**: read-only, by Agent Execution only (via the Security Investigation Agent). No other module — and certainly nothing in Sentinel Core — ever reads or writes this store.
- **Why this distinction matters**: keeping it out of the Aggregate list is what keeps the boundary honest — a data refresh here can run on any schedule, fail, or lag arbitrarily far behind without that ever being a domain-consistency question. It is infrastructure supporting one advisory feature (remediation guidance), not a citizen of the domain model.

## Cross-Aggregate Reference Rules

| Aggregate | References (by ID only) | Never embeds |
|---|---|---|
| Analysis | `RepositoryId`, `PolicyVersionId` | Repository's live config, Policy Version's rule content |
| Report | `AnalysisId`, `AgentExecutionId` (nullable) | Analysis's mutable internals — reads the frozen Security Result view only |
| Notification | `AnalysisId`, `ReportId` (nullable) | — |
| Audit Record | `AnalysisId` (nullable), actor identity | — |
| Agent Execution | `AnalysisId`, `SecurityKnowledgeBaseEntry` version IDs used | Analysis's Finding objects — reads them, does not copy/own them across a transaction boundary |

## Transactional Consistency Rules

| Must be atomic together | Can be eventually consistent |
|---|---|
| Findings + Risk + Security Score + Verdict + Analysis status=completed (T3) | Audit Record for that Analysis (written after T3 commits) |
| One Scanner Execution's status + its own Findings (T2) | Other Scanner Executions' T2 transactions (fully independent) |
| A Policy Version's content at publish time (T-Policy) | Any Analysis referencing an older Policy Version (unaffected by new publishes) |
| — | Agent Execution output, Report's AI section, and any Notification beyond the mandatory GitHub channel (all downstream of T3, never blocking it) |

## Consistency & Failure Alignment

This transaction design is the concrete implementation of guarantees already stated elsewhere:

- **QA-02 (determinism)**: T3 reads only Findings, Risk, and the referenced Policy Version — never anything from the AI & Agent Module or the Security Intelligence & Data Module — so the same inputs always produce the same T3 result, regardless of AI provider.
- **QA-03 (scanner failure isolation)**: each scanner's T2 is independent; a crash affects only that scanner's row, never blocks another scanner's T2 or the eventual T3.
- **QA-04 (AI degradation)**: T3 has zero transactional relationship to Agent Execution or AI Enrichment — a `pending-unavailable` Agent Execution can exist indefinitely against an already-`completed` Analysis without contradiction.
- **P-02/P-03/P-04**: enforced structurally here, not just procedurally — the AI & Agent Module and Security Intelligence & Data Module hold no write permission on the `analysis`, `finding`, or `policy_version` tables at all; their transactions target entirely separate tables (`agent_execution`, `security_knowledge_base_entry`).
- **Decision 6 (LLM unavailable)**: directly modeled as T3 committing unconditionally on schedule, with `T-Agent` and the AI section of Report as independent, resumable, non-blocking transactions.
