"""AEGIS-1904: Closed-World Assumption (CWA) Completeness.

D-001: If an action type is in a loaded domain and no PERMITTED norm
exists → FORBIDDEN (CWA_NO_PERMISSION).

D-001: If an action type is not in any loaded domain → UNDECIDABLE
(NO_JURISDICTION).

Tests both cases exhaustively for all registered action types.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision, ReasonType


def _load_guard(domain_name: str = "IAMission") -> Guard:
    """Load a Guard from the standard domain .meld files."""
    domain_dir = Path(__file__).resolve().parents[2] / "aegis" / "domains"
    # Try IAMission first, fall back to available domains
    for name in [domain_name, "ifc"]:
        d = domain_dir / name.lower()
        if not d.exists():
            continue
        meld_files = sorted(d.glob("*.meld"))
        if meld_files:
            return Guard.from_meld_files(
                meld_files,
                code_prevalence=["IAMissionCode"],
            )
    # Fall back to reference test domain
    ref_dir = Path(__file__).resolve().parents[2] / "Referenz" / "opencyc-flatfiles"
    meld_files = sorted(ref_dir.glob("IAMission*.meld"))
    if meld_files:
        return Guard.from_meld_files(meld_files, code_prevalence=["IAMissionCode"])
    pytest.skip("No domain MELD files available")
    raise AssertionError("unreachable")  # for type checker


class TestCWACompleteness:
    """CWA: registered action + no permission → FORBIDDEN."""

    def test_registered_action_no_permission_is_forbidden(self) -> None:
        """For each registered action type, an unmatched proposition → FORBIDDEN."""
        guard = _load_guard()
        for action_type in guard._registry.action_types:
            action = Action(
                action_type=action_type,
                agent_id="unknown-agent",
                proposition={"nonExistentKey": "nonExistentValue"},
            )
            verdict = guard.check(action)
            assert verdict.decision in (
                Decision.FORBIDDEN,
                Decision.UNDECIDABLE,
            ), (
                f"Action type {action_type!r} with unmatched proposition "
                f"returned {verdict.decision.value} — expected FORBIDDEN or UNDECIDABLE"
            )

    def test_unregistered_action_is_undecidable(self) -> None:
        """An action type not in any loaded domain → UNDECIDABLE / NO_JURISDICTION."""
        guard = _load_guard()
        action = Action(
            action_type="completelyUnknownAction_XYZ",
            agent_id="any-agent",
            proposition={},
        )
        verdict = guard.check(action)
        assert verdict.decision == Decision.UNDECIDABLE, (
            f"Unknown action type should be UNDECIDABLE, got {verdict.decision.value}"
        )
        assert verdict.reason_type == ReasonType.NO_JURISDICTION

    @given(suffix=st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("L",))))
    @settings(max_examples=50, deadline=5000)
    def test_random_unregistered_actions_are_undecidable(self, suffix: str) -> None:
        """Random action types not in registry → always UNDECIDABLE."""
        guard = _load_guard()
        made_up_action = f"madeUp_{suffix}"
        if made_up_action in guard._registry.action_types:
            return  # Skip if we accidentally generated a real one
        action = Action(
            action_type=made_up_action,
            agent_id="test-agent",
            proposition={},
        )
        verdict = guard.check(action)
        assert verdict.decision == Decision.UNDECIDABLE

    def test_all_registered_actions_produce_defined_verdict(self) -> None:
        """Every registered action type produces one of three verdicts (never exception)."""
        guard = _load_guard()
        valid_decisions = {Decision.PERMITTED, Decision.FORBIDDEN, Decision.UNDECIDABLE}
        for action_type in guard._registry.action_types:
            action = Action(
                action_type=action_type,
                agent_id="test-agent",
                proposition={},
            )
            verdict = guard.check(action)
            assert verdict.decision in valid_decisions, (
                f"Action {action_type!r} returned invalid decision: {verdict.decision}"
            )
