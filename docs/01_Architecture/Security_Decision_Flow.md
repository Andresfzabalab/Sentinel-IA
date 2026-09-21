# Security Decision Flow

## Why this document exists
This is the authoritative, detailed version of the pipeline sketched in `Architecture_Overview.md` and used across every other document. It exists specifically to make the AI-advisory / deterministic-policy split (section 18 of the project handoff) unambiguous and traceable step by step.

## Full flow
```
1. Scanner Findings (Raw)
   Each scanner (Semgrep, Bandit, Trivy, Gitleaks, Checkov, ...) produces output
   in its own unique native format. No two scanners share a schema.

2. Normalization
   Each scanner's adapter (Scanner context) translates its native format into
   the single common NormalizedFinding model. No component downstream ever
   sees native scanner output. (P-05)

3. Correlation
   The Analysis Orchestrator groups related NormalizedFindings — duplicates
   across scanners, chains of related issues — into correlated findings.
   This is Analysis-domain logic, owned by the Orchestrator's correlation
   responsibility, NOT by the AI context. The FindingsCorrelated event is
   produced by the Analysis Domain. (corrects prior mis-attribution to AI)

4. AI Engine — ADVISORY ONLY
   The AI context (via AIPort) receives correlated findings and may:
     - deduplicate noisy/near-identical findings for readability
     - explain each finding in plain language
     - suggest remediation
   The AI context MUST NOT emit, influence, or be consulted for a PASS/BLOCK
   verdict. Its output schema structurally has no verdict field. (P-02)

5. Risk Engine — DETERMINISTIC
   Adjusts each correlated finding's severity based on configurable
   heuristics: path patterns, artifact type, correlation density.
   Given the same inputs and configuration, always produces the same
   output. No AI call. (P-03)

6. Policy Engine — DETERMINISTIC
   Evaluates DevSecOps-configured rules and thresholds against the
   risk-assessed findings. This is the ONLY step that produces PASS or
   BLOCK. Rules are versioned and human-authored. (P-04)

7. Result Generation
   - Developer view → GitHub PR status check + inline comments + summary
     comment (see Input_Output_Model.md for redaction rules)
   - DevSecOps view → full report (Markdown/SARIF/JSON/HTML)

8. Audit Recording
   Every run's findings, risk scores, policy version, rule(s) applied, and
   final verdict are recorded immutably in the Audit context.
```

## Why AI sits between Correlation and Risk, not after Policy
AI enrichment must happen before Risk/Policy so that explanations and remediation suggestions are available in the final report — but it must structurally be impossible for AI output to feed back into the verdict. Placing Risk and Policy as the only two steps with write access to "severity" and "verdict" fields respectively, with AI's output type excluding both, enforces this independent of where AI sits in the sequence.

## Failure handling within this flow
- If a scanner fails (step 1–2): the Orchestrator proceeds with the remaining scanners' NormalizedFindings; the gap is recorded (QA-03).
- If the AI provider fails or times out (step 4): the flow proceeds directly from Correlation to Risk with no enrichment; findings are still reported without AI explanations (QA-04).
- Risk (step 5) and Policy (step 6) never degrade — they are in-process, deterministic, and have no external dependency that could fail this way.

## Relationship to other documents
This flow is the ground truth referenced by `Analysis_Lifecycle.md` (12-stage breakdown), `Finding_Lifecycle.md` (per-finding transformations), and `Domain_Events.md` (events emitted at each step).
