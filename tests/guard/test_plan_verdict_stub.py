"""Tests for PlanVerdict + Guard.plan_check.

Originally the AEGIS-2702 stub-only contract; AEGIS-2710 replaced the
stub with the real PlanPipeline. These tests now lock the
backward-compatible behaviour of the entry point: the result is still
a PlanVerdict, the action API is untouched, the enum is intact, and
``Plan.from_action(a)`` round-trips through the new evaluator.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import Plan
from aegis.guard.verdict import Decision, PlanDecision, PlanVerdict


@pytest.fixture
def small_guard(tmp_path: Path) -> Guard:
    meld = tmp_path / "vocab.meld"
    meld.write_text(
        """
        (aegis-schema-version 1)
        (case TestVocabMt)
        (isa share ActionType)
        (genlPreds permittedToDo-WRT permittedToDo)
        (permittedToDo-WRT TestCode agent-1 (share))
        """,
        encoding="utf-8",
    )
    return Guard.from_meld_files([meld])


class TestPlanCheckEntryPoint:
    def test_plan_check_returns_plan_verdict(self, small_guard: Guard) -> None:
        action = Action(action_type="share", agent_id="agent-1")
        plan = Plan.from_action(action)
        verdict = small_guard.plan_check(plan)
        assert isinstance(verdict, PlanVerdict)

    def test_plan_check_threads_evaluation_mode(self, small_guard: Guard) -> None:
        action = Action(action_type="share", agent_id="agent-1")
        verdict = small_guard.plan_check(Plan.from_action(action))
        assert verdict.evaluation_mode in ("legacy", "ddic", "v1_legacy")

    def test_empty_plan_is_forbidden(self, small_guard: Guard) -> None:
        verdict = small_guard.plan_check(Plan())
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert "empty" in verdict.reason_summary

    def test_plan_check_per_step_verdicts_populated(self, small_guard: Guard) -> None:
        action = Action(action_type="share", agent_id="agent-1")
        plan = Plan.from_action(action)
        verdict = small_guard.plan_check(plan)
        assert len(verdict.per_step_verdicts) == 1


class TestActionApiUnchanged:
    """AEGIS-2702 acceptance: Guard.check is unaffected by the new
    plan API. Lock that contract in explicitly."""

    def test_check_still_works_for_permitted_action(self, small_guard: Guard) -> None:
        action = Action(action_type="share", agent_id="agent-1")
        verdict = small_guard.check(action)
        assert verdict.decision == Decision.PERMITTED


class TestPlanVerdictFrozen:
    def test_plan_verdict_is_frozen(self) -> None:
        v = PlanVerdict(plan_decision=PlanDecision.UNDECIDABLE)
        try:
            v.plan_decision = PlanDecision.PERMITTED  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("PlanVerdict must be frozen")


class TestPlanDecisionEnum:
    def test_three_values(self) -> None:
        assert {d.value for d in PlanDecision} == {
            "PERMITTED", "FORBIDDEN", "UNDECIDABLE",
        }
