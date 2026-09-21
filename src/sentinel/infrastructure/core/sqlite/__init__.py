"""SqliteAnalysisStore, SqliteRepositoryConfigStore, SqlitePolicyStore,
SqliteAuditStore, SqliteNotificationStore, SqliteAuditRecorderPort.

Uses sqlite3 directly for T1-T3 transactions (BEGIN IMMEDIATE ... COMMIT),
per docs/03_API/Persistence_Strategy.md — no ORM encapsulates these
critical transactions. Schema migrations are managed separately by
Alembic (see scripts/migrations/), which owns only schema versioning, never
transaction execution. (Phase 1)
"""
