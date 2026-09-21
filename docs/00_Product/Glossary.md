# Glossary

## Why this document exists
Establishes the ubiquitous language used consistently across product, architecture and domain documents. If a term used elsewhere isn't here, add it here first.

| Term | Definition |
|---|---|
| **Artifact** | A file or file type changed in a Pull Request that SentinelAI can classify and analyze (source file, Dockerfile, K8s manifest, Terraform file, GitHub Actions workflow, dependency manifest). |
| **Scanner** | An external tool (Semgrep, Bandit, Trivy, Gitleaks, Checkov, ...) executed as an independent process to analyze one or more artifact types. |
| **NormalizedFinding** | The common data model that every scanner adapter must translate its native output into. No component downstream of the Scanner context ever sees a scanner's native format. |
| **Correlation** | The act of grouping related findings (duplicates across scanners, chains of related issues) into a coherent picture. This is Analysis domain logic, not AI logic. |
| **AI Enrichment** | The advisory-only process by which the AI context deduplicates, explains, and suggests remediation for findings. Never produces a PASS/BLOCK verdict. |
| **Risk Assessment** | Deterministic, heuristic-based adjustment of finding severity based on context (path patterns, artifact type, correlation density). No AI involved. |
| **Policy Evaluation** | Deterministic evaluation of DevSecOps-configured rules and thresholds against risk-assessed findings, producing the PASS/BLOCK verdict. The only source of that verdict. |
| **Port** | A domain-defined interface (e.g., `RepositoryPort`, `ScannerPort`, `AIProviderPort`, `RiskAssessmentPort`, `PolicyPort`) that the Analysis Orchestrator calls without knowing the concrete adapter behind it. |
| **Adapter** | A concrete implementation of a port (e.g., a Semgrep adapter implementing part of `ScannerPort`, an Ollama adapter implementing `AIProviderPort`). |
| **Analysis Orchestrator** | The thin coordinator that drives one PR analysis from start to finish by calling ports in sequence. Contains no business logic beyond artifact classification and finding correlation. |
| **Bounded Context** | A DDD boundary with its own model, language and responsibility. SentinelAI has 10: Identity, Repository, Analysis, Scanner, AI, Risk, Policy, Reporting, Audit, Notification. |
| **In-process component** | A component that runs inside SentinelAI's own Python process and fails together with it (e.g., the Orchestrator, Risk Engine, Policy Engine). |
| **Independent process** | A component that runs outside SentinelAI's process and can fail without taking the rest of the system down (e.g., a scanner subprocess, the Ollama runtime). |
| **DevSecOps** | The persona with direct, configuration-level access to SentinelAI. See `Personas.md`. |
| **Developer** | The persona who interacts with SentinelAI only indirectly, through GitHub. See `Personas.md`. |
