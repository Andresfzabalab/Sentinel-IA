"""Proves webhook signature validation (GitHub_Integration.md)."""

from __future__ import annotations

import hashlib
import hmac

from sentinel.infrastructure.core.github.signature import verify_github_signature

_SECRET = "whsec_test"


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes() -> None:
    body = b'{"action": "opened"}'
    assert verify_github_signature(_SECRET, body, _sign(body)) is True


def test_invalid_signature_fails() -> None:
    body = b'{"action": "opened"}'
    assert verify_github_signature(_SECRET, body, "sha256=" + "0" * 64) is False


def test_missing_signature_header_fails() -> None:
    assert verify_github_signature(_SECRET, b"{}", None) is False


def test_wrong_prefix_fails() -> None:
    body = b"{}"
    assert verify_github_signature(_SECRET, body, "sha1=deadbeef") is False


def test_a_tampered_body_with_the_original_signature_fails() -> None:
    """The exact attack this check exists to stop: reusing a stale, valid
    signature against a modified payload (Testing_Strategy.md's Security
    Tests: 'tampered body with a stale/reused signature')."""
    original_body = b'{"action": "opened", "pull_request": {"number": 1}}'
    signature = _sign(original_body)
    tampered_body = b'{"action": "opened", "pull_request": {"number": 999}}'

    assert verify_github_signature(_SECRET, tampered_body, signature) is False


def test_wrong_secret_fails() -> None:
    body = b"{}"
    assert verify_github_signature("a-different-secret", body, _sign(body)) is False
