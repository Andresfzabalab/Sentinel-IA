# Objectives

## Why this document exists
Translates the Vision and Mission into concrete, checkable objectives, including the hardware and engineering constraints that shape every later architecture decision.

## Product objectives
1. Analyze a real Pull Request end-to-end (fetch → classify → scan → normalize → correlate → AI-enrich → risk-assess → policy-evaluate → report → audit) for at least Python, a Dockerfile, and a GitHub Actions workflow.
2. Support at least one local AI provider (Ollama) and one API provider (OpenAI, Claude, or Gemini) behind the same `AIProviderPort`, switchable via configuration only.
3. Guarantee that no code path allows the AI to set the PASS/BLOCK verdict — enforced structurally (Policy Engine is the only producer of the verdict) and verified by tests (see `Architecture_Principles.md`).
4. Produce a full audit trail for every analysis run.

## Engineering objectives
- Demonstrate hexagonal architecture with clean port/adapter boundaries between all 10 bounded contexts.
- Demonstrate Domain-Driven Design: bounded contexts, aggregates, domain events, ubiquitous language.
- Demonstrate professional engineering practice: testing (unit/integration/contract), CI/CD, observability, documentation-first process, and explicit architecture decision records.
- Serve as a technical portfolio for AppSec / DevSecOps / Security Engineering / Security Automation / AI Security / Software Architecture / Python Backend roles.

## Hardware and engineering constraints
| Constraint | Implication |
|---|---|
| Intel i7 8th-gen, 16GB RAM, no dedicated GPU, mechanical HDD | Cannot assume GPU-accelerated inference; must default to small/quantized local models or API providers; I/O-heavy operations (scanner subprocesses, SQLite) must account for HDD latency, not SSD speed |
| Single developer, part-time | Documentation and architecture must stay pragmatic (3 well-argued pages beats 20 padded ones); avoid speculative generality that isn't justified by a near-term requirement |
| Portfolio requirement | Every non-obvious decision needs a rationale that survives an interview question, not just a working implementation |

## Definition of "done" for an objective
An objective is done when it is: implemented, tested, documented (what/why/impact), and demonstrable end-to-end — not merely coded.
