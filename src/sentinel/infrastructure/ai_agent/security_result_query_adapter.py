"""SecurityResultQueryAdapter -- implements ai_agent's SecurityResultQueryPort
by reading Sentinel Core's frozen Analysis (via SqliteAnalysisStoreAdapter.load()).
Lives in infrastructure/ specifically because it crosses the module
boundary -- neither ai_agent/application/ nor core/application/ may import
the other directly (Module_Boundaries.md's one-way dependency direction);
infrastructure/ is where cross-module wiring is allowed to happen.

Read-only: this class has no method that writes anything -- there is
nothing else to call.
"""

from __future__ import annotations

from sentinel.ai_agent.ports.security_result_query_port import FindingView, SecurityResultView
from sentinel.infrastructure.core.sqlite.analysis_store_adapter import SqliteAnalysisStoreAdapter


class SecurityResultQueryAdapter:
    def __init__(self, analysis_store_adapter: SqliteAnalysisStoreAdapter) -> None:
        self._analysis_store_adapter = analysis_store_adapter

    def get(self, analysis_id: str) -> SecurityResultView | None:
        try:
            analysis = self._analysis_store_adapter.load(analysis_id)
        except KeyError:
            return None

        if analysis.status != "completed":
            return None

        return SecurityResultView(
            analysis_id=analysis.id,
            correlation_id=analysis.correlation_id,
            findings=tuple(
                FindingView(
                    finding_id=f.id,
                    scanner_id=f.scanner_id,
                    category=f.category,
                    artifact_path=f.artifact_path,
                    rule_or_check_id=f.rule_or_check_id,
                    severity_level=f.severity.level,
                    risk_level=f.risk.adjusted_level if f.risk else None,
                    secret_value_redaction_flag=f.secret_value_redaction_flag,
                    correlation_group_id=f.correlation_group_id,
                    location_file=f.location_file,
                    location_line_start=f.location_line_start,
                    location_line_end=f.location_line_end,
                )
                for f in analysis.findings
            ),
            security_score=analysis.security_score.value,
            policy_version_id=analysis.policy_version_id,
            verdict=analysis.verdict.value,
            triggered_rules=analysis.verdict.triggered_rules,
            completed_at=analysis.completed_at,
            degradation_any_scanner_failed=bool(analysis.degradation_any_scanner_failed),
            degradation_ai_available_at_completion=bool(analysis.degradation_ai_available_at_completion),
        )
