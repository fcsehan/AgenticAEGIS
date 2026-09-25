"""Tests for AEGIS-2312 claim-governance release-gate."""

from __future__ import annotations

import json
from pathlib import Path

from aegis.ifc.claim_governance import (
    ClaimEligibility,
    ClaimGap,
    ClaimName,
    evaluate_full_guard_coverage_claim,
    evaluate_olson_claim,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestOlsonClaimAgainstRealRepo:
    """Run the gate against the actual repository layout. The Olson
    artefacts ship with the repo so the eligible path must work
    out-of-the-box; the failing paths use temporary directories."""

    def test_eligible_when_artefacts_present_and_suite_green(self) -> None:
        result = evaluate_olson_claim(
            repo_root=REPO_ROOT,
            formal_tests_passed=362,
            formal_tests_failed=0,
        )
        assert result.eligible is True
        assert result.claim == ClaimName.OLSON_DDIC_IMPLEMENTED
        assert result.gaps == ()

    def test_blocked_when_failure_count_nonzero(self) -> None:
        result = evaluate_olson_claim(
            repo_root=REPO_ROOT,
            formal_tests_passed=361,
            formal_tests_failed=1,
        )
        assert result.eligible is False
        assert any("test failure" in g.reason for g in result.gaps)

    def test_blocked_when_pass_count_below_threshold(self) -> None:
        result = evaluate_olson_claim(
            repo_root=REPO_ROOT,
            formal_tests_passed=10,
            formal_tests_failed=0,
            expected_minimum_tests=360,
        )
        assert result.eligible is False
        assert any("expected at least" in g.reason for g in result.gaps)


class TestOlsonClaimAgainstEmptyRepo:
    def test_blocked_for_missing_tests(self, tmp_path: Path) -> None:
        result = evaluate_olson_claim(
            repo_root=tmp_path,
            formal_tests_passed=362,
            formal_tests_failed=0,
        )
        assert result.eligible is False
        artefacts = {g.artefact for g in result.gaps}
        # All five formal test files reported as missing.
        assert "tests/formal/test_olson_karli_examples.py" in artefacts
        assert "tests/formal/test_olson_table_65.py" in artefacts

    def test_blocked_for_missing_docs(self, tmp_path: Path) -> None:
        # Create the tests but no docs.
        tests_dir = tmp_path / "tests" / "formal"
        tests_dir.mkdir(parents=True)
        for name in (
            "test_olson_karli_examples.py",
            "test_olson_table_65.py",
            "test_olson_conformance.py",
            "test_ddic_soundness.py",
            "test_ddic_combinatorial.py",
        ):
            (tests_dir / name).write_text("")

        result = evaluate_olson_claim(
            repo_root=tmp_path,
            formal_tests_passed=362,
            formal_tests_failed=0,
        )
        assert result.eligible is False
        artefacts = {g.artefact for g in result.gaps}
        assert "docs/spec/DDIC_VERIFICATION.md" in artefacts
        assert "docs/spec/OLSON_CH6_CONFORMANCE.md" in artefacts


class TestFullGuardClaim:
    def test_eligible_when_release_passed_and_no_bypass(self) -> None:
        result = evaluate_full_guard_coverage_claim(
            release_claim_passed=True,
            bypass_count=0,
        )
        assert result.eligible is True
        assert result.claim == ClaimName.FULL_GUARD_COVERAGE

    def test_blocked_when_release_failed(self) -> None:
        result = evaluate_full_guard_coverage_claim(
            release_claim_passed=False,
            bypass_count=0,
        )
        assert result.eligible is False
        assert any(g.artefact == "release_gate" for g in result.gaps)

    def test_blocked_when_bypass_count_nonzero(self) -> None:
        result = evaluate_full_guard_coverage_claim(
            release_claim_passed=True,
            bypass_count=1,
        )
        assert result.eligible is False
        assert any(g.artefact == "bypass_proof" for g in result.gaps)


class TestSerialization:
    def test_to_dict_round_trip(self) -> None:
        result = evaluate_olson_claim(
            repo_root=REPO_ROOT,
            formal_tests_passed=362,
            formal_tests_failed=0,
        )
        payload = json.loads(json.dumps(result.to_dict()))
        assert payload["claim"] == "OLSON_DDIC_IMPLEMENTED"
        assert payload["eligible"] is True
        assert payload["gaps"] == []

    def test_summary_eligible(self) -> None:
        result = ClaimEligibility(
            claim=ClaimName.OLSON_DDIC_IMPLEMENTED,
            eligible=True,
        )
        assert "ELIGIBLE" in result.summary()
        assert "OLSON_DDIC_IMPLEMENTED" in result.summary()

    def test_summary_blocked_lists_gaps(self) -> None:
        result = ClaimEligibility(
            claim=ClaimName.OLSON_DDIC_IMPLEMENTED,
            eligible=False,
            gaps=(ClaimGap(artefact="x", reason="y"),),
        )
        assert "BLOCKED" in result.summary()
        assert "x:y" in result.summary()


class TestFrozen:
    def test_eligibility_is_frozen(self) -> None:
        result = ClaimEligibility(
            claim=ClaimName.OLSON_DDIC_IMPLEMENTED,
            eligible=True,
        )
        try:
            result.eligible = False  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("ClaimEligibility must be frozen")

    def test_gap_is_frozen(self) -> None:
        gap = ClaimGap(artefact="x", reason="y")
        try:
            gap.reason = "z"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("ClaimGap must be frozen")
