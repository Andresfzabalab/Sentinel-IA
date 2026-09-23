"""Initial schema -- every table in docs/03_API/Data_Model.md.

Revision ID: 0001
Revises:
Create Date: 2026-09-21

Forward-only and additive-first (Persistence_Strategy.md's Migrations
principles): this migration creates the full MVP schema in one step since
it is the first revision; every future schema change is a new revision
that only adds or evolves, never edits this one's history.
"""

from __future__ import annotations

from alembic import op

from sentinel.infrastructure.ai_agent.sqlite.schema import (
    ALL_TABLES_IN_ORDER as AI_AGENT_TABLES,
)
from sentinel.infrastructure.ai_agent.sqlite.schema import (
    DROP_TABLES_IN_ORDER as AI_AGENT_DROPS,
)
from sentinel.infrastructure.core.sqlite.schema import (
    ALL_INDEXES_IN_ORDER as CORE_INDEXES,
)
from sentinel.infrastructure.core.sqlite.schema import (
    ALL_TABLES_IN_ORDER as CORE_TABLES,
)
from sentinel.infrastructure.core.sqlite.schema import (
    DROP_TABLES_IN_ORDER as CORE_DROPS,
)
from sentinel.infrastructure.intelligence.sqlite.schema import (
    ALL_TABLES_IN_ORDER as INTELLIGENCE_TABLES,
)
from sentinel.infrastructure.intelligence.sqlite.schema import (
    DROP_TABLES_IN_ORDER as INTELLIGENCE_DROPS,
)

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in CORE_TABLES:
        op.execute(statement)
    for statement in CORE_INDEXES:
        op.execute(statement)
    for statement in AI_AGENT_TABLES:
        op.execute(statement)
    for statement in INTELLIGENCE_TABLES:
        op.execute(statement)


def downgrade() -> None:
    for statement in INTELLIGENCE_DROPS:
        op.execute(statement)
    for statement in AI_AGENT_DROPS:
        op.execute(statement)
    for statement in CORE_DROPS:
        op.execute(statement)
