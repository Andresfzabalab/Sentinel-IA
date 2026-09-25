"""Manual Knowledge Base refresh (Project_Structure.md's scripts/ folder).

The ONLY point in SentinelAI's normal operation that reaches out to the
public internet -- everything else (webhook processing, scanning, the AI
agent itself) runs entirely against the local SQLite-backed Knowledge Base
that this command populates. Contacts exactly two pre-configured, trusted
hosts (cwe-api.mitre.org, www.cisa.gov) and nothing else; the process never
calls this on its own (composition.py's startup seeding uses only the
built-in StaticSeedSource, so the Local Execution Gate never depends on
network reachability).

Usage: python scripts/refresh_knowledge_base.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sentinel.infrastructure.core.sqlite.connection import connect  # noqa: E402
from sentinel.infrastructure.intelligence.sources.cisa_kev_source import CisaKevSource  # noqa: E402
from sentinel.infrastructure.intelligence.sources.composite_source import (  # noqa: E402
    CompositeSecurityIntelligenceSource,
)
from sentinel.infrastructure.intelligence.sources.mitre_cwe_source import MitreCweSource  # noqa: E402
from sentinel.infrastructure.intelligence.sources.static_seed_source import StaticSeedSource  # noqa: E402
from sentinel.infrastructure.intelligence.sqlite.knowledge_base_store import SqliteKnowledgeBaseStore  # noqa: E402
from sentinel.infrastructure.intelligence.sqlite.knowledge_base_store_adapter import (  # noqa: E402
    SqliteKnowledgeBaseStoreAdapter,
    new_entry_id,
)
from sentinel.intelligence.application.knowledge_refresh_service import KnowledgeRefreshService  # noqa: E402
from sentinel.shared.config import ConfigurationError, load_settings  # noqa: E402

_TOPICS: tuple[str, ...] = ("sast", "sca", "secret", "container", "iac")


def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"Cannot refresh Knowledge Base: {exc}", file=sys.stderr)
        sys.exit(1)

    connection = connect(settings.database_path)
    store_adapter = SqliteKnowledgeBaseStoreAdapter(SqliteKnowledgeBaseStore(connection))

    cwe_source = MitreCweSource()
    kev_source = CisaKevSource()
    try:
        source = CompositeSecurityIntelligenceSource((StaticSeedSource(), cwe_source, kev_source))
        updated = KnowledgeRefreshService(source, store_adapter).refresh(_TOPICS, id_factory=new_entry_id)
    finally:
        cwe_source.close()
        kev_source.close()
        connection.close()

    if updated:
        print(f"Knowledge Base updated for: {', '.join(updated)}")
    else:
        print("Knowledge Base already up to date -- no changes.")


if __name__ == "__main__":
    main()
