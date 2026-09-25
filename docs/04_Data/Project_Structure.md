# Project Structure

## Purpose

This document fixes the physical layout of the SentinelAI Python project: which directory holds which module, layer, or responsibility, and — more importantly — which import directions are allowed between them. Every rule here exists to make a decision already made elsewhere (module boundaries, hexagonal architecture, port/adapter separation) mechanically enforceable by where a file lives, not just by convention someone has to remember.

## Top-Level Layout

```
sentinel-ai/
├── src/
│   └── sentinel/
│       ├── core/                   # Sentinel Core module
│       ├── intelligence/           # Security Intelligence & Data Module
│       ├── ai_agent/               # AI & Agent Module
│       ├── infrastructure/         # Concrete adapters for every module's ports
│       ├── interfaces/             # Entry points: HTTP API, webhook receiver, CLI
│       └── shared/                 # Infrastructure-agnostic utilities only — see "The `shared/` Risk" below
├── tests/                          # Mirrors src/, plus integration/contract/e2e suites (Testing_Strategy.md)
├── scripts/                        # Operational scripts: migration runner, recovery-sweep trigger, dev bootstrap
├── configs/                        # Static, non-secret configuration (Configuration_and_Secrets.md)
├── docs/                           # This documentation set
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## `src/sentinel/core/` — Sentinel Core Module

```
core/
├── domain/
│   ├── analysis/        # Analysis Aggregate Root, Finding, ScannerExecution, Artifact/PullRequestSnapshot/Severity/Risk/
│   │                     # SecurityScore/Verdict VOs (value_objects.py) + entities.py (also owns Correlation -- Domain_Services.md)
│   ├── repository/      # Repository Aggregate Root
│   ├── policy/          # Policy Aggregate Root, PolicyVersion VO
│   ├── audit/           # AuditRecord Entity
│   ├── notification/    # Notification Entity
│   ├── services/        # The 5 pure Domain Services: artifact_classification, scanner_selection,
│   │                     # risk_assessment, security_score, policy_evaluation
│   └── exceptions.py    # Domain-level invariant violations (VerdictAlreadySet, DuplicatePolicyVersion, etc.)
├── application/
│   ├── analysis_orchestrator.py           # THE thin coordinator (P-01)
│   ├── analysis_write_queue.py            # Per-analysis_id serialization lock -- lives here, not infrastructure/,
│   │                                       # because it is pure in-process concurrency control with zero infra
│   │                                       # dependency; the Orchestrator (P-01/P-06) may depend on it directly
│   ├── repository_configuration_service.py # UC-3 (T-Repo) as a callable operation
│   ├── policy_publishing_service.py        # UC-4/UC-9 (T-Policy; suppression is just content in `rules`)
│   └── report_generation_service.py        # UC-5's Report projection (Security-Result-only until Phase 9/10 add AI Enrichment)
└── ports/                # repository_port.py, scanner_port.py, working_directory_port.py, risk_port.py,
                           # policy_port.py, event_bus_port.py, store_ports.py (AnalysisStore/RepositoryConfigStore/
                           # PolicyStore/AuditStore/NotificationStore -- interfaces only, implementations live in infrastructure/)
```

**On `AnalysisWriteQueue`'s location**: an earlier implementation pass placed this under `infrastructure/core/sqlite/` (reasoning: it exists to protect SQLite writes). That turned out to be a boundary violation waiting to happen -- the Orchestrator needs to use this lock directly around each scanner completion (Phase 6), and `core/application/` may never import `infrastructure/` (P-01/P-06's own violation test). Since the class itself only imports `threading` and has no actual SQLite dependency, the fix was to move it, not to add an exception to the rule.

`domain/` contains every Aggregate, Entity, and Value Object from `Entities_Value_Objects.md`, plus the pure Domain Services from `Domain_Services.md` (Artifact Classification, Scanner Selection, Risk Assessment, Security Score Calculation, Policy Evaluation). **Nothing in `domain/` imports anything from `infrastructure/`, `interfaces/`, or another module's `domain/`.** It may only import from its own `ports/` (the interfaces, never a concrete adapter) — this is what P-01 and P-06's violation tests actually check against in code.

## `src/sentinel/intelligence/` — Security Intelligence & Data Module

```
intelligence/
├── domain/       # SecurityKnowledgeBaseEntry — a data concept, not a domain Aggregate (Aggregates_and_Boundaries.md)
├── application/  # Knowledge Refresh Service (Application/Orchestration Service, per Domain_Services.md)
└── ports/        # SecurityIntelligenceSourcePort, KnowledgeBaseStore, SecurityKnowledgeBasePort (interfaces only)
```

## `src/sentinel/ai_agent/` — AI & Agent Module

```
ai_agent/
├── domain/        # AgentExecution Entity, AI Enrichment Value Object
├── application/   # Agent Execution Runner, Report Generation Service, AI Enrichment Service
├── agents/        # The Agent Execution Framework: Agent Registry, Tool Registry, guardrails/execution-limit enforcement,
│                  # and the Security Investigation Agent itself, registered as the framework's first agent
└── ports/         # AIProviderPort, AgentExecutionStore (interfaces only)
```

`agents/` exists as its own directory, separate from `application/`, because the Agent Execution Framework is reusable infrastructure for *any future agent* (`AI_Agent_Architecture.md` §4) — a second agent is added here, as a new file registered with the framework, without touching `application/`'s orchestration code.

## `src/sentinel/infrastructure/` — Every Concrete Adapter

```
infrastructure/
├── core/
│   ├── github/            # signature.py (webhook HMAC check), client.py (GitHubClient: PR files/status,
│   │                       # retry+backoff+rate-limit), oauth_client.py (GitHubOAuthClient -- a separate
│   │                       # credential/concern from client.py's PAT, per Configuration_and_Secrets.md),
│   │                       # repository_port_adapter.py (GitHubRepositoryPort)
│   ├── scanners/           # subprocess_runner.py + json_scanner_adapter.py (shared P-09/P-05 machinery),
│   │                       # semgrep.py/bandit.py/trivy.py/gitleaks.py/checkov.py (one parse_*_output function
│   │                       # each -- the P-05 boundary), composite_scanner_port.py (dispatches by scanner_id),
│   │                       # git_checkout_provider.py (WorkingDirectoryPort's real adapter, Phase 6)
│   └── sqlite/             # connection.py, schema.py, exceptions.py, plus one *_store.py (row/DTO-level) and
│                           # one *_store_adapter.py (domain-object-level, implements the core/ports/ Protocol)
│                           # per Aggregate: analysis, repository_config, policy, audit, notification;
│                           # session_store.py (Phase 8, no domain-facing adapter -- Session isn't an Aggregate)
├── ai_agent/
│   ├── providers/         # AIProviderPort implementations: ollama.py, openai.py, anthropic.py, gemini.py
│   └── sqlite/            # SqliteAgentExecutionStore
└── intelligence/
    ├── sources/           # SecurityIntelligenceSourcePort implementations, one per feed
    └── sqlite/            # SqliteKnowledgeBaseStore
```

This is the **only** place third-party infrastructure libraries are imported (the GitHub SDK/HTTP client, `sqlite3`, an AI provider's SDK, a scanner's CLI wrapper). `infrastructure/` may import from any module's `domain/` and `ports/` (to implement a port and to construct/return domain objects) but a module's `domain/` and `application/` never import back from `infrastructure/` — dependency inversion, enforced by directory structure. This is also where `Data_Model.md`'s "no SQL foreign key crosses a module boundary" and "single SQLite file, module ownership by table prefix" rules are physically implemented: `infrastructure/core/sqlite/`, `infrastructure/ai_agent/sqlite/`, and `infrastructure/intelligence/sqlite/` each open the same file but each only ever issues SQL against its own module's tables.

## `src/sentinel/interfaces/` — Entry Points

```
interfaces/
├── http/
│   ├── webhooks/      # github_webhook.py: POST /webhooks/github (GitHub_Integration.md) -- the product's primary entry point
│   ├── api/            # Implemented Phase 8: auth.py (login/callback/logout), analyses.py (POST/GET /analyses,
│   │                   # GET /analyses/{id}, GET /analyses/{id}/report), repositories.py, policies.py, audit.py
│   ├── middleware/     # auth.py: require_devsecops_session, a FastAPI dependency checked against the `session`
│   │                   # table (Identity's actual, simplified shape -- see Bounded_Contexts.md)
│   └── app.py          # create_app(): the FastAPI factory, registers every router above + the ApiError/HTTPException handler
├── cli/               # Not yet built. Still intended as a thin wrapper over the same api/ handlers, per the
│                       # confirmed decision that it must never precede or replace the webhook (C4_Container.md §10)
└── composition.py     # The composition root: wires every port to its concrete adapter at startup, per Configuration_and_Secrets.md's local execution gate
```

`interfaces/` is the only layer allowed to import from *every* module's `application/`, `ports/`, and `infrastructure/` — this is the composition root, where dependency injection actually happens. It contains no business logic of its own: an HTTP handler in `interfaces/http/` parses a request, calls into `application/`, and formats a response — nothing more.

## The `shared/` Risk

A `shared/` directory is tempting and easy to misuse — it can quietly become the backdoor that lets two modules couple without ever importing each other directly. Its contents are restricted to genuinely infrastructure-agnostic, side-effect-free utilities with **no domain concepts and no module-specific logic**: `correlationId` derivation (Mode A/B, per `Domain_Events.md`), JSON (de)serialization helpers, the structured-logging setup (`Observability_and_Logging.md`), and the error-envelope shape (`API_Contract.md`). If a proposed addition to `shared/` references `Analysis`, `Finding`, `Policy`, or any other domain concept, it does not belong there — it belongs in the owning module's `domain/`.

## Naming Convention Carried Over from `Ports_and_Interfaces.md`

No file, class, or directory anywhere in `src/sentinel/` is named `*Repository` for a persistence concern — `Repository` is reserved for the domain concept (`repository/` under `core/domain/`). Every persistence adapter is named `*Store` (`SqliteAnalysisStore`, not `AnalysisRepository`), exactly as `Ports_and_Interfaces.md` already requires at the port level; this section only confirms the same rule holds at the file-naming level, where the ambiguity would otherwise resurface.

## `tests/`, `scripts/`, `configs/`

- **`tests/`** mirrors `src/sentinel/`'s module structure (`tests/core/`, `tests/intelligence/`, `tests/ai_agent/`, `tests/infrastructure/`, `tests/interfaces/`), plus `tests/integration/`, `tests/contract/`, and `tests/e2e/` for cross-cutting suites — fully specified in `Testing_Strategy.md`.
- **`scripts/`** holds operational, run-once-by-a-human scripts: the migration runner (`Persistence_Strategy.md`), a manual trigger for the crash-recovery sweep, local developer setup, and the manual Knowledge Base refresh (`refresh_knowledge_base.py`, `AI_Agent_Architecture.md` §11) — the one deliberate, human-triggered point where SentinelAI reaches the public internet; nothing else in the running process ever does. Nothing here is imported by `src/sentinel/` — scripts call into the application layer, never the reverse.
- **`configs/`** holds static, non-secret configuration read at startup: default scanner timeouts, the artifact classification rule set, and which scanners exist system-wide (`Configuration_and_Secrets.md`'s "Scanner configuration" row). Nothing secret is ever placed here — see `Configuration_and_Secrets.md` for what belongs in `.env` instead.

## Import Direction Summary

```
interfaces/  ──────▶  application/ (any module)  ──────▶  domain/ (own module only)
     │                        │                                  │
     │                        ▼                                  ▼
     └──────────────▶  ports/ (own module)  ◀──────────────  domain/ depends on ports/, never on infrastructure/
                              ▲
                              │ implements
                     infrastructure/ (own module's ports)
```

Cross-module traffic is limited to exactly the ports already named as such in `Ports_and_Interfaces.md`: `SecurityResultQueryPort` and `SecurityKnowledgeBasePort` (both read-only) and `AuditRecorderPort` (write, restricted to Audit). No other import path between `core/`, `intelligence/`, and `ai_agent/` is permitted — this is the same rule `Module_Boundaries.md` states architecturally, made mechanically checkable here by directory boundary and, in CI, by an import-linter rule (`Architecture_Principles.md`'s own violation-test pattern for P-06).
