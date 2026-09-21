# Input/Output Model

## Why this document exists
Catalogs every significant data input and output in the system along with its sensitivity, so `05_Security` and `04_Data` have a concrete inventory to design controls and schemas against.

## Inputs
| Input | Source | Sensitivity | Notes |
|---|---|---|---|
| GitHub webhook payload (PR opened/synchronize) | GitHub | Medium — contains repo metadata, no secrets expected but must be signature-verified | Entry point to the whole pipeline |
| PR diff / changed files | GitHub API (via Repository Port) | Medium–High — may contain source code, config, occasionally accidental secrets | Fed to artifact classification and scanners |
| Scanner native output | Scanner subprocess (Semgrep, Bandit, Trivy, Gitleaks, Checkov, ...) | Medium — may contain file paths, code snippets, and (for Gitleaks) actual detected secret values | Must be normalized; secret values require special handling (redaction in reports, secure storage) |
| AI provider response | Ollama (local) or API provider (OpenAI/Claude/Gemini) | Low–Medium — advisory text; treated as untrusted, non-executable | Never parsed as instructions or as a verdict |
| DevSecOps configuration | DevSecOps (Identity-authenticated) | High — governs scanner selection, AI provider, policy thresholds | Changes must themselves be audited |
| Policy rules | DevSecOps | High — directly determines PASS/BLOCK | Versioned, part of the audit trail |

## Outputs
| Output | Destination | Sensitivity | Notes |
|---|---|---|---|
| GitHub status check (PASS/BLOCK) | GitHub → Developer | Low | No finding detail, just the verdict |
| Inline PR comments | GitHub → Developer | Medium | Finding explanation + remediation, scoped to relevant lines; no full secret values displayed |
| Summary PR comment | GitHub → Developer | Medium | Aggregated, non-sensitive overview |
| Full analysis report (Markdown/SARIF/JSON/HTML) | SentinelAI → DevSecOps | High | Full finding detail; SARIF enables tool interoperability |
| Audit record | SentinelAI → Audit context (immutable store) | High | Who/when/what/result/policy-version for every run and every config/policy change |
| Notifications | SentinelAI → Slack/Teams/email/webhooks (near-term) | Medium–High depending on channel | Must respect the same redaction rules as PR comments |

## Redaction rule (cross-cutting)
Any output visible to the Developer persona (status check, inline/summary comments) must never contain a raw detected secret value — only its location and type. Full detail, if ever needed, is DevSecOps-only and behind the Reporting/Audit access boundary.

## What this document conditions
`04_Data` must design the `NormalizedFinding` schema and persistence model to carry a sensitivity/redaction flag per field, not just a severity field.
