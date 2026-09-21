# Product Requirements Document (PRD)

## Why this document exists
This is the single reference for *what SentinelAI must do* before any architecture or code decision is made. It exists to prevent scope drift and to give architecture documents concrete requirements to satisfy.

## Problem statement
Developers open Pull Requests that may introduce vulnerabilities across source code, dependencies, containers, Kubernetes manifests, IaC, CI/CD pipelines and secrets. Today this review is manual, fragmented across tools, or skipped. SentinelAI must turn PR security review into an automated, explainable, policy-enforced step in the delivery pipeline.

## Target users
- **Developer**: opens PRs, needs fast, actionable, in-context feedback. Does not configure the system.
- **DevSecOps engineer**: owns configuration, policy thresholds, suppressions, and the audit trail. See `Personas.md`.

## Functional requirements (MVP)
1. **Trigger**: SentinelAI reacts to a GitHub PR event (opened, synchronize) via webhook.
2. **Artifact classification**: identify which files changed and their type (source, Dockerfile, K8s/Helm, Terraform, GitHub Actions, dependency manifest, arbitrary file for secret scanning).
3. **Scanning**: run the applicable scanners as independent processes per artifact type (see `MVP.md` for the scanner list).
4. **Normalization**: translate each scanner's native output into a common `NormalizedFinding` model.
5. **Correlation**: group related findings (e.g., same vulnerability reported by two tools, or a chain of related issues) — this is Analysis domain logic, not AI logic.
6. **AI enrichment (advisory only)**: deduplicate noisy findings, explain them in plain language, suggest remediation. Must never emit or influence a PASS/BLOCK verdict directly.
7. **Risk assessment (deterministic)**: adjust severity based on configurable heuristics (path patterns, artifact type, correlation density) — no AI involved.
8. **Policy evaluation (deterministic)**: apply DevSecOps-defined rules and thresholds to produce PASS or BLOCK.
9. **Reporting**: generate a GitHub status check, inline PR comments, a summary comment for the developer, and a full report (Markdown/SARIF/JSON/HTML) for DevSecOps.
10. **Audit**: record who/when/what/result for every analysis and every policy decision, immutably.
11. **Notification**: deliver results to GitHub at minimum; Slack/Teams/email/webhooks are near-term extensions.

## Non-functional requirements
- Must run on commodity hardware without a GPU (see `Objectives.md`).
- Must degrade gracefully if the AI provider is slow/unavailable (analysis continues without enrichment).
- Must survive individual scanner crashes without failing the whole pipeline.
- Must be auditable: every PASS/BLOCK decision must be traceable to a specific, versioned policy rule.
- Cross-platform: Windows, Linux, macOS for local development.

## Explicit non-goals (MVP)
- Full running Kubernetes cluster analysis (static PR-file analysis only).
- DAST execution.
- Automated pentesting.
- Multi-tenant SaaS billing/provisioning (single-operator deployment for MVP).

## Acceptance criteria for MVP
See `MVP.md` and `Success_Metrics.md`.
