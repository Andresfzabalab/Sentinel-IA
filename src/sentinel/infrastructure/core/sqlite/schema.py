"""Sentinel Core's SQLite DDL — the single source of truth for its tables.

Transcribed directly from docs/03_API/Data_Model.md. This module is
imported both by the Alembic migration (schema versioning only) and by
tests that need a real schema without running the full migration engine —
never duplicated by hand in a second place.

Creation order matters for SQLite's forward-reference tolerance: `policy`
and `policy_version` reference each other (policy.current_version_id ->
policy_version.id, policy_version.policy_id -> policy.id). SQLite allows a
CREATE TABLE to name a FOREIGN KEY target that doesn't exist yet -- it is
only resolved when a row is actually written, by which point both tables
exist. No cross-module foreign key is ever declared here (Data_Model.md's
physical-layout rule) -- those columns are plain TEXT/id columns with no
REFERENCES clause.
"""

from __future__ import annotations

import sqlite3

CREATE_POLICY = """
CREATE TABLE IF NOT EXISTS policy (
    id TEXT PRIMARY KEY,
    current_version_id TEXT NULL REFERENCES policy_version(id),
    created_at TEXT NOT NULL
);
"""

CREATE_POLICY_VERSION = """
CREATE TABLE IF NOT EXISTS policy_version (
    id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL REFERENCES policy(id),
    version_number INTEGER NOT NULL,
    rules TEXT NOT NULL,
    published_at TEXT NOT NULL,
    published_by TEXT NOT NULL,
    UNIQUE (policy_id, version_number)
);
"""

CREATE_REPOSITORY = """
CREATE TABLE IF NOT EXISTS repository (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'github',
    external_identifier TEXT NOT NULL UNIQUE,
    enabled_scanners TEXT NOT NULL,
    assigned_policy_id TEXT NOT NULL REFERENCES policy(id),
    ai_provider_config TEXT NULL,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_ANALYSIS = """
CREATE TABLE IF NOT EXISTS analysis (
    id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL UNIQUE,
    trigger_mode TEXT NOT NULL CHECK (trigger_mode IN ('mode_a', 'mode_b')),
    repository_id TEXT NOT NULL REFERENCES repository(id),
    policy_version_id TEXT NOT NULL REFERENCES policy_version(id),
    status TEXT NOT NULL CHECK (status IN ('started', 'running', 'completed', 'failed')),
    failure_reason TEXT NULL,
    pr_context_retrieval_status TEXT NULL CHECK (pr_context_retrieval_status IN ('succeeded', 'failed')),
    pr_number INTEGER NULL,
    pr_head_branch TEXT NULL,
    pr_base_branch TEXT NULL,
    pr_author TEXT NULL,
    pr_head_commit_sha TEXT NULL,
    manual_trigger_key TEXT NULL,
    security_score REAL NULL,
    verdict TEXT NULL CHECK (verdict IN ('PASS', 'BLOCK')),
    degradation_any_scanner_failed BOOLEAN NULL,
    degradation_ai_available_at_completion BOOLEAN NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT NULL
);
"""

CREATE_ANALYSIS_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_analysis_repository_id ON analysis(repository_id);",
    "CREATE INDEX IF NOT EXISTS ix_analysis_status ON analysis(status);",
)

CREATE_ARTIFACT = """
CREATE TABLE IF NOT EXISTS artifact (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(id),
    path TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    change_kind TEXT NOT NULL CHECK (change_kind IN ('added', 'modified', 'deleted')),
    UNIQUE (analysis_id, path)
);
"""

CREATE_SCANNER_EXECUTION = """
CREATE TABLE IF NOT EXISTS scanner_execution (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(id),
    scanner_id TEXT NOT NULL,
    scanner_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'timed_out')),
    exit_code INTEGER NULL,
    timeout_seconds INTEGER NOT NULL,
    execution_metadata TEXT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NULL,
    failure_note TEXT NULL,
    UNIQUE (analysis_id, scanner_id)
);
"""

CREATE_FINDING = """
CREATE TABLE IF NOT EXISTS finding (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(id),
    scanner_execution_id TEXT NOT NULL REFERENCES scanner_execution(id),
    scanner_id TEXT NOT NULL,
    category TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    location_file TEXT NULL,
    location_line_start INTEGER NULL,
    location_line_end INTEGER NULL,
    rule_or_check_id TEXT NOT NULL,
    severity_level TEXT NOT NULL,
    severity_raw_value TEXT NULL,
    risk_level TEXT NULL,
    risk_heuristics_applied TEXT NULL,
    correlation_group_id TEXT NULL,
    secret_value_redaction_flag BOOLEAN NOT NULL DEFAULT 0
);
"""

CREATE_FINDING_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_finding_analysis_id ON finding(analysis_id);",
    "CREATE INDEX IF NOT EXISTS ix_finding_correlation_group_id ON finding(correlation_group_id);",
)

CREATE_AUDIT_RECORD = """
CREATE TABLE IF NOT EXISTS audit_record (
    id TEXT PRIMARY KEY,
    subject_analysis_id TEXT NULL REFERENCES analysis(id),
    correlation_id TEXT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('scanner', 'sentinel-core', 'llm-agent')),
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

CREATE_AUDIT_RECORD_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_audit_record_subject_analysis_id ON audit_record(subject_analysis_id);",
    "CREATE INDEX IF NOT EXISTS ix_audit_record_correlation_id ON audit_record(correlation_id);",
)

CREATE_NOTIFICATION = """
CREATE TABLE IF NOT EXISTS notification (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(id),
    channel TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'delivered', 'failed')),
    attempted_at TEXT NOT NULL,
    content_snapshot TEXT NULL
);
"""

# Order matters: SQLite tolerates forward FK references within one
# CREATE TABLE, but the referenced table must exist by the time a row is
# actually inserted -- this order also just reads naturally top-down.
ALL_TABLES_IN_ORDER: tuple[str, ...] = (
    CREATE_POLICY,
    CREATE_POLICY_VERSION,
    CREATE_REPOSITORY,
    CREATE_ANALYSIS,
    CREATE_ARTIFACT,
    CREATE_SCANNER_EXECUTION,
    CREATE_FINDING,
    CREATE_AUDIT_RECORD,
    CREATE_NOTIFICATION,
)

ALL_INDEXES_IN_ORDER: tuple[str, ...] = (
    *CREATE_ANALYSIS_INDEXES,
    *CREATE_FINDING_INDEXES,
    *CREATE_AUDIT_RECORD_INDEXES,
)

# Reverse of ALL_TABLES_IN_ORDER, respecting FK dependents-before-dependencies.
DROP_TABLES_IN_ORDER: tuple[str, ...] = (
    "DROP TABLE IF EXISTS notification;",
    "DROP TABLE IF EXISTS audit_record;",
    "DROP TABLE IF EXISTS finding;",
    "DROP TABLE IF EXISTS scanner_execution;",
    "DROP TABLE IF EXISTS artifact;",
    "DROP TABLE IF EXISTS analysis;",
    "DROP TABLE IF EXISTS repository;",
    "DROP TABLE IF EXISTS policy_version;",
    "DROP TABLE IF EXISTS policy;",
)


def create_core_schema(conn: sqlite3.Connection) -> None:
    for statement in ALL_TABLES_IN_ORDER:
        conn.execute(statement)
    for statement in ALL_INDEXES_IN_ORDER:
        conn.execute(statement)


def drop_core_schema(conn: sqlite3.Connection) -> None:
    for statement in DROP_TABLES_IN_ORDER:
        conn.execute(statement)
