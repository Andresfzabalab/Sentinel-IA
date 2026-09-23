"""Analysis Orchestrator -- THE thin coordinator (P-01).

Implements UC-1/UC-2's main flow: classify artifacts, correlate findings,
and call RepositoryPort/ScannerPort/RiskPort/PolicyPort/*Store ports in
sequence. It contains no scanning, AI, risk, or policy logic itself -- all
of that lives behind the ports it calls (Architecture_Overview.md), and it
imports nothing from `infrastructure/` at all -- only `core/ports/`
(interfaces) and `core/domain/` (entities and pure services), per
Project_Structure.md's import direction rule and P-01/P-06's violation
test ("the Orchestrator module has no direct dependency on any scanner
library, AI SDK, or policy rule structure -- only on the port interfaces").

Phase 3 scope: wired against a Fake RepositoryPort and Fake ScannerPort,
with real SQLite-backed adapters (infrastructure/core/sqlite/*_adapter.py)
behind the *Store ports. Real RepositoryPort/ScannerPort adapters replace
the fakes in Phase 4 (GitHub) and Phase 5 (scanners) without any change to
this class -- that is the entire point of the port/adapter boundary
(QA-06, QA-07).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sentinel.core.domain.analysis.entities import Analysis, Finding, ScannerExecution
from sentinel.core.domain.analysis.value_objects import Artifact, PullRequestSnapshot, Severity
from sentinel.core.domain.audit.entities import AuditRecord
from sentinel.core.domain.notification.entities import Notification
from sentinel.core.domain.services.artifact_classification import ChangedFile, classify_artifacts
from sentinel.core.domain.services.policy_evaluation import PolicyFinding
from sentinel.core.domain.services.risk_assessment import RiskAssessmentInput
from sentinel.core.domain.services.scanner_selection import select_scanners
from sentinel.core.domain.services.security_score import ScoredFinding, calculate_security_score
from sentinel.core.ports.event_bus_port import EventBusPort
from sentinel.core.ports.policy_port import PolicyPort
from sentinel.core.ports.repository_port import AnalysisResultSummary, RepositoryPort, RepositoryPortError
from sentinel.core.ports.risk_port import RiskPort
from sentinel.core.ports.scanner_port import ScannerPort
from sentinel.core.ports.store_ports import AnalysisStore, AuditStore, NotificationStore, PolicyStore, RepositoryConfigStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ScannerRuntimeConfig:
    version: str
    timeout_seconds: int


@dataclass(frozen=True)
class AnalysisTrigger:
    """The Orchestrator's single input, equivalent to a consumed
    `PullRequestReceived` event (Domain_Events.md). `correlation_id` is
    always pre-computed by the caller (webhook handler or CLI/API, per
    shared/correlation.py) -- the Orchestrator never derives it itself.
    """

    correlation_id: str
    repository_id: str
    trigger_mode: str  # 'mode_a' | 'mode_b'
    pr_number: int | None = None
    base_branch: str | None = None
    head_branch: str | None = None
    author: str | None = None
    head_commit_sha: str | None = None  # known from the webhook payload itself -- never re-derived via API
    manual_trigger_key: str | None = None
    changed_files: tuple[ChangedFile, ...] = ()  # Mode B only -- supplied directly, no RepositoryPort call


class AnalysisOrchestrator:
    def __init__(
        self,
        *,
        repository_port: RepositoryPort,
        scanner_port: ScannerPort,
        risk_port: RiskPort,
        policy_port: PolicyPort,
        event_bus: EventBusPort,
        analysis_store: AnalysisStore,
        repository_config_store: RepositoryConfigStore,
        policy_store: PolicyStore,
        audit_store: AuditStore,
        notification_store: NotificationStore,
        scanner_runtime_config: dict[str, ScannerRuntimeConfig] | None = None,
        id_factory: "callable[[], str]" = lambda: str(uuid.uuid4()),
        clock: "callable[[], str]" = _utc_now_iso,
    ) -> None:
        self._repository_port = repository_port
        self._scanner_port = scanner_port
        self._risk_port = risk_port
        self._policy_port = policy_port
        self._event_bus = event_bus
        self._analysis_store = analysis_store
        self._repository_config_store = repository_config_store
        self._policy_store = policy_store
        self._audit_store = audit_store
        self._notification_store = notification_store
        self._scanner_runtime_config = scanner_runtime_config or {}
        self._id_factory = id_factory
        self._clock = clock

    def process(self, trigger: AnalysisTrigger) -> str:
        """Returns the analysisId -- either a freshly created one, or a
        pre-existing one if `trigger.correlation_id` was already processed
        (Domain_Events.md's idempotency rule). This check happens FIRST,
        before any PR retrieval or scanning, so a duplicate delivery never
        does wasted work.
        """
        existing_id = self._analysis_store.find_existing_id(trigger.correlation_id)
        if existing_id is not None:
            return existing_id

        analysis_id = self._id_factory()
        created_at = self._clock()

        repository = self._repository_config_store.get_repository(trigger.repository_id)
        policy_version = self._policy_store.get_current_policy_version(repository.assigned_policy_id)

        pr_snapshot: PullRequestSnapshot | None = None
        if trigger.trigger_mode == "mode_a":
            try:
                changed_file_refs = self._repository_port.fetch_changed_files(
                    repository.external_identifier, trigger.pr_number
                )
            except RepositoryPortError:
                return self._handle_pr_context_failure(trigger, repository, policy_version, analysis_id, created_at)

            pr_snapshot = PullRequestSnapshot(
                provider="github",
                pr_number=trigger.pr_number,
                base_branch=trigger.base_branch,
                head_branch=trigger.head_branch,
                author=trigger.author,
                head_commit_sha=trigger.head_commit_sha,
                changed_file_paths=tuple(f.path for f in changed_file_refs),
            )
            changed_files = tuple(ChangedFile(path=f.path, change_kind=f.change_kind) for f in changed_file_refs)
        else:
            changed_files = trigger.changed_files

        artifacts: tuple[Artifact, ...] = classify_artifacts(changed_files)
        selected_scanner_ids = select_scanners(artifacts, repository.enabled_scanners)
        scanner_executions = [
            ScannerExecution(
                id=f"{analysis_id}-se-{scanner_id}",
                scanner_id=scanner_id,
                scanner_version=self._scanner_runtime_config.get(
                    scanner_id, ScannerRuntimeConfig(version="unknown", timeout_seconds=120)
                ).version,
                timeout_seconds=self._scanner_runtime_config.get(
                    scanner_id, ScannerRuntimeConfig(version="unknown", timeout_seconds=120)
                ).timeout_seconds,
                started_at=created_at,
            )
            for scanner_id in selected_scanner_ids
        ]

        analysis = Analysis.start(
            id=analysis_id,
            correlation_id=trigger.correlation_id,
            trigger_mode=trigger.trigger_mode,
            repository_id=repository.id,
            policy_version_id=policy_version.id,
            artifacts=artifacts,
            scanner_executions=scanner_executions,
            pr_snapshot=pr_snapshot,
            manual_trigger_key=trigger.manual_trigger_key,
            created_at=created_at,
        )

        persisted_id = self._analysis_store.create_or_get(analysis)
        if persisted_id != analysis.id:
            # A concurrent identical trigger won the race -- duplicate, stop here.
            return persisted_id

        self._run_scanners(analysis)
        self._finalize(analysis, policy_version)
        self._publish_result(repository, analysis)

        return analysis_id

    # -- Internal steps ---------------------------------------------------

    def _handle_pr_context_failure(self, trigger, repository, policy_version, analysis_id, created_at) -> str:
        failed = Analysis.create_failed(
            id=analysis_id,
            correlation_id=trigger.correlation_id,
            repository_id=repository.id,
            policy_version_id=policy_version.id,
            failure_reason="pr_context_retrieval_failed",
            created_at=created_at,
        )
        persisted_id = self._analysis_store.create_failed(failed)

        self._audit_store.append(
            AuditRecord(
                id=f"{persisted_id}-audit-failed",
                actor="system",
                event_type="AnalysisFailed",
                origin="sentinel-core",
                payload={"failureReason": "pr_context_retrieval_failed"},
                created_at=self._clock(),
                subject_analysis_id=persisted_id,
                correlation_id=trigger.correlation_id,
            )
        )

        if trigger.head_commit_sha:
            self._deliver_status(
                repository.external_identifier,
                trigger.head_commit_sha,
                persisted_id,
                AnalysisResultSummary(verdict="ERROR", description="Could not retrieve PR context — analysis did not run"),
            )

        return persisted_id

    def _run_scanners(self, analysis: Analysis) -> None:
        for execution in list(analysis.scanner_executions):
            result = self._scanner_port.run(
                execution.scanner_id, execution.scanner_version, execution.timeout_seconds, analysis.artifacts
            )
            completed_at = self._clock()
            findings = tuple(
                Finding(
                    id=f"{analysis.id}-f-{execution.scanner_id}-{i}",
                    scanner_execution_id=execution.id,
                    scanner_id=execution.scanner_id,
                    category=nf.category,
                    artifact_path=nf.artifact_path,
                    artifact_type=nf.artifact_type,
                    rule_or_check_id=nf.rule_or_check_id,
                    severity=Severity(level=nf.severity_level, raw_value=nf.severity_raw_value),
                    location_file=nf.location_file,
                    location_line_start=nf.location_line_start,
                    location_line_end=nf.location_line_end,
                    secret_value_redaction_flag=nf.secret_value_redaction_flag,
                )
                for i, nf in enumerate(result.findings)
            )

            analysis.complete_scanner_execution(
                execution.scanner_id, result.status, completed_at,
                exit_code=result.exit_code, failure_note=result.failure_note, findings=findings,
            )
            self._analysis_store.complete_scanner_execution(
                analysis.id, analysis.find_scanner_execution(execution.scanner_id), findings
            )

            self._event_bus.publish(
                "ScannerExecutionCompleted",
                {"correlationId": analysis.correlation_id, "analysisId": analysis.id,
                 "scannerId": execution.scanner_id, "status": result.status},
            )

    def _finalize(self, analysis: Analysis, policy_version) -> None:
        analysis.correlate_findings()
        group_sizes = analysis.correlation_group_sizes()

        risk_inputs = tuple(
            RiskAssessmentInput(
                finding_id=f.id, severity=f.severity, artifact_path=f.artifact_path,
                correlation_group_size=group_sizes[f.id],
            )
            for f in analysis.findings
        )
        risks = self._risk_port.assess(risk_inputs)
        for finding in analysis.findings:
            finding.assign_risk(risks[finding.id])

        security_score = calculate_security_score(
            tuple(ScoredFinding(finding_id=f.id, risk_level=f.risk.adjusted_level) for f in analysis.findings)
        )

        policy_findings = tuple(
            PolicyFinding(
                finding_id=f.id, risk_level=f.risk.adjusted_level,
                rule_or_check_id=f.rule_or_check_id, artifact_path=f.artifact_path,
            )
            for f in analysis.findings
        )
        policy_result = self._policy_port.evaluate(policy_findings, security_score, policy_version)

        degradation_any_scanner_failed = any(
            se.status in ("failed", "timed_out") for se in analysis.scanner_executions
        )

        analysis.record_verdict(
            policy_result.verdict,
            security_score,
            degradation_any_scanner_failed=degradation_any_scanner_failed,
            degradation_ai_available_at_completion=False,  # AI & Agent Module not wired until Phase 9
            completed_at=self._clock(),
        )
        self._analysis_store.finalize(analysis)

        self._event_bus.publish(
            "PolicyEvaluated",
            {"correlationId": analysis.correlation_id, "analysisId": analysis.id, "verdict": analysis.verdict.value},
        )

        self._audit_store.append(
            AuditRecord(
                id=f"{analysis.id}-audit-completed",
                actor="system",
                event_type="AnalysisCompleted",
                origin="sentinel-core",
                payload={
                    "verdict": analysis.verdict.value,
                    "securityScore": security_score.value,
                    "policyVersionId": policy_version.id,
                    "suppressedFindingIds": list(policy_result.suppressed_finding_ids),
                },
                created_at=self._clock(),
                subject_analysis_id=analysis.id,
                correlation_id=analysis.correlation_id,
            )
        )

        self._event_bus.publish(
            "AnalysisCompleted", {"correlationId": analysis.correlation_id, "analysisId": analysis.id}
        )

    def _publish_result(self, repository, analysis: Analysis) -> None:
        if analysis.pr_snapshot is None:
            return  # Mode B has no PR / commit to post a status against

        description = (
            "No blocking findings" if analysis.verdict.value == "PASS"
            else f"Blocked: {len(analysis.verdict.triggered_rules)} triggered rule(s)"
        )
        self._deliver_status(
            repository.external_identifier,
            analysis.pr_snapshot.head_commit_sha,
            analysis.id,
            AnalysisResultSummary(verdict=analysis.verdict.value, description=description),
        )

    def _deliver_status(self, external_identifier: str, head_commit_sha: str, analysis_id: str, result: AnalysisResultSummary) -> None:
        try:
            delivered = self._repository_port.publish_result(external_identifier, head_commit_sha, result)
        except Exception:  # noqa: BLE001 -- a Notification failure must never affect the verdict already decided
            delivered = False

        self._notification_store.record_attempt(
            Notification(
                id=f"{analysis_id}-notif-{self._clock()}",
                analysis_id=analysis_id,
                channel="github-status",
                status="delivered" if delivered else "failed",
                attempted_at=self._clock(),
                content_snapshot=f'{{"verdict": "{result.verdict}", "description": "{result.description}"}}',
            )
        )
