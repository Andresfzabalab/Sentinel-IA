"""Add session table -- Phase 8's DevSecOps API session tokens.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25

Additive-first (Persistence_Strategy.md's Migrations principles): a new
table, no change to any existing one.
"""

from __future__ import annotations

from alembic import op

from sentinel.infrastructure.core.sqlite.schema import CREATE_SESSION

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(CREATE_SESSION)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session;")
