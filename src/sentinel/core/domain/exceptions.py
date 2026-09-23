"""Domain-level invariant violations for Sentinel Core's Aggregates.

These are the application/domain-layer counterparts of the SQL-level
guards in infrastructure/core/sqlite/exceptions.py (Persistence_Strategy.md's
"belt and suspenders" pattern) -- raised by Aggregate methods themselves,
independent of whatever storage technology eventually persists the result.
"""

from __future__ import annotations


class VerdictAlreadySet(RuntimeError):
    """Analysis.record_verdict() called on an Analysis that already has a verdict."""


class FindingsFrozen(RuntimeError):
    """An attempt to add a Finding to an Analysis that has already completed."""


class ScannerExecutionAlreadyTerminal(RuntimeError):
    """An attempt to complete a ScannerExecution that already reached a terminal state."""


class MissingRiskAssessment(RuntimeError):
    """Analysis.record_verdict() called while a Finding has no Risk assigned yet."""


class DuplicatePolicyVersion(RuntimeError):
    """Policy.publish_version() called with a version_number already published."""


class RepositoryMissingPolicy(RuntimeError):
    """A Repository was constructed or updated with no assigned Policy."""
