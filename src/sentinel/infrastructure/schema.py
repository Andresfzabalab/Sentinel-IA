"""Combines every module's schema into the one physical SQLite file.

Per docs/03_API/Data_Model.md: "One SQLite file for the MVP." Module
ownership is enforced by table-prefix/module convention and by each
adapter only ever issuing SQL against its own module's tables -- not by
separate physical files. This is the single entry point the migration and
any test fixture should call, so all three modules' schemas are always
created together, in a dependency-safe order.
"""

from __future__ import annotations

import sqlite3

from sentinel.infrastructure.ai_agent.sqlite.schema import (
    create_ai_agent_schema,
    drop_ai_agent_schema,
)
from sentinel.infrastructure.core.sqlite.schema import (
    create_core_schema,
    drop_core_schema,
)
from sentinel.infrastructure.intelligence.sqlite.schema import (
    create_intelligence_schema,
    drop_intelligence_schema,
)


def create_full_schema(conn: sqlite3.Connection) -> None:
    create_core_schema(conn)
    create_ai_agent_schema(conn)
    create_intelligence_schema(conn)


def drop_full_schema(conn: sqlite3.Connection) -> None:
    # Reverse of creation: intelligence and ai_agent have no inbound FK from
    # core, so their drop order relative to core doesn't matter -- core's
    # own internal drop order (handled inside drop_core_schema) does.
    drop_intelligence_schema(conn)
    drop_ai_agent_schema(conn)
    drop_core_schema(conn)
