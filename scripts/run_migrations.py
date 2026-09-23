"""Operational migration runner (Project_Structure.md's scripts/ folder).

Thin wrapper around `alembic upgrade head` that reuses Phase 0's
configuration gate, so migrations are run against the same DATABASE_PATH
the application itself would use -- never a hardcoded or guessed path.

Usage: python scripts/run_migrations.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sentinel.shared.config import ConfigurationError, load_settings  # noqa: E402


def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"Cannot run migrations: {exc}", file=sys.stderr)
        sys.exit(1)

    import os

    os.environ["DATABASE_PATH"] = settings.database_path

    project_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(project_root / "alembic.ini"))
    command.upgrade(cfg, "head")
    print(f"Migrations applied to {settings.database_path}")


if __name__ == "__main__":
    main()
