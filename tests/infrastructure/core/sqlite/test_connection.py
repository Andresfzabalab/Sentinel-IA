"""Regression test: the shared connection must be usable from a thread
other than the one that created it (FastAPI/Starlette dispatch request
handling -- and BackgroundTasks specifically -- via a worker thread, not
necessarily the thread that opened the connection at startup).
"""

from __future__ import annotations

import threading

from sentinel.infrastructure.core.sqlite.connection import connect
from sentinel.infrastructure.schema import create_full_schema


def test_connection_is_usable_from_a_different_thread_than_the_one_that_created_it(tmp_path) -> None:
    db_path = tmp_path / "cross_thread_test.sqlite"
    conn = connect(str(db_path))
    create_full_schema(conn)

    result: dict[str, object] = {}

    def query_from_worker_thread() -> None:
        try:
            row = conn.execute("SELECT COUNT(*) AS c FROM analysis").fetchone()
            result["count"] = row["c"]
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    worker = threading.Thread(target=query_from_worker_thread)
    worker.start()
    worker.join()

    assert "error" not in result, f"cross-thread query failed: {result.get('error')}"
    assert result["count"] == 0

    conn.close()
