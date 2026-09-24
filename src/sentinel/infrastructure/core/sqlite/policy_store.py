"""SqlitePolicyStore -- implements PolicyStore (T-Policy).

Touches only `policy` and `policy_version`. `policy_version` rows are
never updated after insert (Data_Model.md) -- this is what guarantees
QA-01's reconstructability. Suppression rules (UC-9) are just content
inside `rules`, not a separate table or transaction type.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


class DuplicatePolicyVersion(RuntimeError):
    """Raised when a (policy_id, version_number) pair is published twice."""


@dataclass(frozen=True)
class PolicyCreate:
    id: str
    created_at: str


@dataclass(frozen=True)
class PolicyVersionPublish:
    id: str
    policy_id: str
    version_number: int
    rules: str  # JSON: thresholds + suppression rules together
    published_at: str
    published_by: str


class SqlitePolicyStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_policy(self, policy: PolicyCreate) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                "INSERT INTO policy (id, current_version_id, created_at) VALUES (?, NULL, ?)",
                (policy.id, policy.created_at),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def publish_version(self, version: PolicyVersionPublish) -> None:
        """T-Policy -- Version Published.

        `UNIQUE(policy_id, version_number)` makes "publish the same version
        twice" a detectable, rejected condition rather than a silent
        duplicate.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            try:
                conn.execute(
                    """
                    INSERT INTO policy_version (id, policy_id, version_number, rules, published_at, published_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version.id,
                        version.policy_id,
                        version.version_number,
                        version.rules,
                        version.published_at,
                        version.published_by,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK;")
                raise DuplicatePolicyVersion(
                    f"policy_id={version.policy_id!r} version_number={version.version_number!r} "
                    "already published"
                ) from exc

            conn.execute(
                "UPDATE policy SET current_version_id = ? WHERE id = ?",
                (version.id, version.policy_id),
            )
            conn.execute("COMMIT;")
        except DuplicatePolicyVersion:
            raise
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def get_policy(self, policy_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM policy WHERE id = ?", (policy_id,)).fetchone()

    def get_policy_version(self, policy_version_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM policy_version WHERE id = ?", (policy_version_id,)
        ).fetchone()

    def get_current_version(self, policy_id: str) -> sqlite3.Row | None:
        policy = self.get_policy(policy_id)
        if policy is None or policy["current_version_id"] is None:
            return None
        return self.get_policy_version(policy["current_version_id"])

    def get_max_version_number(self, policy_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT MAX(version_number) AS max_version FROM policy_version WHERE policy_id = ?", (policy_id,)
        ).fetchone()
        return row["max_version"] if row and row["max_version"] is not None else None
