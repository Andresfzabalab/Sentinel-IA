"""Finding, ScannerExecution (child Entities), and Analysis (Aggregate Root).

Per docs/02_Domain/Entities_Value_Objects.md and
docs/02_Domain/Aggregates_and_Boundaries.md's Primary Aggregate. All three
live in the same consistency boundary as Analysis -- there is exactly one
Aggregate here, not three independent ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sentinel.core.domain.analysis.value_objects import (
    Artifact,
    PullRequestSnapshot,
    Risk,
    SecurityScore,
    Severity,
    Verdict,
)
from sentinel.core.domain.exceptions import (
    FindingsFrozen,
    MissingRiskAssessment,
    ScannerExecutionAlreadyTerminal,
    VerdictAlreadySet,
)

AnalysisStatus = str  # 'started' | 'running' | 'completed' | 'failed'
ScannerExecutionStatus = str  # 'running' | 'succeeded' | 'failed' | 'timed_out'
TERMINAL_SCANNER_STATUSES = frozenset({"succeeded", "failed", "timed_out"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Finding:
    """Identity: (AnalysisId, scannerId, ruleOrCategoryId, locationHash) --
    scoped to one Analysis, never global (Entities_Value_Objects.md). `id`
    is the concrete, generated identifier used everywhere else to
    reference this Finding (Data_Contracts.md's "IDs are stable").

    No AI Enrichment attribute exists here, deliberately -- see
    Entities_Value_Objects.md's "On AI Enrichment" note: that association
    lives entirely on the AI Enrichment side, never as a Finding attribute.
    """

    id: str
    scanner_execution_id: str
    scanner_id: str
    category: str
    artifact_path: str
    artifact_type: str
    rule_or_check_id: str
    severity: Severity
    location_file: str | None = None
    location_line_start: int | None = None
    location_line_end: int | None = None
    risk: Risk | None = None
    correlation_group_id: str | None = None
    secret_value_redaction_flag: bool = False

    def assign_risk(self, risk: Risk) -> None:
        """Risk can only be set after Severity exists (it always does, by
        construction) and is deterministic given the same inputs (P-03).
        Re-assessment replaces the value; it is not append-only at this level
        -- only the owning Analysis freezes it once completed.
        """
        self.risk = risk

    def assign_correlation_group(self, correlation_group_id: str | None) -> None:
        self.correlation_group_id = correlation_group_id


@dataclass
class ScannerExecution:
    """One concrete, isolated invocation of a Scanner. Identity:
    (AnalysisId, scannerId) -- one execution per scanner per Analysis.
    """

    id: str
    scanner_id: str
    scanner_version: str
    timeout_seconds: int
    started_at: str
    status: ScannerExecutionStatus = "running"
    completed_at: str | None = None
    exit_code: int | None = None
    failure_note: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_SCANNER_STATUSES

    def complete(self, status: ScannerExecutionStatus, completed_at: str, *, exit_code: int | None = None,
                 failure_note: str | None = None) -> None:
        """Exactly one terminal state per execution (P-09, QA-03). A
        `failed`/`timed_out` status is recorded exactly like `succeeded` --
        never erased, never reinterpreted as "no findings".
        """
        if self.is_terminal:
            raise ScannerExecutionAlreadyTerminal(
                f"scanner_execution {self.id!r} already reached terminal status {self.status!r}"
            )
        self.status = status
        self.completed_at = completed_at
        self.exit_code = exit_code
        self.failure_note = failure_note


@dataclass
class Analysis:
    """The primary Aggregate Root. Owns Finding and ScannerExecution as
    child entities within the same consistency boundary. References
    `repository_id` and `policy_version_id` by id only -- never an embedded
    copy of either aggregate's mutable state.
    """

    id: str
    correlation_id: str
    trigger_mode: str  # 'mode_a' | 'mode_b'
    repository_id: str
    policy_version_id: str
    created_at: str
    pr_snapshot: PullRequestSnapshot | None = None
    manual_trigger_key: str | None = None
    status: AnalysisStatus = "running"
    failure_reason: str | None = None
    artifacts: tuple[Artifact, ...] = ()
    scanner_executions: list[ScannerExecution] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    security_score: SecurityScore | None = None
    verdict: Verdict | None = None
    degradation_any_scanner_failed: bool | None = None
    degradation_ai_available_at_completion: bool | None = None
    completed_at: str | None = None

    # -- Construction --------------------------------------------------

    @classmethod
    def start(
        cls,
        *,
        id: str,
        correlation_id: str,
        trigger_mode: str,
        repository_id: str,
        policy_version_id: str,
        artifacts: tuple[Artifact, ...],
        scanner_executions: list[ScannerExecution],
        pr_snapshot: PullRequestSnapshot | None = None,
        manual_trigger_key: str | None = None,
        created_at: str | None = None,
    ) -> "Analysis":
        """T1 happy path: an Analysis is created directly in 'running'
        status with its full artifact/scanner-execution set already known
        -- Scanner Executions are never added later, one at a time.
        """
        return cls(
            id=id,
            correlation_id=correlation_id,
            trigger_mode=trigger_mode,
            repository_id=repository_id,
            policy_version_id=policy_version_id,
            created_at=created_at or _utc_now_iso(),
            pr_snapshot=pr_snapshot,
            manual_trigger_key=manual_trigger_key,
            status="running",
            artifacts=artifacts,
            scanner_executions=list(scanner_executions),
        )

    @classmethod
    def create_failed(
        cls,
        *,
        id: str,
        correlation_id: str,
        repository_id: str,
        policy_version_id: str,
        failure_reason: str,
        pr_snapshot: PullRequestSnapshot | None = None,
        created_at: str | None = None,
    ) -> "Analysis":
        """T1-Failed path (Mode A only): terminal on arrival, never passes
        through 'running'. No verdict will ever be produced for this
        instance (Persistence_Strategy.md).
        """
        now = created_at or _utc_now_iso()
        return cls(
            id=id,
            correlation_id=correlation_id,
            trigger_mode="mode_a",
            repository_id=repository_id,
            policy_version_id=policy_version_id,
            created_at=now,
            pr_snapshot=pr_snapshot,
            status="failed",
            failure_reason=failure_reason,
            completed_at=now,
        )

    # -- Scanning phase --------------------------------------------------

    def find_scanner_execution(self, scanner_id: str) -> ScannerExecution:
        for execution in self.scanner_executions:
            if execution.scanner_id == scanner_id:
                return execution
        raise KeyError(f"No scanner_execution for scanner_id={scanner_id!r} on analysis {self.id!r}")

    def complete_scanner_execution(
        self,
        scanner_id: str,
        status: ScannerExecutionStatus,
        completed_at: str,
        *,
        exit_code: int | None = None,
        failure_note: str | None = None,
        findings: tuple[Finding, ...] = (),
    ) -> None:
        """T2: completes one ScannerExecution and appends its Findings (if
        any). Findings may only be added while the Analysis itself is still
        `running` -- once `completed`, the set is frozen (Entities_Value_Objects.md).
        """
        if self.status == "completed":
            raise FindingsFrozen(f"analysis {self.id!r} already completed; cannot add findings")

        execution = self.find_scanner_execution(scanner_id)
        execution.complete(status, completed_at, exit_code=exit_code, failure_note=failure_note)
        self.findings.extend(findings)

    @property
    def all_scanner_executions_terminal(self) -> bool:
        return all(execution.is_terminal for execution in self.scanner_executions)

    # -- Correlation (stays inside the Aggregate, not a Domain Service) --

    @staticmethod
    def _correlation_key(finding: Finding) -> tuple:
        if finding.location_file is not None and finding.location_line_start is not None:
            return (finding.artifact_path, finding.location_file, finding.location_line_start)
        return (finding.artifact_path, finding.category)

    def correlate_findings(self) -> None:
        """Groups Findings referring to the same underlying issue (e.g. the
        same secret flagged by two tools, or two scanners reporting the
        same line) into a shared `correlation_group_id`. This is
        Analysis-domain logic, entirely within this Aggregate's own
        boundary -- NOT AI logic (Security_Decision_Flow.md corrects a
        prior mis-attribution to AI). Deterministic: the same Findings
        always produce the same grouping (QA-02), and a singleton group
        (no duplicate) is left with `correlation_group_id = None`.
        """
        groups: dict[tuple, list[Finding]] = {}
        for finding in self.findings:
            groups.setdefault(self._correlation_key(finding), []).append(finding)

        group_index = 0
        for key in sorted(groups.keys(), key=str):
            members = groups[key]
            if len(members) < 2:
                continue
            group_index += 1
            group_id = f"{self.id}-corr-{group_index}"
            for finding in members:
                finding.assign_correlation_group(group_id)

    def correlation_group_sizes(self) -> dict[str, int]:
        """Finding id -> size of its correlation group (1 if uncorrelated).
        Feeds Risk Assessment's correlation-density heuristic.
        """
        counts: dict[str, int] = {}
        for finding in self.findings:
            if finding.correlation_group_id:
                counts[finding.correlation_group_id] = counts.get(finding.correlation_group_id, 0) + 1

        return {
            finding.id: counts[finding.correlation_group_id] if finding.correlation_group_id else 1
            for finding in self.findings
        }

    # -- Finalization (T3) ------------------------------------------------

    def record_verdict(
        self,
        verdict: Verdict,
        security_score: SecurityScore,
        *,
        degradation_any_scanner_failed: bool,
        degradation_ai_available_at_completion: bool,
        completed_at: str,
    ) -> None:
        """The ONLY way a verdict is ever attached to this Analysis (P-02,
        P-04). Write-once: a second call always raises, regardless of the
        value passed. Every Finding must already carry a Risk assessment --
        Risk (Section 9 of Analysis_Lifecycle.md) must never run after
        Policy, and this is the structural check for that ordering.
        """
        if self.verdict is not None:
            raise VerdictAlreadySet(f"analysis {self.id!r} already has verdict {self.verdict.value!r}")

        for finding in self.findings:
            if finding.risk is None:
                raise MissingRiskAssessment(
                    f"finding {finding.id!r} on analysis {self.id!r} has no Risk assigned"
                )

        self.security_score = security_score
        self.verdict = verdict
        self.degradation_any_scanner_failed = degradation_any_scanner_failed
        self.degradation_ai_available_at_completion = degradation_ai_available_at_completion
        self.status = "completed"
        self.completed_at = completed_at
