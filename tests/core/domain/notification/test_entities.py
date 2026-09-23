"""Proves a Notification is immutable per attempt -- a retry is a new
instance, never a mutation of a failed one (Ubiquitous_Language.md).
"""

from __future__ import annotations

import dataclasses

import pytest

from sentinel.core.domain.notification.entities import Notification


def test_notification_is_immutable() -> None:
    notification = Notification(id="n-1", analysis_id="an-1", channel="github-status", status="failed", attempted_at="t0")

    with pytest.raises(dataclasses.FrozenInstanceError):
        notification.status = "delivered"
