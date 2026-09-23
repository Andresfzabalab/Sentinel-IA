"""SqliteAnalysisStore -- implements the Analysis Aggregate's T1/T2/T3
transactions exactly as specified in docs/03_API/Persistence_Strategy.md.

Uses sqlite3 directly (BEGIN IMMEDIATE ... COMMIT), never an ORM, per the
project's explicit decision that no ORM encapsulates SentinelAI's
verdict-critical transactions. The dataclasses below are plain data
carriers (rows-to-be), not domain Entities -- Phase 2 introduces the
domain layer; Phase 3 wires it to this store.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from sentinel.infrastructure.core.sqlite.exceptions import (
    ScannerExecutionNotRunning,
    VerdictAlreadySet,
)


@dataclass(frozen=True)
class ArtifactCreate:
    id: str
    path: str
    artifact_type: str
    change_kind: str  # 'added' | 'modified' | 'deleted'


@dataclass(frozen=True)
class ScannerExecutionSeed:
    id: str
    scanner_id: str
    scanner_version: str
    timeout_seconds: int
    started_at: str


@dataclass(frozen=True)
class AnalysisCreate:
    """T1 happy path (Mode A after successful PR-context retrieval, or Mode B)."""

    id: str
    correlation_id: str
    trigger_mode: str  # 'mode_a' | 'mode_b'
    repository_id: str
    policy_version_id: str
    created_at: str
    pr_context_retrieval_status: str | None = None  # 'succeeded' under Mode A, None under Mode B
    pr_number: int | None = None
    pr_head_branch: str | None = None
    pr_base_branch: str | None = None
    pr_author: str | None = None
    pr_head_commit_sha: str | None = None
    manual_trigger_key: str | None = None


@dataclass(frozen=True)
class AnalysisFailed:
    """T1-Failed path (Mode A only) -- PR context retrieval exhausted its retries."""

    id: str
    correlation_id: str
    repository_id: str
    policy_version_id: str
    failure_reason: str
    created_at: str
    pr_number: int | None = None
    pr_head_branch: str | None = None
    pr_base_branch: str | None = None
    pr_author: str | None = None
    pr_head_commit_sha: str | None = None


@dataclass(frozen=True)
class FindingCreate:
    id: str
    scanner_execution_id: str
    scanner_id: str
    category: str
    artifact_path: str
    artifact_type: str
    rule_or_check_id: str
    severity_level: str
    location_file: str | None = None
    location_line_start: int | None = None
    location_line_end: int | None = None
    severity_raw_value: str | None = None
    secret_value_redaction_flag: bool = False


@dataclass(frozen=True)
class ScannerExecutionCompletion:
    analysis_id: str
    scanner_id: str
    status: str  # 'succeeded' | 'failed' | 'timed_out'
    completed_at: str
    exit_code: int | None = None
    execution_metadata: str | None = None
    failure_note: str | None = None
    findings: tuple[FindingCreate, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FindingRiskUpdate:
    finding_id: str
    correlation_group_id: str | None
    risk_level: str
    risk_heuristics_applied: str  # JSON array, per Data_Model.md


@dataclass(frozen=True)
class T3Finalize:
    analysis_id: str
    security_score: float
    verdict: str  # 'PASS' | 'BLOCK'
    degradation_any_scanner_failed: bool
    degradation_ai_available_at_completion: bool
    completed_at: str
    finding_updates: tuple[FindingRiskUpdate, ...] = field(default_factory=tuple)


class SqliteAnalysisStore:
    """Implements AnalysisStore against `analysis`, `artifact`,
    `scanner_execution`, and `finding` -- the only tables it touches
    (docs/03_API/Persistence_Strategy.md's Repositories/Adapters table).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def find_analysis_id_by_correlation_id(self, correlation_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT id FROM analysis WHERE correlation_id = ?", (correlation_id,)
        ).fetchone()
        return row["id"] if row is not None else None

    def create_analysis(
        self,
        analysis: AnalysisCreate,
        artifacts: tuple[ArtifactCreate, ...],
        scanner_executions: tuple[ScannerExecutionSeed, ...],
    ) -> str:
        """T1 -- Analysis Created (happy path).

        Idempotent on `correlation_id`: if an Analysis already exists for
        it, no new row is written and the existing `analysisId` is
        returned. The `UNIQUE(correlation_id)` constraint is the final
        backstop even if the upfront check were ever bypassed.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            existing = conn.execute(
                "SELECT id FROM analysis WHERE correlation_id = ?", (analysis.correlation_id,)
            ).fetchone()
            if existing is not None:
                conn.execute("COMMIT;")
                return existing["id"]

            try:
                conn.execute(
                    """
                    INSERT INTO analysis (
                        id, correlation_id, trigger_mode, repository_id, policy_version_id,
                        status, pr_context_retrieval_status, pr_number, pr_head_branch,
                        pr_base_branch, pr_author, pr_head_commit_sha, manual_trigger_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        analysis.id,
                        analysis.correlation_id,
                        analysis.trigger_mode,
                        analysis.repository_id,
                        analysis.policy_version_id,
                        analysis.pr_context_retrieval_status,
                        analysis.pr_number,
                        analysis.pr_head_branch,
                        analysis.pr_base_branch,
                        analysis.pr_author,
                        analysis.pr_head_commit_sha,
                        analysis.manual_trigger_key,
                        analysis.created_at,
                    ),
                )
            except sqlite3.IntegrityError:
                # UNIQUE(correlation_id) backstop: a concurrent T1 won the race.
                conn.execute("ROLLBACK;")
                existing = conn.execute(
                    "SELECT id FROM analysis WHERE correlation_id = ?", (analysis.correlation_id,)
                ).fetchone()
                if existing is None:
                    raise
                return existing["id"]

            for artifact in artifacts:
                conn.execute(
                    "INSERT INTO artifact (id, analysis_id, path, artifact_type, change_kind) VALUES (?, ?, ?, ?, ?)",
                    (artifact.id, analysis.id, artifact.path, artifact.artifact_type, artifact.change_kind),
                )

            for se in scanner_executions:
                conn.execute(
                    """
                    INSERT INTO scanner_execution (
                        id, analysis_id, scanner_id, scanner_version, status, timeout_seconds, started_at
                    ) VALUES (?, ?, ?, ?, 'running', ?, ?)
                    """,
                    (se.id, analysis.id, se.scanner_id, se.scanner_version, se.timeout_seconds, se.started_at),
                )

            conn.execute("COMMIT;")
            return analysis.id
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def create_failed_analysis(self, failed: AnalysisFailed) -> str:
        """T1-Failed -- Analysis Created in terminal 'failed' state (Mode A only).

        Never passes through 'running'; completed_at is set immediately.
        No artifact/scanner_execution/finding row is ever written.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            existing = conn.execute(
                "SELECT id FROM analysis WHERE correlation_id = ?", (failed.correlation_id,)
            ).fetchone()
            if existing is not None:
                conn.execute("COMMIT;")
                return existing["id"]

            try:
                conn.execute(
                    """
                    INSERT INTO analysis (
                        id, correlation_id, trigger_mode, repository_id, policy_version_id,
                        status, failure_reason, pr_context_retrieval_status,
                        pr_number, pr_head_branch, pr_base_branch, pr_author, pr_head_commit_sha,
                        created_at, completed_at
                    ) VALUES (?, ?, 'mode_a', ?, ?, 'failed', ?, 'failed', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        failed.id,
                        failed.correlation_id,
                        failed.repository_id,
                        failed.policy_version_id,
                        failed.failure_reason,
                        failed.pr_number,
                        failed.pr_head_branch,
                        failed.pr_base_branch,
                        failed.pr_author,
                        failed.pr_head_commit_sha,
                        failed.created_at,
                        failed.created_at,
                    ),
                )
            except sqlite3.IntegrityError:
                conn.execute("ROLLBACK;")
                existing = conn.execute(
                    "SELECT id FROM analysis WHERE correlation_id = ?", (failed.correlation_id,)
                ).fetchone()
                if existing is None:
                    raise
                return existing["id"]

            conn.execute("COMMIT;")
            return failed.id
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def complete_scanner_execution(self, completion: ScannerExecutionCompletion) -> None:
        """T2 -- Scanner Execution Completed.

        Only ever UPDATEs a scanner_execution row T1 already created; never
        INSERTs one. The `AND status = 'running'` clause is a storage-level
        backstop against completing the same execution twice.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            cursor = conn.execute(
                """
                UPDATE scanner_execution
                SET status = ?, exit_code = ?, execution_metadata = ?, completed_at = ?, failure_note = ?
                WHERE analysis_id = ? AND scanner_id = ? AND status = 'running'
                """,
                (
                    completion.status,
                    completion.exit_code,
                    completion.execution_metadata,
                    completion.completed_at,
                    completion.failure_note,
                    completion.analysis_id,
                    completion.scanner_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ScannerExecutionNotRunning(
                    f"No running scanner_execution for analysis_id={completion.analysis_id!r} "
                    f"scanner_id={completion.scanner_id!r}"
                )

            for finding in completion.findings:
                conn.execute(
                    """
                    INSERT INTO finding (
                        id, analysis_id, scanner_execution_id, scanner_id, category,
                        artifact_path, artifact_type, location_file, location_line_start,
                        location_line_end, rule_or_check_id, severity_level, severity_raw_value,
                        secret_value_redaction_flag
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        finding.id,
                        completion.analysis_id,
                        finding.scanner_execution_id,
                        finding.scanner_id,
                        finding.category,
                        finding.artifact_path,
                        finding.artifact_type,
                        finding.location_file,
                        finding.location_line_start,
                        finding.location_line_end,
                        finding.rule_or_check_id,
                        finding.severity_level,
                        finding.severity_raw_value,
                        finding.secret_value_redaction_flag,
                    ),
                )

            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def finalize_verdict(self, finalize: T3Finalize) -> None:
        """T3 -- Correlation + Risk + Policy Finalized.

        The `WHERE verdict IS NULL` clause enforces write-once at the SQL
        level, on top of the application-layer `Analysis.recordVerdict()`
        invariant. If it affects zero rows, that is a serious invariant
        violation (re-deciding an already-decided verdict), not a no-op.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            for update in finalize.finding_updates:
                conn.execute(
                    """
                    UPDATE finding
                    SET correlation_group_id = ?, risk_level = ?, risk_heuristics_applied = ?
                    WHERE id = ? AND analysis_id = ?
                    """,
                    (
                        update.correlation_group_id,
                        update.risk_level,
                        update.risk_heuristics_applied,
                        update.finding_id,
                        finalize.analysis_id,
                    ),
                )

            cursor = conn.execute(
                """
                UPDATE analysis
                SET security_score = ?, verdict = ?, degradation_any_scanner_failed = ?,
                    degradation_ai_available_at_completion = ?, status = 'completed', completed_at = ?
                WHERE id = ? AND verdict IS NULL
                """,
                (
                    finalize.security_score,
                    finalize.verdict,
                    finalize.degradation_any_scanner_failed,
                    finalize.degradation_ai_available_at_completion,
                    finalize.completed_at,
                    finalize.analysis_id,
                ),
            )
            if cursor.rowcount == 0:
                raise VerdictAlreadySet(
                    f"analysis_id={finalize.analysis_id!r} already has a verdict, or does not exist"
                )

            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def get_analysis(self, analysis_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM analysis WHERE id = ?", (analysis_id,)).fetchone()

    def get_scanner_executions(self, analysis_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM scanner_execution WHERE analysis_id = ?", (analysis_id,)
        ).fetchall()

    def get_findings(self, analysis_id: str) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM finding WHERE analysis_id = ?", (analysis_id,)).fetchall()

    def get_artifacts(self, analysis_id: str) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM artifact WHERE analysis_id = ?", (analysis_id,)).fetchall()
