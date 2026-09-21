# Finding Lifecycle

## Why this document exists
Traces a single finding through its 7 transformations from raw scanner output to its final resting place in a report and the audit trail — the most granular view in `02_Domain`, useful for designing the actual data model in `04_Data`.

## The 7 transformations

### 1. Raw finding (scanner-native format)
Produced by a scanner tool in its own unique schema (Semgrep JSON, Bandit JSON, Trivy JSON, Gitleaks JSON, Checkov JSON, ...). Exists only inside the Scanner context's adapter boundary.

### 2. NormalizedFinding
The scanner's adapter translates the raw finding into the common schema: scanner source, artifact path, rule id, raw severity, description, location. This is the only form any component outside the Scanner context is allowed to see (P-05).

### 3. CorrelatedFinding
The Analysis context's `FindingCorrelator` groups one or more NormalizedFindings referring to the same underlying issue (e.g., the same secret flagged by two tools, or a chain of related misconfigurations) into a single CorrelatedFinding. Produced as part of the `FindingsCorrelated` event (owned by Analysis — see `Domain_Events.md`).

### 4. Enriched finding
The AI context attaches an `EnrichmentResult` (explanation, remediation suggestion, deduplication flag) to the CorrelatedFinding. Advisory only — this transformation adds explanatory text, it never changes severity or produces a verdict (P-02). This step may be skipped entirely under AI degradation (QA-04), in which case the finding proceeds without step 4's content.

### 5. Risk-assessed finding
The Risk context attaches a `RiskAssessment` (contextual severity, contributing heuristics) to the CorrelatedFinding, deterministically, independent of whether step 4 occurred (P-03).

### 6. Policy-evaluated finding
The Policy context evaluates the risk-assessed finding against the active PolicyVersion's rules, contributing to the overall AnalysisRun's Verdict (PASS/BLOCK) alongside all other findings in the run (P-04).

### 7. Reported / audited finding
The finding's final state is rendered into:
- A **Developer-facing** form (inline PR comment: type, location, plain-language explanation if available, remediation if available — no raw secret values).
- A **DevSecOps-facing** form (full report entry: all of the above plus raw severity, all correlated NormalizedFindings, RiskAssessment detail).
- An **Audit** entry (immutable snapshot of the finding as it stood when the Verdict was produced).

## Invariant across all 7 stages
A finding's identity (its correlation group) is stable from stage 3 onward — enrichment, risk assessment, and policy evaluation all attach data to the same CorrelatedFinding id rather than creating new, disconnected records. This is what lets the Audit context reconstruct "why was this specific finding treated this way" (QA-01) without reassembling data from multiple unrelated tables.

## What can be skipped, and what cannot
| Stage | Can be skipped? |
|---|---|
| 1–3 (raw → normalized → correlated) | No |
| 4 (enrichment) | Yes, under AI degradation |
| 5 (risk) | No |
| 6 (policy) | No |
| 7 (reporting/audit) | Reporting to external channels can partially fail; the Audit entry cannot be skipped |
