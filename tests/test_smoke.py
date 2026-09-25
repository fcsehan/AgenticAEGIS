"""Smoke tests — verify package is importable and version is set."""

from __future__ import annotations


def test_import_aegis() -> None:
    import aegis

    assert aegis.__version__


def test_version_format() -> None:
    from aegis import __version__

    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_errors_importable() -> None:
    from aegis.errors import (
        AegisError,
        AuditWriteError,
        EvaluationError,
        LoadError,
    )

    assert issubclass(LoadError, AegisError)
    assert issubclass(EvaluationError, AegisError)
    assert issubclass(AuditWriteError, AegisError)


def test_cli_help() -> None:
    """CLI --help exits 0."""
    from aegis.cli import main

    try:
        main(["--help"])
    except SystemExit as e:
        assert e.code == 0


def test_subpackages_importable() -> None:
    """All subpackages can be imported."""
    import importlib

    packages = [
        "aegis.engine",
        "aegis.deontic",
        "aegis.tms",
        "aegis.kb",
        "aegis.guard",
        "aegis.audit",
        "aegis.conduct",
        "aegis.domains",
        "aegis.api",
        "aegis.orchestrator",
        "aegis.editor",
        "aegis.ops",
        "aegis.observability",
        "aegis.testing",
    ]
    for pkg in packages:
        importlib.import_module(pkg)
