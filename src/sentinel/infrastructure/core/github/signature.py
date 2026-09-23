"""GitHub webhook signature validation (docs/03_API/GitHub_Integration.md).

Every incoming webhook is HMAC-SHA256 signed by GitHub using the shared
webhook secret, delivered in `X-Hub-Signature-256` (format:
`sha256=<hex digest>`). Verification must happen before any parsing of the
payload and before any correlationId derivation -- an unsigned or forged
payload must never reach Sentinel Core's domain logic
(System_Boundaries.md's "untrusted input, must be verified" row).
"""

from __future__ import annotations

import hashlib
import hmac

_SIGNATURE_PREFIX = "sha256="


def verify_github_signature(secret: str, payload: bytes, signature_header: str | None) -> bool:
    """Constant-time comparison -- never a plain `==`, to avoid timing
    side-channels (GitHub_Integration.md's Signature Validation).
    """
    if not signature_header or not signature_header.startswith(_SIGNATURE_PREFIX):
        return False

    expected_digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    expected_header = _SIGNATURE_PREFIX + expected_digest
    return hmac.compare_digest(expected_header, signature_header)
