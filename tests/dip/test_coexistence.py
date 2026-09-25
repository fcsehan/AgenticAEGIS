"""Tests for DIP/Manual-Domain coexistence policy (AEGIS-3505, D-015)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.dip.coexistence import (
    DomainCoexistenceError,
    default_output_dir,
    is_manual_domain,
    validate_output_target,
)


def test_default_output_dir_is_dip_generated() -> None:
    target = default_output_dir("gdpr")
    assert target == Path("aegis/domains/dip-generated/gdpr")
    # Crucially: not the manual-domain path.
    assert target != Path("aegis/domains/gdpr")


def test_default_output_for_manual_name_does_not_collide(tmp_path: Path) -> None:
    """Even if the user picks a name like 'pharma' that exists as a manual
    domain, the default target lives under the dip-generated subtree and
    therefore does not collide."""
    # Setup: a manual pharma domain.
    manual_root = tmp_path / "domains"
    (manual_root / "pharma").mkdir(parents=True)
    (manual_root / "pharma" / "Manual.meld").write_text("()")

    # The default DIP target is dip-generated/pharma — not manual_root/pharma.
    default = default_output_dir("pharma")
    assert "dip-generated" in str(default)


def test_is_manual_domain_true_when_meld_present(tmp_path: Path) -> None:
    (tmp_path / "pharma").mkdir()
    (tmp_path / "pharma" / "Foo.meld").write_text("()")
    assert is_manual_domain("pharma", root=tmp_path) is True


def test_is_manual_domain_false_when_directory_missing(tmp_path: Path) -> None:
    assert is_manual_domain("ghost", root=tmp_path) is False


def test_is_manual_domain_false_when_directory_empty(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert is_manual_domain("empty", root=tmp_path) is False


def test_is_manual_domain_false_for_dip_generated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A path under aegis/domains/dip-generated/ is never a manual domain,
    even when it contains .meld files."""
    dip_root = tmp_path / "domains" / "dip-generated"
    dip_root.mkdir(parents=True)
    (dip_root / "foo").mkdir()
    (dip_root / "foo" / "Generated.meld").write_text("()")

    # Point DIP_GENERATED_ROOT at our temp tree for the duration of the test.
    monkeypatch.setattr(
        "aegis.dip.coexistence.DIP_GENERATED_ROOT",
        dip_root,
    )
    assert is_manual_domain("foo", root=dip_root.parent) is False


def test_hard_conflict_writing_into_existing_manual_domain(
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "domains"
    (manual_root / "pharma").mkdir(parents=True)
    (manual_root / "pharma" / "Manual.meld").write_text("()")

    target = manual_root / "pharma"

    with pytest.raises(DomainCoexistenceError, match="manual domain already exists"):
        validate_output_target(target, "pharma", manual_root=manual_root)


def test_hard_conflict_not_overridable_by_force(tmp_path: Path) -> None:
    manual_root = tmp_path / "domains"
    (manual_root / "pharma").mkdir(parents=True)
    (manual_root / "pharma" / "Manual.meld").write_text("()")

    target = manual_root / "pharma"

    # Even with force=True, hard conflicts must remain refused.
    with pytest.raises(DomainCoexistenceError):
        validate_output_target(target, "pharma", force=True, manual_root=manual_root)


def test_soft_conflict_existing_meld_files_blocked_without_force(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out"
    target.mkdir()
    (target / "Existing.meld").write_text("()")

    with pytest.raises(DomainCoexistenceError, match="existing .meld files"):
        validate_output_target(target, "anyname", manual_root=tmp_path / "domains")


def test_soft_conflict_overridable_by_force(tmp_path: Path) -> None:
    target = tmp_path / "out"
    target.mkdir()
    (target / "Existing.meld").write_text("()")

    # With force=True the soft conflict is allowed.
    validate_output_target(
        target,
        "anyname",
        force=True,
        manual_root=tmp_path / "domains",
    )


def test_empty_target_directory_is_allowed(tmp_path: Path) -> None:
    target = tmp_path / "out"
    target.mkdir()
    # No .meld files — allowed without force.
    validate_output_target(target, "anyname", manual_root=tmp_path / "domains")


def test_nonexistent_target_directory_is_allowed(tmp_path: Path) -> None:
    target = tmp_path / "newdir"
    # Does not exist yet — allowed without force.
    validate_output_target(target, "anyname", manual_root=tmp_path / "domains")


def test_dip_generated_target_does_not_trigger_hard_conflict(tmp_path: Path) -> None:
    """Writing into the DIP-generated subtree must never trigger the hard
    conflict, even if the name matches an existing manual domain."""
    manual_root = tmp_path / "domains"
    (manual_root / "pharma").mkdir(parents=True)
    (manual_root / "pharma" / "Manual.meld").write_text("()")

    dip_target = manual_root / "dip-generated" / "pharma"
    # No .meld files yet under dip_target — should pass.
    validate_output_target(dip_target, "pharma", manual_root=manual_root)
