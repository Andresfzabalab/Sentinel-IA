"""Domain-level invariant violations for the Security Intelligence & Data Module."""

from __future__ import annotations


class DuplicateKnowledgeBaseEntry(RuntimeError):
    """Raised when a (topic, version) pair is published twice."""
