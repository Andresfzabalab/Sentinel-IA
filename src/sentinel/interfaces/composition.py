"""Composition root: the process entry point.

Enforces docs/03_API/Configuration_and_Secrets.md's Local Execution Gate —
a missing mandatory secret must stop the process before it ever starts
serving, with a clear, actionable error, never a partially-usable process.

From Phase 1 onward, this is also where every port gets wired to its
concrete adapter; Phase 0 wires only configuration + logging + the (still
route-less beyond /health) FastAPI app.
"""

from __future__ import annotations

import sys

import uvicorn

from sentinel.interfaces.http.app import create_app
from sentinel.shared.config import ConfigurationError, load_settings


def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"SentinelAI failed to start: {exc}", file=sys.stderr)
        sys.exit(1)

    app = create_app(settings=settings)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
