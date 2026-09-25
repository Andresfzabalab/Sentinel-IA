"""Proves SecurityResultQueryAdapter's cross-module read: a completed
Analysis projects into a SecurityResultView with the fields the AI & Agent
Module needs, and an in-progress/unknown Analysis projects to None -- never
a partially-filled view (Module_Boundaries.md's read-only contract).
"""

from __future__ import annotations

import pytest

from sentinel.infrastructure.ai_agent.security_result_query_adapter import SecurityResultQueryAdapter
from sentinel.infrastructure.core.sqlite.analysis_store import (
    AnalysisCreate,
    FindingCreate,
    FindingRiskUpdate,
    ScannerExecutionCompletion,
    ScannerExecutionSeed,
    SqliteAnalysisStore,
    T3Finalize,
)
from sentinel.infrastructure.core.sqlite.analysis_store_adapter import SqliteAnalysisStoreAdapter
from sentinel.infrastructure.core.sqlite.policy_store import PolicyCreate, PolicyVersionPublish, SqlitePolicyStore
from sentinel.infrastructure.core.sqlite.repository_config_store import (
    RepositoryCreate,
    SqliteRepositoryConfigStore,
)


@pytest.fixture()
def seeded_repository_id(sqlite_conn) -> str:
    """Minimal Sentinel Core config an Analysis row's foreign keys require
    -- same seeding as tests/infrastructure/core/sqlite/conftest.py, kept
    local here since that conftest's fixtures aren't visible outside their
    own directory tree.
    """
    policy_store = SqlitePolicyStore(sqlite_conn)
    policy_store.create_policy(PolicyCreate(id="policy-1", created_at="2026-01-01T00:00:00Z"))
    policy_store.publish_version(
        PolicyVersionPublish(
            id="policy-1-v1", policy_id="policy-1", version_number=1, rules='{"blockOn": "critical"}',
            published_at="2026-01-01T00:00:00Z", published_by="devsecops-1",
        )
    )
    SqliteRepositoryConfigStore(sqlite_conn).create_repository(
        RepositoryCreate(
            id="repo-1", external_identifier="acme/widgets", enabled_scanners='["semgrep", "gitleaks"]',
            assigned_policy_id="policy-1", created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        )
    )
    return "repo-1"


def test_get_returns_a_view_for_a_completed_analysis(sqlite_conn, seeded_repository_id) -> None:
    raw_store = SqliteAnalysisStore(sqlite_conn)
    adapter = SecurityResultQueryAdapter(SqliteAnalysisStoreAdapter(raw_store))

    raw_store.create_analysis(
        AnalysisCreate(
            id="an-1", correlation_id="corr-1", trigger_mode="mode_a", repository_id="repo-1",
            policy_version_id="policy-1-v1", created_at="t0",
        ),
        artifacts=(),
        scanner_executions=(
            ScannerExecutionSeed(id="se-1", scanner_id="semgrep", scanner_version="1.0", timeout_seconds=60, started_at="t0"),
        ),
    )
    raw_store.complete_scanner_execution(
        ScannerExecutionCompletion(
            analysis_id="an-1", scanner_id="semgrep", status="succeeded", completed_at="t1",
            exit_code=0,
            findings=(
                FindingCreate(
                    id="f-1", scanner_execution_id="se-1", scanner_id="semgrep", category="sast",
                    artifact_path="app.py", artifact_type="source", rule_or_check_id="r1", severity_level="critical",
                ),
            ),
        )
    )
    raw_store.finalize_verdict(
        T3Finalize(
            analysis_id="an-1", security_score=60.0, verdict="BLOCK",
            degradation_any_scanner_failed=False, degradation_ai_available_at_completion=True,
            completed_at="t2",
            finding_updates=(
                FindingRiskUpdate(finding_id="f-1", correlation_group_id=None, risk_level="critical", risk_heuristics_applied="[]"),
            ),
        )
    )

    view = adapter.get("an-1")

    assert view is not None
    assert view.analysis_id == "an-1"
    assert view.verdict == "BLOCK"
    assert view.security_score == 60.0
    assert view.degradation_ai_available_at_completion is True
    assert len(view.findings) == 1
    assert view.findings[0].finding_id == "f-1"
    assert view.findings[0].risk_level == "critical"


def test_get_returns_none_for_a_still_running_analysis(sqlite_conn, seeded_repository_id) -> None:
    raw_store = SqliteAnalysisStore(sqlite_conn)
    adapter = SecurityResultQueryAdapter(SqliteAnalysisStoreAdapter(raw_store))

    raw_store.create_analysis(
        AnalysisCreate(
            id="an-2", correlation_id="corr-2", trigger_mode="mode_a", repository_id="repo-1",
            policy_version_id="policy-1-v1", created_at="t0",
        ),
        artifacts=(), scanner_executions=(),
    )

    assert adapter.get("an-2") is None


def test_get_returns_none_for_an_unknown_analysis_id(sqlite_conn) -> None:
    adapter = SecurityResultQueryAdapter(SqliteAnalysisStoreAdapter(SqliteAnalysisStore(sqlite_conn)))

    assert adapter.get("does-not-exist") is None
