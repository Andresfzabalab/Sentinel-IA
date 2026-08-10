# SentinelAI

> **Intelligent Application Security Review Platform**

## Vision

SentinelAI is an AI-powered SaaS platform designed to improve
application security by analyzing Pull Requests before code reaches
production.

Instead of relying on a single security scanner or language model,
SentinelAI orchestrates multiple specialized security engines (SAST,
SCA, Secret Scanning, Infrastructure as Code analysis, Container
Security, Pipeline Security and future DAST capabilities) and combines
their findings through an intelligent reasoning engine.

The platform provides contextual risk analysis, explains vulnerabilities
in natural language, recommends secure remediations and integrates
directly into the software development lifecycle.

## Mission

Build an extensible, vendor-agnostic Application Security platform
capable of helping development teams deliver secure software through
automated, contextual and explainable security reviews.

## Long-term Goals

-   Analyze Pull Requests automatically.
-   Support multiple Git providers.
-   Support multiple AI providers.
-   Remain independent of any specific scanner.
-   Provide explainable security recommendations.
-   Generate enterprise-grade reports.
-   Become a modular AppSec platform ready for SaaS deployment.

## Core Principles

-   Product-first mindset.
-   Clean and maintainable architecture.
-   Domain-Driven Design.
-   Hexagonal Architecture.
-   Security by Design.
-   Vendor independence.
-   Automation first.
-   Documentation as a first-class artifact.
-   Testability and observability by default.

## Project Status

Current Phase:

**Architecture & Product Design**

At this stage the project is intentionally focused on documentation,
architecture, domain modeling and engineering decisions before
implementation begins.

## Repository Structure

The repository will evolve around five major areas:

``` text
docs/      -> Product, Architecture and Engineering documentation
src/       -> Application source code
tests/     -> Automated tests
tools/     -> Development and automation utilities
.github/   -> CI/CD workflows
```

## Documentation Philosophy

Every important engineering decision will be documented before
implementation.

The documentation is considered part of the product itself, not an
afterthought.

## License

To be defined.
