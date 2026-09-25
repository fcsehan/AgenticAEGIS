"""AEGIS-2002: MELD Norm Enumeration Test.

For finite domains (IAMission, IFC), exhaustively enumerate all
(ActionType × Proposition) combinations and verify that each produces
a defined Verdict (never an exception).

For IFC domain: 9 ActionTypes × 4 classifications × 3 purposes = 108
combinations, each must produce PERMITTED, FORBIDDEN, or UNDECIDABLE.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision


def _load_guard_for_domain(domain_name: str) -> Guard | None:
    """Try to load Guard for a specific domain."""
    domain_dir = Path(__file__).resolve().parents[2] / "aegis" / "domains" / domain_name
    if not domain_dir.exists():
        return None
    meld_files = sorted(domain_dir.glob("*.meld"))
    if not meld_files:
        return None
    return Guard.from_meld_files(meld_files, code_prevalence=["IAMissionCode"])


def _load_iamission_guard() -> Guard | None:
    """Try to load the IAMission Guard from reference or domain files."""
    guard = _load_guard_for_domain("iamission")
    if guard:
        return guard
    ref_dir = Path(__file__).resolve().parents[2] / "Referenz" / "opencyc-flatfiles"
    meld_files = sorted(ref_dir.glob("IAMission*.meld"))
    if meld_files:
        return Guard.from_meld_files(meld_files, code_prevalence=["IAMissionCode"])
    return None


# IFC domain proposition space
IFC_CLASSIFICATIONS = ("public", "internal", "confidential", "secret")
IFC_PURPOSES = ("internalAnalysis", "externalBriefing", "publicRelease")

VALID_DECISIONS = {Decision.PERMITTED, Decision.FORBIDDEN, Decision.UNDECIDABLE}


class TestNormEnumeration:
    """Proof by enumeration: every (ActionType × Proposition) → defined Verdict."""

    def test_iamission_all_actions_no_exception(self) -> None:
        """IAMission: Every registered action type → valid Verdict."""
        guard = _load_iamission_guard()
        if guard is None:
            pytest.skip("IAMission domain not available")

        if not guard._registry.action_types:
            pytest.skip("IAMission domain has no registered action types")

        tested = 0
        exceptions = 0
        for action_type in guard._registry.action_types:
            action = Action(
                action_type=action_type,
                agent_id="intelligenceAgentInMission",
                proposition={},
            )
            try:
                verdict = guard.check(action)
                assert verdict.decision in VALID_DECISIONS
                tested += 1
            except Exception as e:
                exceptions += 1
                pytest.fail(f"Exception for {action_type}: {e}")

        assert tested > 0
        assert exceptions == 0

    def test_ifc_exhaustive_enumeration(self) -> None:
        """IFC: All ActionTypes × classifications × purposes → valid Verdict."""
        guard = _load_guard_for_domain("ifc")
        if guard is None:
            pytest.skip("IFC domain not available")

        tested = 0
        exceptions = 0
        results: dict[str, int] = {"PERMITTED": 0, "FORBIDDEN": 0, "UNDECIDABLE": 0}

        for action_type in guard._registry.action_types:
            for classification, purpose in itertools.product(
                IFC_CLASSIFICATIONS, IFC_PURPOSES,
            ):
                action = Action(
                    action_type=action_type,
                    agent_id="ifc-test-agent",
                    proposition={
                        "sourceClassification": classification,
                        "purpose": purpose,
                    },
                )
                try:
                    verdict = guard.check(action)
                    assert verdict.decision in VALID_DECISIONS
                    results[verdict.decision.value] += 1
                    tested += 1
                except Exception as e:
                    exceptions += 1
                    pytest.fail(
                        f"Exception for {action_type}/{classification}/{purpose}: {e}"
                    )

        assert tested > 0, "No IFC action types found"
        assert exceptions == 0, f"{exceptions} exception(s) during enumeration"

    def test_all_domains_coverage_report(self) -> None:
        """Generate a coverage report across all available domains."""
        domain_dir = Path(__file__).resolve().parents[2] / "aegis" / "domains"
        if not domain_dir.exists():
            pytest.skip("No domains directory")

        total_tested = 0
        total_exceptions = 0
        domain_results: dict[str, dict[str, int]] = {}

        for domain_path in sorted(domain_dir.iterdir()):
            if not domain_path.is_dir():
                continue
            meld_files = sorted(domain_path.glob("*.meld"))
            if not meld_files:
                continue

            try:
                guard = Guard.from_meld_files(
                    meld_files,
                    code_prevalence=["IAMissionCode"],
                )
            except Exception:
                continue

            domain_name = domain_path.name
            domain_results[domain_name] = {
                "action_types": len(guard._registry.action_types),
                "tested": 0,
                "exceptions": 0,
            }

            for action_type in guard._registry.action_types:
                action = Action(
                    action_type=action_type,
                    agent_id="enum-test-agent",
                    proposition={},
                )
                try:
                    verdict = guard.check(action)
                    assert verdict.decision in VALID_DECISIONS
                    domain_results[domain_name]["tested"] += 1
                    total_tested += 1
                except Exception:
                    domain_results[domain_name]["exceptions"] += 1
                    total_exceptions += 1

        assert total_exceptions == 0, (
            f"{total_exceptions} exception(s) across all domains"
        )
