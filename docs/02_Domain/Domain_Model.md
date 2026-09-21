# Domain Model

## Why this document exists
Gives the top-level map of all 10 bounded contexts, how they relate, and the dependency rules between them — the entry point for `02_Domain` before the per-context detail in `Bounded_Contexts.md`.

## The 10 bounded contexts
| Context | Responsibility | Decision nature |
|---|---|---|
| Identity | Users, authentication, authorization, roles, organizations | Config/trust |
| Repository | Repositories, branches, commits, Pull Requests, Git integration | Data access |
| Analysis | THIN orchestration of the pipeline: classification, coordination, correlation | Coordination + minimal domain logic |
| Scanner | Executes external scanner tools, normalizes results | Adapter-heavy |
| AI | Interprets/enriches findings — ADVISORY ONLY, never decides PASS/BLOCK | Advisory |
| Risk | Contextual severity assessment — deterministic, heuristic-based | Deterministic |
| Policy | Corporate rules, thresholds, approval/rejection — DETERMINISTIC, decides PASS/BLOCK | Deterministic, decision-making |
| Reporting | Generates reports (Markdown, SARIF, JSON, HTML) | Presentation |
| Audit | Immutable record of who/when/what/result/decisions | Compliance |
| Notification | Delivers results to GitHub, Slack, Teams, email, webhooks | Delivery |

## Dependency rules (P-06, Domain independence)
- The **Analysis** context (Orchestrator) is the only context permitted to call all of: Repository, Scanner, AI, Risk, Policy ports, in sequence. It coordinates but does not own their logic.
- **Risk** must not depend on **AI** (P-03) — deterministic, no AI call.
- **Policy** must not depend on **AI** (P-04) — deterministic, no AI call.
- **Scanner** exposes only `NormalizedFinding` outward — no context outside Scanner may depend on a scanner's native format (P-05).
- **Reporting**, **Audit**, and **Notification** react to domain events published by other contexts (primarily Analysis, Risk, Policy) — they do not call back into the pipeline.
- **Identity** is depended upon by every context that needs authorization checks (chiefly Repository access and Policy/config changes by DevSecOps) but depends on nothing else.

## Relationship diagram (textual)
```
Identity ← (auth checks) ← Repository, Policy(config), Reporting, Audit(access)

Repository → Analysis (PR context)
Analysis → Scanner (select + run) → NormalizedFinding → Analysis (correlate)
Analysis → AI (advisory enrichment)
Analysis → Risk (deterministic severity)
Analysis → Risk-assessed findings → Policy (deterministic verdict)
Analysis/Policy → events → Reporting, Audit, Notification
```

## Why exactly 10 contexts (not fewer, not more)
- **Risk was split out as its own context** (correction from prior draft) rather than folded into Analysis or Policy, because it has its own ubiquitous language (heuristics, contextual severity) and its own determinism guarantee (P-03) that needs to be independently testable and auditable, separate from Policy's rule evaluation.
- **AI is a context of its own**, not a utility function inside Analysis, specifically to make its advisory-only boundary (P-02) a structural fact — it has its own port with an output type that cannot express a verdict.
- Contexts were not merged further (e.g., Reporting+Notification) because they have different consumers (DevSecOps/Developer vs. external channels) and different failure/versioning characteristics.

## What this document conditions
`Bounded_Contexts.md` details each context's internal model, ports, and boundary rules; `Domain_Events.md` lists exactly which events cross these boundaries.
