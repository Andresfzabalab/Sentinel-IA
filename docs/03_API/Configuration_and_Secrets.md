# Configuration and Secrets

## Purpose

This document draws the line between **configuration** (data DevSecOps manages at runtime, stored in SentinelAI's own database) and **secrets** (credentials that must never be stored in the database in plaintext, never committed to Git, and only ever supplied through environment variables or a dedicated secret store). It also defines the local execution gate that keeps SentinelAI from starting in an unsafe or incomplete configuration state.

## Configuration (stored in SentinelAI's database, DevSecOps-managed)

These are ordinary application data, per `Data_Model.md` — they live in the `repository` and `policy`/`policy_version` tables, changed through the API endpoints in `API_Contract.md` (UC-3, UC-4), and are themselves audited (`Input_Output_Model.md`).

| Configuration | Where it lives | Managed via |
|---|---|---|
| Repository configuration (enabled scanners, assigned Policy, AI provider *reference*, active flag) | `repository` table | `POST /repositories/{id}/config` (UC-3) |
| Scanner configuration (which scanners are available system-wide, their invocation parameters/timeouts) | Application-level config, not per-repository secret data | Static config file or environment, read at startup — this is operational tuning, not a per-repository DevSecOps decision, and is not modeled as its own domain Aggregate |
| Policy configuration (thresholds, suppression rules) | `policy` / `policy_version` tables | `POST /policies/{id}/versions` (UC-4/UC-9) |
| AI provider configuration | `repository.ai_provider_config` (JSON) | `POST /repositories/{id}/config` — **contains a provider name and non-secret settings only** (e.g., `{"provider": "ollama", "model": "qwen"}` or `{"provider": "openai", "model": "..."}`) — never an API key |

**Rule**: nothing in this section may ever contain a raw credential. `ai_provider_config` names *which* provider and *how* to call it; the credential that authorizes the call lives exclusively in the Secrets section below, looked up by provider name at call time.

## Secrets (environment variables only, never in the database, never in Git)

| Secret | Used by | Environment variable |
|---|---|---|
| GitHub Personal Access Token | `RepositoryPort` adapter (`GitHub_Integration.md`) | `GITHUB_TOKEN` |
| GitHub webhook secret | Webhook signature validation (`GitHub_Integration.md`) | `GITHUB_WEBHOOK_SECRET` |
| GitHub OAuth client ID / secret | DevSecOps API authentication (`API_Contract.md`) | `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` |
| AI provider API key(s) | `AIProviderPort` adapters | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (only the ones actually configured need be present) |
| Ollama base URL | `AIProviderPort` (local) | `OLLAMA_BASE_URL` (not strictly a secret, but kept alongside the others since it's provider connection configuration, not domain data) |
| Security intelligence source credentials, if any feed requires one | `SecurityIntelligenceSourcePort` adapters | `SECURITY_INTEL_<SOURCE>_API_KEY` (one per configured source) |
| SQLite database file path | All `*Store` adapters | `DATABASE_PATH` (not a secret, but environment-level for the same reason as `OLLAMA_BASE_URL`) |

**Rule**: a secret is read from its environment variable exactly once, at the point an adapter needs to make an authenticated call. It is never logged, never included in an `audit_record.payload`, never returned in an API response, and never echoed in an error message — an error referencing a failed authenticated call states *that* authentication failed, not the value that was tried.

## What Can and Cannot Be Committed to Git

| Can be committed | Cannot be committed |
|---|---|
| `.env.example` — every variable name from the Secrets table above, with placeholder or empty values | `.env` — the real file, excluded via `.gitignore` |
| Static scanner configuration templates (default timeouts, default rule sets) | Any file containing a real token, API key, or webhook secret, under any filename |
| `Data_Model.md`'s schema and migration files | A populated SQLite database file, since `repository.ai_provider_config` and `policy_version.rules` may reflect a real deployment's operational specifics even though they contain no secrets themselves — committing a live DB file is a hygiene problem, not a secrets one, but is still disallowed |
| Documentation referencing environment variable *names* | Documentation or code comments containing an example that is a real, working credential rather than an obvious placeholder |

`.gitignore` must include `.env`, `*.sqlite`, `*.db`, and any local override config file, from the start of the repository's history — not added retroactively once something has already been committed.

## Local Execution Gate

SentinelAI refuses to start, rather than starting in a partially-functional state, when required secrets are absent:

| Missing | Behavior |
|---|---|
| `GITHUB_TOKEN` or `GITHUB_WEBHOOK_SECRET` | Application fails to start. The GitHub integration is not optional for the MVP's primary flow (UC-1), so there is no degraded mode for its absence — this is different from AI provider absence, which the system is explicitly designed to tolerate (`AI_Agent_Architecture.md` §8). |
| `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` | Application fails to start — every DevSecOps-facing endpoint requires this auth mechanism (`API_Contract.md`), so its absence leaves no usable configuration/reporting surface at all. |
| `DATABASE_PATH` | Application fails to start — there is no in-memory fallback; every Aggregate's persistence depends on it. |
| AI provider API key for a **configured** provider (a Repository references it in `ai_provider_config`) | Application starts normally. The specific Repository's Analyses proceed with AI enrichment unavailable (`AI Analysis: PENDING`, per decision 6) — this is the expected degraded path, not a startup failure. |
| Security intelligence source credential | Application starts normally. The Security Intelligence & Data Module's refresh cycle for that source fails and logs the failure; the Security Knowledge Base simply doesn't gain new entries from that source until the credential is supplied — no Analysis is affected, per `Aggregates_and_Boundaries.md`'s Data Management Boundary. |

The distinction driving this table is the same one that runs through the whole architecture: GitHub, the OAuth mechanism, and the database are load-bearing for the deterministic core and the only human-facing control surface, so their absence is a hard stop; AI providers and security intelligence sources are advisory-tier dependencies, so their absence degrades gracefully instead.

## Confirming `GITHUB_TOKEN` as Mandatory: Why Not a Modular "Core Without GitHub" Mode

This is worth stating explicitly rather than leaving as an implicit default, since the architecture is modular elsewhere. Two separate GitHub-related credentials exist (`GITHUB_TOKEN`, the PAT used for PR retrieval/status/comments; `GITHUB_OAUTH_CLIENT_ID`/`GITHUB_OAUTH_CLIENT_SECRET`, used for DevSecOps login), and in principle they could fail independently, with only the webhook-triggered flow (UC-1) disabled while the rest of the system stays up.

That modular split is not adopted for the MVP, for two reasons already established elsewhere rather than invented here:

1. **The PRD's first functional requirement is the GitHub webhook trigger** (`PRD.md`: "SentinelAI reacts to a GitHub PR event... via webhook") — this is not one flow among several equally-weighted options, it is the primary product goal the MVP exists to deliver.
2. **Every DevSecOps-facing capability already requires GitHub OAuth to authenticate** (this conversation's authentication decision, reflected in `API_Contract.md`). Even a DevSecOps user who only ever intends to run Mode B ad hoc scans (UC-2, no PR involved) still cannot reach `POST /analyses` without first completing GitHub OAuth login. There is no capability in the current MVP, including Mode B, that is reachable without GitHub being available in some form.

Given both, splitting `GITHUB_TOKEN` out as independently optional would let the application start in a state where the primary flow is silently disabled while still requiring the same vendor for the only way to notice — a partial-availability mode with no actual independent use case behind it yet. Should a future requirement emerge for SentinelAI to run in a GitHub-free mode (e.g., a different Git provider, or an operator that only ever uses ad hoc scans through a non-OAuth auth mechanism), that would be a new product decision belonging in `09_Decisions`, not a startup-flag change made here without one.
