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
        return self._store.create_analysis(create, artifacts, scanner_executions)

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
        return self._store.create_failed_analysis(failed)

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
        self._store.finalize_verdict(finalize)
