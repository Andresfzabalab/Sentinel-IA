"""Proves the API error envelope shape (API_Contract.md's Error Model)."""

from __future__ import annotations

from sentinel.shared.errors import build_error_envelope


def test_error_envelope_shape_with_correlation_id() -> None:
    envelope = build_error_envelope(code="INVALID_SIGNATURE", message="bad signature", correlation_id="corr-1")

    assert envelope == {
        "error": {
            "code": "INVALID_SIGNATURE",
            "message": "bad signature",
            "correlationId": "corr-1",
        }
    }


def test_error_envelope_correlation_id_defaults_to_none() -> None:
    envelope = build_error_envelope(code="ANALYSIS_NOT_FOUND", message="not found")

    assert envelope["error"]["correlationId"] is None
