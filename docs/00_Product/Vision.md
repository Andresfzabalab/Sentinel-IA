# Vision

## Why this document exists
This document explains the long-term direction of SentinelAI so that every architecture and implementation decision can be checked against a single question: *does this move us toward the vision?*

## Vision Statement
SentinelAI becomes the security reviewer every Pull Request deserves but rarely gets: a vendor-agnostic, AI-assisted analysis layer that reasons over SAST, SCA, secrets, container, Kubernetes, IaC and pipeline findings, explains them in plain language, and lets a human-defined policy — never the AI — decide whether code is safe to merge.

## The problem
Security review of Pull Requests today is either:
- **Absent** — small teams and independent developers ship without automated review beyond a linter.
- **Fragmented** — a dozen scanners each speak a different format (Semgrep, Bandit, Trivy, Gitleaks, Checkov...), with no correlation between them and no unified narrative for the developer.
- **Opaque** — findings arrive as raw JSON or CLI output, with no explanation of *why it matters here* or *how to fix it*, so developers ignore them.
- **Vendor-locked** — commercial platforms tie teams to one AI provider or one Git provider, and rarely explain their reasoning.

## Why now
LLMs are finally good enough to explain and correlate security findings in natural language without needing to be trusted with the actual pass/fail decision — that decision can and should stay deterministic. This split (AI advisory, policy deterministic) is what makes an AI-assisted security tool auditable enough to be taken seriously by a DevSecOps team, and it is the central bet of this project.

## What SentinelAI is not
- Not a replacement for a human security engineer.
- Not a decision-maker: the AI never determines PASS/BLOCK (see `Security_Decision_Flow.md`).
- Not a full DAST or pentesting platform in its MVP — those are future scope.
- Not a "run a giant local LLM" project — it must run on modest hardware (8th-gen i7, 16GB RAM, no GPU) or against external AI APIs.

## Long-term direction (beyond MVP)
1. Pull Request analysis (SAST, SCA, IaC, container, secrets, pipeline) — MVP scope.
2. Conditional DAST against ephemeral environments when a PR touches an API/web surface.
3. AI-assisted pentesting workflows.
4. Organization-wide risk dashboards and trend analysis across repositories.

## What this document conditions
Every subsequent document — MVP scope, architecture boundaries, bounded contexts — must trace back to this vision. If a proposed feature doesn't serve "help developers ship secure software faster while keeping the merge decision deterministic and auditable," it doesn't belong in the near-term roadmap.
