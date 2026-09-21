# System Boundaries

## Why this document exists
Draws an explicit line around what SentinelAI owns versus what it depends on but does not control — a prerequisite for reasoning about trust boundaries and about what `05_Security` needs to protect.

## Inside the system
- All 10 bounded contexts and their domain logic (Identity, Repository, Analysis, Scanner, AI, Risk, Policy, Reporting, Audit, Notification).
- The in-process event bus and persistence adapters.
- Configuration of scanners, AI provider, Git integration, and policy (owned by DevSecOps, stored by SentinelAI).
- The audit trail.

## Outside the system (dependencies, not owned)
- **GitHub** (or future Git providers): source of PR events and destination for status checks/comments. SentinelAI trusts but does not control GitHub's availability or webhook delivery guarantees.
- **Scanner tools** (Semgrep, Bandit, Trivy, Gitleaks, Checkov, ...): external processes whose correctness SentinelAI depends on but does not implement. SentinelAI is responsible for normalizing their output, not for their detection accuracy.
- **AI providers** (Ollama runtime, OpenAI, Claude, Gemini): external inference sources. SentinelAI treats all AI output as untrusted advisory text — it is never structurally capable of producing a verdict (P-02).
- **Operating system / container runtime**: SentinelAI assumes a POSIX-ish or Windows environment capable of spawning subprocesses or Docker containers; it does not manage the underlying OS.

## Trust boundaries
| Boundary | Trust level | Why |
|---|---|---|
| GitHub → SentinelAI (webhook) | Untrusted input, must be verified | Webhook payloads must be signature-verified before triggering any analysis |
| Scanner subprocess → SentinelAI | Untrusted output, must be normalized/validated | A scanner is an independent process; its output is parsed defensively, never executed |
| AI provider → SentinelAI | Untrusted, advisory-only output | AI text is treated as explanatory content, never as executable instructions or as a verdict source (P-02) |
| DevSecOps → SentinelAI (config/policy) | Trusted, authenticated | Only DevSecOps can change policy; every change is itself audited |
| Developer → SentinelAI | Indirect only, via GitHub | Developer never has direct write access to SentinelAI configuration |

## What this document conditions
`05_Security` must design controls specifically for each "untrusted" row above (webhook signature verification, scanner output sandboxing/parsing limits, AI output never reaching an execution path). `Interaction_Model.md` elaborates the two trusted human actors in more detail.
