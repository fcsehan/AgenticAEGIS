"""Import boundary test: aegis-core must never import aegis-guard.

The core packages (deontic, engine, kb) contain pure computation logic.
They must not depend on infrastructure packages (guard, api, ifc,
hardening, orchestrator, audit, ops, redteam, editor, testing, config).

This test enforces the architectural boundary defined in
spec/AEGIS_v2_ARCHITECTURE_SEPARATION.md.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# Core packages — pure computation, no I/O
CORE_PACKAGES = ("aegis.deontic", "aegis.engine", "aegis.kb")

# Guard packages — infrastructure, I/O, hosts
GUARD_PACKAGES = (
    "aegis.guard",
    "aegis.api",
    "aegis.ifc",
    "aegis.hardening",
    "aegis.orchestrator",
    "aegis.audit",
    "aegis.ops",
    "aegis.redteam",
    "aegis.editor",
    "aegis.testing",
    "aegis.config",
)

# Shared (allowed in both directions)
SHARED = ("aegis.errors",)

AEGIS_ROOT = Path(__file__).resolve().parents[1] / "aegis"


def _collect_imports(filepath: Path) -> list[tuple[int, str]]:
    """Extract all aegis imports from a Python file.

    Returns (line_number, imported_module) tuples.
    """
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except SyntaxError:
        return []

    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("aegis."):
                    imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("aegis."):
                imports.append((node.lineno, node.module))
    return imports


def _is_guard_import(module: str) -> bool:
    """Return True if the import targets a guard-side package."""
    return any(module == pkg or module.startswith(pkg + ".") for pkg in GUARD_PACKAGES)


def _is_core_file(filepath: Path) -> bool:
    """Return True if the file belongs to a core package."""
    rel = filepath.relative_to(AEGIS_ROOT)
    module = "aegis." + ".".join(rel.with_suffix("").parts)
    return any(module == pkg or module.startswith(pkg + ".") for pkg in CORE_PACKAGES)


def _find_core_python_files() -> list[Path]:
    """Find all Python files in core packages."""
    files: list[Path] = []
    for pkg in CORE_PACKAGES:
        pkg_dir = AEGIS_ROOT / pkg.split(".")[-1]
        if pkg_dir.is_dir():
            files.extend(pkg_dir.rglob("*.py"))
    return sorted(files)


class TestImportBoundary:
    """Core packages must never import from guard packages."""

    def test_core_does_not_import_guard(self) -> None:
        """Scan all core .py files for guard-side imports."""
        violations: list[str] = []

        for filepath in _find_core_python_files():
            for lineno, module in _collect_imports(filepath):
                if _is_guard_import(module):
                    rel = filepath.relative_to(AEGIS_ROOT.parent)
                    violations.append(f"{rel}:{lineno}: imports {module}")

        assert not violations, (
            f"Core→Guard import boundary violated:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_core_api_surface_importable(self) -> None:
        """The public API surface (aegis.core) must be importable."""
        from aegis.core import (
            DDICEngine,
            DeonticModality,
            InheritanceGraph,
            KnowledgeBase,
            MeldLoader,
            NormFrame,
            NormStatus,
        )

        assert DeonticModality.PERMITTED is not None
        assert NormFrame.__dataclass_fields__

    def test_core_packages_exist(self) -> None:
        """All declared core packages must exist on disk."""
        for pkg in CORE_PACKAGES:
            pkg_dir = AEGIS_ROOT / pkg.split(".")[-1]
            assert pkg_dir.is_dir(), f"Core package missing: {pkg} ({pkg_dir})"

    def test_guard_imports_core_correctly(self) -> None:
        """Guard.check() must import from core packages (sanity check)."""
        guard_path = AEGIS_ROOT / "guard" / "guard.py"
        if not guard_path.exists():
            pytest.skip("guard.py not found")

        imports = _collect_imports(guard_path)
        core_imports = [
            m for _, m in imports
            if any(m.startswith(pkg) for pkg in CORE_PACKAGES)
        ]
        assert len(core_imports) > 0, (
            "Guard.check() should import from core packages (deontic, engine, kb)"
        )
