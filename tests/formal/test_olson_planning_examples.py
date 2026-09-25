"""AEGIS-2714 (Epic 27) — Olson-style planning scenarios.

Five Karli-derived scenarios re-cast as plans. Each scenario reflects
a Norm + Plan-Constraint combination from Olson Ch. 6.4 and asserts
the corresponding PlanDecision.

These are NOT Olson conformance tests against the Karli truth-table
(those are in test_olson_karli_examples.py); they are *derivations*
that show the plan-evaluator behaves consistently with Olson's
intended planner semantics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import (
    Plan,
    PlanStep,
    StateSnapshot,
    ViolationType,
)
from aegis.guard.verdict import PlanDecision


def _write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def karli_planner_guard(tmp_path_factory: pytest.TempPathFactory) -> Guard:
    """A small Karli-style domain with explicit plan-norms."""
    d = tmp_path_factory.mktemp("karli")
    onto = _write(d, "onto.meld", """
        (case KarliMt)
        (isa helpCook ActionType)
        (isa helpCookVegetables ActionType)
        (isa eatVegetables ActionType)
        (isa wearHelmet ActionType)
        (isa rideBike ActionType)
        (isa announce ActionType)
        (isa attend ActionType)
    """)
    rules = _write(d, "rules.meld", """
        (case KarliRules)
        (permittedToDo karli helpCook)
        (permittedToDo karli helpCookVegetables)
        (permittedToDo karli eatVegetables)
        (permittedToDo karli wearHelmet)
        (permittedToDo karli rideBike)
        (permittedToDo karli announce)
        (permittedToDo karli attend)
        ;; Plan-level: helmets must come before biking.
        (obligateSequence wearHelmet rideBike)
        ;; Plan-level: at most one announce per plan.
        (forbidAggregate announce 1)
        ;; Plan-level: helping cook implies preparing veg first.
        (requirePrecondition helpCook (vegPrepared yes))
    """)
    return Guard.from_meld_files([onto, rules])


def _step(action_type: str, agent: str = "karli",
          duration: float = 0.0,
          pre: dict | None = None,
          post: dict | None = None) -> PlanStep:
    return PlanStep(
        action=Action(action_type=action_type, agent_id=agent),
        scheduled_duration_s=duration,
        pre_state=StateSnapshot(fields=pre or {}),
        post_state=StateSnapshot(fields=post or {}),
    )


# ── Scenario 1: Karli helps cook with veg already prepared ───────


class TestScenario1HelpCookHappyPath:
    def test_with_veg_prepared_passes(
        self, karli_planner_guard: Guard,
    ) -> None:
        plan = Plan(
            steps=(_step("helpCook"),),
            initial_state=StateSnapshot(fields={"vegPrepared": "yes"}),
        )
        verdict = karli_planner_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED


# ── Scenario 2: Karli helps cook without prepared veg ─────────────


class TestScenario2HelpCookMissingPrecondition:
    def test_without_veg_blocked(
        self, karli_planner_guard: Guard,
    ) -> None:
        plan = Plan(steps=(_step("helpCook"),))
        verdict = karli_planner_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert any(
            v.violation_type == ViolationType.PRECONDITION_VIOLATION
            for v in verdict.violations
        )


# ── Scenario 3: Bike ride with helmet first ───────────────────────


class TestScenario3HelmetThenBike:
    def test_helmet_first_passes(
        self, karli_planner_guard: Guard,
    ) -> None:
        plan = Plan(steps=(
            _step("wearHelmet"),
            _step("rideBike"),
        ))
        verdict = karli_planner_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED


# ── Scenario 4: Bike ride without helmet ──────────────────────────


class TestScenario4BikeWithoutHelmet:
    def test_inverse_order_blocked(
        self, karli_planner_guard: Guard,
    ) -> None:
        plan = Plan(steps=(
            _step("rideBike"),
            _step("wearHelmet"),
        ))
        verdict = karli_planner_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert any(
            v.violation_type == ViolationType.SEQUENCE_VIOLATION
            for v in verdict.violations
        )


# ── Scenario 5: Aggregate cap on announcements ────────────────────


class TestScenario5AnnounceTwiceBlocked:
    def test_two_announces_blocked(
        self, karli_planner_guard: Guard,
    ) -> None:
        plan = Plan(steps=(
            _step("announce"),
            _step("announce"),
        ))
        verdict = karli_planner_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert any(
            v.violation_type == ViolationType.AGGREGATE_VIOLATION
            for v in verdict.violations
        )

    def test_one_announce_passes(
        self, karli_planner_guard: Guard,
    ) -> None:
        plan = Plan(steps=(_step("announce"),))
        verdict = karli_planner_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED
