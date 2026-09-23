"""Shared fixture for persistence tests: a real SQLite file per test
(Testing_Strategy.md's Persistence Tests), with the full schema applied
via the same DDL Alembic uses -- no domain logic involved.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from sentinel.infrastructure.core.sqlite.connection import connect
from sentinel.infrastructure.schema import create_full_schema


@pytest.fixture()
def sqlite_conn(tmp_path) -> Iterator["sqlite3.Connection"]:  # type: ignore[name-defined]
    db_path = tmp_path / "sentinel_test.sqlite"
    conn = connect(str(db_path))
    create_full_schema(conn)
    try:
        yield conn
    finally:
        conn.close()
