"""AEGIS-1101: Determinism Checker tests.

Verifies that Guard.check() produces identical results for identical inputs
across many invocations (Invariant I1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.testing.determinism import DeterminismChecker

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "domains"
MELD_DIR = Path(__file__).parent.parent / "aegis" / "domains" / "iamission"


def _load_test_guard() -> Guard:
    return Guard.from_meld_files(
        [
            FIXTURE_DIR / "test_ontology.meld",
            FIXTURE_DIR / "test_action_vocab.meld",
            FIXTURE_DIR / "test_deontic_rules.meld",
        ]
    )


def _load_ia_guard() -> Guard:
    meld_files = sorted(MELD_DIR.glob("*.meld"))
    return Guard.from_meld_files(meld_files, code_prevalence=["IAMissionCode"])


class TestDeterminismChecker:
    def test_permitted_action_deterministic(self) -> None:
        guard = _load_test_guard()
        checker = DeterminismChecker(guard)
        result = checker.verify(
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgent",
                proposition={"dataClassification": "unclassified"},
            ),
            n=100,
        )
        assert result.deterministic
        assert result.runs == 100

    def test_forbidden_action_deterministic(self) -> None:
        guard = _load_test_guard()
        checker = DeterminismChecker(guard)
        result = checker.verify(
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgent",
                proposition={"dataClassification": "secret"},
            ),
            n=100,
        )
        assert result.deterministic

    def test_undecidable_action_deterministic(self) -> None:
        guard = _load_test_guard()
        checker = DeterminismChecker(guard)
        result = checker.verify(
            Action(action_type="unknownAction", agent_id="someAgent"),
            n=100,
        )
        assert result.deterministic

    def test_batch_verify(self) -> None:
        guard = _load_test_guard()
        checker = DeterminismChecker(guard)
        actions = [
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgent",
                proposition={"dataClassification": "unclassified"},
            ),
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgent",
                proposition={"dataClassification": "secret"},
            ),
            Action(action_type="unknownAction", agent_id="someAgent"),
        ]
        results = checker.verify_batch(actions, n=50)
        assert len(results) == 3
        assert all(r.deterministic for r in results)

    def test_invalid_n_raises(self) -> None:
        guard = _load_test_guard()
        checker = DeterminismChecker(guard)
        with pytest.raises(ValueError, match="n must be >= 2"):
            checker.verify(
                Action(action_type="test", agent_id="a"), n=1
            )


class TestIAMissionDeterminism:
    """Determinism checks against the full IAMission domain (20+ actions)."""

    def test_ia_mission_all_verdicts_deterministic(self) -> None:
        guard = _load_ia_guard()
        checker = DeterminismChecker(guard)

        actions = [
            # PERMITTED
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgentInMission",
                proposition={"dataClassification": "unclassified"},
            ),
            # FORBIDDEN — classified
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgentInMission",
                proposition={"dataClassification": "classified"},
            ),
            # FORBIDDEN — secret
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgentInMission",
                proposition={"dataClassification": "secret"},
            ),
            # FORBIDDEN — personal data external
            Action(
                action_type="sendDataExternal",
                agent_id="personalStaffAgentInMission",
                proposition={"dataCategory": "personal", "recipient": "externalService"},
            ),
            # FORBIDDEN — delete
            Action(
                action_type="deleteRecord",
                agent_id="intelligenceAgentInMission",
            ),
            # FORBIDDEN — ops agent shares classified
            Action(
                action_type="shareIntelligence",
                agent_id="operationsAgentInMission",
                proposition={"dataClassification": "classified"},
            ),
            # UNDECIDABLE — unknown action
            Action(
                action_type="nonexistentAction",
                agent_id="intelligenceAgentInMission",
            ),
        ]

        results = checker.verify_batch(actions, n=100)
        for r in results:
            assert r.deterministic, (
                f"Non-deterministic for {r.action.action_type}: {r.diff}"
            )
