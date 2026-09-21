# MVP

## Why this document exists
Defines exactly what ships first, so architecture and domain design don't over-build for scope that isn't real yet.

## MVP scope: Pull Request Security Review

### In scope
| Artifact type | Analysis | Example tool (candidate, see `Technology_Strategy.md`) |
|---|---|---|
| Python, Java, JS/TS source | SAST | Semgrep, Bandit |
| Dockerfile, docker-compose | Container security | Trivy, Checkov |
| Kubernetes YAML, Helm | K8s/IaC security (static, PR-scoped) | Checkov, Kubesec |
| Terraform | IaC security | Checkov, tfsec |
| GitHub Actions workflows | Pipeline security | Semgrep, actionlint-style checks |
| requirements.txt, package.json | SCA (dependency vulnerabilities) | Trivy, pip-audit |
| Any modified file | Secret scanning | Gitleaks |

### Explicitly out of scope for MVP
- **Full cluster Kubernetes analysis** — only static analysis of manifests modified in the PR; no live-cluster introspection.
- **DAST** — deferred to future vision, triggered conditionally only once ephemeral environments exist.
- **Pentesting** — future vision only.
- **Multi-repo / organization dashboards** — single repository, single PR flow first.

## MVP pipeline (high level)
See `Security_Decision_Flow.md` for the authoritative version. Summary: PR event → artifact classification → parallel scanners (independent processes) → normalization → correlation (Analysis domain) → AI enrichment (advisory, Ollama or API) → Risk Engine (deterministic) → Policy Engine (deterministic, PASS/BLOCK) → GitHub status + report → audit record.

## MVP actors
- Developer interacts only through GitHub.
- DevSecOps configures scanners, AI provider, and policy; views full reports and the audit trail.

## MVP success condition
A DevSecOps engineer can point SentinelAI at a real GitHub repository, define one policy (e.g., "block on any critical secret or high-severity SAST finding"), open a PR with a deliberately introduced vulnerability, and see: the PR blocked, an explained finding, a remediation suggestion, and a corresponding audit entry — using either a local Ollama model or an API provider, interchangeably, via configuration.
