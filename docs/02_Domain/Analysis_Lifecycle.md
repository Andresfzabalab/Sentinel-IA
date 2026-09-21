
# Analysis Lifecycle

## Why this document exists
Breaks the Security Decision Flow into 12 concrete stages with approximate timing characteristics, so implementation work has a clear, ordered checklist and so QA-04 (graceful AI degradation) and QA-03 (scanner resilience) have specific stages to attach to.

## The 12 stages

| # | Stage | Owning context | Nature | Can degrade? |
|---|---|---|---|---|
| 1 | Receive PR event (webhook) | Repository | I/O, fast (ms) | No — required |
| 2 | Fetch PR context (files, diff, metadata) | Repository | I/O, network-bound | No — required |
| 3 | Classify artifacts | Analysis | In-process, fast | No — required |
| 4 | Select applicable scanners | Scanner | In-process, fast | No — required |
| 5 | Execute scanners (parallel, independent processes) | Scanner | I/O + CPU, variable, seconds–minutes | Yes — per-scanner failure is isolated (P-09) |
| 6 | Normalize scanner output | Scanner | In-process, fast | No — required per successful scanner |
| 7 | Correlate findings | Analysis | In-process, fast | No — required |
| 8 | AI enrichment (advisory) | AI | I/O, variable, seconds (local) to seconds+ (API) | Yes — skipped entirely on timeout/failure (QA-04) |
| 9 | Risk assessment | Risk | In-process, fast, deterministic | No — required |
| 10 | Policy evaluation | Policy | In-process, fast, deterministic | No — required, produces the Verdict |
| 11 | Report + notify | Reporting, Notification | I/O to GitHub and other channels | Partial — GitHub status check is required; other channels are best-effort |
| 12 | Audit recording | Audit | In-process persistence | No — required, must succeed even if step 11's external delivery partially fails |

## Timing note (reference hardware)
On the reference hardware (no GPU), stage 8 (local Ollama) is expected to be the slowest in-budget stage; a configurable timeout bounds it so a single slow inference never blocks the whole run past a defined ceiling — after which the pipeline proceeds without enrichment (QA-04).

## Ordering invariants
- Stage 9 (Risk) must never run before stage 7 (Correlation) — risk is assessed per correlated finding, not per raw finding.
- Stage 10 (Policy) must never run before stage 9 (Risk) — policy evaluates risk-assessed findings.
- Stage 8 (AI) may run in parallel with the start of stage 9 preparation but its result, if any, only affects Reporting content (stage 11), never Risk or Policy inputs (P-02, P-03, P-04).
- Stage 12 (Audit) always runs, even if stage 11's external notification partially fails — the audit record is the source of truth, not the notification delivery status.

## Relationship to other documents
This is the stage-by-stage expansion of `Security_Decision_Flow.md`; per-finding state transitions within these stages are detailed in `Finding_Lifecycle.md`.
