"""correlationId derivation (Mode A / Mode B) per docs/02_Domain/Domain_Events.md.

Mode A (PR-linked trigger — UC-1 webhook, or UC-2 against an existing PR):
correlationId is a deterministic function of (repositoryId, prNumber,
headCommitSha) — the same three inputs always produce the same value, with
no random or time-based component. This is precisely what lets a
redelivered GitHub webhook be recognized as the same trigger, not a new one.

Mode B (ad hoc manual trigger, no Pull Request involved — UC-2): correlationId
is derived from (repositoryId, manualTriggerKey), where manualTriggerKey is
either supplied explicitly by DevSecOps or freshly generated when absent.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

# Namespaced so a Mode A and a Mode B id can never collide even if their
# raw inputs happened to coincide — correlationId's identity mode is part
# of what it identifies (Domain_Events.md's Mode A/Mode B distinction).
_MODE_A_NAMESPACE = "sentinelai:correlation:mode-a"
_MODE_B_NAMESPACE = "sentinelai:correlation:mode-b"


def derive_mode_a_correlation_id(repository_id: str, pr_number: int, head_commit_sha: str) -> str:
    """Deterministic correlationId for a PR-linked trigger.

    Same (repository_id, pr_number, head_commit_sha) always yields the same
    id — this determinism is the redelivery-detection mechanism itself, not
    just a convenient identifier.
    """
    payload = f"{_MODE_A_NAMESPACE}:{repository_id}:{pr_number}:{head_commit_sha}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ModeBCorrelation:
    correlation_id: str
    manual_trigger_key: str


def derive_mode_b_correlation_id(repository_id: str, manual_trigger_key: str | None) -> ModeBCorrelation:
    """correlationId for an ad hoc manual trigger with no Pull Request (UC-2, Mode B).

    If DevSecOps supplies manual_trigger_key explicitly, reusing the same
    key reproduces the same correlationId (an intentional idempotent
    re-run). If no key is supplied, a fresh UUID is generated each call, so
    two otherwise-identical ad hoc requests are treated as two separate,
    legitimate Analyses — never silently deduplicated.
    """
    key = manual_trigger_key if manual_trigger_key else str(uuid.uuid4())
    payload = f"{_MODE_B_NAMESPACE}:{repository_id}:{key}"
    correlation_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return ModeBCorrelation(correlation_id=correlation_id, manual_trigger_key=key)
