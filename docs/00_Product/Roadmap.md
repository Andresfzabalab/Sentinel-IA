# Roadmap

## Why this document exists
Sequences the work so that documentation, architecture, research and implementation happen in the right order (`Documentation First → Architecture Before Code → Security by Design → Research Driven Engineering`), and shows how MVP grows into the full vision without contradicting today's boundaries.

## Phase 0.5 — Documentation & Architecture (current)
- `00_Product`, `01_Architecture`, `02_Domain` (this regeneration, with section 18 corrections applied).
- Remaining folders: `03_API`, `04_Data`, `05_Security`, `06_Development`, `07_Operations`, `08_Engineering_Research`, `09_Decisions`, `10_Future`, `11_Engineering`, `12_Quality`.
- No implementation code before this phase closes.

## Phase 1 — MVP core (single artifact type, single scanner, walking skeleton)
- Analysis Orchestrator (thin), one scanner adapter (e.g., Semgrep for Python), Risk Engine, Policy Engine, SQLite persistence, GitHub webhook trigger, GitHub status check output.
- Goal: prove the full pipeline end-to-end before adding scanner breadth.

## Phase 2 — MVP breadth
- Add remaining scanners (Bandit, Trivy, Gitleaks, Checkov) and artifact types (containers, K8s manifests, Terraform, GitHub Actions, SCA manifests).
- Add AI enrichment via `AIProviderPort` (Ollama first, then one API provider).
- Add full reporting (Markdown/SARIF/JSON/HTML) and audit trail.

## Phase 3 — Productionization
- PostgreSQL as an alternative to SQLite for persistence at scale.
- Observability (structured logs, metrics, tracing).
- CI/CD pipeline for SentinelAI itself.
- License/token-gated execution for protected capabilities (see `Handoff` section 6), without coupling the architecture to the licensing mechanism.

## Phase 4 — Future vision (not committed, not designed yet)
- Conditional DAST against ephemeral environments.
- AI-assisted pentesting workflows.
- Multi-repository / organization-wide risk dashboards.
- Notification integrations beyond GitHub (Slack, Teams, email, webhooks).

## Roadmap discipline
No phase begins before the previous phase's documentation exists and the walking skeleton (Phase 1) proves the architecture end-to-end. Scope for later phases is intentionally left thin here; it gets its own design work in `10_Future` when it becomes near-term.
