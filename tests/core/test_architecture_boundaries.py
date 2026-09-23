"""Static boundary checks for P-01/P-06 (Architecture_Principles.md).

These are the "violation test" style checks the docs describe: cheap,
import-based static assertions that fail loudly if a future change
reintroduces a dependency direction the architecture forbids. This is not
a full import-linter setup (left for 08_Engineering_Research/CI hardening
in a later phase) -- just the two rules this project has already been
burned by once (Phase 3's initial gateway placement).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "sentinel"


def _imported_top_level_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _files_under(*relative_parts: str) -> list[Path]:
    return list((SRC_ROOT / Path(*relative_parts)).rglob("*.py"))


def test_core_application_never_imports_infrastructure() -> None:
    """P-01: the Orchestrator (and any other Application Service) may only
    depend on core/ports/ and core/domain/, never on a concrete adapter.
    """
    offending: list[str] = []
    for py_file in _files_under("core", "application"):
        for module in _imported_top_level_modules(py_file):
            if module.startswith("sentinel.infrastructure"):
                offending.append(f"{py_file}: imports {module!r}")

    assert offending == [], "core/application/ must never import sentinel.infrastructure:\n" + "\n".join(offending)


def test_core_domain_never_imports_infrastructure_or_ports() -> None:
    """P-06: domain code depends on nothing outside its own module -- not
    even on the port interfaces (those are consumed by application/), and
    never on a concrete adapter or a third-party infrastructure library.
    """
    offending: list[str] = []
    for py_file in _files_under("core", "domain"):
        for module in _imported_top_level_modules(py_file):
            if module.startswith("sentinel.infrastructure") or module.startswith("sentinel.core.ports"):
                offending.append(f"{py_file}: imports {module!r}")

    assert offending == [], "core/domain/ must never import sentinel.infrastructure or sentinel.core.ports:\n" + "\n".join(offending)


def test_core_ports_never_imports_infrastructure() -> None:
    """Port interfaces are pure contracts -- they may reference domain
    types (for method signatures) but never a concrete adapter.
    """
    offending: list[str] = []
    for py_file in _files_under("core", "ports"):
        for module in _imported_top_level_modules(py_file):
            if module.startswith("sentinel.infrastructure"):
                offending.append(f"{py_file}: imports {module!r}")

    assert offending == [], "core/ports/ must never import sentinel.infrastructure:\n" + "\n".join(offending)
