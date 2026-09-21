# Data Model

## Purpose

This document translates the Aggregates, Entities, and Value Objects already fixed in `Aggregates_and_Boundaries.md` and `Entities_Value_Objects.md` into concrete SQLite tables for the MVP. It does not introduce new domain concepts or invariants — every table, column, and constraint here exists to persist something already decided; where a choice was purely technical (types, indexes, physical layout), that choice is stated explicitly as new.

## Scope & Physical Layout

**One SQLite file for the MVP.** `C4_Container.md` and `Deployment_Strategy.md` describe a single SQLite container — this document does not split that into multiple physical database files. The module boundaries from `Module_Boundaries.md` and the "each module owns its own persistence" rule from `Ports_and_Interfaces.md` are enforced at the **application/code level**, not by physical file separation:

- Tables are grouped by owning module via a naming prefix: `core_*` (Sentinel Core — `AnalysisStore`, `RepositoryConfigStore`, `PolicyStore`, `AuditStore`, `NotificationStore`), `agent_*` (AI & Agent Module — `AgentExecutionStore`), `knowledge_*` (Security Intelligence & Data Module — `KnowledgeBaseStore`).
- **No SQL foreign key crosses a module boundary.** `agent_execution.subject_analysis_id` and `ai_enrichment.subject_id` reference `analysis.id`/`finding.id` *by value only* — there is deliberately no `FOREIGN KEY` constraint enforced by SQLite across these, because a DB-level constraint would physically couple two modules' schemas, which is exactly what `Ports_and_Interfaces.md`'s "no `*Store` port is shared across modules" rule exists to prevent. Referential integrity for these cross-module references is the responsibility of the owning module's own write path (it only ever writes an ID it already read via a read-only port), not the database engine.
- A future PostgreSQL migration (`Deployment_Strategy.md`, Phase 3+) could split these into separate databases per module if isolation requirements grow; that is out of scope for the MVP and not designed here.

## Table Catalog

| Table | Owning module | Implements |
|---|---|---|
| `analysis` | Sentinel Core | `Analysis` Aggregate Root (includes the frozen `PullRequestSnapshot`) |
| `artifact` | Sentinel Core | `Artifact` Value Objects, child of `analysis` |
| `scanner_execution` | Sentinel Core | `ScannerExecution` Entity, child of `analysis` |
| `finding` | Sentinel Core | `Finding` Entity, child of `analysis` |
| `repository` | Sentinel Core | `Repository` Aggregate Root |
| `policy` | Sentinel Core | `Policy` Aggregate Root |
| `policy_version` | Sentinel Core | `PolicyVersion` Value Object, child of `policy` |
| `audit_record` | Sentinel Core | `AuditRecord` Entity (append-only) |
| `notification` | Sentinel Core | `Notification` Entity |
| `agent_execution` | AI & Agent Module | `AgentExecution` Entity |
| `ai_enrichment` | AI & Agent Module | `AI Enrichment` Value Object |
| `security_knowledge_base_entry` | Security Intelligence & Data Module | `SecurityKnowledgeBaseEntry` (data-management boundary, not an Aggregate) |

**Not a table**: `Security Result` (it *is* the `analysis` row once `status = 'completed'` — no separate storage), `Report` (a disposable projection, computed on read from `analysis` + `agent_execution` + `ai_enrichment` — persisting it would violate `Data_Contracts.md`'s "never itself a source of truth" rule), raw scanner native output (never stored at all, per P-05 — only `NormalizedFinding` content, already reflected in `finding`).

## Table Definitions

### `analysis`
Implements the `Analysis` Aggregate Root, including its `PullRequestSnapshot` (VO, inlined as nullable columns rather than a separate table, since it has no identity of its own and is only ever read alongside its owning Analysis).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | `analysisId`, a UUID |
| `correlation_id` | TEXT | NOT NULL, UNIQUE | Mode A or Mode B, per `Domain_Events.md`; the UNIQUE constraint is what makes the idempotency check enforceable at the DB level |
| `trigger_mode` | TEXT | NOT NULL, CHECK IN (`mode_a`,`mode_b`) | — |
| `repository_id` | TEXT | NOT NULL, FK → `repository.id` | — |
| `policy_version_id` | TEXT | NOT NULL, FK → `policy_version.id` | Resolved from `repository.assigned_policy_id`'s current version at T1; never "current policy" |
| `status` | TEXT | NOT NULL, CHECK IN (`started`,`running`,`completed`,`failed`) | Per `Entities_Value_Objects.md`'s Analysis lifecycle, extended with `failed` — see note below |
| `failure_reason` | TEXT | NULL | Populated only when `status = 'failed'` (e.g. `pr_context_retrieval_failed`, `github_api_unreachable`) |
| `pr_context_retrieval_status` | TEXT | NULL, CHECK IN (`succeeded`,`failed`) | Mode A only — tracks whether the changed-files retrieval that Artifact Classification depends on succeeded; always NULL under Mode B, since Mode B supplies its artifact set directly (`API_Contract.md`) and never calls GitHub for it |
| `pr_number` | INTEGER | NULL | Absent under Mode B |
| `pr_head_branch` | TEXT | NULL | Absent under Mode B |
| `pr_base_branch` | TEXT | NULL | Absent under Mode B |
| `pr_author` | TEXT | NULL | Absent under Mode B |
| `pr_head_commit_sha` | TEXT | NULL | Absent under Mode B; part of Mode A's `correlationId` derivation |
| `manual_trigger_key` | TEXT | NULL | Present only under Mode B |
| `security_score` | REAL | NULL | Set at T3 only |
| `verdict` | TEXT | NULL, CHECK IN (`PASS`,`BLOCK`) | Write-once (P-04); enforced at the application layer via `Analysis.recordVerdict()`, not by a DB trigger |
| `degradation_any_scanner_failed` | BOOLEAN | NULL | Set at T3 |
| `degradation_ai_available_at_completion` | BOOLEAN | NULL | Set at T3 |
| `created_at` | TEXT | NOT NULL | ISO 8601, set at T1 |
| `completed_at` | TEXT | NULL | Set at T3 |

Indexes: `UNIQUE(correlation_id)` (already a constraint above), `INDEX(repository_id)`, `INDEX(status)`.

**On the `failed` status.**

`failed` is a terminal state used when SentinelAI determines that it cannot produce a trustworthy Security Result for the Analysis.

A failed Analysis never has a verdict and can never transition back to `running` or `completed`.

`failure_reason` identifies the concrete cause of the failure. Examples include:
- `pr_context_retrieval_failed`
- `policy_not_configured`
- other terminal pre-verdict failures explicitly defined by `Error_Handling_and_Resilience.md`.

A completed Analysis always has a verdict. A failed Analysis never has a verdict.

This is distinct from degradation flags, which apply only to completed Analyses that successfully reached a verdict despite non-blocking dependency failures.

See `Persistence_Strategy.md`'s "Pre-T1 Context Retrieval and the `failed` Path" for exactly when this status is written.

**On notification failures.** A failed `notification` row (below) is never reflected in `analysis`'s status or degradation columns, and no column is added here for it. This is intentional, not an oversight: `Ubiquitous_Language.md`'s Notification entry states a failed delivery must never be interpreted as a failed Analysis — the two facts live in two different tables on purpose.

### `artifact`
Child of `analysis`, written once at T1.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | — |
| `analysis_id` | TEXT | NOT NULL, FK → `analysis.id` | — |
| `path` | TEXT | NOT NULL | — |
| `artifact_type` | TEXT | NOT NULL | source / dockerfile / k8s-helm / terraform / github-actions / dependency-manifest / other |
| `change_kind` | TEXT | NOT NULL, CHECK IN (`added`,`modified`,`deleted`) | — |

Indexes: `UNIQUE(analysis_id, path)`.

### `scanner_execution`
Child of `analysis`. **One row per eligible scanner is inserted at T1**, with `status = 'running'`, as soon as Scanner Selection has determined which scanners apply — this is the single rule this table follows; there is no second path that creates a `scanner_execution` row at T2. Each scanner's own T2 only ever `UPDATE`s the row T1 already created for it (`Persistence_Strategy.md`). This is also what makes Crash & Restart Recovery well-defined: a row can be found at `status = 'running'` after a crash only because T1 guarantees it was created up front, for every eligible scanner, not conditionally on that scanner having reported back.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | This **is** the execution identifier — one immutable, unique value per concrete run, referenced by `finding.scanner_execution_id` and citable directly from Audit |
| `analysis_id` | TEXT | NOT NULL, FK → `analysis.id` | — |
| `scanner_id` | TEXT | NOT NULL | Which scanner capability (Semgrep, Bandit, Trivy, Gitleaks, Checkov) |
| `scanner_version` | TEXT | NOT NULL | The concrete version of the scanner tool used for *this* execution — required so Audit can reconstruct exactly which tool version produced a given historical Finding, independent of whatever version is configured today |
| `status` | TEXT | NOT NULL, CHECK IN (`running`,`succeeded`,`failed`,`timed_out`) | A `failed`/`timed_out` row is never deleted or reinterpreted as "no findings" (P-09) |
| `exit_code` | INTEGER | NULL | The raw subprocess exit code; NULL while `running` |
| `timeout_seconds` | INTEGER | NOT NULL | The timeout actually applied to this execution — recorded per-row (not just read from current config) so a historical execution's behavior stays explainable even after the configured default changes |
| `execution_metadata` | TEXT | NULL | JSON — adapter-specific detail (invoked command, working directory, resource limits applied). A catch-all rather than named columns per scanner, consistent with P-05: scanner-specific detail stays behind the adapter boundary, not promoted into the shared schema |
| `started_at` | TEXT | NOT NULL | — |
| `completed_at` | TEXT | NULL | — |
| `failure_note` | TEXT | NULL | Human-readable summary; `execution_metadata` carries the structured detail |

Indexes: `UNIQUE(analysis_id, scanner_id)`.

### `finding`
Child of `analysis`, rows inserted at that scanner's T2; `risk_level`, `risk_heuristics_applied`, and `correlation_group_id` updated at T3 only.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Scoped to one Analysis, per `Entities_Value_Objects.md` |
| `analysis_id` | TEXT | NOT NULL, FK → `analysis.id` | — |
| `scanner_execution_id` | TEXT | NOT NULL, FK → `scanner_execution.id` | — |
| `scanner_id` | TEXT | NOT NULL | — |
| `category` | TEXT | NOT NULL | — |
| `artifact_path` | TEXT | NOT NULL | — |
| `artifact_type` | TEXT | NOT NULL | — |
| `location_file` | TEXT | NULL | Not every scanner reports line-level location |
| `location_line_start` | INTEGER | NULL | — |
| `location_line_end` | INTEGER | NULL | — |
| `rule_or_check_id` | TEXT | NOT NULL | Opaque outside the Scanner context (P-05) |
| `severity_level` | TEXT | NOT NULL | — |
| `severity_raw_value` | TEXT | NULL | — |
| `risk_level` | TEXT | NULL | Set at T3 (P-03) |
| `risk_heuristics_applied` | TEXT | NULL | JSON array; set at T3 |
| `correlation_group_id` | TEXT | NULL | Set at T3 |
| `secret_value_redaction_flag` | BOOLEAN | NOT NULL, DEFAULT 0 | Required by `Input_Output_Model.md`'s redaction rule |

**No `ai_enrichment_ref` column.** `Data_Contracts.md` deliberately removed this — `finding` is part of the frozen Security Result and never gains a column pointing at something produced after T3. The Report Generation Service joins `ai_enrichment` to `finding` by `subject_id = finding.id` at read time; this is a query-time join, never a stored foreign key on `finding`.

Indexes: `INDEX(analysis_id)`, `INDEX(correlation_group_id)`.

### `repository`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | — |
| `provider` | TEXT | NOT NULL, DEFAULT `'github'` | — |
| `external_identifier` | TEXT | NOT NULL, UNIQUE | e.g. `owner/repo` |
| `enabled_scanners` | TEXT | NOT NULL | JSON array of scanner IDs |
| `assigned_policy_id` | TEXT | NOT NULL, FK → `policy.id` | Invariant: never null — a Repository must have a Policy before any Analysis can produce a verdict |
| `ai_provider_config` | TEXT | NULL | JSON — **references** a provider/config name only; never contains a raw API key (`Configuration_and_Secrets.md`) |
| `active` | BOOLEAN | NOT NULL, DEFAULT 1 | — |
| `created_at` / `updated_at` | TEXT | NOT NULL | — |

### `policy`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | — |
| `current_version_id` | TEXT | NULL, FK → `policy_version.id` | Null only before the first version is published |
| `created_at` | TEXT | NOT NULL | — |

### `policy_version`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | — |
| `policy_id` | TEXT | NOT NULL, FK → `policy.id` | — |
| `version_number` | INTEGER | NOT NULL | — |
| `rules` | TEXT | NOT NULL | JSON: thresholds and suppression rules (UC-9) together — suppression is just content within `rules`, not a separate table |
| `published_at` | TEXT | NOT NULL | — |
| `published_by` | TEXT | NOT NULL | DevSecOps identity |

Indexes: `UNIQUE(policy_id, version_number)`. **Rows in this table are never updated after insert** — this is what guarantees QA-01.

### `audit_record`
Append-only; no application code path issues an `UPDATE` or `DELETE` against this table.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | — |
| `subject_analysis_id` | TEXT | NULL, FK → `analysis.id` | Null for configuration-change records not tied to an Analysis |
| `correlation_id` | TEXT | NULL | Present when `subject_analysis_id` is present |
| `actor` | TEXT | NOT NULL | DevSecOps identity, or `'system'` |
| `event_type` | TEXT | NOT NULL | — |
| `origin` | TEXT | NOT NULL, CHECK IN (`scanner`,`sentinel-core`,`llm-agent`) | Per `AI_Agent_Architecture.md` §9 — classifies **which subsystem produced the record**, not who requested it |
| `payload` | TEXT | NOT NULL | JSON — the recorded facts |
| `created_at` | TEXT | NOT NULL | — |

Indexes: `INDEX(subject_analysis_id)`, `INDEX(correlation_id)`.

**Resolving `origin` for DevSecOps-initiated actions (config/policy changes).** `origin` and `actor` answer two different questions, and together they already cover this case without a fourth `origin` value: `origin` says *which subsystem's data this is* (Scanner-produced, Sentinel Core-computed, or LLM/Agent-generated, per `AI_Agent_Architecture.md` §9's provenance table); `actor` says *who caused it* (a specific DevSecOps identity, or `'system'` for something automated). Repository and Policy are both Sentinel Core Aggregates (`Module_Boundaries.md`'s bounded-context mapping), so a DevSecOps configuration or Policy change is recorded as `origin = 'sentinel-core'` with `actor = '<devsecops-identity>'` — the same `origin` value a fully automated Policy Evaluation verdict uses, but with `actor = 'system'` instead. No new `origin` value is introduced for this case; the two columns together already disambiguate it.

### `notification`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | — |
| `analysis_id` | TEXT | NOT NULL, FK → `analysis.id` | — |
| `channel` | TEXT | NOT NULL | e.g. `github-status`, `github-comment`, `slack` |
| `status` | TEXT | NOT NULL, CHECK IN (`pending`,`delivered`,`failed`) | — |
| `attempted_at` | TEXT | NOT NULL | — |
| `content_snapshot` | TEXT | NULL | A denormalized copy of what was actually sent — **not** a foreign key to a `report` row, since Report is never persisted |

### `agent_execution` *(AI & Agent Module's own store)*

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | — |
| `subject_analysis_id` | TEXT | NOT NULL, **no FK constraint** | Cross-module reference by value only, per the physical-layout rule above |
| `correlation_id` | TEXT | NOT NULL | Inherited from the originating Analysis |
| `agent_type` | TEXT | NOT NULL | Extensible via the Agent Registry |
| `status` | TEXT | NOT NULL, CHECK IN (`running`,`completed`,`pending_unavailable`) | — |
| `tool_calls_log` | TEXT | NOT NULL | JSON array |
| `knowledge_base_entries_used` | TEXT | NOT NULL | JSON array of `{topic, version}` |
| `execution_limits` | TEXT | NOT NULL | JSON: `maxDurationSeconds`, `maxToolCalls`, `maxOutputSize` |
| `started_at` | TEXT | NOT NULL | — |
| `completed_at` | TEXT | NULL | Null while `running` or `pending_unavailable` |

### `ai_enrichment` *(AI & Agent Module's own store)*

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | — |
| `scope` | TEXT | NOT NULL, CHECK IN (`finding`,`analysis`) | — |
| `subject_id` | TEXT | NOT NULL, **no FK constraint** | A `finding.id` or `analysis.id`, cross-module reference by value only |
| `explanation` | TEXT | NOT NULL | — |
| `consequence_framing` | TEXT | NULL | — |
| `prioritization_hint` | TEXT | NULL | — |
| `remediation_suggestion` | TEXT | NULL | — |
| `remediation_status` | TEXT | NOT NULL, CHECK IN (`provided`,`insufficient_knowledge`) | Never silently omitted (decision 5) |
| `knowledge_base_entries_cited` | TEXT | NULL | JSON array of `{topic, version}` |
| `source_agent_execution_id` | TEXT | NOT NULL, FK → `agent_execution.id` | This FK **is** enforced — both tables belong to the same module's own store |
| `created_at` | TEXT | NOT NULL | — |

**Structural exclusion, enforced at the schema level**: this table has no `verdict` or `security_score` column, and none may ever be added without a breaking `contractVersion` change (P-02, `Data_Contracts.md`).

### `security_knowledge_base_entry` *(Security Intelligence & Data Module's own store)*

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | — |
| `topic` | TEXT | NOT NULL | — |
| `version` | INTEGER | NOT NULL | — |
| `content` | TEXT | NOT NULL | — |
| `source_reference` | TEXT | NULL | — |
| `published_at` | TEXT | NOT NULL | — |

Indexes: `UNIQUE(topic, version)`. **No relationship to any Analysis, Repository, or Policy** — no FK, no `analysis_id` column, no `correlation_id` column, consistent with `Aggregates_and_Boundaries.md`'s "Data Management Boundary."

## SQLite → PostgreSQL Type Mapping (future reference only)

| SQLite (MVP) | PostgreSQL (Phase 3+) |
|---|---|
| `TEXT` (UUID) | `UUID` |
| `TEXT` (JSON blob) | `JSONB` |
| `BOOLEAN` (stored as 0/1) | `BOOLEAN` (native) |
| `TEXT` (ISO 8601 timestamp) | `TIMESTAMPTZ` |
| `INTEGER` | `INTEGER` / `BIGINT` as needed |

This table is a reference for the eventual migration (`Deployment_Strategy.md`, `Technology_Strategy.md`) — no PostgreSQL-specific feature (partitioning, native arrays, row-level security) is designed here, since introducing one now would be exactly the kind of premature complexity `Architecture_Patterns.md` already rejects for the MVP.
