# Observability and Logging

## Purpose

This document defines SentinelAI's structured logging: the required fields on every log line, log levels and what triggers each, what must never be logged, and how to reconstruct the full story of one Analysis from logs plus the Audit trail. It also draws one boundary explicitly, because conflating the two is a common and costly mistake: **logs are for engineers debugging the running system; the Audit trail (`audit_record`, `Data_Model.md`) is the durable, business-facing record QA-01 depends on.** Logs may be rotated, sampled, or lost without consequence to SentinelAI's guarantees; the Audit trail may not. Nothing in this document substitutes for, or relaxes, anything already required of the Audit trail.

## Structured Logging

Every log line is a single JSON object (not free-text with embedded values) with a fixed set of core fields, plus event-specific detail:

```json
{
  "timestamp": "2026-09-18T14:03:22.481Z",
  "level": "INFO",
  "module": "core | ai_agent | intelligence | interfaces",
  "component": "AnalysisOrchestrator",
  "event": "t3_committed",
  "correlationId": "...",
  "analysisId": "..." ,
  "scannerExecutionId": null,
  "agentExecutionId": null,
  "message": "T3 committed: verdict=BLOCK, score=42",
  "detail": { }
}
```

- `correlationId` and `analysisId` are nullable independently, and deliberately so: `correlationId` exists from the moment a webhook signature is verified, before `analysisId` exists at all — a log line from the pre-T1 retrieval phase carries `correlationId` and `analysisId: null`; every line from T1 onward carries both.
- `scannerExecutionId` is present only on lines specific to one Scanner Execution (invocation, timeout, completion) — never on Analysis-level lines.
- `agentExecutionId` is present only on lines specific to one Agent Execution — never on Sentinel Core lines, reinforcing the module boundary (`Module_Boundaries.md`) at the logging level too.
- `module` identifies which of the three modules emitted the line, mirroring `Project_Structure.md`'s top-level layout — this alone makes it possible to filter for "everything the AI & Agent Module did," independent of any specific Analysis.

## Log Levels

| Level | Used for |
|---|---|
| `DEBUG` | Detailed step-by-step tracing (individual Domain Service calls, port method invocations) — off by default, enabled only for local troubleshooting |
| `INFO` | Normal lifecycle events: T1/T2/T3 commits, webhook accepted, Analysis reached `completed`, Agent Execution `completed`, Notification delivered |
| `WARNING` | Expected-but-notable degradation: a scanner `timed_out`/`failed` but others succeeded, AI provider unreachable (`pending_unavailable`), a repeated invalid webhook signature from the same source (possible probing, not yet a confirmed attack), a Knowledge Base refresh cycle skipped |
| `ERROR` | A secondary-table write failure (`T-Audit`, `T-Notify`, `T-Agent`, `T-Knowledge`) after retries, a Notification delivery ultimately failed, a scanner adapter's own internal exception it had to catch and convert |
| `CRITICAL` | A verdict-critical SQLite write (T1 or T3) failed after retries are exhausted (`Error_Handling_and_Resilience.md`) — this is the one condition that genuinely needs a human's attention promptly, since an Analysis is stuck `running` for an infrastructure reason, not a designed-for degradation |

Two things are deliberately **not** `ERROR`/`CRITICAL`, because treating them as such would misrepresent working-as-designed behavior: an AI provider being unavailable (`WARNING` at most — this is QA-04's graceful degradation, not a malfunction), and a `failed` Analysis produced via the T1-Failed path (`INFO` — SentinelAI correctly determined it could not analyze this PR and said so; that is the system functioning correctly, not failing).

## What Must Never Be Logged

| Never logged | Why |
|---|---|
| `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_OAUTH_CLIENT_SECRET`, AI provider API keys, any value from `Configuration_and_Secrets.md`'s Secrets table | Same rule stated there, restated here at the point it's actually enforced: a failed authenticated call logs *that* authentication failed, never the credential that was tried |
| A raw secret value from a Finding where `secret_value_redaction_flag = true` | The same redaction rule that governs Developer-facing Reports (`Input_Output_Model.md`) applies to logs — a log line is not exempt from redaction just because DevSecOps, not a Developer, might read it |
| Full PR diff or file contents | Unbounded size and unnecessary — a log line references an `analysisId`/`artifactPath`, it does not embed the file |
| Raw AI provider prompts/responses at `INFO` or above | May contain source code or Finding detail; available at `DEBUG` only, and even then still subject to the secret-redaction rule above |
| OAuth session tokens or the underlying GitHub token held server-side (`API_Contract.md`'s OAuth Boundary Contract) | A session-validation failure logs "invalid/expired session," never the token value |
| Full request/response bodies for DevSecOps API calls, by default | Logged at `DEBUG` only, with the same secret-redaction rule applied first |

**Enforcement mechanism, not just policy**: the redaction rule is implemented once, as a shared logging utility (`shared/`, per `Project_Structure.md`) that every module's logging call passes Finding/secret-bearing data through — never re-implemented ad hoc per call site, which is how redaction rules silently get skipped in practice.

## Auditable Events vs. Log Events

| | Audit Record (`audit_record` table) | Log line |
|---|---|---|
| Durability | Indefinite, per QA-01 | Rotated/retained per operational policy, far shorter |
| Purpose | Reconstruct a historical verdict or configuration change | Debug the running system, right now or recently |
| Who reads it | DevSecOps, via `GET /audit-records` (`API_Contract.md`) | Engineers, via log tooling |
| What triggers a write | Exactly the events already defined in `AI_Agent_Architecture.md` §9 and `Data_Model.md`'s `audit_record` table | Every meaningful step, including ones that never rise to Audit-worthy (a `DEBUG` trace line is never an Audit Record) |

A `CRITICAL` log line about a stuck T3 write is *not* an Audit Record — nothing was decided, so there is nothing to audit yet. Once the write eventually succeeds, the resulting `AnalysisCompleted`/`PolicyEvaluated` Audit Record is written normally, and the earlier `CRITICAL` log lines remain in the logs only, as the operational story of why it was delayed.

## Diagnosing a Complete Analysis

Given a `correlationId` (the one identifier guaranteed to exist from before `analysisId` does, per `Domain_Events.md`), a complete diagnostic picture is assembled from:

1. All log lines matching that `correlationId`, ordered by timestamp — this alone tells the operational story: webhook received, retrieval attempts, T1 commit, each scanner's `scannerExecutionId` lifecycle, T3 commit, any Agent Execution's `agentExecutionId` lifecycle, Notification attempts.
2. The `analysis` row itself (status, verdict, degradation flags, `failure_reason` if terminal).
3. Every `scanner_execution` and `finding` row for that `analysisId`.
4. Every `agent_execution` and `ai_enrichment` row referencing that `analysisId` (queried by value, per `Data_Model.md`'s no-cross-module-FK rule — the query joins by `subject_analysis_id`/`subject_id`, not a database-enforced relationship).
5. Every `notification` row for that `analysisId`.
6. Every `audit_record` row with that `correlation_id`.

This six-part assembly is the same shape regardless of whether the Analysis succeeded, degraded, or reached `failed` — the only difference is which rows exist and what they contain. A future diagnostic script or admin endpoint should implement exactly this assembly, not a bespoke query per failure type.

## Metrics (Optional, Not a Phase-1 Requirement)

Basic counters and timers — Analyses by terminal status, per-scanner execution duration, AI provider call latency, T3 duration — are useful and cheap to add once structured logging exists (they can be derived from the same events), but no `Quality_Attributes.md` scenario currently requires a dedicated metrics/alerting platform for the MVP's single-operator scale. This is deliberately left as a natural extension of structured logging rather than a separate system to build now, consistent with the project's stated bias against unnecessary complexity.

## Log Retention

Logs are an operational convenience, not the durable record — a rotation policy (e.g., a fixed number of days or total size) is appropriate and does not require the indefinite retention `Persistence_Strategy.md` mandates for `audit_record`. Choosing a specific window is an operational tuning decision, not fixed here.
