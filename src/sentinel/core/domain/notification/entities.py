"""Notification -- delivery and decision are different facts
(Ubiquitous_Language.md): a failed Notification must never be interpreted
as a failed Analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NotificationStatus = Literal["pending", "delivered", "failed"]


@dataclass(frozen=True)
class Notification:
    id: str
    analysis_id: str
    channel: str
    status: NotificationStatus
    attempted_at: str
    content_snapshot: str | None = None
