"""AEGIS-2714 (Epic 27) — Pl-Tot + Pl-Det theorems.

Pl-Tot: termination for every plan with len(steps) ≤ MAX_PLAN_STEPS.
Pl-Det: bitwise reproducibility for identical inputs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import (
    MAX_PLAN_STEPS,
    Plan,
    PlanStep,
)
from aegis.guard.verdict import PlanDecision

DEVOPS = Path("aegis/domains/devops")


@pytest.fixture(scope="module")
def guard() -> Guard:
    return Guard.from_meld_files([
        DEVOPS / "DevOpsDomainOntologyMt.meld",
        DEVOPS / "DevOpsActionVocabMt.meld",
        DEVOPS / "DevOpsDeonticRulesMt.meld",
        DEVOPS / "DevOpsPlanNormsMt.meld",
    ])


def _readonly_plan(n: int) -> Plan:
    return Plan(steps=tuple(
        PlanStep(action=Action(action_type="readFile", agent_id="opencodeAgent"))
        for _ in range(n)
    ))


# ── Pl-Tot: terminates for valid plan sizes ───────────────────────


class TestTotality:
    def test_zero_step_terminates(self, guard: Guard) -> None:
        verdict = guard.plan_check(Plan())
        assert verdict.plan_decision in {
            PlanDecision.PERMITTED, PlanDecision.FORBIDDEN, PlanDecision.UNDECIDABLE,
        }

    def test_one_step_terminates(self, guard: Guard) -> None:
        verdict = guard.plan_check(_readonly_plan(1))
        assert verdict.plan_decision in {
            PlanDecision.PERMITTED, PlanDecision.FORBIDDEN, PlanDecision.UNDECIDABLE,
        }

    def test_max_steps_terminates(self, guard: Guard) -> None:
        verdict = guard.plan_check(_readonly_plan(MAX_PLAN_STEPS))
        assert verdict.plan_decision in {
            PlanDecision.PERMITTED, PlanDecision.FORBIDDEN, PlanDecision.UNDECIDABLE,
        }

    def test_over_max_steps_terminates_with_undecidable(
        self, guard: Guard,
    ) -> None:
        verdict = guard.plan_check(_readonly_plan(MAX_PLAN_STEPS + 1))
        assert verdict.plan_decision == PlanDecision.UNDECIDABLE

    def test_intermediate_size_terminates(self, guard: Guard) -> None:
        for size in (50, 100, 250):
            verdict = guard.plan_check(_readonly_plan(size))
            assert verdict.plan_decision in {
                PlanDecision.PERMITTED, PlanDecision.FORBIDDEN, PlanDecision.UNDECIDABLE,
            }


# ── Pl-Det: deterministic for identical inputs ────────────────────


class TestDeterminism:
    def test_same_plan_same_decision(self, guard: Guard) -> None:
        plan = _readonly_plan(3)
        v1 = guard.plan_check(plan)
        v2 = guard.plan_check(plan)
        assert v1.plan_decision == v2.plan_decision
        assert v1.reason_summary == v2.reason_summary

    def test_same_plan_same_violation_kinds(self, guard: Guard) -> None:
        plan = Plan(steps=(
            PlanStep(action=Action(
                action_type="deployArtifact", agent_id="ciAgent",
            )),
            PlanStep(action=Action(
                action_type="testArtifact", agent_id="ciAgent",
            )),
        ))
        v1 = guard.plan_check(plan)
        v2 = guard.plan_check(plan)
        assert [v.violation_type for v in v1.violations] == [
            v.violation_type for v in v2.violations
        ]

    def test_per_step_verdicts_identical(self, guard: Guard) -> None:
        plan = _readonly_plan(5)
        v1 = guard.plan_check(plan)
        v2 = guard.plan_check(plan)
        for s1, s2 in zip(v1.per_step_verdicts, v2.per_step_verdicts, strict=True):
            assert s1.decision == s2.decision

    def test_evaluation_mode_stable(self, guard: Guard) -> None:
        plan = _readonly_plan(2)
        modes = {guard.plan_check(plan).evaluation_mode for _ in range(3)}
        assert len(modes) == 1

    def test_different_plans_can_differ(self, guard: Guard) -> None:
        """Sanity: different plans CAN produce different outcomes — the
        determinism property is about identical inputs, not about
        making the world a single-decision place."""
        a = _readonly_plan(1)
        b = Plan(steps=(
            PlanStep(action=Action(
                action_type="deployArtifact", agent_id="ciAgent",
            )),
            PlanStep(action=Action(
                action_type="testArtifact", agent_id="ciAgent",
            )),
        ))
        va = guard.plan_check(a)
        vb = guard.plan_check(b)
        # Both terminate; we just want to assert no crash + we got a
        # decision either way.
        assert va.plan_decision is not None
        assert vb.plan_decision is not None
