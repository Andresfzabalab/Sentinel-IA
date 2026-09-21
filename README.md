# SentinelAI

**AI-Assisted Application Security Platform for Pull Request Analysis**

SentinelAI is a vendor-agnostic security platform that integrates into the software development lifecycle at the Pull Request level. It analyzes code changes, infrastructure definitions, container configurations, dependency manifests, and pipeline definitions to identify security issues before they reach production.

Unlike traditional SAST-only tools, SentinelAI treats a Pull Request as a collection of heterogeneous artifacts — each requiring a different security analysis strategy. It orchestrates multiple specialized scanners, correlates their findings, and uses AI reasoning to deduplicate, prioritize, explain, and recommend remediations.

## What This Project Is

An independent engineering project developed, researched, and maintained by one engineer following professional engineering practices. It is designed as a production-grade SaaS platform, not a prototype or proof of concept.

## Current Phase

**Phase 0.5 — Engineering Foundation**

The project is in its documentation and architecture design phase. No implementation code exists yet. The goal is to fully define what we are building, why, how it will work, what technologies we need, and how it will evolve — before writing any application code.

## Documentation

All project documentation lives under `docs/` and is organized by concern:

| Folder | Purpose |
|---|---|
| `00_Product` | What we are building, for whom, and why |
| `01_Architecture` | System architecture, patterns, deployment strategy |
| `02_Domain` | Domain model, bounded contexts, entities, events |
| `03_API` | REST API design, endpoints, authentication, webhooks |
| `04_Data` | Database design, persistence strategy, caching |
| `05_Security` | How SentinelAI itself is secured (not client findings) |
| `06_Development` | Coding standards, Git workflow, testing strategy |
| `07_Operations` | CI/CD, logging, monitoring, deployment |
| `08_Engineering_Research` | Technology investigations and evaluations |
| `09_Decisions` | Architecture Decision Records (ADRs) |
| `10_Future` | Ideas beyond the current scope |
| `11_Engineering` | Development process, patterns, checklists |
| `12_Quality` | Quality gates, acceptance criteria, technical debt |
| `99_Meetings` | Session logs and progress tracking |

## Philosophy

```
Documentation First → Architecture Before Code → Security by Design → Research Driven Engineering
```

Every document exists to explain a decision, guide an implementation, serve as a future reference, justify a technical choice, or prevent repeating a research effort. Nothing exists simply to fill a folder.

## License

Apache License 2.0 (tentative — subject to review before formal publication).

## Hardware Constraints

The initial development environment has no dedicated GPU, 16 GB RAM, and a mechanical HDD. The architecture is designed to work within these constraints: no dependency on large local models, API-first AI integration with local model support via lightweight runtimes like Ollama.
