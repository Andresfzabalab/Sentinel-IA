"""Proves correlationId derivation Mode A / Mode B (Domain_Events.md)."""

from __future__ import annotations

from sentinel.shared.correlation import derive_mode_a_correlation_id, derive_mode_b_correlation_id


def test_mode_a_is_deterministic_for_identical_inputs() -> None:
    first = derive_mode_a_correlation_id("repo-1", 42, "abc123")
    second = derive_mode_a_correlation_id("repo-1", 42, "abc123")

    assert first == second


def test_mode_a_changes_when_head_commit_sha_changes() -> None:
    """A synchronize event with a new commit is a legitimately new unit of work."""
    original = derive_mode_a_correlation_id("repo-1", 42, "abc123")
    new_commit = derive_mode_a_correlation_id("repo-1", 42, "def456")

    assert original != new_commit


def test_mode_a_changes_when_repository_or_pr_number_changes() -> None:
    base = derive_mode_a_correlation_id("repo-1", 42, "abc123")

    assert base != derive_mode_a_correlation_id("repo-2", 42, "abc123")
    assert base != derive_mode_a_correlation_id("repo-1", 99, "abc123")


def test_mode_b_with_explicit_key_is_deterministic() -> None:
    first = derive_mode_b_correlation_id("repo-1", "retry-key-1")
    second = derive_mode_b_correlation_id("repo-1", "retry-key-1")

    assert first.correlation_id == second.correlation_id
    assert first.manual_trigger_key == "retry-key-1"


def test_mode_b_without_key_generates_two_distinct_analyses() -> None:
    """No key supplied means no deduplication is intended (Domain_Events.md)."""
    first = derive_mode_b_correlation_id("repo-1", None)
    second = derive_mode_b_correlation_id("repo-1", None)

    assert first.correlation_id != second.correlation_id
    assert first.manual_trigger_key != second.manual_trigger_key


def test_mode_a_and_mode_b_never_collide_even_with_overlapping_inputs() -> None:
    mode_a = derive_mode_a_correlation_id("repo-1", 1, "same-value")
    mode_b = derive_mode_b_correlation_id("repo-1", "same-value")

    assert mode_a != mode_b.correlation_id
