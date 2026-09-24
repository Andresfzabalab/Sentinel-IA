"""Proves the per-analysis_id serialization queue (moved to core/application/
in Phase 6, since it has no infrastructure dependency and the Orchestrator
now uses it directly for real concurrent scanner completions).
"""

from __future__ import annotations

import threading

from sentinel.core.application.analysis_write_queue import AnalysisWriteQueue


def test_same_analysis_id_returns_the_same_lock_instance():
    queue = AnalysisWriteQueue()

    assert queue.lock_for("an-1") is queue.lock_for("an-1")


def test_different_analysis_ids_get_different_locks():
    queue = AnalysisWriteQueue()

    assert queue.lock_for("an-1") is not queue.lock_for("an-2")


def test_lock_actually_serializes_concurrent_writers_for_the_same_analysis():
    queue = AnalysisWriteQueue()
    lock = queue.lock_for("an-1")
    counter = {"value": 0, "max_concurrent": 0, "in_critical_section": 0}
    guard = threading.Lock()

    def worker() -> None:
        with lock:
            with guard:
                counter["in_critical_section"] += 1
                counter["max_concurrent"] = max(counter["max_concurrent"], counter["in_critical_section"])
            counter["value"] += 1
            with guard:
                counter["in_critical_section"] -= 1

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert counter["value"] == 10
    assert counter["max_concurrent"] == 1
