# Success Metrics

## Why this document exists
Defines how we will know SentinelAI's MVP works — as an engineering system and as a portfolio artifact — rather than relying on subjective judgment.

## Functional success metrics (MVP)
| Metric | Target |
|---|---|
| End-to-end PR analysis completes | For a PR touching Python, Dockerfile, and GitHub Actions files, all applicable scanners run and report to a single correlated result |
| Scanner isolation | A crashed/killed scanner subprocess does not abort the overall analysis; the run completes with a partial-results note |
| AI degradation | With the AI provider unreachable, the analysis still completes and reaches a PASS/BLOCK verdict, without AI-generated explanations |
| Determinism of verdict | Given the same findings and the same policy configuration, PASS/BLOCK is identical across repeated runs, regardless of AI provider used |
| Provider swap | Switching from Ollama to an API provider (or vice versa) requires only configuration changes, no code changes |
| Auditability | Every analysis run produces an immutable audit record containing who/when/what/result and the exact policy rule(s) that produced the verdict |

## Engineering quality metrics
- Test coverage on domain logic (Analysis, Risk, Policy) meaningfully higher than on adapters (per `Quality_Attributes.md`).
- Architecture boundary violations (e.g., domain importing an adapter) caught by static checks or violation tests (see `Architecture_Principles.md`).
- Documentation exists and is current for every bounded context before its implementation is merged.

## Portfolio success metrics
- The project can be explained end-to-end in an interview using only its own documentation: problem, architecture rationale, trade-offs, and what would change at 10x scale.
- At least one Architecture Decision Record (`09_Decisions`) documents a real trade-off made and rejected alternatives, not just the chosen option.

## Explicit non-metrics
- Number of scanners integrated is not a success metric by itself — correctness, correlation quality, and auditability matter more than breadth.
- Model size or "AI sophistication" is not a success metric — the AI is advisory and replaceable by design.
