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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone

from sentinel.core.application.analysis_write_queue import AnalysisWriteQueue
from sentinel.core.application.notification_dispatch_service import NotificationDispatchService
from sentinel.core.domain.analysis.entities import Analysis, Finding, ScannerExecution
from sentinel.core.domain.analysis.value_objects import Artifact, PullRequestSnapshot, Severity
from sentinel.core.domain.audit.entities import AuditRecord
from sentinel.core.domain.services.artifact_classification import ChangedFile, classify_artifacts
from sentinel.core.domain.services.policy_evaluation import PolicyFinding
from sentinel.core.domain.services.risk_assessment import RiskAssessmentInput
from sentinel.core.domain.services.scanner_selection import select_scanners
from sentinel.core.domain.services.security_score import ScoredFinding, calculate_security_score
from sentinel.core.ports.event_bus_port import EventBusPort
from sentinel.core.ports.policy_port import PolicyPort
from sentinel.core.ports.repository_port import AnalysisResultSummary, RepositoryPort, RepositoryPortError
from sentinel.core.ports.risk_port import RiskPort
from sentinel.core.ports.scanner_port import ScannerPort, ScannerRunResult
from sentinel.core.ports.store_ports import AnalysisStore, AuditStore, NotificationStore, PolicyStore, RepositoryConfigStore
from sentinel.core.ports.working_directory_port import WorkingDirectoryError, WorkingDirectoryPort
from sentinel.shared.logging import get_logger

_logger = get_logger("core", "AnalysisOrchestrator")


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
        working_directory_port: WorkingDirectoryPort | None = None,
        analysis_write_queue: AnalysisWriteQueue | None = None,
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
        self._scanner_runtime_config = scanner_runtime_config or {}
        # None until Phase 6 wires a real checkout provider in composition.py;
        # scanners then simply degrade honestly against no real files (P-09).
        self._working_directory_port = working_directory_port
        self._analysis_write_queue = analysis_write_queue or AnalysisWriteQueue()
        self._id_factory = id_factory
        self._clock = clock
        self._notification_dispatch_service = NotificationDispatchService(repository_port, notification_store, clock=clock)

    def process(self, trigger: AnalysisTrigger) -> str:
        """Returns the analysisId -- either a freshly created one, or a
        pre-existing one if `trigger.correlation_id` was already processed
        (Domain_Events.md's idempotency rule). This check happens FIRST,
        before any PR retrieval or scanning, so a duplicate delivery never
        does wasted work.
        """
        existing_id = self._analysis_store.find_existing_id(trigger.correlation_id)
        if existing_id is not None:
            _logger.info(
                "analysis_duplicate_trigger", "Duplicate trigger for an already-processed correlationId",
                correlation_id=trigger.correlation_id, analysis_id=existing_id,
            )
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
            _logger.info(
                "analysis_duplicate_trigger", "Concurrent trigger lost the T1 race for the same correlationId",
                correlation_id=trigger.correlation_id, analysis_id=persisted_id,
            )
            return persisted_id

        _logger.info(
            "t1_committed", f"T1 committed: analysis {analysis.id} created, {len(scanner_executions)} scanner(s) selected",
            correlation_id=trigger.correlation_id, analysis_id=analysis.id,
            detail={"selectedScanners": list(selected_scanner_ids)},
        )

        self._run_scanners(analysis, repository)
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

        _logger.info(
            "t1_failed_committed", "T1-Failed committed: PR context could not be retrieved, no verdict will be produced",
            correlation_id=trigger.correlation_id, analysis_id=persisted_id,
            detail={"failureReason": "pr_context_retrieval_failed"},
        )

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
            self._notification_dispatch_service.deliver_status(
                repository.external_identifier,
                trigger.head_commit_sha,
                persisted_id,
                AnalysisResultSummary(verdict="ERROR", description="Could not retrieve PR context — analysis did not run"),
                correlation_id=trigger.correlation_id,
            )

        return persisted_id

    def _run_scanners(self, analysis: Analysis, repository) -> None:
        """Runs every selected scanner concurrently (Phase 6) against a real
        working directory when one can be prepared. Completions are applied
        under the per-analysis_id lock (AnalysisWriteQueue), so the
        in-memory Aggregate mutation and its persistence happen as one
        uninterrupted step per scanner, even though multiple scanners
        finish at unpredictable, overlapping times.
        """
        executions = list(analysis.scanner_executions)
        if not executions:
            return

        working_directory = self._prepare_working_directory(analysis, repository)
        try:
            with ThreadPoolExecutor(max_workers=len(executions)) as pool:
                future_to_execution = {
                    pool.submit(
                        self._scanner_port.run,
                        execution.scanner_id, execution.scanner_version, execution.timeout_seconds,
                        analysis.artifacts, working_directory,
                    ): execution
                    for execution in executions
                }
                for future in as_completed(future_to_execution):
                    execution = future_to_execution[future]
                    result = future.result()
                    self._apply_scanner_result(analysis, execution, result)
        finally:
            if working_directory and self._working_directory_port is not None:
                self._working_directory_port.cleanup(working_directory)

    def _prepare_working_directory(self, analysis: Analysis, repository) -> str:
        if self._working_directory_port is None or analysis.pr_snapshot is None:
            return ""
        try:
            return self._working_directory_port.prepare(
                repository.external_identifier, analysis.pr_snapshot.head_commit_sha
            )
        except WorkingDirectoryError:
            # A checkout failure degrades to scanners running with no real
            # files -- each adapter already reports 'failed' honestly for
            # that (P-09); it must never block or fail the whole Analysis.
            return ""

    def _apply_scanner_result(self, analysis: Analysis, execution: ScannerExecution, result: ScannerRunResult) -> None:
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

        with self._analysis_write_queue.lock_for(analysis.id):
            analysis.complete_scanner_execution(
                execution.scanner_id, result.status, completed_at,
                exit_code=result.exit_code, failure_note=result.failure_note, findings=findings,
            )
            self._analysis_store.complete_scanner_execution(
                analysis.id, analysis.find_scanner_execution(execution.scanner_id), findings
            )

        log = _logger.info if result.status == "succeeded" else _logger.warning
        log(
            "t2_committed", f"T2 committed: scanner {execution.scanner_id} {result.status}, {len(findings)} finding(s)",
            correlation_id=analysis.correlation_id, analysis_id=analysis.id, scanner_execution_id=execution.id,
            detail={"scannerId": execution.scanner_id, "status": result.status, "findingCount": len(findings)},
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

        _logger.info(
            "t3_committed", f"T3 committed: verdict={analysis.verdict.value}, score={security_score.value}",
            correlation_id=analysis.correlation_id, analysis_id=analysis.id,
            detail={"verdict": analysis.verdict.value, "securityScore": security_score.value,
                    "degradationAnyScannerFailed": degradation_any_scanner_failed},
        )

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
        self._notification_dispatch_service.dispatch_for_completed_analysis(repository, analysis)

    # -- Crash & Restart Recovery (Persistence_Strategy.md) ----------------

    def recover_incomplete_analyses(self) -> None:
        """Must run once, before accepting new triggers, after a process
        restart. Two steps, exactly as documented:

        1. Every scanner_execution still 'running' has no in-memory handle
           left -- the process that held it is the one that just restarted
           -- so each becomes 'failed' with a distinguishing note.
        2. Every Analysis still 'running' is re-evaluated against that
           now-resolved scanner set and, if all its executions have reached
           a terminal state, proceeds through the same finalization
           (`_finalize`) and result publication (`_publish_result`) as the
           normal flow -- producing a verdict from whatever scanners had
           genuinely completed before the crash (P-09/QA-03), never a
           second hang.
        """
        _logger.info("recovery_sweep_started", "Startup recovery sweep beginning")

        recovered_ids = self._analysis_store.recover_stale_scanner_executions(
            "process restarted mid-execution", self._clock()
        )
        if recovered_ids:
            _logger.warning(
                "recovery_sweep_scanners_recovered",
                f"{len(recovered_ids)} analysis(es) had stale scanner executions marked failed after a restart",
                detail={"analysisIds": list(recovered_ids)},
            )

        running_ids = self._analysis_store.find_running_analysis_ids()
        for analysis_id in running_ids:
            analysis = self._analysis_store.load(analysis_id)
            if not analysis.all_scanner_executions_terminal:
                continue  # cannot happen after the sweep above, guarded for clarity/safety

            policy_version = self._policy_store.get_version(analysis.policy_version_id)
            self._finalize(analysis, policy_version)

            try:
                repository = self._repository_config_store.get_repository(analysis.repository_id)
                self._publish_result(repository, analysis)
            except Exception:  # noqa: BLE001 -- notification is best-effort; the verdict is already recorded
                pass

        _logger.info(
            "recovery_sweep_completed", f"Startup recovery sweep completed: {len(running_ids)} analysis(es) finalized",
            detail={"finalizedCount": len(running_ids)},
        )
