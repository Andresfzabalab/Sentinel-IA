"""Proves SqliteSessionStore's basic CRUD (Phase 8)."""

from __future__ import annotations

from sentinel.infrastructure.core.sqlite.session_store import SessionCreate, SqliteSessionStore


def test_create_and_get_session(sqlite_conn) -> None:
    store = SqliteSessionStore(sqlite_conn)
    store.create_session(SessionCreate(token="tok-1", devsecops_login="dana", created_at="t0", expires_at="t1"))

    row = store.get_session("tok-1")

    assert row["devsecops_login"] == "dana"
    assert row["expires_at"] == "t1"


def test_get_unknown_session_returns_none(sqlite_conn) -> None:
    store = SqliteSessionStore(sqlite_conn)

    assert store.get_session("does-not-exist") is None


def test_delete_session_removes_it(sqlite_conn) -> None:
    store = SqliteSessionStore(sqlite_conn)
    store.create_session(SessionCreate(token="tok-1", devsecops_login="dana", created_at="t0", expires_at="t1"))

    store.delete_session("tok-1")

    assert store.get_session("tok-1") is None


def test_delete_unknown_session_is_a_safe_noop(sqlite_conn) -> None:
    store = SqliteSessionStore(sqlite_conn)

    store.delete_session("does-not-exist")  # must not raise
