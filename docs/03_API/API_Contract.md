# API Contract

## Purpose

This document defines SentinelAI's external interfaces: the GitHub webhook entry point, the DevSecOps-facing REST endpoints for triggering analyses and reading results, authentication, the error model, and how correlation/idempotency (`Domain_Events.md`) surface at the API boundary. Response bodies reuse the contracts already fixed in `Data_Contracts.md` — this document does not redefine `Security Result`, `Finding`, `AI Enrichment`, `Agent Execution`, or `Report`, it only specifies how they're transported.

## Authentication

Two distinct auth mechanisms, for two distinct categories of caller — these are never interchangeable:

| Endpoint category | Caller | Mechanism |
|---|---|---|
| GitHub webhook (`POST /webhooks/github`) | GitHub (system-to-system) | HMAC-SHA256 signature verification (`GitHub_Integration.md`) — **not** OAuth, not a bearer token. GitHub is a trusted, signature-verified system source, not an authenticated human actor (`Application_Use_Cases.md` UC-1). |
| All DevSecOps-facing endpoints (trigger, status, report, audit, configuration) | DevSecOps (human) | **OAuth against GitHub.** DevSecOps authenticates with their GitHub identity; SentinelAI validates the resulting token on every request and maps it to a DevSecOps identity for the `actor` field in Audit Records. No separate SentinelAI-specific credential is issued for the MVP. |

Every DevSecOps-facing route requires a valid session/token; there is no anonymous or unauthenticated path to any endpoint below except the webhook receiver.

### OAuth Boundary Contract

This section fixes the minimum contractual surface for "OAuth against GitHub" — enough for `API_Contract.md` to be internally consistent and for the auth mechanism to have testable edges, without designing the full OAuth implementation (that remains `08_Engineering_Research`/implementation-phase work).

| Endpoint | Purpose |
|---|---|
| `GET /auth/login` | Redirects to GitHub's OAuth authorize URL. No body; the entry point for a DevSecOps user with no active session. |
| `GET /auth/callback` | GitHub's OAuth redirect target. Exchanges the authorization code for a token, resolves the DevSecOps identity, and establishes a session. |
| `POST /auth/logout` | Revokes the current session. |

**Session/token model**: on successful callback, SentinelAI issues its own short-lived session token (not the raw GitHub token) to the DevSecOps client; the underlying GitHub token is held server-side only and is never returned to the caller. Every subsequent DevSecOps-facing request carries this session token (e.g., as a bearer token or cookie — the specific transport is an implementation detail, not fixed here).

**Validation**: every DevSecOps-facing endpoint validates the session token on each request; an invalid or absent token is `401`, before any business logic runs — the same "reject before processing" posture already established for webhook signature validation (`GitHub_Integration.md`).

**Expiration**: sessions expire after a fixed, configurable window; an expired session is `401` and requires a new `GET /auth/login` round trip. The exact duration is a configuration value, not an architectural decision, and is not fixed here.

**Revocation**: `POST /auth/logout` invalidates the session token server-side immediately; it does not, by itself, revoke GitHub's own OAuth grant (that remains under the DevSecOps user's control via their GitHub account settings) — SentinelAI revokes its own session, not GitHub's authorization.

## Endpoints

### `POST /webhooks/github`
Implements UC-1. Receives a GitHub `pull_request` webhook (`opened` or `synchronize`).

- **Auth**: signature verification only (`X-Hub-Signature-256`), per `GitHub_Integration.md`.
- **Request body**: the raw GitHub webhook payload.
- **Behavior**: verify signature → derive `correlationId` (Mode A) → check idempotency → if new, accept and return quickly (see `GitHub_Integration.md` for why this responds before T1 fully completes); if a duplicate, still return success without creating a second Analysis.
- **Response**: `202 Accepted` with `{ "correlationId": "...", "analysisId": "..." | null }`. `analysisId` is `null` only in the brief window between acceptance and T1's commit; poll `GET /analyses/{analysisId}` once available, or `GET /analyses?correlationId=...` in the meantime.
- **Errors**: `401` (invalid signature — never processed further), `400` (malformed payload).

### `POST /analyses`
Implements UC-2 (manual trigger, Mode A or Mode B).

- **Auth**: OAuth (DevSecOps).
- **Request body**:
```
{
  "repositoryId": "...",
  "prReference": { "prNumber": 123 } | null,   // present → Mode A; absent → Mode B
  "artifactSet": [...] | null,                  // required when prReference is absent (Mode B)
  "idempotencyKey": "..." | null                // optional, Mode B only — becomes manualTriggerKey
}
```
- **Behavior**: identical downstream flow to the webhook path from T1 onward (`Application_Use_Cases.md` UC-2's "identical to UC-1 from step 4 onward").
- **Response**: `202 Accepted`, same shape as the webhook response. If `idempotencyKey` matches an existing Mode B Analysis, returns the existing `analysisId` rather than creating a new one.
- **Errors**: `401` (not authenticated), `403` (DevSecOps lacks "execute manual analyses" permission), `404` (unknown `repositoryId`), `400` (Mode B request missing `artifactSet`).

### `GET /analyses?correlationId=...`
Resolves the interval between a trigger being accepted and its `analysisId` becoming available (see `POST /webhooks/github` and `POST /analyses` below, both of which can return `analysisId: null`). This endpoint was referenced by both trigger endpoints in the original draft of this contract without being defined; it is defined here explicitly, not left implicit.

- **Auth**: OAuth (DevSecOps) — the webhook path itself doesn't call this; it's for a caller that accepted a `202` and needs to resolve the resulting `analysisId` (or discover the `failed` outcome, see `Data_Model.md`'s `failed` status) once it exists.
- **Response** (`200`): `{ "analysisId": "..." | null, "correlationId": "...", "status": "..." | null }` — `status` and `analysisId` are both `null` only in the brief window before T1 (or the T1-Failed path, `Persistence_Strategy.md`) has committed.
- **Errors**: `400` (missing `correlationId` query parameter).

### `GET /analyses/{analysisId}`
Returns Analysis status and, once available, the Security Result.

- **Auth**: OAuth (DevSecOps).
- **Response** (`200`): `{ "analysisId", "correlationId", "status", "failureReason": "..." | null, "securityResult": <Security Result contract, Data_Contracts.md> | null }`. `securityResult` is `null` while `status != "completed"`. `failureReason` is populated only when `status = "failed"` (`Data_Model.md`) — a caller must treat `failed` as terminal (no verdict will ever arrive) and distinct from `running` (still in progress) or `completed` (verdict present).
- **Errors**: `404` (unknown `analysisId`).

### `GET /analyses/{analysisId}/report`
Implements UC-5. Query parameter `audience=developer|devsecops` (default `devsecops`).

- **Auth**: OAuth (DevSecOps) for `audience=devsecops`; the `developer`-audience shape is also available to DevSecOps in this API (Developers themselves never call this API directly — they see results only through GitHub, per `Interaction_Model.md`).
- **Response** (`200`): the `Report` contract (`Data_Contracts.md`), including `aiSection.status` — a caller must not treat `pending` as an error.
- **Errors**: `404` (unknown `analysisId`), `409` (Analysis not yet `completed` — no report exists to generate).

### `GET /audit-records`
Implements UC-6. Query parameters: `analysisId`, `correlationId`, `from`, `to` (any combination; at least one required).

- **Auth**: OAuth (DevSecOps).
- **Response** (`200`): `{ "records": [ <Audit Record>, ... ] }`, each entry including `origin` (`scanner`/`sentinel-core`/`llm-agent`) so provenance is visible in the response, not just internally (`AI_Agent_Architecture.md` §9).
- **Errors**: `400` (no filter provided — this endpoint never returns the entire audit trail unfiltered).

### `POST /repositories/{repositoryId}/config`
Implements UC-3.

- **Auth**: OAuth (DevSecOps), "configure repositories" permission.
- **Request body**: `{ "enabledScanners": [...], "assignedPolicyId": "...", "aiProviderConfig": {...} | null, "active": true|false }`. `aiProviderConfig` never contains a raw secret — it references a configured provider name only (`Configuration_and_Secrets.md`).
- **Response** (`200`): the updated Repository configuration.
- **Behavior**: writes `T-Repo` only; never retroactively affects an Analysis already `running` (`Application_Use_Cases.md` UC-3).

### `POST /policies/{policyId}/versions`
Implements UC-4 and UC-9 (suppression is content within a version, not a separate endpoint).

- **Auth**: OAuth (DevSecOps), "configure security policies" permission.
- **Request body**: `{ "rules": {...} }` — thresholds and, optionally, suppression rules, per `Aggregates_and_Boundaries.md`'s Policy section.
- **Response** (`201`): the newly published, immutable `PolicyVersion`.
- **Behavior**: `T-Policy` only. Never edits a prior version; never affects an already-`completed` Analysis.

## Error Model

Every error response shares one envelope:

```
{
  "error": {
    "code": "string, machine-readable (e.g. INVALID_SIGNATURE, ANALYSIS_NOT_FOUND, UNAUTHORIZED)",
    "message": "human-readable",
    "correlationId": "..." | null
  }
}
```

- `correlationId` is echoed back whenever the request carried or produced one, so a failure can be traced to the same trigger identity used everywhere else in the system (`Domain_Events.md`).
- HTTP status codes follow standard REST semantics (`400` malformed input, `401` unauthenticated, `403` unauthorized, `404` not found, `409` conflict/precondition, `500` unexpected). No endpoint invents a non-standard status code.
- An error response is never itself evidence of an Analysis failure — a `409` on `GET /analyses/{id}/report` means "not ready yet," not "the Analysis failed" (`Ubiquitous_Language.md`'s Notification/Report distinction applies to API errors the same way it applies to delivery failures).

## Correlation & Idempotency at the API Boundary

- Every response that relates to an Analysis includes both `analysisId` and `correlationId` — never one without the other once both exist.
- `POST /webhooks/github` and `POST /analyses` are the only two idempotent-by-design endpoints: calling either twice with the same underlying identity (redelivered webhook, or a reused `idempotencyKey`) returns the same `analysisId` rather than creating a duplicate Analysis, per `Domain_Events.md`'s Mode A/Mode B rules — this is API-level behavior, not just an internal implementation detail, and callers should rely on it rather than deduplicating client-side.
- `POST /repositories/{id}/config` and `POST /policies/{id}/versions` are **not** idempotent in the same sense — each call is a distinct, intentional configuration change (there is no `correlationId` for configuration changes, per `Domain_Events.md`'s "Explicitly Not Modeled as Separate Events" section).
