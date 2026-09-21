# Persistence Strategy

## Purpose

This document defines how SentinelAI actually reads and writes the tables in `Data_Model.md`: which adapter implements which `*Store` port, how the T1/T2/T3 transactions from `Aggregates_and_Boundaries.md` map onto real SQLite transactions, how concurrent scanner completions are serialized, how idempotency is enforced at the storage layer, and the MVP's approach to migrations and retention.

## Repositories / Adapters

Each `*Store` port from `Ports_and_Interfaces.md` is implemented by exactly one adapter class, and each adapter touches only the tables its own module owns (`Data_Model.md`'s table-prefix convention). No adapter class is shared across modules.

| Port | Adapter | Tables it may touch |
|---|---|---|
| `AnalysisStore` | `SqliteAnalysisStore` | `analysis`, `artifact`, `scanner_execution`, `finding` |
| `RepositoryConfigStore` | `SqliteRepositoryConfigStore` | `repository` |
| `PolicyStore` | `SqlitePolicyStore` | `policy`, `policy_version` |
| `AuditStore` | `SqliteAuditStore` | `audit_record` |
| `NotificationStore` | `SqliteNotificationStore` | `notification` |
| `AgentExecutionStore` | `SqliteAgentExecutionStore` | `agent_execution`, `ai_enrichment` |
| `KnowledgeBaseStore` | `SqliteKnowledgeBaseStore` | `security_knowledge_base_entry` |

This is a direct implementation of the Repository Pattern already named in `Architecture_Patterns.md`: each adapter isolates SQLite-specific code behind the domain-owned port interface, so a Phase 3 PostgreSQL migration touches only these seven adapter classes, never domain logic.

## Transaction Boundaries: T1 / T2 / T3

These map directly onto `Aggregates_and_Boundaries.md`'s transaction definitions — this section adds only the concrete SQLite mechanics.

### Pre-T1 Context Retrieval and the `failed` Path

`Aggregates_and_Boundaries.md`'s T1 is a single atomic transaction that inserts `analysis`, its snapshot columns, **and** its `artifact` rows together. That definition is unchanged here. What this section resolves is a sequencing question T1 itself doesn't address: `artifact` rows require a classified changed-files list, and under Mode A that list comes from a GitHub API call (`GitHub_Integration.md`) that can fail — a call that must therefore happen **before** T1 begins, never inside T1's transaction (external I/O has no place inside a `BEGIN...COMMIT` block, and T1 cannot insert artifact rows it doesn't have yet).

The resolved sequence:

```
Signature verified, correlationId idempotency check passed (no existing Analysis)
    ↓
Mode A only: retrieve PR context (changed files) from GitHub, with retries (GitHub_Integration.md)
    ↓
   ├── Succeeded (or Mode B, which never needs this step) → classify artifacts → T1 fires as defined
   │
   └── Failed after retries exhausted → T1-Failed path (below) — T1's normal shape never fires
```

**T1-Failed — Analysis Created in Terminal `failed` State** (Mode A only; this is the operational answer to the question `GitHub_Integration.md` left open):
```
BEGIN IMMEDIATE;
  INSERT INTO analysis (
    id, correlation_id, trigger_mode, repository_id, policy_version_id,
    status, failure_reason, pr_context_retrieval_status,
    pr_number, pr_head_branch, pr_base_branch, pr_author, pr_head_commit_sha,
    created_at, completed_at
  ) VALUES (
    ..., 'failed', 'pr_context_retrieval_failed', 'failed',
    ..., -- PR identity fields the webhook payload already carried, still recorded
    :now, :now  -- completed_at is set immediately: this Analysis is terminal on arrival, it never passes through 'running'
  );
COMMIT;
```
No `artifact`, `scanner_execution`, or `finding` row is ever written for a `failed` Analysis — there is nothing to classify or scan. **T3 never fires for a `failed` Analysis**: there are no Findings, so there is no Risk, no Security Score, and no verdict. A `failed` Analysis produces no PASS/BLOCK and no Security Result, by construction — this is the direct, deliberate consequence of choosing this path over silently forcing an empty or fabricated verdict.

This resolves the two designs `GitHub_Integration.md` previously left open as contradictory: T1 (the happy path) still requires a classified artifact set, exactly as `Aggregates_and_Boundaries.md` defines it; a Mode A trigger that cannot obtain that artifact set never reaches T1 at all, and is instead recorded directly, once, as `failed` — this is "Option B" from the review, chosen specifically because it requires no change to T1's existing atomic definition.

### T1 — Analysis Created (happy path, Mode A after successful retrieval, or Mode B)
```
BEGIN IMMEDIATE;
  -- idempotency check
  SELECT id, status FROM analysis WHERE correlation_id = :correlation_id;
  -- if a row exists: COMMIT (no-op) and return the existing analysisId
  -- if no row exists:
  INSERT INTO analysis (..., status = 'running', pr_context_retrieval_status = 'succeeded' | NULL); -- 'succeeded' under Mode A, NULL under Mode B
  INSERT INTO artifact (...) -- one row per classified file
  INSERT INTO scanner_execution (analysis_id, scanner_id, status, started_at, timeout_seconds, ...)
    -- one row per scanner Scanner Selection determined eligible for this Analysis's artifacts,
    -- status = 'running', all in this same transaction — never inserted later, on demand, at T2
COMMIT;
```
`BEGIN IMMEDIATE` (rather than a deferred transaction) is used deliberately: it acquires SQLite's write lock at the start of the transaction, so the idempotency check-then-insert sequence cannot race against a second, concurrent T1 for the same `correlation_id` — see "Concurrency Model" below. The `UNIQUE(correlation_id)` constraint on `analysis` is the final backstop even if application-level serialization were ever bypassed.

**One rule, no exceptions**: `scanner_execution` rows are created **only** at T1, one per eligible scanner, in `running` status. T2 (below) never inserts a `scanner_execution` row — it only ever updates one that T1 already created. This is what makes Crash & Restart Recovery well-defined (below): a row found at `status = 'running'` after a crash exists precisely because T1 guarantees its creation up front, not conditionally on that scanner having reported anything back yet.

### T2 — Scanner Execution Completed
```
BEGIN IMMEDIATE;
  UPDATE scanner_execution SET status = :status, exit_code = :exit_code, execution_metadata = :metadata,
    completed_at = :now, failure_note = :note
    WHERE analysis_id = :analysis_id AND scanner_id = :scanner_id AND status = 'running';
    -- UPDATE only — this row already exists from T1; T2 never INSERTs a scanner_execution row
  INSERT INTO finding (...) -- zero or more rows, only if status = 'succeeded'
COMMIT;
```
The `AND status = 'running'` clause mirrors T3's write-once guard on `analysis.verdict`: it is a storage-level backstop against updating a `scanner_execution` row twice (e.g., a duplicate completion signal from the same scanner), on top of whatever the application layer already enforces.
One T2 per scanner, independent of every other scanner's T2 for the same Analysis — see "Concurrency Model" for how independence is preserved despite SQLite's single-writer engine.

### T3 — Correlation + Risk + Policy Finalized
```
BEGIN IMMEDIATE;
  UPDATE finding SET correlation_group_id = ..., risk_level = ..., risk_heuristics_applied = ...
    WHERE analysis_id = :analysis_id; -- one UPDATE per affected finding
  UPDATE analysis SET security_score = :score, verdict = :verdict,
    degradation_any_scanner_failed = :flag, degradation_ai_available_at_completion = :flag2,
    status = 'completed', completed_at = :now
    WHERE id = :analysis_id AND verdict IS NULL; -- WHERE clause enforces write-once at the SQL level too
COMMIT;
```
The `WHERE verdict IS NULL` clause is a second, storage-level enforcement of the write-once invariant already required at the application layer by `Analysis.recordVerdict()` (`Domain_Services.md`) — belt and suspenders, not a replacement for it. If this `UPDATE` affects zero rows, the application layer treats that as a serious invariant violation (an attempt to re-decide an already-decided verdict), not a silent no-op.

**T-Agent, T-Audit, T-Notify, T-Repo, T-Policy, T-Knowledge** all follow the same `BEGIN IMMEDIATE ... COMMIT` shape, scoped to their own module's tables only, exactly as described in `Aggregates_and_Boundaries.md`.

## Concurrency Model: WAL + Serialized Queue per Analysis

SQLite's WAL (Write-Ahead Log) mode is enabled for the MVP database (`PRAGMA journal_mode=WAL`). WAL allows readers to proceed without blocking on an in-progress writer, which matters here because DevSecOps read use cases (UC-5, UC-6) must never be blocked by an in-progress Analysis. It does **not**, by itself, allow two writers to commit at the same instant — SQLite still serializes writes at the file level.

The chosen design adds a second, application-level layer on top of WAL: **a serialization queue keyed per `analysis_id`**, not a single global lock:

- Two T2 transactions for **different** Analyses proceed independently — they queue separately and never wait on each other.
- Two T2 transactions for the **same** Analysis (e.g., Semgrep and Trivy both finishing within milliseconds of each other) are serialized through that Analysis's queue, one at a time, in the order they arrive.
- This exists specifically to protect the "have all eligible Scanner Executions reached a terminal state?" check that decides whether T3 should fire. Without per-Analysis serialization, two nearly-simultaneous T2 completions could both read "not all scanners done yet" before either writes its own completion, and T3 would never trigger. With the queue, each T2's write and the subsequent completion check happen as one uninterrupted step relative to that Analysis's other T2s.
- The queue is in-process (per `Deployment_Strategy.md`'s single-process modular monolith) — no distributed lock is needed for the MVP, since there is exactly one SentinelAI process.

## Crash & Restart Recovery

This is deliberately not a distributed-systems design — SentinelAI is one process (`Deployment_Strategy.md`) — but "one process" still means a mid-execution crash or restart must leave the database in a recoverable, non-hanging state, not an unresolvable one.

- **A scanner never responds**: already covered by the timeout each Scanner Execution is invoked with (`C4_Container.md` §8, `Data_Model.md`'s `timeout_seconds`) — the adapter itself enforces the timeout and writes `status = 'timed_out'` via a normal T2, independent of whether the main process later crashes.
- **The Python process dies mid-Analysis**: any `scanner_execution` row left at `status = 'running'` and any `analysis` row left at `status = 'running'` are now stale — the in-memory subprocess handles and the per-Analysis serialization queue (in-process, per "Concurrency Model" above) are gone with the process, but the rows persist.
- **On SentinelAI startup, a recovery sweep runs once, before accepting new webhooks or triggers**:
  1. Find every `scanner_execution` row with `status = 'running'`. Since no in-memory handle for it can possibly still exist (the process that held it is the one that just restarted), mark each one `failed` with `failure_note = 'process restarted mid-execution'` — a normal T2, using the existing failure representation, not a new status.
  2. For every `analysis` row with `status = 'running'`, re-evaluate the same "have all eligible Scanner Executions reached a terminal state?" condition that normally triggers T3 (`Aggregates_and_Boundaries.md`) — no new completion logic is introduced, the sweep simply re-runs the existing check now that step 1 has resolved any previously-`running` executions to a terminal state. If the condition is now satisfied, T3 proceeds normally (correlation → risk → policy), producing a verdict based on whatever scanners had genuinely completed before the crash, exactly as QA-03/P-09 already require for any scanner failure.
  3. An `analysis` row with `status = 'failed'` is never touched by the sweep — it is already terminal.
- **No row is ever left permanently `running` after a restart**: step 1 guarantees every Scanner Execution reaches a terminal state, and step 2 guarantees every Analysis is re-evaluated against that resolved set — an Analysis that still cannot reach T3 (e.g., every scanner was `running` at crash time and is now `failed`) proceeds to T3 anyway, with `degradation_any_scanner_failed = true`, and produces a verdict from an empty or partial finding set — it does not hang a second time.

## Idempotency at the Storage Layer

`Domain_Events.md` already defines the `correlationId` idempotency rule at the domain level. This section states its storage-level enforcement:

- `analysis.correlation_id` is `UNIQUE`. A second T1 attempt for a `correlationId` that already has a row fails the `INSERT` with a constraint violation, which the application catches and turns into "return the existing `analysisId`," per UC-1/UC-2's idempotency behavior — never a raised, unhandled error.
- `policy_version` and `security_knowledge_base_entry` both have their own `UNIQUE` constraints (`(policy_id, version_number)` and `(topic, version)` respectively) that make "publish the same version twice" a detectable, rejected condition rather than a silent duplicate.

## Migrations

No specific migration tool is locked in here — that is an implementation detail for `08_Engineering_Research`/`09_Decisions`, not an architectural one. The principles that any chosen tool must satisfy:

1. **Forward-only.** A migration adds or changes schema; it is never edited after being applied to any environment. A mistake is fixed by a new, corrective migration, not by rewriting history.
2. **Additive-first**, mirroring `Data_Contracts.md`'s `contractVersion` convention: a new nullable column doesn't require touching existing rows; a column removal or type change is a breaking change, planned and reviewed like any other breaking `contractVersion` bump.
3. **Tracked in a `schema_migrations` table** (migration ID, applied timestamp) inside the same SQLite file, so the running schema version is always self-describing.
4. **No destructive migration runs silently.** Dropping a column or table requires an explicit, reviewed step — never bundled automatically into an unrelated feature migration.

## Retention

| Data | Retention |
|---|---|
| `audit_record` | Indefinite. Never purged automatically — QA-01 requires every historical verdict to remain reconstructable, and a retention job would directly contradict that. |
| `policy_version` | Indefinite. Old versions must remain queryable so a historical Analysis's `policy_version_id` reference always resolves. |
| `analysis` / `finding` / `scanner_execution` / `artifact` | Indefinite for the MVP, consistent with a single-operator deployment at modest scale (`Technology_Strategy.md`'s reference hardware). A configurable retention window is a reasonable future addition but is not designed here, since no current requirement calls for it. |
| `agent_execution` / `ai_enrichment` | Indefinite for the MVP, same reasoning. |
| `notification` | Indefinite for the MVP; the lowest-priority table to eventually prune, since it holds delivery attempts, not decisions. |
| `security_knowledge_base_entry` | Old versions retained (never deleted) — `Entities_Value_Objects.md` already requires this for provenance ("an Agent Execution can cite exactly which knowledge-base version it used"). |

## Eventually Consistent Components

This restates `Aggregates_and_Boundaries.md`'s Transactional Consistency Rules table from a storage-operations angle: `agent_execution`, `ai_enrichment`, the Report projection (never persisted), and any `notification` row beyond the mandatory GitHub channel are all written by transactions with no relationship to T1–T3. Operationally, this means: a slow or stalled AI provider shows up as `agent_execution.status = 'pending_unavailable'` rows sitting indefinitely against already-`completed` Analyses — this is expected steady-state behavior, not a data integrity problem, and no reconciliation job is needed to "fix" it. The only thing that must eventually happen is that `T-Agent` either commits (`completed`) or stays `pending_unavailable` — there is no third, inconsistent state possible given the transaction shapes above.
