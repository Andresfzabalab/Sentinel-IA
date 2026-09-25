# GitHub Integration

## Purpose

This document specifies exactly how the `RepositoryPort` adapter (`Ports_and_Interfaces.md`) talks to GitHub: which webhook events it listens for, how it validates them, how it retrieves PR context, and how it publishes results back — using the **Commit Status API** (not the Checks API) for the MVP, per the decision that a personal access token with a narrower scope is preferable to standing up a GitHub App this early. Nothing here changes the domain-level contract of `RepositoryPort`; this is the adapter's implementation spec.

## Webhook Events

SentinelAI subscribes to exactly one GitHub webhook event type: **`pull_request`**, filtered to two actions:

| Action | Handling |
|---|---|
| `opened` | Triggers UC-1 (Mode A) |
| `synchronize` | Triggers UC-1 (Mode A) — a new `headCommitSha` means a new `correlationId`, hence a new Analysis (`Domain_Events.md`) |
| Any other action (`closed`, `reopened`, `labeled`, etc.) | Received but ignored — acknowledged with `200`/`202` and no Analysis is created. Ignoring, not rejecting, avoids GitHub retrying a webhook SentinelAI has no use for. |

No other GitHub webhook event type (`push`, `issues`, `check_run`, etc.) is subscribed to for the MVP — subscribing to events SentinelAI doesn't act on only adds unused attack surface and noise.

## Signature Validation

Every incoming webhook is HMAC-SHA256 signed by GitHub using a shared webhook secret, delivered in the `X-Hub-Signature-256` header (format: `sha256=<hex digest>`).

1. Compute HMAC-SHA256 of the raw request body using the configured webhook secret (`Configuration_and_Secrets.md`).
2. Compare against the header value using a constant-time comparison (never a plain `==`, to avoid timing side-channels).
3. On mismatch or a missing header: reject with `401` immediately, before any parsing of the payload, and before any `correlationId` derivation. An unsigned or forged payload never reaches Sentinel Core's domain logic (`System_Boundaries.md`'s "Untrusted input, must be verified" row).
4. On match: proceed to `correlationId` derivation and idempotency check (`Domain_Events.md`), then T1.

## PR Retrieval and Changed Files

The webhook payload itself already carries most of what's needed (PR number, head/base branch, author, head commit SHA). Two additional GitHub REST calls complete the PR context:

- `GET /repos/{owner}/{repo}/pulls/{pull_number}/files` — the changed file list, paginated (GitHub returns up to 100 files per page; SentinelAI follows pagination via the `Link` header until exhausted). This is the input to Artifact Classification. This is `RepositoryPort.fetch_changed_files` — the *only* read operation the Orchestrator's port exposes (`Ports_and_Interfaces.md`).
- `GET /repos/{owner}/{repo}/pulls/{pull_number}` — for the webhook-triggered flow (UC-1), this is rarely necessary, since `pull_request` webhook payloads are already rich. It is, however, actively used by the DevSecOps-facing `POST /analyses` endpoint (UC-2, Mode A, `API_Contract.md`): a manually-triggered analysis supplies only a PR number, with no webhook payload to read branches/author/commit SHA from, so this call is what resolves them. This lookup is made directly by the API route (`interfaces/http/api/analyses.py`, via `GitHubClient.get_pull_request`) — it is deliberately *not* part of `RepositoryPort`'s contract, since the Orchestrator itself never needs it (Mode A's identity fields always arrive pre-resolved via `AnalysisTrigger` by the time `process()` is called, whether from the webhook or from this API-layer resolution).

**Commit SHA**: `pull_request.head.sha` from the webhook payload is the `headCommitSha` used in `correlationId` (Mode A). SentinelAI never derives it from a separate API call for the webhook-triggered flow — using the webhook's own value keeps the identifier consistent with the specific delivery being processed. For a DevSecOps manual trigger (UC-2), the equivalent guarantee is that the PR's *current* head_commit_sha is resolved exactly once, immediately before deriving `correlationId`, from the single `GET .../pulls/{pull_number}` call above — never re-resolved a second time later in the same request.

## Scanner Working Directory (Checkout)

Scanners are static analysis tools; they need real files on disk, not just the changed-file paths/types Artifact Classification produces. This was not fully specified when the container-level architecture was first drawn (`C4_Container.md`'s Security Scanner Execution container describes running the tools, not how they obtain file content) and was resolved during implementation (Phase 6, `Implementation_Strategy.md`):

- `WorkingDirectoryPort` (`Ports_and_Interfaces.md`) is implemented by `GitCheckoutProvider`, which performs a real `git clone --no-checkout` followed by `git checkout <head_commit_sha>` into a fresh temporary directory, using the same `GITHUB_TOKEN` PAT as an HTTPS credential (`https://x-access-token:<token>@github.com/<owner>/<repo>.git`).
- This runs once per Analysis, immediately before the scanner loop, and the resulting directory is passed to every selected `ScannerPort.run(...)` call as `working_directory`; it is removed (`cleanup()`) once every scanner has completed, in a `finally` block, regardless of outcome.
- A checkout failure (network issue, invalid commit, `git` not installed) raises `WorkingDirectoryError`, which the Orchestrator catches and treats as "no working directory available" (`working_directory = ""`) rather than failing the Analysis — each scanner adapter already handles a missing/empty directory honestly, resolving to a `'failed'` `ScannerRunResult` (P-09), so the Analysis still reaches a real, degraded-but-valid verdict.
- Mode B (ad hoc manual trigger, no PR) has no commit reference to check out against in the current design, so `working_directory` stays `""` for Mode B regardless of checkout availability — a known, documented limitation, not an oversight; extending Mode B to reference a branch/commit is a candidate future refinement, not required by any current use case.

## Permissions

A single GitHub Personal Access Token (fine-grained, per-repository) is the MVP's only GitHub credential, scoped to exactly what the Commit Status API and PR retrieval require:

| Permission | Why |
|---|---|
| Pull requests: Read | Fetch PR metadata and changed files |
| Commit statuses: Read and write | Publish the PASS/BLOCK result via the Commit Status API |
| Contents: Read | Fetch file contents for scanning where the diff alone is insufficient (e.g., full-file secret scanning context) |
| Issues: Write | Post the summary PR comment (GitHub represents PR comments through the Issues API) |

No `admin`, `write` on repository settings, or organization-level scope is requested — consistent with least privilege (`C4_Container.md` §8). A future move to the Checks API or a GitHub App is an explicit future decision, not something this token's scope anticipates or half-implements.

## GitHub Status (Commit Status API)

The verdict is published via `POST /repos/{owner}/{repo}/statuses/{sha}`:

```
{
  "state": "success" | "failure" | "error",   // PASS → success, BLOCK → failure, T1-Failed (no verdict possible) → error
  "context": "sentinelai/security-analysis",
  "description": "<short summary, e.g. 'No blocking findings', 'Blocked: 2 critical findings', or 'Could not retrieve PR context — analysis did not run'>",
  "target_url": "<link to the DevSecOps-facing report, if externally reachable; omitted otherwise, and always omitted for 'error' since there is no report to link to>"
}
```

This is the mandatory, deterministic channel described in `Module_Boundaries.md` — it is posted by Sentinel Core immediately after T3 commits (for `success`/`failure`), or immediately once retries are exhausted on the pre-T1 context-retrieval failure path (for `error`, see "Failure Handling" below), and it never waits on AI Enrichment or Agent Execution (`AI_Agent_Architecture.md` §8). `error` is not a "processing" or "pending" indicator — it is a terminal state, posted only once retrieval has definitively failed. SentinelAI still does not post any intermediate "analysis running" status for the MVP; the PRD does not require one, and `error` exists to represent a failure outcome, not progress.

## Comments

The Developer-facing summary comment is posted via `POST /repos/{owner}/{repo}/issues/{pull_number}/comments`, containing the redacted summary (`Input_Output_Model.md`'s redaction rule — no raw secret values, no full finding detail). SentinelAI posts **one** summary comment per Analysis; a `synchronize` event's new Analysis posts a new comment rather than editing the previous one, keeping the PR's comment history an honest record of each Analysis run.

## Retries and Duplicate Webhooks

- **Outbound calls to GitHub** (status, comment) use exponential backoff (e.g., 1s, 2s, 4s, up to a small fixed number of attempts) on `5xx` responses and on network failures. A `4xx` (other than `429`) is not retried — it indicates a request problem that retrying won't fix (e.g., an invalid token).
- **Inbound duplicate webhooks**: GitHub redelivers webhooks that don't receive a timely `2xx` response, or on manual redelivery from the GitHub UI. This is precisely what `correlationId` Mode A's idempotency rule (`Domain_Events.md`) exists to absorb — a duplicate delivery for an already-processed `(repositoryId, prNumber, headCommitSha)` is detected via the `UNIQUE(correlation_id)` constraint (`Persistence_Strategy.md`) and acknowledged without creating a second Analysis or posting a second status/comment.

## Rate Limits

GitHub's REST API returns `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers on every response. The adapter:
- Tracks remaining quota from the most recent response.
- If remaining quota drops below a small safety margin, delays non-urgent calls (e.g., a retry of a comment post) until `X-RateLimit-Reset`, rather than continuing to spend the last of the quota.
- On a `403` with a rate-limit-exceeded body (distinguished from a permissions `403` by the response body/headers), treats it as a transient failure subject to the same backoff as a `5xx`, not as an authorization problem.

## Failure Handling

- **Webhook processing**: the adapter verifies the signature and performs the `correlationId` idempotency check synchronously and quickly, then returns `202` — full processing (context retrieval, classification, scanner selection, scanner invocation) proceeds after the response is sent, so GitHub's webhook delivery timeout (a few seconds) is never at risk of being exceeded by the full Analysis pipeline.

- **PR retrieval failure — full operational flow.** This is the resolved answer to what happens when the changed-files retrieval fails (`Persistence_Strategy.md`'s "Pre-T1 Context Retrieval and the `failed` Path" is the authoritative transaction-level definition; this is the same flow from the GitHub-adapter's side):
  1. The retrieval call (`GET .../pulls/{pull_number}/files`) fails or errors after signature verification and idempotency checks have already passed.
  2. The adapter retries with the same exponential backoff policy used for outbound calls ("Retries and Duplicate Webhooks" above) — a fixed, small number of attempts.
  3. **If a retry succeeds**: classification proceeds normally and T1 fires as originally defined — the transient failure leaves no trace beyond the retry delay.
  4. **If all retries are exhausted**: the Analysis is created directly in the terminal `failed` status (`Data_Model.md`), with `failure_reason = 'pr_context_retrieval_failed'`. It never enters `running`, so it can never be mistaken for an in-progress Analysis, and no Analysis is ever left running indefinitely because of this failure mode.
  5. **T3 never fires** for this Analysis — there are no Findings, so no Risk, no Security Score, and no PASS/BLOCK verdict is ever produced for it. This is a deliberate consequence of the design, not an oversight: SentinelAI does not fabricate or default to a verdict when it structurally cannot evaluate the PR.
  6. **GitHub status is still published**, using the Commit Status API's `error` state (distinct from both `success` and `failure`): `{ "state": "error", "context": "sentinelai/security-analysis", "description": "Could not retrieve PR context — analysis did not run" }`. This is the answer to "can a PASS/BLOCK still be produced" (no) and "is the Developer left with no signal at all" (no — they see `error`, which GitHub visually distinguishes from a failing check).
  7. **No summary comment is posted** for a `failed` Analysis — there is no finding content to summarize, and posting a comment implying an analysis occurred would misrepresent what happened.
  8. **Recovery is manual**: DevSecOps can re-trigger the same commit via `POST /analyses` (UC-2, Mode A with the existing PR reference) once the underlying GitHub API issue is resolved. This reuses the existing manual-trigger capability rather than introducing new automatic re-scheduling — consistent with not designing more machinery than the MVP's single-operator scale requires (`Architecture_Patterns.md`'s stance on avoiding speculative generality).

- **Status/comment posting failure** (after T3, verdict already decided): this is a `Notification` failure, per `Ubiquitous_Language.md` — it never changes, blocks, or retries the verdict itself. It is retried per the backoff policy above and, if it ultimately fails, is recorded as `notification.status = 'failed'` (`Data_Model.md`) — visible to DevSecOps via the audit trail, never silently dropped. This case is unrelated to and unaffected by the PR-retrieval-failure flow above: by the time a Notification can fail, T3 has already succeeded and a real verdict already exists.
