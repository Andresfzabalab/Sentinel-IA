# Technology Strategy

## Why this document exists
Lists technology candidates and the criteria for choosing them, without prematurely locking decisions that need dedicated research (`08_Engineering_Research`) or a formal ADR (`09_Decisions`). Per the project's core rule: *technology must respond to a product need, not the other way around.*

## Selection criteria (applied to every candidate below)
1. Runs acceptably on the reference hardware (no GPU, 16GB RAM, mechanical HDD).
2. Does not force coupling between the domain and a specific vendor (P-06/P-07/P-08).
3. Has an active community/maintenance status (avoid abandoned tooling for a portfolio project).
4. Reasonable to operate and debug by a single engineer.

## Language & runtime
- **Python** — chosen for AppSec tooling ecosystem maturity (most scanners are Python-friendly or CLI-wrappable) and for aligning with the "Python Backend Engineering" portfolio goal. Alternatives not seriously considered given the explicit portfolio target.

## Scanners (candidates, pending confirmation in `08_Engineering_Research`)
| Category | Candidate | Notes |
|---|---|---|
| SAST | Semgrep, Bandit | Semgrep for multi-language, Bandit as Python-specific complement |
| SCA | Trivy, pip-audit | Trivy covers containers + dependencies in one tool |
| Container | Trivy | Also covers image vulnerabilities |
| IaC / Kubernetes | Checkov, tfsec, Kubesec | Checkov has broad multi-framework coverage |
| Secrets | Gitleaks | De facto standard, fast, low false-positive baseline |
| Pipeline (GitHub Actions) | Semgrep custom rules / actionlint-style checks | Needs dedicated research — no clear single leader yet |

## AI providers
- **Local**: Ollama running Qwen or DeepSeek Coder — chosen for running acceptably on CPU-only hardware with quantized models.
- **API**: OpenAI, Claude, Gemini — behind the same `AIProviderPort`; no provider is architecturally privileged.

## Persistence
- **MVP**: SQLite, in-process, file-based — zero operational overhead, fits single-operator local development, adequate for the modular monolith's data volume.
- **Phase 3+**: PostgreSQL as an independent process — reconsidered only when multi-instance or concurrent-write needs are real (see `Roadmap.md`).

## Web / API framework
- Candidate: FastAPI, for async support (useful given multiple concurrent external processes: scanners, AI calls) and strong typing alignment with the domain model. To be confirmed in `08_Engineering_Research` before locking in `09_Decisions`.

## CI/CD
- GitHub Actions — consistent with the target Git provider for MVP and directly demonstrates pipeline-security domain knowledge by dogfooding the same category of tool SentinelAI analyzes.

## What is deliberately left open
Framework choices for the API layer, the exact GitHub Actions security-check approach, and the observability stack are intentionally not finalized here — they require the research documented in `08_Engineering_Research` before becoming an ADR in `09_Decisions`.
