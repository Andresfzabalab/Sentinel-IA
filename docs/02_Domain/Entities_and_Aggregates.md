# Entities and Aggregates

## Why this document exists
Names the concrete types per bounded context and their invariants — the level of detail needed before writing any domain code.

## Identity
- **User** (entity) — id, email, role. Invariant: must belong to exactly one Organization.
- **Organization** (aggregate root) — id, name, members. Invariant: must have at least one DevSecOps-role member.
- **Role** (value object) — Developer | DevSecOps.

## Repository
- **Repository** (aggregate root) — id, provider (GitHub, ...), full name, default branch.
- **PullRequest** (entity, within Repository aggregate) — id, number, source/target branch, changed files, status. Invariant: must reference a valid Repository.
- **Commit** (entity) — sha, author, changed files.

## Analysis
- **AnalysisRun** (aggregate root) — id, PullRequest reference, status (pending/running/completed/degraded), timestamps. Invariant: exactly one AnalysisRun is active per PR revision.
- **ArtifactClassification** (value object) — file path → artifact type mapping (source, Dockerfile, K8s manifest, Terraform, GitHub Actions, dependency manifest).
- **CorrelatedFinding** (entity, within AnalysisRun) — groups one or more NormalizedFindings that refer to the same underlying issue. Invariant: must reference at least one NormalizedFinding.

## Scanner
- **ScanRequest** (value object) — artifact type, target files, scanner id.
- **NormalizedFinding** (entity) — id, scanner source, artifact path, rule id, severity (raw), description, location (line/column when available). Invariant: must never contain scanner-native format fields — only the common schema.

## AI
- **EnrichmentRequest** (value object) — CorrelatedFinding reference, context needed for explanation.
- **EnrichmentResult** (entity) — explanation text, remediation suggestion, deduplication flag. Invariant: structurally has no verdict/pass-fail field (P-02).

## Risk
- **RiskAssessment** (entity) — CorrelatedFinding reference, contextual severity, contributing heuristics list. Invariant: deterministic function of (finding, artifact context, configuration) — no randomness, no AI input.

## Policy
- **PolicyRule** (entity) — id, condition (e.g., "severity >= high AND artifact_type == secret"), action (BLOCK/PASS/WARN).
- **PolicyVersion** (aggregate root) — ordered set of PolicyRules, effective timestamp. Invariant: immutable once published; changes create a new version.
- **Verdict** (value object) — PASS | BLOCK, plus the PolicyRule id(s) and PolicyVersion that produced it. Invariant: only ever produced by the Policy context.

## Reporting
- **Report** (entity) — AnalysisRun reference, format (Markdown/SARIF/JSON/HTML), content, audience (Developer/DevSecOps).

## Audit
- **AuditRecord** (aggregate root, append-only) — AnalysisRun reference, actor, timestamp, findings snapshot, RiskAssessment snapshot, PolicyVersion used, Verdict, action taken. Invariant: immutable after creation.

## Notification
- **NotificationRequest** (value object) — AnalysisRun reference, channel, payload, delivery status.

## Cross-context invariant
A `Verdict` (Policy) may only be attached to an `AuditRecord` alongside the exact `PolicyVersion` and `RiskAssessment` snapshot that produced it — never a live/current reference that could change retroactively. This is what makes QA-01 (auditability) hold over time.
