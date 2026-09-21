# Mission

## Why this document exists
Vision describes the destination; this document describes what SentinelAI does today, concretely, to move toward it.

## Mission Statement
Build a vendor-agnostic AI Application Security platform that analyzes Pull Requests, correlates findings from multiple security scanners, uses AI strictly as an advisory layer to explain and suggest remediation, and enforces merge decisions through a deterministic, auditable policy engine.

## What "vendor-agnostic" means in practice
- **AI provider independence**: works with local models via Ollama (Qwen, DeepSeek Coder) or API providers (OpenAI, Claude, Gemini) through a common `AIProviderPort`.
- **Git provider independence**: GitHub first, but the `RepositoryPort` abstraction must not leak GitHub-specific concepts into the domain.
- **Scanner independence**: each scanner (Semgrep, Bandit, Trivy, Gitleaks, Checkov, ...) is wrapped by an adapter that normalizes its unique output format into a single `NormalizedFinding` model — no downstream component ever sees native scanner output.

## Day-to-day mission
For every Pull Request that triggers an analysis, SentinelAI must:
1. Classify the modified artifacts (source code, Dockerfiles, Kubernetes/Helm manifests, Terraform, GitHub Actions workflows, dependency manifests).
2. Run the relevant scanners as independent, isolatable processes.
3. Normalize and correlate their findings.
4. Enrich findings with AI-generated explanations and remediation suggestions — advisory only.
5. Assess contextual severity deterministically (Risk Engine).
6. Evaluate DevSecOps-defined policy rules deterministically to produce PASS/BLOCK.
7. Report results back to the developer (status check, inline/summary comments) and to DevSecOps (full report, audit trail).

## Non-negotiables tied to the mission
- The AI never decides PASS/BLOCK — only Policy does, and Policy is 100% deterministic and configured by a human.
- A scanner crash must not take down the whole analysis (independent process failure).
- A slow or unavailable AI provider must degrade the analysis gracefully, not block it.
