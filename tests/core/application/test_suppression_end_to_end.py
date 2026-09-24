"""Proves Phase 7's exit criterion (Implementation_Strategy.md): a
DevSecOps-authored suppression rule, published as a new Policy Version,
changes a subsequent (not retroactive) Analysis's verdict -- and an
Analysis already completed before that publish is provably unaffected.
"""

from __future__ import annotations

import itertools

from sentinel.core.application.analysis_orchestrator import AnalysisTrigger
from sentinel.core.application.policy_publishing_service import PolicyPublishingService
from sentinel.core.ports.repository_port import ChangedFileRef
from sentinel.core.ports.scanner_port import NormalizedFindingData, ScannerRunResult
from sentinel.infrastructure.core.sqlite.audit_store import SqliteAuditStore
from sentinel.infrastructure.core.sqlite.audit_store_adapter import SqliteAuditStoreAdapter
from sentinel.infrastructure.core.sqlite.policy_store import SqlitePolicyStore
from sentinel.infrastructure.core.sqlite.policy_store_adapter import SqlitePolicyStoreAdapter
from tests.core.application.conftest import seed_policy_and_repository


def _sequential_id_factory(prefix: str = "an"):
    counter = itertools.count(1)
    return lambda: f"{prefix}-{next(counter)}"


def _fixed_clock(value: str = "2026-01-01T00:00:00Z"):
    return lambda: value


def _mode_a_trigger(correlation_id: str, pr_number: int, head_commit_sha: str) -> AnalysisTrigger:
    return AnalysisTrigger(
        correlation_id=correlation_id, repository_id="repo-1", trigger_mode="mode_a",
        pr_number=pr_number, base_branch="main", head_branch="feature", author="dana",
        head_commit_sha=head_commit_sha,
    )


def test_a_new_suppression_rule_never_changes_an_already_completed_analysis(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store,
    analysis_store, sqlite_conn,
):
    seed_policy_and_repository(
        policy_store, repository_config_store, enabled_scanners=("semgrep",),
        policy_rules={"blockOnSeverity": "critical"},
    )
    fake_repository_port.script_changed_files(
        "acme/widgets", 42, (ChangedFileRef(path="app/db.py", change_kind="modified"),)
    )
    fake_repository_port.script_changed_files(
        "acme/widgets", 43, (ChangedFileRef(path="app/db.py", change_kind="modified"),)
    )
    fake_scanner_port.script_result(
        "semgrep",
        ScannerRunResult(
            status="succeeded", exit_code=0,
            findings=(
                NormalizedFindingData(
                    category="sast", artifact_path="app/db.py", artifact_type="source",
                    rule_or_check_id="known-false-positive", severity_level="critical",
                ),
            ),
        ),
    )

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())

    # First Analysis: no suppression published yet -- must BLOCK.
    first_id = orchestrator.process(_mode_a_trigger("corr-before-suppression", 42, "sha-1"))
    first_row_before_publish = analysis_store.get_analysis(first_id)
    assert first_row_before_publish["verdict"] == "BLOCK"

    # DevSecOps now publishes a suppression rule as a NEW Policy Version.
    publishing_service = PolicyPublishingService(
        SqlitePolicyStoreAdapter(policy_store), SqliteAuditStoreAdapter(SqliteAuditStore(sqlite_conn)),
        clock=_fixed_clock("2026-01-02T00:00:00Z"),
    )
    new_version = publishing_service.publish_version(
        "policy-1",
        {
            "blockOnSeverity": "critical",
            "suppressions": [{"ruleOrCheckId": "known-false-positive", "artifactPath": "app/"}],
        },
        actor="devsecops-1",
    )
    assert new_version.version_number == 2

    # The FIRST Analysis, already completed, must be provably unaffected --
    # re-reading it after the publish must show byte-identical results.
    first_row_after_publish = analysis_store.get_analysis(first_id)
    assert first_row_after_publish["verdict"] == "BLOCK"
    assert first_row_after_publish["policy_version_id"] == first_row_before_publish["policy_version_id"]
    assert first_row_after_publish["completed_at"] == first_row_before_publish["completed_at"]

    # A NEW Analysis, triggered after the publish, references the new
    # version and must now PASS -- same finding, different outcome, only
    # because it's a genuinely new Analysis referencing a newer version.
    second_id = orchestrator.process(_mode_a_trigger("corr-after-suppression", 43, "sha-2"))
    second_row = analysis_store.get_analysis(second_id)
    assert second_row["policy_version_id"] == new_version.id
    assert second_row["verdict"] == "PASS"
    assert second_row["policy_version_id"] != first_row_after_publish["policy_version_id"]


def test_suppressed_findings_remain_visible_in_the_findings_table_never_deleted(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store,
    analysis_store, sqlite_conn,
):
    seed_policy_and_repository(
        policy_store, repository_config_store, enabled_scanners=("semgrep",),
        policy_rules={"blockOnSeverity": "critical", "suppressions": [{"ruleOrCheckId": "fp-rule", "artifactPath": "app/"}]},
    )
    fake_repository_port.script_changed_files(
        "acme/widgets", 42, (ChangedFileRef(path="app/db.py", change_kind="modified"),)
    )
    fake_scanner_port.script_result(
        "semgrep",
        ScannerRunResult(
            status="succeeded", exit_code=0,
            findings=(
                NormalizedFindingData(
                    category="sast", artifact_path="app/db.py", artifact_type="source",
                    rule_or_check_id="fp-rule", severity_level="critical",
                ),
            ),
        ),
    )

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    analysis_id = orchestrator.process(_mode_a_trigger("corr-suppressed-visible", 42, "sha-1"))

    row = analysis_store.get_analysis(analysis_id)
    assert row["verdict"] == "PASS"  # suppression prevented the block

    findings = analysis_store.get_findings(analysis_id)
    assert len(findings) == 1  # the finding itself is still recorded, never silently deleted
    assert findings[0]["rule_or_check_id"] == "fp-rule"
    assert findings[0]["risk_level"] == "critical"  # risk/severity computed exactly as any other finding
