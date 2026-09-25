"""SqliteAnalysisStoreAdapter -- implements the domain-facing `AnalysisStore`
port (core/ports/store_ports.py) on top of the row/DTO-level
`SqliteAnalysisStore` (analysis_store.py). This is where domain Analysis
objects are translated to/from the DTOs Phase 1's store already speaks --
the Orchestrator (core/application/) depends only on the port, never on
this adapter or on SqliteAnalysisStore directly (Project_Structure.md's
import direction rule; P-01/P-06).
"""

from __future__ import annotations

import json

from sentinel.core.domain.analysis.entities import Analysis, Finding, ScannerExecution
from sentinel.core.domain.analysis.value_objects import (
    Artifact,
    PullRequestSnapshot,
    Risk,
    SecurityScore,
    Severity,
    Verdict,
)
from sentinel.infrastructure.core.sqlite.analysis_store import (
    AnalysisCreate,
    AnalysisFailed,
    ArtifactCreate,
    FindingCreate,
    FindingRiskUpdate,
    ScannerExecutionCompletion,
    ScannerExecutionSeed,
    SqliteAnalysisStore,
    T3Finalize,
)
from sentinel.shared.logging import get_logger
from sentinel.shared.retry import retry_critical_write

_logger = get_logger("core", "SqliteAnalysisStoreAdapter")


class SqliteAnalysisStoreAdapter:
    def __init__(self, store: SqliteAnalysisStore) -> None:
        self._store = store

    def find_existing_id(self, correlation_id: str) -> str | None:
        return self._store.find_analysis_id_by_correlation_id(correlation_id)

    def create_or_get(self, analysis: Analysis) -> str:
        """T1. Returns the id that ended up persisted -- the caller's own
        `analysis.id` on a fresh create, or a pre-existing id if a
        concurrent/duplicate trigger won the race (Domain_Events.md's
        idempotency rule). Callers must compare the result against
        `analysis.id` to detect the duplicate case.
        """
        pr = analysis.pr_snapshot
        create = AnalysisCreate(
            id=analysis.id,
            correlation_id=analysis.correlation_id,
            trigger_mode=analysis.trigger_mode,
            repository_id=analysis.repository_id,
            policy_version_id=analysis.policy_version_id,
            created_at=analysis.created_at,
            pr_context_retrieval_status="succeeded" if (analysis.trigger_mode == "mode_a" and pr) else None,
            pr_number=pr.pr_number if pr else None,
            pr_head_branch=pr.head_branch if pr else None,
            pr_base_branch=pr.base_branch if pr else None,
            pr_author=pr.author if pr else None,
            pr_head_commit_sha=pr.head_commit_sha if pr else None,
            manual_trigger_key=analysis.manual_trigger_key,
        )
        artifacts = tuple(
            ArtifactCreate(id=f"{analysis.id}-art-{i}", path=a.path, artifact_type=a.type, change_kind=a.change_kind)
            for i, a in enumerate(analysis.artifacts)
        )
        scanner_executions = tuple(
            ScannerExecutionSeed(
                id=se.id, scanner_id=se.scanner_id, scanner_version=se.scanner_version,
                timeout_seconds=se.timeout_seconds, started_at=se.started_at,
            )
            for se in analysis.scanner_executions
        )
        return retry_critical_write(
            lambda: self._store.create_analysis(create, artifacts, scanner_executions),
            logger=_logger, event="t1_write", correlation_id=analysis.correlation_id, analysis_id=analysis.id,
        )

    def create_failed(self, analysis: Analysis) -> str:
        pr = analysis.pr_snapshot
        failed = AnalysisFailed(
            id=analysis.id,
            correlation_id=analysis.correlation_id,
            repository_id=analysis.repository_id,
            policy_version_id=analysis.policy_version_id,
            failure_reason=analysis.failure_reason or "unknown",
            created_at=analysis.created_at,
            pr_number=pr.pr_number if pr else None,
            pr_head_branch=pr.head_branch if pr else None,
            pr_base_branch=pr.base_branch if pr else None,
            pr_author=pr.author if pr else None,
        )
        return retry_critical_write(
            lambda: self._store.create_failed_analysis(failed),
            logger=_logger, event="t1_failed_write", correlation_id=analysis.correlation_id, analysis_id=analysis.id,
        )

    def complete_scanner_execution(
        self, analysis_id: str, execution: ScannerExecution, findings: tuple[Finding, ...]
    ) -> None:
        completion = ScannerExecutionCompletion(
            analysis_id=analysis_id,
            scanner_id=execution.scanner_id,
            status=execution.status,
            completed_at=execution.completed_at,
            exit_code=execution.exit_code,
            failure_note=execution.failure_note,
            findings=tuple(
                FindingCreate(
                    id=f.id,
                    scanner_execution_id=f.scanner_execution_id,
                    scanner_id=f.scanner_id,
                    category=f.category,
                    artifact_path=f.artifact_path,
                    artifact_type=f.artifact_type,
                    rule_or_check_id=f.rule_or_check_id,
                    severity_level=f.severity.level,
                    severity_raw_value=f.severity.raw_value,
                    location_file=f.location_file,
                    location_line_start=f.location_line_start,
                    location_line_end=f.location_line_end,
                    secret_value_redaction_flag=f.secret_value_redaction_flag,
                )
                for f in findings
            ),
        )
        self._store.complete_scanner_execution(completion)

    def finalize(self, analysis: Analysis) -> None:
        finalize = T3Finalize(
            analysis_id=analysis.id,
            security_score=analysis.security_score.value,
            verdict=analysis.verdict.value,
            degradation_any_scanner_failed=bool(analysis.degradation_any_scanner_failed),
            degradation_ai_available_at_completion=bool(analysis.degradation_ai_available_at_completion),
            completed_at=analysis.completed_at,
            finding_updates=tuple(
                FindingRiskUpdate(
                    finding_id=f.id,
                    correlation_group_id=f.correlation_group_id,
                    risk_level=f.risk.adjusted_level,
                    risk_heuristics_applied=json.dumps(list(f.risk.heuristics_applied)),
                )
                for f in analysis.findings
            ),
        )
        retry_critical_write(
            lambda: self._store.finalize_verdict(finalize),
            logger=_logger, event="t3_write", correlation_id=analysis.correlation_id, analysis_id=analysis.id,
        )

    def load(self, analysis_id: str) -> Analysis:
        """Reconstructs the full domain Aggregate from its persisted rows.
        Needed by the Crash & Restart Recovery sweep (Persistence_Strategy.md)
        to re-run finalization against an Analysis that survived a process
        restart, and generally useful as the read-side of this Store.
        """
        row = self._store.get_analysis(analysis_id)
        if row is None:
            raise KeyError(f"analysis {analysis_id!r} not found")

        artifact_rows = self._store.get_artifacts(analysis_id)
        artifacts = tuple(
            Artifact(path=a["path"], type=a["artifact_type"], change_kind=a["change_kind"]) for a in artifact_rows
        )

        pr_snapshot = None
        if row["pr_number"] is not None:
            pr_snapshot = PullRequestSnapshot(
                provider="github",
                pr_number=row["pr_number"],
                base_branch=row["pr_base_branch"],
                head_branch=row["pr_head_branch"],
                author=row["pr_author"],
                head_commit_sha=row["pr_head_commit_sha"],
                changed_file_paths=tuple(a["path"] for a in artifact_rows),
            )

        scanner_executions = [
            ScannerExecution(
                id=se["id"],
                scanner_id=se["scanner_id"],
                scanner_version=se["scanner_version"],
                timeout_seconds=se["timeout_seconds"],
                started_at=se["started_at"],
                status=se["status"],
                completed_at=se["completed_at"],
                exit_code=se["exit_code"],
                failure_note=se["failure_note"],
            )
            for se in self._store.get_scanner_executions(analysis_id)
        ]

        findings = [
            Finding(
                id=f["id"],
                scanner_execution_id=f["scanner_execution_id"],
                scanner_id=f["scanner_id"],
                category=f["category"],
                artifact_path=f["artifact_path"],
                artifact_type=f["artifact_type"],
                rule_or_check_id=f["rule_or_check_id"],
                severity=Severity(level=f["severity_level"], raw_value=f["severity_raw_value"]),
                location_file=f["location_file"],
                location_line_start=f["location_line_start"],
                location_line_end=f["location_line_end"],
                risk=(
                    Risk(adjusted_level=f["risk_level"], heuristics_applied=tuple(json.loads(f["risk_heuristics_applied"])))
                    if f["risk_level"] is not None
                    else None
                ),
                correlation_group_id=f["correlation_group_id"],
                secret_value_redaction_flag=bool(f["secret_value_redaction_flag"]),
            )
            for f in self._store.get_findings(analysis_id)
        ]

        return Analysis(
            id=row["id"],
            correlation_id=row["correlation_id"],
            trigger_mode=row["trigger_mode"],
            repository_id=row["repository_id"],
            policy_version_id=row["policy_version_id"],
            created_at=row["created_at"],
            pr_snapshot=pr_snapshot,
            manual_trigger_key=row["manual_trigger_key"],
            status=row["status"],
            failure_reason=row["failure_reason"],
            artifacts=artifacts,
            scanner_executions=scanner_executions,
            findings=findings,
            security_score=SecurityScore(value=row["security_score"]) if row["security_score"] is not None else None,
            verdict=(
                Verdict(value=row["verdict"], policy_version_id=row["policy_version_id"])
                if row["verdict"] is not None
                else None
            ),
            degradation_any_scanner_failed=(
                bool(row["degradation_any_scanner_failed"]) if row["degradation_any_scanner_failed"] is not None else None
            ),
            degradation_ai_available_at_completion=(
                bool(row["degradation_ai_available_at_completion"])
                if row["degradation_ai_available_at_completion"] is not None
                else None
            ),
            completed_at=row["completed_at"],
        )

    def find_running_analysis_ids(self) -> tuple[str, ...]:
        return tuple(self._store.find_running_analysis_ids())

    def recover_stale_scanner_executions(self, failure_note: str, completed_at: str) -> tuple[str, ...]:
        """Crash & Restart Recovery, step 1: every scanner_execution still
        'running' becomes 'failed' -- a normal T2, using the existing
        failure representation, not a new status (Persistence_Strategy.md).
        Returns the distinct analysis_ids that had at least one row
        recovered, so the caller knows which Analyses to re-evaluate.
        """
        affected: set[str] = set()
        for row in self._store.find_running_scanner_executions():
            self._store.complete_scanner_execution(
                ScannerExecutionCompletion(
                    analysis_id=row["analysis_id"],
                    scanner_id=row["scanner_id"],
                    status="failed",
                    completed_at=completed_at,
                    failure_note=failure_note,
                )
            )
            affected.add(row["analysis_id"])
        return tuple(affected)
