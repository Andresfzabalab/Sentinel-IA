"""Alembic environment: manages ONLY schema versioning for the one SQLite
file (Data_Model.md's "one SQLite file for the MVP"). It reads
DATABASE_PATH from the environment (Configuration_and_Secrets.md) rather
than a value baked into alembic.ini, so the same migration set applies
wherever SentinelAI runs.

This module uses SQLAlchemy Core only to open a connection for Alembic's
own bookkeeping (its `alembic_version` table) and to execute the raw DDL
strings that are the actual schema definition (see
src/sentinel/infrastructure/*/sqlite/schema.py). No ORM model, session, or
declarative mapping is used anywhere -- the T1-T3 transactions themselves
never go through this engine, only through the stdlib sqlite3 module in
infrastructure/*/sqlite/*_store.py.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

config = context.config


def _database_url() -> str:
    database_path = os.environ.get("DATABASE_PATH")
    if not database_path:
        raise RuntimeError(
            "DATABASE_PATH is not set. Migrations require the same mandatory "
            "configuration as the application (Configuration_and_Secrets.md)."
        )
    return f"sqlite:///{database_path}"


def run_migrations_online() -> None:
    connectable = create_engine(_database_url())

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)

        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
